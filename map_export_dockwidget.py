#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @Email     :
# @File      : map_export_dockwidget.py
# @Created   : 2025/7/28 11:47
# @Desc      : Map Export DockWidget with i18n support

import json
import os
import random
import re
from hmac import new

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsFillSymbol,
    QgsGeometry,
    QgsJsonUtils,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsMessageLog,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QSettings, Qt, QTimer, QTranslator, QVariant, pyqtSignal
from qgis.PyQt.QtGui import QClipboard, QColor, QFont
from qgis.PyQt.QtWidgets import QApplication, QMessageBox
from qgis.utils import iface

from .map_export_crosshair_tool import CrosshairOverlay
from .tile_utils import *

# 加载UI文件
FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'map_export_dockwidget_base.ui'))


class MapExportDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        super(MapExportDockWidget, self).__init__(parent)

        # 首先加载翻译器
        self.translator = None
        self.load_translator()

        # 初始化状态变量
        self.crosshair = None
        self.crosshair_visible = True
        self.tile_boundary_visible = False
        self.gcj_02_flag = True
        self._is_jumping = False  # 增加跳转标志位，防止覆盖用户输入内容

        # 设置UI
        self.setupUi(self)

        # 强制重新翻译UI元素
        self.retranslateUi()

        # 设置默认值
        self.setup_default_values()

        # 初始化模板下拉框
        self.init_templates()

        # 连接信号和槽
        self.connect_signals()

        # 初始化十字准线（默认显示）
        self.init_crosshair()

        # 设置屏幕中心变化监听
        self.setup_map_center_tracking()

        # 更新UI文本（处理动态翻译）
        self.update_ui_texts()

        # 初始化坐标输入框显示
        QTimer.singleShot(500, self.update_coord_input_placeholder)

    def tr(self, message):
        """翻译函数"""
        return QCoreApplication.translate('MapExportDockWidget', message)

    def generate_random_color(self):
        """生成随机颜色（排除过浅和过深的颜色）"""
        # 生成 HSV 色彩空间中的颜色，确保颜色鲜艳且可见
        import colorsys

        # 色相：0-1 随机
        hue = random.random()
        # 饱和度：0.5-0.9 确保颜色鲜艳
        saturation = random.uniform(0.5, 0.9)
        # 明度：0.4-0.8 避免过深或过浅
        value = random.uniform(0.4, 0.8)

        # 转换为 RGB
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)

        # 转换为十六进制颜色
        return '#{:02x}{:02x}{:02x}'.format(int(r * 255), int(g * 255), int(b * 255))

    def setup_default_values(self):
        """设置默认值"""
        self.layer_name_edit.setText("mx")
        self.create_layer_checkbox.setChecked(True)
        self.zoom_layer_checkbox.setChecked(True)
        self.level_combo.setCurrentText("13")  # 默认13级

    def init_templates(self):
        """初始化模板下拉框"""
        self.template_combo.clear()

        # 获取翻译后的模板选项
        template_items = [
            self.tr("-- Select Template --"),
            "POINT (WKT)",
            "LINESTRING (WKT)",
            "POLYGON (WKT)",
            "Point (GeoJSON)",
            "LineString (GeoJSON)",
            "Polygon (GeoJSON)",
        ]

        self.template_combo.addItems(template_items)

    def get_template_examples(self):
        """获取模板示例数据"""
        return {
            self.tr("-- Select Template --"): '',
            'POINT (WKT)': 'POINT (116.397468 39.909138)',
            'LINESTRING (WKT)': 'LINESTRING (116.3891602 39.9023438, 116.4111328 39.9023438)',
            'POLYGON (WKT)': (
                'POLYGON ((116.3891602 39.9023438, 116.4111328 39.9023438, 116.4111328 39.9243164, 116.3891602 39.9243164, 116.3891602 39.9023438))'
            ),
            'Point (GeoJSON)': (
                """{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [116.397468,39.909138,0]
            }
        }
    ]
}"""
            ),
            'LineString (GeoJSON)': (
                '''{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                   [116.3891602, 39.9023438], 
                   [116.4111328, 39.9023438], 
                   [116.4111328, 39.9243164]
                ]
            }
        }
    ]
}'''
            ),
            'Polygon (GeoJSON)': (
                '''{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                       [116.3891602, 39.9023438], 
                       [116.4111328, 39.9023438], 
                       [116.4111328, 39.9243164], 
                       [116.3891602, 39.9243164], 
                       [116.3891602, 39.9023438]
                    ]
                ]
            }
        }
    ]
}'''
            ),
        }

    def load_translator(self):
        """加载翻译文件"""
        try:
            plugin_dir = os.path.dirname(__file__)
            locale_path = os.path.join(plugin_dir, 'i18n')

            current_locale = QSettings().value('locale/userLocale', 'en')
            QgsMessageLog.logMessage(f"Current locale: {current_locale}", "MxExport Plugin")

            # 语言代码映射
            locale_mapping = {
                # 簡體中文
                'zh-Hans': 'zh_CN',
                'zh_CN': 'zh_CN',
                'zh-CN': 'zh_CN',
                # 繁體中文
                'zh-Hant': 'zh_TW',
                'zh_TW': 'zh_TW',
                'zh-TW': 'zh_TW',
                'zh_HK': 'zh_TW',
                'zh-HK': 'zh_TW',
                'zh_MO': 'zh_TW',
                # 日文
                'ja': 'ja',
                'ja_JP': 'ja',
            }

            if current_locale.startswith('zh'):
                # 更精確的中文判斷
                if current_locale in ['zh-Hant', 'zh_TW', 'zh-TW', 'zh_HK', 'zh-HK', 'zh_MO']:
                    file_suffix = 'zh_TW'  # 繁體中文
                else:
                    file_suffix = 'zh_CN'  # 簡體中文（默認）
            elif current_locale.startswith('ja'):
                file_suffix = 'ja'
            else:
                file_suffix = 'en'

            translator_file = os.path.join(locale_path, f'MxExport_{file_suffix}.qm')

            QgsMessageLog.logMessage(f"尝试加载翻译文件: {translator_file}", "MxExport Plugin")

            if os.path.exists(translator_file):
                self.translator = QTranslator()
                if self.translator.load(translator_file):
                    QCoreApplication.installTranslator(self.translator)
                    QgsMessageLog.logMessage(f"成功加载翻译文件: {translator_file}", "MxExport Plugin")
                    return True
                else:
                    QgsMessageLog.logMessage(f"翻译文件加载失败: {translator_file}", "MxExport Plugin")
            else:
                QgsMessageLog.logMessage(f"翻译文件不存在: {translator_file}", "MxExport Plugin")

            return False

        except Exception as e:
            QgsMessageLog.logMessage(f"加载翻译文件时出错: {str(e)}", "MxExport Plugin")
            return False

    def update_ui_texts(self):
        """更新UI文本（处理动态翻译）"""
        current_locale = QSettings().value('locale/userLocale', 'en')
        QgsMessageLog.logMessage(f"Current locale: {current_locale}", "MxExport Plugin")

        # 测试翻译是否工作
        test_translation = self.tr("Hide Crosshair")
        QgsMessageLog.logMessage(f"Current locale: {test_translation}", "MxExport Plugin")

        # 更新窗口标题
        self.setWindowTitle("MxExport")

        # 更新按钮状态文本
        self.update_button_texts()

    def update_button_texts(self):
        """更新按钮文本状态"""
        # 十字准线按钮
        if self.crosshair_visible:
            self.show_crosshair_btn.setText(self.tr("Hide Crosshair"))
        else:
            self.show_crosshair_btn.setText(self.tr("Show Crosshair"))

        # 瓦片边界按钮
        if self.tile_boundary_visible:
            self.show_tile_boundary_btn.setText(self.tr("Hide Tile Boundary"))
        else:
            self.show_tile_boundary_btn.setText(self.tr("Show Tile Boundary"))

    def init_crosshair(self):
        """初始化十字准线（默认显示）"""
        try:
            canvas = iface.mapCanvas()
            if self.crosshair is None:
                self.crosshair = CrosshairOverlay(canvas, self)
                self.crosshair.show_crosshair_display()
                self.crosshair_visible = True
                self.update_button_texts()
        except Exception as e:
            print(f"初始化十字准线时出错: {e}")

    def connect_signals(self):
        """连接信号和槽"""
        # 模板相关
        self.template_combo.currentTextChanged.connect(self.on_template_changed)

        # 按钮信号
        self.clear_btn.clicked.connect(self.clear_input)
        self.confirm_btn.clicked.connect(self.confirm_action)

        # 坐标转换相关信号
        self.goto_coord_btn.clicked.connect(self.goto_coordinate)
        self.show_crosshair_btn.clicked.connect(self.toggle_crosshair_display)
        self.x_y_coord_edit.returnPressed.connect(self.goto_coordinate)
        self.set_point_btn.clicked.connect(self.set_point_layer)
        self.coord_type_combo.currentTextChanged.connect(self.on_coord_type_changed)

        # tile边界相关信号
        self.show_tile_boundary_btn.clicked.connect(self.toggle_tile_boundary)
        self.tile_type_combo.currentTextChanged.connect(self.on_tile_type_settings_changed)
        self.level_combo.currentTextChanged.connect(self.on_tile_settings_changed)

        # 复制按钮信号
        self.current_coord_copy_btn.clicked.connect(self.copy_current_coord)
        self.nds_tile_id_copy_btn.clicked.connect(self.copy_nds_tile_id)

    def setup_map_center_tracking(self):
        """设置地图中心变化监听"""
        canvas = iface.mapCanvas()
        # extentsChanged 仅在停止移动后触发
        canvas.extentsChanged.connect(self.on_map_extent_changed)
        # mapCanvasRefreshed 在地图移动、缩放过程中持续触发，实现实时更新
        canvas.mapCanvasRefreshed.connect(self.on_map_refreshed)

    def on_map_refreshed(self):
        """地图刷新时实时更新（用于平移过程中的实时效果）"""
        # 实时更新中心点信息，传参表示当前是“预览”模式
        self.update_center_info(is_preview=True)
        # 实时更新瓦片边界
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            self.update_tile_boundary()

    def on_map_extent_changed(self):
        """地图范围改变时更新tile边界和中心信息"""
        self.update_center_info(is_preview=False)
        self.update_coord_input_placeholder()
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            self.update_tile_boundary()

    def on_tile_settings_changed(self):
        """tile设置改变时更新显示"""
        self.update_center_info()
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            self.update_tile_boundary()

    def on_coord_type_changed(self):
        """坐标系类型改变时更新显示"""
        self.update_center_info()
        self.update_coord_input_placeholder()

    def update_coord_input_placeholder(self):
        """根据坐标类型更新输入框的值和标签"""
        try:
            coord_type = self.coord_type_combo.currentText()

            if "NDS TileID" in coord_type:
                # Get current NDS TileID of screen center
                wgs84_point = self.get_center_point('EPSG:4326')
                tile_level = int(self.level_combo.currentText())
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), tile_level, is_wgs84=True)
                self.x_y_coord_edit.setText(str(tile_id))
                self.x_y_label.setText(self.tr("NDS TileID:"))

            elif "XYZ Tile" in coord_type:
                # Get current XYZ Tile coordinates of screen center
                wgs84_point = self.get_center_point('EPSG:4326')
                z = 14  # Default level 14
                x, y = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), z)
                self.x_y_coord_edit.setText(f"{z},{x},{y}")
                self.x_y_label.setText(self.tr("Z, X, Y:"))

            elif "WGS84" in coord_type:
                # Get WGS84 coordinates
                point = self.get_center_point('EPSG:4326')
                self.x_y_coord_edit.setText(f"{point.x():.6f},{point.y():.6f}")
                self.x_y_label.setText(self.tr("Longitude, Latitude:"))

            elif "3857" in coord_type:
                # Get EPSG:3857 coordinates
                point = self.get_center_point('EPSG:3857')
                self.x_y_coord_edit.setText(f"{point.x():.2f},{point.y():.2f}")
                self.x_y_label.setText(self.tr("X, Y (EPSG:3857):"))

        except Exception as e:
            QgsMessageLog.logMessage(f"Error updating coord input: {str(e)}", "MxExport Plugin")

    def on_tile_type_settings_changed(self):
        """tile类型设置改变时更新显示"""
        tile_type_text = self.tile_type_combo.currentText()
        level_str = self.level_combo.currentText()

        if level_str:
            level = int(level_str)
            if tile_type_text == "NDS" and level > 13:
                self.level_combo.setCurrentText("13")

        self.update_center_info()
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            self.update_tile_boundary()

    def get_dynamic_precision(self, crs_code):
        """根据当前地图分辨率计算动态显示精度"""
        canvas = iface.mapCanvas()

        # 1. 获取当前画布的分辨率（单位取决于画布 CRS，通常是米或度）
        mup = canvas.mapUnitsPerPixel()

        # 2. 如果显示的是 WGS84 但画布是 3857 (米)，需要将分辨率换算成度
        # 粗略换算：1度 ≈ 111319.5米
        if "4326" in crs_code:
            canvas_crs = canvas.mapSettings().destinationCrs().authid()
            if "3857" in canvas_crs or "900913" in canvas_crs:
                mup = mup / 111319.5

        if not mup or mup <= 0:
            return 6 if "4326" in crs_code else 2

        import math

        try:
            # 精度计算逻辑：取分辨率的负对数并向上取整
            # 例如：mup = 0.00001 -> precision = 5
            precision = math.ceil(-math.log10(mup))
        except (ValueError, OverflowError):
            precision = 6

        if "4326" in crs_code:
            # WGS84(4326)：确保在缩放时精度有变化，且范围在 4..8
            # 额外 +1 是为了比当前像素分辨率更精确一点
            return max(4, min(8, precision + 1))
        elif "3857" in crs_code:
            # 3857 (米)：范围在 0..3
            return max(0, min(3, precision))

        return precision

    def update_center_info(self, is_preview=False):
        """更新屏幕中心位置信息

        Args:
            is_preview (bool): 是否为预览模式。预览模式下（拖动中）不更新输入框，减少抖动。
        """
        try:
            # 获取屏幕中心坐标（根据UI选择的坐标系）
            center_point = self.get_center_point()

            # 确定坐标系类型
            coord_type = self.coord_type_combo.currentText()

            # 1) 第一行“屏幕中心位置”回显：仅根据 4326/3857 显示经纬度或墨卡托
            is_mercator_system = "3857" in coord_type
            if is_mercator_system:
                p_3857 = self.get_center_point('EPSG:3857')
                prec = self.get_dynamic_precision('EPSG:3857')
                coord_text = self.tr("X, Y (EPSG:3857): {0:.{2}f}, {1:.{2}f}").format(p_3857.x(), p_3857.y(), prec)
            else:
                p_4326 = self.get_center_point('EPSG:4326')
                prec = self.get_dynamic_precision('EPSG:4326')
                coord_text = self.tr("Longitude, Latitude: {0:.{2}f}, {1:.{2}f}").format(p_4326.x(), p_4326.y(), prec)
            self.current_coord_label.setText(coord_text)

            # 2) 输入框回显：
            # 只有在非预览模式（停止拖动后）、非跳转中、且输入框没有焦点时才更新，彻底消除拖动时的跳变
            if not is_preview and not self._is_jumping and not self.x_y_coord_edit.hasFocus():
                if "NDS TileID" in coord_type:
                    wgs84_point = self.get_center_point('EPSG:4326')
                    tile_level = int(self.level_combo.currentText())
                    tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), tile_level, is_wgs84=True)
                    self.x_y_coord_edit.setText(str(tile_id))

                elif "XYZ Tile" in coord_type:
                    wgs84_point = self.get_center_point('EPSG:4326')
                    z = int(self.level_combo.currentText())
                    x, y = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), z)
                    self.x_y_coord_edit.setText(f"{z},{x},{y}")

                elif is_mercator_system:
                    p_3857 = self.get_center_point('EPSG:3857')
                    prec = self.get_dynamic_precision('EPSG:3857')
                    self.x_y_coord_edit.setText(f"{p_3857.x():.{prec}f}, {p_3857.y():.{prec}f}")

                else:
                    p_4326 = self.get_center_point('EPSG:4326')
                    prec = self.get_dynamic_precision('EPSG:4326')
                    self.x_y_coord_edit.setText(f"{p_4326.x():.{prec}f}, {p_4326.y():.{prec}f}")

            # 计算并显示瓦片信息（始终使用WGS84坐标进行瓦片计算）
            wgs84_point = self.get_center_point('EPSG:4326')
            tile_type_text = self.tile_type_combo.currentText()
            level = int(self.level_combo.currentText())

            if tile_type_text == "NDS":
                if level > 13:
                    QMessageBox.warning(self, self.tr("Warning"), self.tr("NDS Tile level cannot exceed 13"))
                    self.level_combo.setCurrentText("13")
                    level = 13
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), level, is_wgs84=True)
                x, y = parse_tile_id_2_nds(tile_id)
            else:  # XYZ
                x, y = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), level)
                tile_id = None

            # 构建瓦片信息文本
            tile_prefix = "NDS" if tile_type_text == "NDS" else "XYZ"
            tile_text = self.tr("{0} Level {1} Tile: ").format(tile_prefix, level)

            if tile_id:
                tile_text += self.tr("TileID[ {0} ], ").format(tile_id)

            tile_text += self.tr("x[ {0} ], y[ {1} ]").format(x, y)
            self.nds_tile_id_label.setText(tile_text)

        except Exception as e:
            self.current_coord_label.setText(self.tr("Unable to get coordinates"))
            self.nds_tile_id_label.setText(self.tr("NDS Level 13 TileID: Unable to calculate"))

    def set_point_layer(self):
        """设置点图层"""
        try:
            # 获取地图画布的坐标系
            canvas = iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()
            canvas_crs_code = canvas_crs.authid() or 'EPSG:4326'

            # 获取当前选择坐标系的坐标
            c_p = self.get_center_point()
            point = QgsPointXY(c_p.x(), c_p.y())

            # 确定坐标系
            coord_type = self.coord_type_combo.currentText()
            if "3857" in coord_type:
                crs_code = "EPSG:3857"
                # 对于3857坐标系使用较少的小数位数
                layer_name = self.tr("marker_{0:.2f}_{1:.2f}").format(point.x(), point.y())
            else:
                crs_code = "EPSG:4326"
                # 对于4326坐标系使用更多的小数位数
                layer_name = self.tr("marker_{0:.6f}_{1:.6f}").format(point.x(), point.y())

            # 创建点图层，使用画布坐标系
            layer = QgsVectorLayer(f"Point?crs={canvas_crs_code}", layer_name, "memory")

            # 如果用户选择的坐标系与画布坐标系不同，需要进行转换
            if crs_code != canvas_crs_code:
                source_crs = QgsCoordinateReferenceSystem(crs_code)
                transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
                point = transform.transform(point)

            # 添加标签字段
            provider = layer.dataProvider()
            provider.addAttributes([QgsField("label", QVariant.String)])
            layer.updateFields()

            # 创建要素
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(point))

            # 根据原始坐标系设置标签格式
            if "3857" in coord_type:
                c_p_orig = self.get_center_point(crs_code)
                label_text = f'{c_p_orig.x():.2f}, {c_p_orig.y():.2f}'
            else:
                c_p_orig = self.get_center_point(crs_code)
                label_text = f'{c_p_orig.x():.6f}, {c_p_orig.y():.6f}'

            feature.setAttributes([label_text])
            provider.addFeatures([feature])
            layer.updateExtents()

            # 设置符号样式（使用随机颜色和更小的尺寸）
            random_color = self.generate_random_color()
            symbol_properties = {
                'name': 'star',
                'size': '4',  # 从 6 改为 4，更小
                'color': random_color,
                'outline_color': '#FFFFFF',
                'outline_width': '0.3',  # 从 0.5 改为 0.3，更细
                'outline_style': 'solid',
            }
            symbol = QgsMarkerSymbol.createSimple(symbol_properties)
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)

            # 设置标注样式
            labeling = QgsPalLayerSettings()
            labeling.fieldName = 'label'
            labeling.enabled = True

            text_format = QgsTextFormat()
            text_format.setFont(QFont("Arial", 10, QFont.Bold))
            text_format.setColor(QColor(0, 0, 128))

            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(1)
            buffer_settings.setColor(QColor("white"))
            text_format.setBuffer(buffer_settings)

            labeling.setFormat(text_format)
            labeling.placement = QgsPalLayerSettings.Placement.AroundPoint
            labeling.dist = 2

            layer.setLabeling(QgsVectorLayerSimpleLabeling(labeling))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()

            # 添加到项目
            QgsProject.instance().addMapLayer(layer, False)
            root = QgsProject.instance().layerTreeRoot()
            root.insertLayer(0, layer)

            # 缩放到图层
            canvas.setExtent(layer.extent())
            canvas.refresh()

            QMessageBox.information(self, self.tr("Success"), self.tr("Marker layer created: {0}").format(layer_name))

        except ValueError:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Invalid coordinate format, please enter numbers"))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error creating point layer: {0}").format(str(e)))

    def goto_coordinate(self):
        """跳转到指定坐标"""
        try:
            x_y_text = self.x_y_coord_edit.text().strip()
            x_y_text = re.sub(r'\s+', ' ', x_y_text)

            # 获取选择的坐标系类型
            coord_type = self.coord_type_combo.currentText()

            # 处理 NDS TileID
            if "NDS TileID" in coord_type:
                try:
                    tile_id = int(x_y_text)
                except ValueError:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("NDS TileID must be an integer"))
                    return

                try:
                    center_point = self.tile_id_to_center_point(tile_id)
                except Exception as e:
                    QMessageBox.warning(self, self.tr("Error"), str(e))
                    return

            # 处理 XYZ Tile
            elif "XYZ Tile" in coord_type:
                # 使用正则支持多种分隔符：逗号、空格、斜杠、竖线等
                x_y_arr = re.split(r'[,\s/|]+', x_y_text)
                x_y_arr = [item for item in x_y_arr if item]  # 过滤空字符串

                if len(x_y_arr) < 3:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("Please enter Z, X, Y coordinates"))
                    return

                try:
                    # 调整顺序为 Z, X, Y
                    z = int(x_y_arr[0].strip())
                    x = int(x_y_arr[1].strip())
                    y = int(x_y_arr[2].strip())
                except ValueError:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("Z, X and Y must be integers"))
                    return

                try:
                    center_point = self.xyz_to_center_point(x, y, z)
                except Exception as e:
                    QMessageBox.warning(self, self.tr("Error"), str(e))
                    return
            else:
                # 处理经纬度坐标
                # 使用正则支持多种分隔符：逗号、空格、斜杠、竖线等
                x_y_arr = re.split(r'[,\s/|]+', x_y_text)
                x_y_arr = [item for item in x_y_arr if item]  # 过滤空字符串

                if len(x_y_arr) < 2:
                    QMessageBox.warning(self, self.tr("Warning"), self.tr("Please enter complete X and Y coordinates"))
                    return

                x = float(x_y_arr[0].strip())
                y = float(x_y_arr[1].strip())
                center_point = QgsPointXY(x, y)

                # 根据坐标类型设置源坐标系
                if "WGS84" in coord_type:
                    source_crs = QgsCoordinateReferenceSystem('EPSG:4326')
                elif "3857" in coord_type:
                    source_crs = QgsCoordinateReferenceSystem('EPSG:3857')
                else:
                    source_crs = QgsCoordinateReferenceSystem('EPSG:4326')

                # 坐标转换
                canvas = iface.mapCanvas()
                canvas_crs = canvas.mapSettings().destinationCrs()

                if source_crs != canvas_crs:
                    transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
                    center_point = transform.transform(center_point)

                canvas.setCenter(center_point)
                canvas.refresh()
                return

            # 对于 NDS TileID 或 XYZ Tile，进行坐标转换并跳转
            canvas = iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()
            canvas_crs_code = canvas_crs.authid()

            # 如果画布坐标系不是WGS84，需要进行转换
            if canvas_crs_code != 'EPSG:4326':
                source_crs = QgsCoordinateReferenceSystem('EPSG:4326')
                transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
                center_point = transform.transform(center_point)

            canvas.setCenter(center_point)
            canvas.refresh()

        except ValueError:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Invalid coordinate format, please enter numbers"))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error jumping to coordinate: {0}").format(str(e)))

    def tile_id_to_center_point(self, tile_id):
        """根据NDS Tile ID获取中心点坐标（WGS84）"""
        try:
            # 获取Tile级别
            level = parse_tile_level(tile_id)
            x, y = parse_tile_id_2_nds(tile_id)

            # 获取Tile边界（WGS84坐标）
            x_min, y_min, x_max, y_max = get_tile_bounds(
                tile_id, tile_type=CoordinatesSystemType.NDS, out_type=CoordinatesSystemType.WGS84
            )

            # 计算中心点
            center_x = (x_min + x_max) / 2
            center_y = (y_min + y_max) / 2

            return QgsPointXY(center_x, center_y)
        except Exception as e:
            raise Exception(self.tr("Failed to parse NDS Tile ID: {0}").format(str(e)))

    def xyz_to_center_point(self, x, y, level):
        """根据XYZ坐标获取中心点（WGS84）"""
        try:
            # 获取XYZ Tile的边界
            x_min, y_min, x_max, y_max = get_x_y_bounds(
                x, y, level, tile_type=CoordinatesSystemType.XYZ, out_type=CoordinatesSystemType.WGS84
            )

            # 计算中心点
            center_x = (x_min + x_max) / 2
            center_y = (y_min + y_max) / 2

            return QgsPointXY(center_x, center_y)
        except Exception as e:
            raise Exception(self.tr("Failed to parse XYZ coordinates: {0}").format(str(e)))

    def nds_xy_to_center_point(self, x, y, level):
        """根据NDS XY坐标获取中心点（WGS84）"""
        try:
            # 获取NDS坐标对应的边界
            x_min, y_min, x_max, y_max = get_x_y_bounds(
                x, y, level, tile_type=CoordinatesSystemType.NDS, out_type=CoordinatesSystemType.WGS84
            )

            # 计算中心点
            center_x = (x_min + x_max) / 2
            center_y = (y_min + y_max) / 2

            return QgsPointXY(center_x, center_y)
        except Exception as e:
            raise Exception(self.tr("Failed to parse NDS coordinates: {0}").format(str(e)))

    def toggle_crosshair_display(self):
        """切换十字准线显示状态"""
        try:
            if self.crosshair is None:
                self.init_crosshair()
                return

            if self.crosshair_visible:
                self.crosshair.hide_crosshair()
                self.crosshair_visible = False
            else:
                self.crosshair.show()
                self.crosshair.show_crosshair_display()
                self.crosshair_visible = True

            self.update_button_texts()

        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Error"), self.tr("Error toggling crosshair display: {0}").format(str(e))
            )

    def toggle_tile_boundary(self):
        """切换tile边界显示"""
        try:
            if not hasattr(self, 'crosshair') or self.crosshair is None:
                self.init_crosshair()

            if self.crosshair.show_tile_boundary:
                self.crosshair.hide_tile_boundary()
                self.tile_boundary_visible = False
            else:
                self.update_tile_boundary()
                self.crosshair.show_tile_boundary = True
                self.tile_boundary_visible = True

            self.update_button_texts()

        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Error"), self.tr("Error toggling tile boundary display: {0}").format(str(e))
            )

    def update_tile_boundary(self):
        """更新tile边界显示"""
        try:
            if hasattr(self, 'crosshair') and self.crosshair:
                # 1. 强制重绘覆盖层
                self.crosshair.update()
                # 2. 强制画布视口更新，这会立即触发 paintEvent 而不需要移动地图
                iface.mapCanvas().viewport().update()

        except Exception as e:
            QgsMessageLog.logMessage(f"Error updating tile boundary: {str(e)}", "MxExport", Qgis.Critical)

    def on_template_changed(self, template_name):
        """模板改变时的处理"""
        examples = self.get_template_examples()
        self.wkt_text_edit.setPlainText(examples.get(template_name, ''))

    def clear_input(self):
        """清空输入"""
        self.wkt_text_edit.clear()
        self.template_combo.setCurrentIndex(0)
        self.x_y_coord_edit.clear()

    def confirm_action(self):
        """确认操作"""
        current_tab = self.tabWidget.currentIndex()

        if current_tab == 1:  # WKT/GeoJSON标签页
            self.process_wkt_geojson()
        elif current_tab == 0:  # 坐标转换标签页
            self.goto_coordinate()

    def create_geometry_from_geojson(self, geometry_data):
        """从GeoJSON geometry对象创建QgsGeometry

        Args:
            geometry_data: GeoJSON geometry 对象字典

        Returns:
            QgsGeometry对象，如果失败则返回None
        """
        geom = None
        geom_type = geometry_data.get('type', '')
        coords = geometry_data.get('coordinates', [])

        try:
            # 根据类型直接从坐标创建
            if geom_type == 'Point':
                if len(coords) >= 2:
                    geom = QgsGeometry.fromPointXY(QgsPointXY(coords[0], coords[1]))
            elif geom_type == 'LineString':
                if len(coords) >= 2:
                    points = [QgsPointXY(coord[0], coord[1]) for coord in coords]
                    geom = QgsGeometry.fromPolylineXY(points)
            elif geom_type == 'Polygon':
                if len(coords) >= 1 and len(coords[0]) >= 3:
                    points = [QgsPointXY(coord[0], coord[1]) for coord in coords[0]]
                    geom = QgsGeometry.fromPolygonXY([points])
            elif geom_type == 'MultiPoint':
                if len(coords) >= 1:
                    points = [QgsPointXY(coord[0], coord[1]) for coord in coords]
                    geom = QgsGeometry.fromMultiPointXY(points)
            elif geom_type == 'MultiLineString':
                if len(coords) >= 1:
                    lines = [[QgsPointXY(coord[0], coord[1]) for coord in line] for line in coords]
                    geom = QgsGeometry.fromMultiPolylineXY(lines)
            elif geom_type == 'MultiPolygon':
                if len(coords) >= 1:
                    polygons = [
                        [[QgsPointXY(coord[0], coord[1]) for coord in ring] for ring in poly] for poly in coords
                    ]
                    geom = QgsGeometry.fromMultiPolygonXY(polygons)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error creating geometry from coordinates: {str(e)}", "MxExport Plugin")
            geom = None

        return geom

    def process_wkt_geojson(self):
        """处理WKT/GeoJSON数据，采用先解析后显示的思路，支持跨行GeoJSON"""
        input_text = self.wkt_text_edit.toPlainText().strip()
        layer_name = self.layer_name_edit.text().strip() or "mx"

        from datetime import datetime

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        layer_name += f"_{now_str}"

        if not input_text:
            QMessageBox.warning(self, self.tr("Warning"), self.tr("Please enter WKT or GeoJSON data"))
            return

        # 1. 解析阶段：提取所有几何体和属性
        parsed_items = []  # 存储格式: (QgsGeometry, properties_dict)
        formatted_segments = []  # 存储格式化后的文本片段
        import re

        # 提取所有的 JSON 块 (通过查找匹配的 {} )
        def extract_json_blocks(text):
            blocks = []
            stack = 0
            start = -1
            for i, char in enumerate(text):
                if char == '{':
                    if stack == 0:
                        start = i
                    stack += 1
                elif char == '}':
                    stack -= 1
                    if stack == 0 and start != -1:
                        blocks.append((start, i + 1))
            return blocks

        json_indices = extract_json_blocks(input_text)
        last_end = 0
        segments = []
        for start, end in json_indices:
            if start > last_end:
                segments.append(('wkt', input_text[last_end:start]))
            segments.append(('json', input_text[start:end]))
            last_end = end
        if last_end < len(input_text):
            segments.append(('wkt', input_text[last_end:]))

        for seg_type, content in segments:
            content = content.strip()
            if not content:
                continue
            try:
                if seg_type == 'json':
                    data = json.loads(content)
                    # 格式化 JSON
                    formatted_segments.append(json.dumps(data, indent=2, ensure_ascii=False))

                    temp_features = []
                    if isinstance(data, list):
                        temp_features = data
                    elif isinstance(data, dict):
                        if data.get('type') == 'FeatureCollection':
                            temp_features = data.get('features', [])
                        elif data.get('type') == 'Feature':
                            temp_features = [data]
                        elif 'type' in data:
                            temp_features = [{"type": "Feature", "geometry": data, "properties": {}}]
                    for feat in temp_features:
                        geom_data = feat.get('geometry')
                        props = feat.get('properties', {})
                        if geom_data:
                            geom = self.create_geometry_from_geojson(geom_data)
                            if geom and not geom.isNull():
                                parsed_items.append((geom, props))
                else:
                    wkt_patterns = r'(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION)\s*\(.*?\)'
                    matches = list(re.finditer(wkt_patterns, content, re.IGNORECASE | re.DOTALL))
                    if matches:
                        for match in matches:
                            wkt_str = match.group(0)
                            geom = QgsGeometry.fromWkt(wkt_str)
                            if geom and not geom.isNull():
                                parsed_items.append((geom, {"source": "WKT"}))
                                # 格式化 WKT：压缩多余空白并转为大写
                                formatted_wkt = re.sub(r'\s+', ' ', wkt_str).strip().upper()
                                formatted_segments.append(formatted_wkt)
                    else:
                        for line in content.split('\n'):
                            line = line.strip()
                            if not line:
                                continue
                            geom = QgsGeometry.fromWkt(line)
                            if geom and not geom.isNull():
                                parsed_items.append((geom, {"source": "WKT"}))
                                formatted_segments.append(line.upper())
            except Exception as e:
                QgsMessageLog.logMessage(f"Segment parse error: {str(e)}", "MxExport", Qgis.Warning)
                formatted_segments.append(content)  # 出错则保留原样

        # 将格式化后的内容写回输入框
        if formatted_segments:
            self.wkt_text_edit.setPlainText("\n\n".join(formatted_segments))

        if not parsed_items:
            QMessageBox.warning(self, self.tr("Warning"), self.tr("No valid geometry data found"))
            return

        # 2. 渲染阶段：分类渲染
        self.render_items_to_layer(parsed_items, layer_name)

    def render_items_to_layer(self, parsed_items, layer_name):
        """将统一格式的 parsed_items (geom, props) 分类渲染到不同的图层中"""
        try:
            # 1. 按几何类型分组
            groups = {'Point': [], 'LineString': [], 'Polygon': []}

            for geom, props in parsed_items:
                g_type = QgsWkbTypes.displayString(geom.wkbType())
                if 'Point' in g_type:
                    groups['Point'].append((geom, props))
                elif 'Line' in g_type:
                    groups['LineString'].append((geom, props))
                elif 'Polygon' in g_type:
                    groups['Polygon'].append((geom, props))
                else:
                    # 默认归类为线（或者你可以根据需要添加更多类型）
                    groups['LineString'].append((geom, props))

            canvas = iface.mapCanvas()
            dest_crs = canvas.mapSettings().destinationCrs()
            canvas_crs_code = dest_crs.authid() or 'EPSG:4326'

            created_layers = []

            # 2. 为每个非空组创建图层
            for g_type, items in groups.items():
                if not items:
                    continue

                suffix = ""
                if g_type == 'Point':
                    suffix = "_pt"
                elif g_type == 'LineString':
                    suffix = "_ln"
                elif g_type == 'Polygon':
                    suffix = "_pg"

                specific_layer_name = f"{layer_name}{suffix}"
                layer = self.create_single_type_layer(items, g_type, specific_layer_name, dest_crs)

                if layer:
                    created_layers.append(layer)

            if not created_layers:
                return

            # 3. 缩放至总范围
            if self.zoom_layer_checkbox.isChecked():
                total_extent = QgsRectangle()
                total_extent.setMinimal()

                valid_extent = False
                for layer in created_layers:
                    # 确保图层范围是最新的
                    layer.updateExtents()
                    extent = layer.extent()
                    if not extent.isEmpty():
                        total_extent.combineExtentWith(extent)
                        valid_extent = True

                if valid_extent and not total_extent.isEmpty():
                    # 稍微扩大一点范围，避免几何体紧贴边缘
                    total_extent.scale(1.1)
                    canvas.setExtent(total_extent)
                    canvas.refresh()

            QMessageBox.information(self, self.tr("Success"), self.tr("Created {0} layers").format(len(created_layers)))

        except Exception as e:
            QgsMessageLog.logMessage(f"Render error: {str(e)}", "MxExport", Qgis.Critical)
            QMessageBox.critical(self, self.tr("Error"), f"Render error: {str(e)}")

    def create_single_type_layer(self, items, layer_type, layer_name, dest_crs):
        """为特定类型的数据创建图层"""
        try:
            uri = f"{layer_type}?crs={dest_crs.authid() or 'EPSG:4326'}&index=yes"
            layer = QgsVectorLayer(uri, layer_name, "memory")

            if not layer.isValid():
                return None

            provider = layer.dataProvider()

            # 收集属性键
            all_props_keys = set()
            for _, props in items:
                all_props_keys.update(props.keys())

            # 添加字段
            new_fields = []
            for name in sorted(all_props_keys):
                new_fields.append(QgsField(name, QVariant.String))
            provider.addAttributes(new_fields)
            layer.updateFields()

            # 转换要素
            features = []
            source_crs = QgsCoordinateReferenceSystem('EPSG:4326')
            do_transform = dest_crs.authid() != 'EPSG:4326'
            transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance()) if do_transform else None

            for geom, props in items:
                feat = QgsFeature(layer.fields())
                new_geom = QgsGeometry(geom)
                if do_transform:
                    new_geom.transform(transform)
                feat.setGeometry(new_geom)

                if not layer.fields().isEmpty():
                    attrs = [props.get(field.name(), None) for field in layer.fields()]
                    feat.setAttributes(attrs)
                features.append(feat)

            # 写入要素 (内存图层直接通过 provider 写入最快且不会保持编辑状态)
            provider.addFeatures(features)
            layer.updateExtents()

            # 设置样式
            self.apply_random_style(layer, layer_type)

            # 添加到地图
            QgsProject.instance().addMapLayer(layer)
            layer.triggerRepaint()

            return layer
        except Exception as e:
            QgsMessageLog.logMessage(f"Failed to create layer {layer_name}: {str(e)}", "MxExport", Qgis.Critical)
            return None

        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), f"Render error: {str(e)}")

    def apply_random_style(self, layer, layer_type):
        """为图层应用随机样式"""
        color = self.generate_random_color()
        if "Point" in layer_type:
            symbol = QgsMarkerSymbol.createSimple(
                {'name': 'circle', 'size': '3', 'color': color, 'outline_color': '#FFFFFF'}
            )
        elif "Line" in layer_type:
            symbol = QgsLineSymbol.createSimple({'line_color': color, 'line_width': '0.5'})
        elif "Polygon" in layer_type:
            symbol = QgsFillSymbol.createSimple({'color': color + '40', 'outline_color': color, 'outline_width': '0.5'})
        else:
            symbol = QgsLineSymbol.createSimple({'line_color': color, 'line_width': '0.5'})

        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    def get_center_point(self, target_crs_code=None):
        """获取屏幕中心点坐标

        Args:
            target_crs_code: 目标坐标系代码，如果为None则根据UI选择确定
        """
        canvas = iface.mapCanvas()
        center_point = canvas.center()

        # 如果没有指定目标坐标系，则根据UI选择确定
        if target_crs_code is None:
            coord_type = self.coord_type_combo.currentText()
            if "3857" in coord_type:
                target_crs_code = 'EPSG:3857'
            else:
                target_crs_code = 'EPSG:4326'

        canvas_crs = canvas.mapSettings().destinationCrs()
        target_crs = QgsCoordinateReferenceSystem(target_crs_code)

        if canvas_crs != target_crs:
            transform = QgsCoordinateTransform(canvas_crs, target_crs, QgsProject.instance())
            transformed_point = transform.transform(center_point)
        else:
            transformed_point = center_point

        return transformed_point

    def copy_current_coord(self):
        """复制当前屏幕中心坐标"""
        center_point = self.get_center_point()
        value = f"{center_point.x():.6f},{center_point.y():.6f}"

        clipboard = QApplication.clipboard()
        clipboard.setText(value)

        QMessageBox.information(self, self.tr("Copy Successful: lon,lat"), value)

    def copy_nds_tile_id(self):
        """复制NDS瓦片ID信息"""
        # 始终使用WGS84坐标进行瓦片计算
        center_point = self.get_center_point('EPSG:4326')
        level = int(self.level_combo.currentText())

        if self.tile_type_combo.currentText() == "NDS":
            if level > 13:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("NDS Tile level cannot exceed 13"))
                self.level_combo.setCurrentText("13")
                level = 13
            tile_id = encode_tile_id(center_point.x(), center_point.y(), level, is_wgs84=True)
            x, y = parse_tile_id_2_nds(tile_id)
        else:  # XYZ
            x, y = latlon_to_xyz(center_point.x(), center_point.y(), level)
            tile_id = None

        # 构建复制文本
        tile_text = ''
        tile_text_info = ''

        if tile_id:
            tile_text += f"{tile_id},"
            tile_text_info += 'tileId,'

        tile_text += f"{x},{y}"
        tile_text_info += 'x,y'

        clipboard = QApplication.clipboard()
        clipboard.setText(tile_text)

        QMessageBox.information(self, self.tr("Copy Successful: {0}").format(tile_text_info), tile_text)

    def changeEvent(self, event):
        """处理语言变更事件"""
        if event.type() == QEvent.LanguageChange:
            # 重新翻译UI
            self.retranslateUi()
            # 更新动态文本
            self.init_templates()
            self.update_ui_texts()
            self.update_center_info()
        super().changeEvent(event)

    def retranslateUi(self, widget=None):
        # 调用父类的retranslateUi方法
        if hasattr(super(), 'retranslateUi'):
            super().retranslateUi(self)

        self.init_templates()
        self.update_ui_texts()
        if hasattr(self, 'current_coord_label'):
            self.update_center_info()

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        # 隐藏十字准线
        if hasattr(self, 'crosshair') and self.crosshair:
            try:
                self.crosshair.hide()
                self.crosshair.deleteLater()
                self.crosshair = None
            except:
                pass

        # 断开地图范围变化信号
        try:
            canvas = iface.mapCanvas()
            canvas.extentsChanged.disconnect(self.on_map_extent_changed)
            canvas.mapCanvasRefreshed.disconnect(self.on_map_refreshed)
        except:
            # 忽略信号未连接或 canvas 已销毁的异常
            pass

        # 发射插件关闭信号给主类
        self.closingPlugin.emit()
        event.accept()
