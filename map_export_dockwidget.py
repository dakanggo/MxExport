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
                self.crosshair = CrosshairOverlay(canvas)
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
        canvas.extentsChanged.connect(self.on_map_extent_changed)

    def on_map_extent_changed(self):
        """地图范围改变时更新tile边界和中心信息"""
        self.update_center_info()
        self.update_coord_input_placeholder()
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            self.update_tile_boundary()

    def on_tile_settings_changed(self):
        """tile设置改变时更新显示"""
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            self.update_tile_boundary()
        self.update_center_info()

    def on_coord_type_changed(self):
        """坐标系类型改变时更新显示"""
        self.update_center_info()
        self.update_coord_input_placeholder()

    def update_coord_input_placeholder(self):
        """根据坐标类型更新输入框的值和标签"""
        try:
            coord_type = self.coord_type_combo.currentText()

            if "NDS TileID" in coord_type:
                # 获取当前屏幕中心的 NDS TileID
                wgs84_point = self.get_center_point('EPSG:4326')
                tile_level = int(self.level_combo.currentText())
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), tile_level, is_wgs84=True)
                self.x_y_coord_edit.setText(str(tile_id))
                self.x_y_label.setText(self.tr("NDS TileID:"))

            elif "XYZ Tile" in coord_type:
                # 获取当前屏幕中心的 XYZ Tile 坐标
                wgs84_point = self.get_center_point('EPSG:4326')
                z = 14  # 默认 level 为 14
                x, y = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), z)
                self.x_y_coord_edit.setText(f"{x},{y},{z}")
                self.x_y_label.setText(self.tr("X, Y, Z (Level):"))

            elif "WGS84" in coord_type:
                # 获取 WGS84 坐标
                point = self.get_center_point('EPSG:4326')
                self.x_y_coord_edit.setText(f"{point.x():.6f},{point.y():.6f}")
                self.x_y_label.setText(self.tr("Longitude, Latitude:"))

            elif "3857" in coord_type:
                # 获取 EPSG:3857 坐标
                point = self.get_center_point('EPSG:3857')
                self.x_y_coord_edit.setText(f"{point.x():.2f},{point.y():.2f}")
                self.x_y_label.setText(self.tr("X, Y (EPSG:3857):"))

        except Exception as e:
            QgsMessageLog.logMessage(f"Error updating coord input: {str(e)}", "MxExport Plugin")

    def on_tile_type_settings_changed(self):
        """tile类型设置改变时更新显示"""
        if hasattr(self, 'crosshair') and self.crosshair and self.crosshair.show_tile_boundary:
            # 获取tile类型和级别
            tile_type_text = self.tile_type_combo.currentText()
            level = int(self.level_combo.currentText())
            if tile_type_text == "NDS" and level > 2:
                self.level_combo.setCurrentText(str(level - 1))
            elif level < 19:
                self.level_combo.setCurrentText(str(level + 1))
            self.update_tile_boundary()
        self.update_center_info()

    def update_center_info(self):
        """更新屏幕中心位置信息"""
        try:
            # 获取屏幕中心坐标（根据UI选择的坐标系）
            center_point = self.get_center_point()

            # 确定坐标系类型
            coord_type = self.coord_type_combo.currentText()
            is_mercator = "3857" in coord_type

            # 更新坐标输入框
            if is_mercator:
                # 3857坐标系使用较少的小数位数
                self.x_y_coord_edit.setText(f"{center_point.x():.2f}, {center_point.y():.2f}")
                # 更新坐标显示标签
                coord_text = self.tr("X, Y (EPSG:3857): {0:.2f}, {1:.2f}").format(center_point.x(), center_point.y())
            else:
                # WGS84坐标系使用更多小数位数
                self.x_y_coord_edit.setText(f"{center_point.x():.6f}, {center_point.y():.6f}")
                # 更新坐标显示标签
                coord_text = self.tr("Longitude, Latitude: {0:.6f}, {1:.6f}").format(center_point.x(), center_point.y())

            self.current_coord_label.setText(coord_text)

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
                x_y_arr = x_y_text.split(',')
                if len(x_y_arr) < 3:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("Please enter X, Y, Z coordinates"))
                    return

                try:
                    x = int(x_y_arr[0].strip())
                    y = int(x_y_arr[1].strip())
                    z = int(x_y_arr[2].strip())
                except ValueError:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("X, Y and Z must be integers"))
                    return

                try:
                    center_point = self.xyz_to_center_point(x, y, z)
                except Exception as e:
                    QMessageBox.warning(self, self.tr("Error"), str(e))
                    return
            else:
                # 处理经纬度坐标
                x_y_arr = x_y_text.split(',')
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
            # 始终使用WGS84坐标进行瓦片边界计算
            wgs84_point = self.get_center_point('EPSG:4326')
            tile_type_text = self.tile_type_combo.currentText()
            level = int(self.level_combo.currentText())

            # 获取当前canvas的坐标系，用于确定polygon的坐标系
            canvas = iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()
            canvas_crs_code = canvas_crs.authid()

            if tile_type_text == "NDS":
                if level > 13:
                    QMessageBox.warning(self, self.tr("Warning"), self.tr("NDS Tile level cannot exceed 13"))
                    self.level_combo.setCurrentText("13")
                    level = 13
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), level, is_wgs84=True)
                polygon = get_tile_bounds_polygon(tile_id, tile_type=CoordinatesSystemType.NDS)
            else:  # XYZ
                mx, my = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), level)
                polygon = get_x_y_bounds_polygon(mx, my, level, tile_type=CoordinatesSystemType.XYZ)

            # 如果是3857坐标系，则将polygon转成魔卡托坐标polygon
            if canvas_crs_code == "EPSG:3857":
                new_polygon_arr = []
                for x, y in polygon:  # polygon 现在是坐标列表
                    x, y = lonlat_to_mercator(x, y)
                    new_polygon_arr.append((x, y))
                polygon = new_polygon_arr

            if hasattr(self, 'crosshair') and self.crosshair:
                self.crosshair.set_tile_boundary(polygon)

        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error updating tile boundary: {0}").format(str(e)))

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
        """处理WKT/GeoJSON数据"""
        input_text = self.wkt_text_edit.toPlainText().strip()
        layer_name = self.layer_name_edit.text().strip() or "mx"

        from datetime import datetime

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        layer_name += f"_{now_str}"

        if not input_text:
            QMessageBox.warning(self, self.tr("Warning"), self.tr("Please enter WKT or GeoJSON data"))
            return

        try:
            # 处理引号
            if input_text.startswith(('\'', '"')) and input_text.endswith(('\'', '"')):
                input_text = input_text[1:-1]

            # 判断是WKT还是GeoJSON
            if input_text.startswith(('{', '[')):
                geojson_data = json.loads(input_text)

                # 处理数组格式（可能是 FeatureCollection 的简化形式）
                if isinstance(geojson_data, list):
                    geojson_data = {"type": "FeatureCollection", "features": geojson_data}

                # 检查 GeoJSON 类型
                if not isinstance(geojson_data, dict) or 'type' not in geojson_data:
                    QMessageBox.warning(self, self.tr("Warning"), self.tr("Invalid GeoJSON format"))
                    return

                geojson_type = geojson_data['type']

                if geojson_type == 'FeatureCollection':
                    # FeatureCollection - 创建一个图层，包含多个要素
                    self.process_geojson_collection(geojson_data, layer_name)
                    return
                elif geojson_type == 'Feature':
                    # Feature 对象 - 提取 geometry 并处理
                    if 'geometry' not in geojson_data:
                        QMessageBox.warning(self, self.tr("Warning"), self.tr("GeoJSON Feature missing geometry"))
                        return
                    geom = self.create_geometry_from_geojson(geojson_data['geometry'])
                    if geom is None or geom.isNull() or geom.isEmpty():
                        QMessageBox.warning(self, self.tr("Warning"), self.tr("GeoJSON geometry is empty"))
                        return
                    input_text = geom.asWkt()
                elif geojson_type in [
                    'Point',
                    'LineString',
                    'Polygon',
                    'MultiPoint',
                    'MultiLineString',
                    'MultiPolygon',
                    'GeometryCollection',
                ]:
                    # 纯 Geometry 对象 - 直接处理
                    geom = self.create_geometry_from_geojson(geojson_data)
                    if geom is None or geom.isNull() or geom.isEmpty():
                        QMessageBox.warning(self, self.tr("Warning"), self.tr("GeoJSON geometry is empty"))
                        return
                    input_text = geom.asWkt()
                else:
                    QMessageBox.warning(
                        self, self.tr("Warning"), self.tr("Unsupported GeoJSON type: {0}").format(geojson_type)
                    )
                    return
            else:
                # 验证WKT格式
                if QgsGeometry.fromWkt(input_text).isNull():
                    QMessageBox.warning(self, self.tr("Warning"), self.tr("Invalid WKT format"))
                    return

            self.process_wkt(input_text, layer_name)

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Invalid JSON format: {0}").format(str(e)))
            QgsMessageLog.logMessage(f"JSON decode error: {str(e)}", "MxExport Plugin", QgsMessageLog.CRITICAL)
        except Exception as e:
            error_msg = str(e)
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error processing data: {0}").format(error_msg))
            QgsMessageLog.logMessage(
                f"Error processing WKT/GeoJSON: {error_msg}\nInput: {input_text[:200]}",
                "MxExport Plugin",
                QgsMessageLog.CRITICAL,
            )

    def process_geojson_collection(self, geojson_data, layer_name):
        """处理 GeoJSON FeatureCollection - 创建一个图层包含多个要素"""
        try:
            # 处理不同的输入格式
            if isinstance(geojson_data, list):
                # 如果是列表，假设是 features 列表
                features = geojson_data
            elif isinstance(geojson_data, dict):
                if geojson_data.get('type') == 'FeatureCollection':
                    features = geojson_data.get("features", [])
                elif geojson_data.get('type') == 'Feature':
                    # 单个 Feature，转换为列表
                    features = [geojson_data]
                else:
                    # 可能是纯 Geometry，转换为 Feature
                    features = [{"type": "Feature", "geometry": geojson_data, "properties": {}}]
            else:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("Invalid GeoJSON format"))
                return

            if not features:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("GeoJSON data is empty"))
                return

            QgsMessageLog.logMessage(f"Processing {len(features)} features", "MxExport Plugin")

            # 提取所有几何体、properties并确定最合适的图层类型
            geoms_and_props = []
            geom_types = set()
            all_properties_keys = set()

            for idx, feature in enumerate(features):
                QgsMessageLog.logMessage(f"Processing feature {idx}: {json.dumps(feature)[:200]}", "MxExport Plugin")
                try:
                    # 处理不同的 feature 格式
                    if isinstance(feature, dict):
                        if feature.get('type') == 'Feature':
                            geometry_data = feature.get("geometry")
                        elif 'type' in feature and feature['type'] in [
                            'Point',
                            'LineString',
                            'Polygon',
                            'MultiPoint',
                            'MultiLineString',
                            'MultiPolygon',
                        ]:
                            # 纯 Geometry 对象
                            geometry_data = feature
                        else:
                            QgsMessageLog.logMessage(f"Warning: Unknown feature format: {feature}", "MxExport Plugin")
                            continue
                    else:
                        QgsMessageLog.logMessage(f"Warning: Feature is not a dict: {type(feature)}", "MxExport Plugin")
                        continue

                    if geometry_data is None:
                        QgsMessageLog.logMessage("Warning: Feature missing geometry", "MxExport Plugin")
                        continue

                    # 使用统一的辅助函数创建几何体
                    geom_json = json.dumps(geometry_data)
                    QgsMessageLog.logMessage(f"Geometry JSON: {geom_json[:200]}", "MxExport Plugin")

                    geom = self.create_geometry_from_geojson(geometry_data)

                    if geom is None:
                        geom = QgsGeometry()  # 创建空几何体

                    geom_type = geometry_data.get('type', 'Unknown')
                    QgsMessageLog.logMessage(
                        f"Geometry created: type={geom_type}, isNull={geom.isNull()}, isEmpty={geom.isEmpty()}, wkbType={geom.wkbType()}",
                        "MxExport Plugin",
                    )

                    if geom.isNull():
                        QgsMessageLog.logMessage(
                            f"Warning: Geometry is null for feature: {json.dumps(feature)[:100]}", "MxExport Plugin"
                        )
                        continue

                    if geom.isEmpty():
                        QgsMessageLog.logMessage(
                            f"Warning: Geometry is empty for feature: {json.dumps(feature)[:100]}", "MxExport Plugin"
                        )
                        continue

                    if True:  # 改为始终处理非空几何
                        # 获取properties
                        if isinstance(feature, dict) and 'properties' in feature:
                            props = feature.get("properties", {})
                        else:
                            props = {}
                        if props:
                            all_properties_keys.update(props.keys())
                        # 获取几何类型名称
                        geom_type_name = QgsWkbTypes.displayString(geom.wkbType())
                        # 转换为简化的类型名称
                        if 'Point' in geom_type_name:
                            geom_type_simple = 'Point'
                        elif 'Line' in geom_type_name:
                            geom_type_simple = 'LineString'
                        elif 'Polygon' in geom_type_name:
                            geom_type_simple = 'Polygon'
                        else:
                            geom_type_simple = geom_type_name
                        geoms_and_props.append((geom, props))
                        geom_types.add(geom_type_simple)
                except Exception as e:
                    QgsMessageLog.logMessage(f"Warning: Failed to parse feature geometry: {str(e)}", "MxExport Plugin")
                    continue

            if not geoms_and_props:
                error_msg = (
                    f"No valid geometries found. Processed {len(features)} features. Check QGIS log for details."
                )
                QMessageBox.warning(self, self.tr("Warning"), self.tr("GeoJSON data is empty") + f"\n{error_msg}")
                QgsMessageLog.logMessage(error_msg, "MxExport Plugin", QgsMessageLog.WARNING)
                return

            QgsMessageLog.logMessage(f"Successfully parsed {len(geoms_and_props)} geometries", "MxExport Plugin")

            # 确定图层类型（如果有多种类型，使用 Geometry）
            if len(geom_types) == 1:
                geom_type_name = list(geom_types)[0]
                if geom_type_name == 'Point':
                    layer_type = "Point"
                elif geom_type_name in ('LineString', 'MultiLineString'):
                    layer_type = "LineString"
                elif geom_type_name in ('Polygon', 'MultiPolygon'):
                    layer_type = "Polygon"
                else:
                    layer_type = "Geometry"
            else:
                layer_type = "Geometry"

            if self.create_layer_checkbox.isChecked():
                # 获取当前地图画布的坐标系
                canvas = iface.mapCanvas()
                canvas_crs = canvas.mapSettings().destinationCrs()
                canvas_crs_code = canvas_crs.authid() or 'EPSG:4326'

                # 创建图层，使用与画布相同的坐标系
                layer = QgsVectorLayer(f"{layer_type}?crs={canvas_crs_code}", layer_name, "memory")
                provider = layer.dataProvider()

                # 为图层添加属性字段
                fields = []
                for key in sorted(all_properties_keys):
                    fields.append(QgsField(key, QVariant.String))

                if fields:
                    provider.addAttributes(fields)
                    layer.updateFields()

                # 添加要素
                features_list = []
                source_crs = QgsCoordinateReferenceSystem('EPSG:4326')

                for geom, props in geoms_and_props:
                    # geom 已经是 QgsGeometry 对象，直接使用
                    qgs_geom = geom

                    # 如果画布坐标系与源坐标系不同，进行转换
                    if canvas_crs_code != 'EPSG:4326':
                        transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
                        qgs_geom.transform(transform)

                    feature = QgsFeature()
                    feature.setGeometry(qgs_geom)

                    # 设置属性值
                    if props and fields:
                        attributes = []
                        for key in sorted(all_properties_keys):
                            attributes.append(props.get(key, ''))
                        feature.setAttributes(attributes)

                    features_list.append(feature)

                # 添加所有要素到图层
                provider.addFeatures(features_list)
                layer.updateExtents()

                # 根据几何类型设置符号样式（使用随机颜色和更细的线条）
                random_color = self.generate_random_color()

                if layer_type == "Point":
                    symbol_properties = {
                        'name': 'circle',
                        'size': '3',  # 从 5 改为 3，更小
                        'color': random_color,
                        'outline_color': '#FFFFFF',
                        'outline_width': '0.3',  # 从 0.5 改为 0.3，更细
                    }
                    symbol = QgsMarkerSymbol.createSimple(symbol_properties)
                elif layer_type == "LineString":
                    symbol = QgsLineSymbol.createSimple(
                        {'line_color': random_color, 'line_width': '0.5'}
                    )  # 从 1 改为 0.5
                elif layer_type == "Polygon":
                    # 多边形填充色使用半透明
                    fill_color = random_color + '40'  # 添加透明度
                    symbol = QgsFillSymbol.createSimple(
                        {'color': fill_color, 'outline_color': random_color, 'outline_width': '0.5'}
                    )
                else:
                    symbol = QgsLineSymbol.createSimple({'line_color': random_color, 'line_width': '0.5'})

                renderer = QgsSingleSymbolRenderer(symbol)
                layer.setRenderer(renderer)

                # 添加到项目
                QgsProject.instance().addMapLayer(layer)

                if self.zoom_layer_checkbox.isChecked():
                    canvas.setExtent(layer.extent())
                    canvas.refresh()

            QMessageBox.information(
                self,
                self.tr("Success"),
                self.tr("GeoJSON data processed successfully and layer created: {0}").format(layer_name),
            )

        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error processing GeoJSON data: {0}").format(str(e)))

    def process_wkt(self, wkt_text, layer_name):
        """处理WKT数据"""
        geometry = QgsGeometry.fromWkt(wkt_text)
        if geometry.isNull():
            raise Exception(self.tr("Invalid WKT format"))

        # 根据几何类型确定图层类型
        geom_type = geometry.wkbType()
        if QgsWkbTypes.geometryType(geom_type) == QgsWkbTypes.PointGeometry:
            layer_type = "Point"
        elif QgsWkbTypes.geometryType(geom_type) == QgsWkbTypes.LineGeometry:
            layer_type = "LineString"
        elif QgsWkbTypes.geometryType(geom_type) == QgsWkbTypes.PolygonGeometry:
            layer_type = "Polygon"
        else:
            layer_type = "Geometry"

        if self.create_layer_checkbox.isChecked():
            # 获取当前地图画布的坐标系
            canvas = iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()
            canvas_crs_code = canvas_crs.authid() or 'EPSG:4326'

            # WKT通常假设为WGS84坐标
            source_crs_code = 'EPSG:4326'

            # 创建图层时使用地图画布的坐标系
            layer = QgsVectorLayer(f"{layer_type}?crs={canvas_crs_code}", layer_name, "memory")

            feature = QgsFeature()

            # 如果地图画布坐标系与WGT坐标系不同，需要进行坐标转换
            if canvas_crs_code != source_crs_code:
                source_crs = QgsCoordinateReferenceSystem(source_crs_code)
                transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
                geometry.transform(transform)

            feature.setGeometry(geometry)

            layer.dataProvider().addFeatures([feature])
            layer.updateExtents()

            # 为 WKT 图层也设置随机颜色和细线条
            random_color = self.generate_random_color()

            if layer_type == "Point":
                symbol_properties = {
                    'name': 'circle',
                    'size': '3',
                    'color': random_color,
                    'outline_color': '#FFFFFF',
                    'outline_width': '0.3',
                }
                symbol = QgsMarkerSymbol.createSimple(symbol_properties)
            elif layer_type == "LineString":
                symbol = QgsLineSymbol.createSimple({'line_color': random_color, 'line_width': '0.5'})
            elif layer_type == "Polygon":
                fill_color = random_color + '40'  # 半透明填充
                symbol = QgsFillSymbol.createSimple(
                    {'color': fill_color, 'outline_color': random_color, 'outline_width': '0.5'}
                )
            else:
                symbol = QgsLineSymbol.createSimple({'line_color': random_color, 'line_width': '0.5'})

            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)

            QgsProject.instance().addMapLayer(layer)

            if self.zoom_layer_checkbox.isChecked():
                iface.mapCanvas().setExtent(layer.extent())
                iface.mapCanvas().refresh()

        QMessageBox.information(
            self,
            self.tr("Success"),
            self.tr("WKT data processed successfully and layer created: {0}").format(layer_name),
        )

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
        """关闭事件"""
        # 清理十字准线
        if hasattr(self, 'crosshair') and self.crosshair:
            self.crosshair.hide()

        # 断开信号连接
        try:
            canvas = iface.mapCanvas()
            canvas.extentsChanged.disconnect(self.on_map_extent_changed)
        except:
            pass

        self.closingPlugin.emit()
        event.accept()
