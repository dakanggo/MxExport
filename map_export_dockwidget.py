#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @Email     :
# @File      : map_export_dockwidget.py
# @Created   : 2025/7/28 11:47
# @Desc      :
import os
from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal, QSettings, Qt, QTimer
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
from qgis.PyQt.QtGui import QClipboard
from qgis.core import (QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem,
                       QgsFeature, QgsGeometry, QgsWkbTypes, QgsPointXY, QgsRectangle,
                       QgsCoordinateTransform, QgsTextFormat, QgsTextBufferSettings, QgsField, QgsSingleSymbolRenderer,
                       QgsMarkerSymbol,
                       QgsPalLayerSettings,
                       QgsTextFormat,
                       QgsTextBufferSettings, QgsVectorLayerSimpleLabeling)
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QColor, QFont
from qgis.utils import iface
from qgis.gui import QgsMapCanvas
import json
import re
from .map_export_crosshair_tool import CrosshairOverlay
from .tile_utils import *
from shapely.geometry import shape, mapping

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'map_export_dockwidget_base.ui'))

EXAMPLES = {
    'Select Template': '',
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
}'''}


class MapExportDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        super(MapExportDockWidget, self).__init__(parent)
        self.setupUi(self)

        # 设置窗口标题
        self.setWindowTitle("MxExport")

        # 初始化十字准线
        self.crosshair = None
        self.crosshair_visible = True  # 默认显示

        # 初始化模板下拉框
        self.init_templates()

        # 连接信号和槽
        self.connect_signals()

        # 设置默认值
        self.layer_name_edit.setText("mx")
        self.create_layer_checkbox.setChecked(True)
        self.zoom_layer_checkbox.setChecked(True)
        self.level_combo.setCurrentText("13")  # 默认13级

        # 初始化十字准线（默认显示）
        self.init_crosshair()

        # 设置屏幕中心变化监听
        self.setup_map_center_tracking()

        self.gcj_02_flag = True  # 是否使用GCJ-02坐标系

    def init_templates(self):
        """初始化模板下拉框"""
        templates = EXAMPLES.keys()
        self.template_combo.addItems(templates)

    def init_crosshair(self):
        """初始化十字准线（默认显示）"""
        try:
            canvas = iface.mapCanvas()
            if self.crosshair is None:
                self.crosshair = CrosshairOverlay(canvas)
                self.crosshair.show_crosshair_display()
                self.crosshair_visible = True
                self.show_crosshair_btn.setText("隐藏十字准线")
        except Exception as e:
            print(f"初始化十字准线时出错: {e}")

    def connect_signals(self):
        """连接信号和槽"""
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
        self.clear_btn.clicked.connect(self.clear_input)
        self.confirm_btn.clicked.connect(self.confirm_action)
        # self.cancel_btn.clicked.connect(self.cancel_action)

        # 坐标转换相关信号
        self.goto_coord_btn.clicked.connect(self.goto_coordinate)
        self.show_crosshair_btn.clicked.connect(self.toggle_crosshair_display)
        self.x_y_coord_edit.returnPressed.connect(self.goto_coordinate)
        # 设置点图层相关信号
        self.set_point_btn.clicked.connect(self.set_point_layer)

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
            # 获取屏幕中心坐标
            wgs84_point = self.get_center_point()
            # 转换为WGS84坐标
            self.x_y_coord_edit.setText(f"{wgs84_point.x():.6f}, {wgs84_point.y():.6f}")

            # 更新坐标显示
            coord_text = f"经度,纬度:   {wgs84_point.x():.6f},{wgs84_point.y():.6f}"
            self.current_coord_label.setText(coord_text)

            tile_type_text = self.tile_type_combo.currentText()
            level = int(self.level_combo.currentText())

            # 根据坐标和level计算tile_id
            # 根据tile类型设置坐标系类型
            # 使用get_tile_bounds_polygon函数获取polygon
            if tile_type_text == "NDS":
                if level > 13:
                    QMessageBox.warning(self, "警告", "NDS Tile级别不能大于13")
                    self.level_combo.setCurrentText("13")
                    level = 13
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), level, is_wgs84=True)
                x, y = parse_tile_id_2_nds(tile_id)
            else:  # XYZ
                x, y = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), level)
                tile_id = None

            tile_id_text = f'{"NDS" if tile_type_text == "NDS" else "XYZ"} {level} 级 Tile: '
            if tile_id:
                tile_id_text += f"TileID[ {tile_id} ] ,"

            tile_id_text += f"x[ {x} ],y[ {y} ]"

            self.nds_tile_id_label.setText(tile_id_text)

        except Exception as e:
            self.current_coord_label.setText("无法获取坐标")
            self.nds_tile_id_label.setText("NDS 13级 TileID: 无法计算")

    def set_point_layer(self):
        """设置点图层"""
        try:
            c_p = self.get_center_point()
            # 创建点
            point = QgsPointXY(c_p.x(), c_p.y())

            # 创建图层名称，同时也用作标注内容
            layer_name = f"set_{point.x():.6f}, {point.y():.6f}"

            # --- 1. 创建图层并添加字段 ---
            # 创建一个内存中的点图层
            # "Point?crs=EPSG:4326" 定义了这是一个WGS84坐标系的点图层
            layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")

            # 为了能显示标注，我们需要给图层添加一个字段来存储文本
            provider = layer.dataProvider()
            provider.addAttributes([QgsField("label", QVariant.String)])  # 添加一个名为"label"的字符串类型字段
            layer.updateFields()  # 更新图层字段

            # --- 2. 创建要素并设置几何和属性 ---
            # 创建一个要素（Feature）
            feature = QgsFeature()
            # 设置要素的几何（即那个点）
            feature.setGeometry(QgsGeometry.fromPointXY(point))
            # 设置要素的属性（将图层名存入"label"字段）
            feature.setAttributes([f'{point.x():.6f}, {point.y():.6f}'])
            # 将要素添加到图层的数据提供者中
            provider.addFeatures([feature])
            layer.updateExtents()

            # --- 3. 设置一个特殊的符号样式（红色五角星） ---
            # 形状：五角星 ('circle', 'square', 'cross', 'triangle' 等)
            # 定义符号的属性
            symbol_properties = {
                'name': 'star',  # 使用五角星形状
                'size': '6',  # 稍微增大
                'color': '#4A90E2',  # 现代蓝色
                'outline_color': '#FFFFFF',  # 白色边框更清新
                'outline_width': '0.5',  # 稍粗的边框
                'outline_style': 'solid'
            }
            # 使用属性字典创建一个标记符号
            symbol = QgsMarkerSymbol.createSimple(symbol_properties)
            # 创建一个单一符号渲染器，并将我们的符号应用给它
            renderer = QgsSingleSymbolRenderer(symbol)
            # 将这个渲染器应用到图层上
            layer.setRenderer(renderer)

            # --- 4. 设置标注样式 ---
            # 创建一个图层标注对象
            labeling = QgsPalLayerSettings()
            # 设置从哪个字段读取标注内容
            labeling.fieldName = 'label'
            # 启用标注
            labeling.enabled = True

            # 自定义标注文本格式
            text_format = QgsTextFormat()
            text_format.setFont(QFont("Arial", 10, QFont.Bold))  # 字体：Arial, 10号, 加粗
            text_format.setColor(QColor(0, 0, 128))  # 颜色：深蓝色

            # 为标注添加一个“光环”或“缓冲区”，让它在任何背景下都清晰可见
            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(1)  # 缓冲区大小
            buffer_settings.setColor(QColor("white"))  # 缓冲区颜色
            text_format.setBuffer(buffer_settings)

            # 将文本格式应用到标注设置中
            labeling.setFormat(text_format)

            # 设置标注的位置（例如，在点的右上角）
            labeling.placement = QgsPalLayerSettings.Placement.AroundPoint
            labeling.dist = 2  # 标注距离点的距离

            # 将完整的标注设置应用到图层
            layer.setLabeling(QgsVectorLayerSimpleLabeling(labeling))
            layer.setLabelsEnabled(True)  # 确保标注是开启状态
            layer.triggerRepaint()  # 触发重绘以显示样式和标注

            # --- 5. 将图层添加到地图项目 ---
            # 添加到项目
            QgsProject.instance().addMapLayer(layer, False)
            root = QgsProject.instance().layerTreeRoot()
            root.insertLayer(0, layer)  # 插入到图层树的最顶层

            # 缩放到图层
            iface.mapCanvas().setExtent(layer.extent())
            iface.mapCanvas().refresh()

            QMessageBox.information(self, "成功", f"已创建标记点图层: {layer_name}")

        except ValueError:
            QMessageBox.warning(self, "错误", "坐标格式不正确，请输入数字")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建点图层时发生错误: {str(e)}")

    def goto_coordinate(self):
        """跳转到指定坐标"""
        try:
            x_y_text = self.x_y_coord_edit.text().strip()
            # 去空格
            x_y_text = re.sub(r'\s+', ' ', x_y_text)
            x_y_arr = x_y_text.split(',')
            x_text = float(x_y_arr[0].strip()) if len(x_y_arr) > 0 else 116.39747
            y_text = float(x_y_arr[1].strip()) if len(x_y_arr) > 1 else 39.90923

            if not x_text or not y_text:
                QMessageBox.warning(self, "警告", "请输入完整的X和Y坐标")
                return

            # 解析坐标
            x = float(x_text)
            y = float(y_text)

            # 获取选择的坐标系类型
            coord_type = self.coord_type_combo.currentText()

            # 创建点
            point = QgsPointXY(x, y)

            # 根据坐标类型设置源坐标系
            if "WGS84" in coord_type:
                source_crs = QgsCoordinateReferenceSystem('EPSG:4326')
            elif "3857" in coord_type:
                source_crs = QgsCoordinateReferenceSystem('EPSG:3857')
            else:  # UTM或其他
                source_crs = QgsCoordinateReferenceSystem('EPSG:4326')  # 默认为WGS84

            # 获取画布坐标系
            canvas = iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()

            # 坐标转换
            if source_crs != canvas_crs:
                transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
                point = transform.transform(point)

            # 设置地图中心
            canvas.setCenter(point)
            canvas.refresh()


        except ValueError:
            QMessageBox.warning(self, "错误", "坐标格式不正确，请输入数字")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"跳转坐标时发生错误: {str(e)}")

    def toggle_crosshair_display(self):
        """切换十字准线显示状态"""
        try:
            if self.crosshair is None:
                self.init_crosshair()
                return

            if self.crosshair_visible:
                self.crosshair.hide_crosshair()
                self.crosshair_visible = False
                self.show_crosshair_btn.setText("显示十字准线")
            else:
                self.crosshair.show()
                self.crosshair.show_crosshair_display()
                self.crosshair_visible = True
                self.show_crosshair_btn.setText("隐藏十字准线")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"切换十字准线显示时发生错误: {str(e)}")

    def toggle_tile_boundary(self):
        """切换tile边界显示"""
        try:
            if not hasattr(self, 'crosshair') or self.crosshair is None:
                self.init_crosshair()

            if self.crosshair.show_tile_boundary:
                self.crosshair.hide_tile_boundary()
                self.show_tile_boundary_btn.setText("显示Tile边界")
            else:
                self.update_tile_boundary()
                self.crosshair.show_tile_boundary = True
                self.show_tile_boundary_btn.setText("隐藏Tile边界")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"切换tile边界显示时发生错误: {str(e)}")

    def update_tile_boundary(self):
        """更新tile边界显示"""
        try:
            # 获取屏幕中心坐标
            wgs84_point = self.get_center_point()
            # 获取tile类型和level
            tile_type_text = self.tile_type_combo.currentText()
            level = int(self.level_combo.currentText())

            # 根据坐标和level计算tile_id

            # 根据tile类型设置坐标系类型
            # 使用get_tile_bounds_polygon函数获取polygon
            if tile_type_text == "NDS":
                if level > 13:
                    QMessageBox.warning(self, "警告", "NDS Tile级别不能大于13")
                    self.level_combo.setCurrentText("13")
                    level = 13
                tile_id = encode_tile_id(wgs84_point.x(), wgs84_point.y(), level, is_wgs84=True)
                polygon = get_tile_bounds_polygon(tile_id, tile_type=CoordinatesSystemType.NDS)
            else:  # XYZ
                mx, my = latlon_to_xyz(wgs84_point.x(), wgs84_point.y(), level)
                polygon = get_x_y_bounds_polygon(mx, my, level, tile_type=CoordinatesSystemType.XYZ)

            # 设置polygon到crosshair
            if hasattr(self, 'crosshair') and self.crosshair:
                self.crosshair.set_tile_boundary(polygon)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"更新tile边界时发生错误: {str(e)}")

    def on_template_changed(self, template_name):
        """模板改变时的处理"""
        self.wkt_text_edit.setPlainText(EXAMPLES[template_name])

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
        layer_name = self.layer_name_edit.text().strip() or "dakang"
        from datetime import datetime
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        layer_name += f"_{now_str}"
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入WKT或GeoJSON数据")
            return

        try:
            if input_text.startswith('\'') or input_text.startswith('"'):
                input_text = input_text[1:-1]

            if input_text.endswith("'") or input_text.endswith('"'):
                input_text = input_text[:-1]
            # 判断是WKT还是GeoJSON
            if input_text.startswith('{') or input_text.startswith('['):
                geojson_data = json.loads(input_text)
                if 'type' not in geojson_data or geojson_data['type'] == 'FeatureCollection':
                    geom_arr = []
                    for feature in geojson_data["features"]:
                        geom = shape(feature["geometry"])
                        if geom.is_empty:
                            continue
                        geom_arr.append(geom)
                    # 合并
                    if len(geom_arr) == 1:
                        input_text = geom_arr[0].wkt
                    elif len(geom_arr) > 1:
                        union_geom = shape.unary_union(geom_arr)
                        input_text = union_geom.wkt
                elif geojson_data['type'] == 'Feature':
                    geom = shape(geojson_data['geometry'])
                    if geom.is_empty:
                        QMessageBox.warning(self, "警告", "GeoJSON数据为空")
                        return
                    input_text = geom.wkt
            else:
                # 假设是WKT格式
                if not QgsGeometry.fromWkt(input_text).isNull():
                    input_text = input_text.strip()
                else:
                    QMessageBox.warning(self, "警告", "无效的WKT格式")
                    return

            self.process_wkt(input_text, layer_name)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"处理数据时出错: {str(e)}")

    def process_wkt(self, wkt_text, layer_name):
        """处理WKT数据"""
        # 创建几何对象
        geometry = QgsGeometry.fromWkt(wkt_text)
        if geometry.isNull():
            raise Exception("无效的WKT格式")

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

        # 创建图层
        if self.create_layer_checkbox.isChecked():
            layer = QgsVectorLayer(f"{layer_type}?crs=EPSG:4326", layer_name, "memory")

            # 添加要素
            feature = QgsFeature()
            feature.setGeometry(geometry)

            layer.dataProvider().addFeatures([feature])
            layer.updateExtents()

            # 添加到项目
            QgsProject.instance().addMapLayer(layer)

            # 缩放到图层
            if self.zoom_layer_checkbox.isChecked():
                iface.mapCanvas().setExtent(layer.extent())
                iface.mapCanvas().refresh()

        QMessageBox.information(self, "成功", f"WKT数据已成功处理并创建图层: {layer_name}")

    def process_geojson(self, geojson_text, layer_name):
        """处理GeoJSON数据"""
        try:
            geojson_data = json.loads(geojson_text)
        except json.JSONDecodeError:
            raise Exception("无效的GeoJSON格式")

        if self.create_layer_checkbox.isChecked():
            # 创建临时GeoJSON文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
                json.dump(geojson_data, f)
                temp_file = f.name

            # 创建图层
            layer = QgsVectorLayer(temp_file, layer_name, "ogr")
            if not layer.isValid():
                raise Exception("无法创建GeoJSON图层")

            # 添加到项目
            QgsProject.instance().addMapLayer(layer)

            # 缩放到图层
            if self.zoom_layer_checkbox.isChecked():
                iface.mapCanvas().setExtent(layer.extent())
                iface.mapCanvas().refresh()

            # 清理临时文件
            import os
            try:
                os.unlink(temp_file)
            except:
                pass

        QMessageBox.information(self, "成功", f"GeoJSON数据已成功处理并创建图层: {layer_name}")

    def cancel_action(self):
        """取消操作"""
        self.close()

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

    def get_center_point(self):
        canvas = iface.mapCanvas()
        center_point = canvas.center()

        canvas_crs = canvas.mapSettings().destinationCrs()
        wgs84_crs = QgsCoordinateReferenceSystem('EPSG:4326')

        if canvas_crs != wgs84_crs:
            transform = QgsCoordinateTransform(canvas_crs, wgs84_crs, QgsProject.instance())
            wgs84_point = transform.transform(center_point)
        else:
            wgs84_point = center_point
        return wgs84_point

    def copy_current_coord(self):
        # 获取QLabel中的文本内容
        center_point = self.get_center_point()
        # 移除标签部分，只复制数值
        value = f"{center_point.x():.6f},{center_point.y():.6f}"
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(value)
        # 弹窗
        QMessageBox.information(self, "复制成功:    lon,lat ", f"{value}")

    def copy_nds_tile_id(self):
        # 获取QLabel中的文本内容
        # 转换为WGS84坐标
        center_point = self.get_center_point()
        level = int(self.level_combo.currentText())

        if self.tile_type_combo.currentText() == "NDS":
            if level > 13:
                QMessageBox.warning(self, "警告", "NDS Tile级别不能大于13")
                self.level_combo.setCurrentText("13")
                level = 13
            tile_id = encode_tile_id(center_point.x(), center_point.y(), level, is_wgs84=True)
            x, y = parse_tile_id_2_nds(tile_id)
        else:  # XYZ
            x, y = latlon_to_xyz(center_point.x(), center_point.y(), level)
            tile_id = None
        tile_text_info = ''
        tile_text = ''
        if tile_id:
            tile_text += f"{tile_id},"
            tile_text_info += 'tileId,'

        tile_text += f"{x},{y}"
        tile_text_info += 'x,y'
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(tile_text)
        QMessageBox.information(self, f"复制成功:   {tile_text_info}", f"{tile_text}")
