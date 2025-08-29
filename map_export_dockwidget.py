#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @Email     :
# @File      : map_export_dockwidget.py
# @Created   : 2025/7/28 11:47
# @Desc      : Map Export DockWidget with i18n support

from hmac import new
import os
from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import (pyqtSignal, QSettings, Qt, QTimer,
                              QCoreApplication, QEvent, QVariant, QSettings, QTranslator)
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
from qgis.PyQt.QtGui import QClipboard, QColor, QFont
from qgis.core import (QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem,
                       QgsFeature, QgsGeometry, QgsWkbTypes, QgsPointXY, QgsRectangle,
                       QgsCoordinateTransform, QgsTextFormat, QgsTextBufferSettings,
                       QgsField, QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsMessageLog,
                       QgsPalLayerSettings, QgsVectorLayerSimpleLabeling)

from qgis.utils import iface
from qgis.gui import QgsMapCanvas
import json
import re
from .map_export_crosshair_tool import CrosshairOverlay
from .tile_utils import *
from shapely.geometry import shape, mapping

# 加载UI文件
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'map_export_dockwidget_base.ui'))


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

    def tr(self, message):
        """翻译函数"""
        return QCoreApplication.translate('MapExportDockWidget', message)

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
            "Polygon (GeoJSON)"
        ]

        self.template_combo.addItems(template_items)

    def get_template_examples(self):
        """获取模板示例数据"""
        return {
            self.tr("-- Select Template --"): '',
            'POINT (WKT)': 'POINT (116.397468 39.909138)',
            'LINESTRING (WKT)': 'LINESTRING (116.3891602 39.9023438, 116.4111328 39.9023438)',
            'POLYGON (WKT)': 'POLYGON ((116.3891602 39.9023438, 116.4111328 39.9023438, 116.4111328 39.9243164, 116.3891602 39.9243164, 116.3891602 39.9023438))',
            'Point (GeoJSON)': """{
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
}""",
            'LineString (GeoJSON)': '''{
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
}''',
            'Polygon (GeoJSON)': '''{
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
        }

    def load_translator(self):
        """加载翻译文件"""
        try:
            plugin_dir = os.path.dirname(__file__)
            locale_path = os.path.join(plugin_dir, 'i18n')

            current_locale = QSettings().value('locale/userLocale', 'en')
            QgsMessageLog.logMessage(
                f"Current locale: {current_locale}",
                "MxExport Plugin"
            )

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

            QgsMessageLog.logMessage(
                f"尝试加载翻译文件: {translator_file}",
                "MxExport Plugin"
            )

            if os.path.exists(translator_file):
                self.translator = QTranslator()
                if self.translator.load(translator_file):
                    QCoreApplication.installTranslator(self.translator)
                    QgsMessageLog.logMessage(
                        f"成功加载翻译文件: {translator_file}",
                        "MxExport Plugin"
                    )
                    return True
                else:
                    QgsMessageLog.logMessage(
                        f"翻译文件加载失败: {translator_file}",
                        "MxExport Plugin"
                    )
            else:
                QgsMessageLog.logMessage(
                    f"翻译文件不存在: {translator_file}",
                    "MxExport Plugin"
                )

            return False

        except Exception as e:
            QgsMessageLog.logMessage(
                f"加载翻译文件时出错: {str(e)}",
                "MxExport Plugin"
            )
            return False

    def update_ui_texts(self):
        """更新UI文本（处理动态翻译）"""
        current_locale = QSettings().value('locale/userLocale', 'en')
        QgsMessageLog.logMessage(
            f"Current locale: {current_locale}",
            "MxExport Plugin"
        )

        # 测试翻译是否工作
        test_translation = self.tr("Hide Crosshair")
        QgsMessageLog.logMessage(
            f"Current locale: {test_translation}",
            "MxExport Plugin"
        )

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
                coord_text = self.tr("X, Y (EPSG:3857): {0:.2f}, {1:.2f}").format(
                    center_point.x(), center_point.y())
            else:
                # WGS84坐标系使用更多小数位数
                self.x_y_coord_edit.setText(f"{center_point.x():.6f}, {center_point.y():.6f}")
                # 更新坐标显示标签
                coord_text = self.tr("Longitude, Latitude: {0:.6f}, {1:.6f}").format(
                    center_point.x(), center_point.y())
            
            self.current_coord_label.setText(coord_text)

            # 计算并显示瓦片信息（始终使用WGS84坐标进行瓦片计算）
            wgs84_point = self.get_center_point('EPSG:4326')
            tile_type_text = self.tile_type_combo.currentText()
            level = int(self.level_combo.currentText())

            if tile_type_text == "NDS":
                if level > 13:
                    QMessageBox.warning(self, self.tr("Warning"),
                                        self.tr("NDS Tile level cannot exceed 13"))
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

            # 创建点图层
            layer = QgsVectorLayer(f"Point?crs={crs_code}", layer_name, "memory")

            # 添加标签字段
            provider = layer.dataProvider()
            provider.addAttributes([QgsField("label", QVariant.String)])
            layer.updateFields()

            # 创建要素
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(point))
            
            # 根据坐标系设置标签格式
            if "3857" in coord_type:
                label_text = f'{point.x():.2f}, {point.y():.2f}'
            else:
                label_text = f'{point.x():.6f}, {point.y():.6f}'
            
            feature.setAttributes([label_text])
            provider.addFeatures([feature])
            layer.updateExtents()

            # 设置符号样式
            symbol_properties = {
                'name': 'star',
                'size': '6',
                'color': '#4A90E2',
                'outline_color': '#FFFFFF',
                'outline_width': '0.5',
                'outline_style': 'solid'
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
            iface.mapCanvas().setExtent(layer.extent())
            iface.mapCanvas().refresh()

            QMessageBox.information(self, self.tr("Success"),
                                    self.tr("Marker layer created: {0}").format(layer_name))

        except ValueError:
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("Invalid coordinate format, please enter numbers"))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"),
                                 self.tr("Error creating point layer: {0}").format(str(e)))

    def goto_coordinate(self):
        """跳转到指定坐标"""
        try:
            x_y_text = self.x_y_coord_edit.text().strip()
            x_y_text = re.sub(r'\s+', ' ', x_y_text)
            x_y_arr = x_y_text.split(',')

            if len(x_y_arr) < 2:
                QMessageBox.warning(self, self.tr("Warning"),
                                    self.tr("Please enter complete X and Y coordinates"))
                return

            x = float(x_y_arr[0].strip())
            y = float(x_y_arr[1].strip())

            # 获取选择的坐标系类型
            coord_type = self.coord_type_combo.currentText()
            point = QgsPointXY(x, y)

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
                point = transform.transform(point)

            # 设置地图中心
            canvas.setCenter(point)
            canvas.refresh()

        except ValueError:
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("Invalid coordinate format, please enter numbers"))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"),
                                 self.tr("Error jumping to coordinate: {0}").format(str(e)))

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
            QMessageBox.critical(self, self.tr("Error"),
                                 self.tr("Error toggling crosshair display: {0}").format(str(e)))

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
            QMessageBox.critical(self, self.tr("Error"),
                                 self.tr("Error toggling tile boundary display: {0}").format(str(e)))

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
                    QMessageBox.warning(self, self.tr("Warning"),
                                        self.tr("NDS Tile level cannot exceed 13"))
                    self.level_combo.setCurrentText("13")
                    level = 13
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), level, is_wgs84=True)
                polygon = get_tile_bounds_polygon(tile_id, tile_type=CoordinatesSystemType.NDS)
            else:  # XYZ
                mx, my = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), level)
                polygon = get_x_y_bounds_polygon(mx, my, level, tile_type=CoordinatesSystemType.XYZ)

            # 如果是3857坐标系，则将polygon转成魔卡托坐标polygon
            if canvas_crs_code == "EPSG:3857":
                new_polygon_arr =  []
                for x,y in polygon.exterior.coords:
                    x,y = lonlat_to_mercator(x,y)
                    new_polygon_arr.append((x,y))
                polygon = Polygon(new_polygon_arr)
            

            if hasattr(self, 'crosshair') and self.crosshair:
                self.crosshair.set_tile_boundary(polygon)

        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"),
                                 self.tr("Error updating tile boundary: {0}").format(str(e)))

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

    def process_wkt_geojson(self):
        """处理WKT/GeoJSON数据"""
        input_text = self.wkt_text_edit.toPlainText().strip()
        layer_name = self.layer_name_edit.text().strip() or "mx"

        from datetime import datetime
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        layer_name += f"_{now_str}"

        if not input_text:
            QMessageBox.warning(self, self.tr("Warning"),
                                self.tr("Please enter WKT or GeoJSON data"))
            return

        try:
            # 处理引号
            if input_text.startswith(('\'', '"')) and input_text.endswith(('\'', '"')):
                input_text = input_text[1:-1]

            # 判断是WKT还是GeoJSON
            if input_text.startswith(('{', '[')):
                geojson_data = json.loads(input_text)
                if 'type' not in geojson_data or geojson_data['type'] == 'FeatureCollection':
                    geom_arr = []
                    for feature in geojson_data["features"]:
                        geom = shape(feature["geometry"])
                        if not geom.is_empty:
                            geom_arr.append(geom)

                    if len(geom_arr) == 1:
                        input_text = geom_arr[0].wkt
                    elif len(geom_arr) > 1:
                        union_geom = shape.unary_union(geom_arr)
                        input_text = union_geom.wkt
                    else:
                        QMessageBox.warning(self, self.tr("Warning"),
                                            self.tr("GeoJSON data is empty"))
                        return
                elif geojson_data['type'] == 'Feature':
                    geom = shape(geojson_data['geometry'])
                    if geom.is_empty:
                        QMessageBox.warning(self, self.tr("Warning"),
                                            self.tr("GeoJSON data is empty"))
                        return
                    input_text = geom.wkt
            else:
                # 验证WKT格式
                if QgsGeometry.fromWkt(input_text).isNull():
                    QMessageBox.warning(self, self.tr("Warning"),
                                        self.tr("Invalid WKT format"))
                    return

            self.process_wkt(input_text, layer_name)

        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"),
                                 self.tr("Error processing data: {0}").format(str(e)))

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
            # 根据坐标类型选择默认坐标系（WKT通常假设为WGS84）
            layer = QgsVectorLayer(f"{layer_type}?crs=EPSG:4326", layer_name, "memory")

            feature = QgsFeature()
            feature.setGeometry(geometry)

            layer.dataProvider().addFeatures([feature])
            layer.updateExtents()

            QgsProject.instance().addMapLayer(layer)

            if self.zoom_layer_checkbox.isChecked():
                iface.mapCanvas().setExtent(layer.extent())
                iface.mapCanvas().refresh()

        QMessageBox.information(self, self.tr("Success"),
                                self.tr("WKT data processed successfully and layer created: {0}").format(layer_name))

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
                QMessageBox.warning(self, self.tr("Warning"),
                                    self.tr("NDS Tile level cannot exceed 13"))
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
