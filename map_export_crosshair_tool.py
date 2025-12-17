#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @Email     :
# @File      : map_export_crosshair_tool.py
# @Created   : 2025/7/28 13:03
# @Desc      :

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QPainter, QPen, QColor, QBrush
from qgis.PyQt.QtWidgets import QWidget, QMessageBox
from qgis.gui import QgsMapCanvas
from qgis.core import QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.utils import iface


class CrosshairOverlay(QWidget):
    """十字准线覆盖层"""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setGeometry(canvas.geometry())
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 显示状态
        self.show_crosshair = True
        self.show_tile_boundary = False
        self.tile_polygon = None

        self.show()

    def get_center_point(self, target_crs_code='EPSG:4326'):
        """获取中心点坐标，支持不同的目标坐标系

        Args:
            target_crs_code: 目标坐标系代码，如 'EPSG:4326' 或 'EPSG:3857'
        """
        canvas = iface.mapCanvas()
        center_point = canvas.center()

        canvas_crs = canvas.mapSettings().destinationCrs()
        target_crs = QgsCoordinateReferenceSystem(target_crs_code)

        if canvas_crs != target_crs:
            transform = QgsCoordinateTransform(canvas_crs, target_crs, QgsProject.instance())
            transformed_point = transform.transform(center_point)
        else:
            transformed_point = center_point
        return transformed_point

    def paintEvent(self, event):
        """绘制十字准线和tile边界"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 获取画布坐标系的中心点，用于绘制
        canvas = iface.mapCanvas()
        center_point = canvas.center()
        canvas_point = self.canvas.getCoordinateTransform().transform(center_point)
        center_x, center_y = int(canvas_point.x()), int(canvas_point.y())
        # 绘制十字准线（改为细长十字）
        if self.show_crosshair:
            # 设置画笔
            pen = QPen(QColor(255, 0, 0), 1, Qt.SolidLine)
            painter.setPen(pen)

            # 十字准线长度
            cross_length = 30
            cross_gap = 8  # 中心留空

            # 绘制水平线（左、右两段）
            painter.drawLine(center_x - cross_length, center_y, center_x - cross_gap, center_y)
            painter.drawLine(center_x + cross_gap, center_y, center_x + cross_length, center_y)

            # 绘制垂直线（上、下两段）
            painter.drawLine(center_x, center_y - cross_length, center_x, center_y - cross_gap)
            painter.drawLine(center_x, center_y + cross_gap, center_x, center_y + cross_length)

            # 绘制中心点
            pen_center = QPen(QColor(255, 0, 0), 1, Qt.SolidLine)
            brush_center = QBrush(QColor(255, 0, 0))
            painter.setPen(pen_center)
            painter.setBrush(brush_center)
            painter.drawEllipse(center_x - 1, center_y - 1, 2, 2)

        # 绘制tile边界
        if self.show_tile_boundary and self.tile_polygon:
            self.draw_tile_boundary(painter)

    def draw_tile_boundary(self, painter):
        """绘制tile边界"""
        try:
            # 设置画笔
            pen = QPen(QColor(0, 0, 204), 2, Qt.SolidLine)  # 增加线宽使边界更明显
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # 获取polygon的边界点
            if self.tile_polygon:
                # tile_polygon 现在是坐标列表
                coords = self.tile_polygon if isinstance(self.tile_polygon, list) else list(self.tile_polygon)

                # 转换坐标到屏幕坐标
                screen_points = []

                # 获取canvas的坐标系信息
                canvas = iface.mapCanvas()
                canvas_crs = canvas.mapSettings().destinationCrs()

                for coord in coords:
                    # tile边界坐标已经是canvas坐标系下的坐标
                    # 直接创建QgsPointXY并转换为屏幕坐标
                    map_point = QgsPointXY(coord[0], coord[1])

                    # 使用canvas的坐标转换将地图坐标转换为屏幕坐标
                    canvas_point = self.canvas.getCoordinateTransform().transform(map_point)
                    screen_points.append((int(canvas_point.x()), int(canvas_point.y())))

                # 绘制polygon边界
                if len(screen_points) > 2:
                    for i in range(len(screen_points)):
                        start_point = screen_points[i]
                        end_point = screen_points[(i + 1) % len(screen_points)]
                        painter.drawLine(start_point[0], start_point[1], end_point[0], end_point[1])

        except Exception as e:
            print(f"绘制tile边界时出错: {e}")
            # 输出更多调试信息
            canvas = iface.mapCanvas()
            canvas_crs = canvas.mapSettings().destinationCrs()
            print(f"Canvas CRS: {canvas_crs.authid()}")
            if self.tile_polygon:
                coords = self.tile_polygon if isinstance(self.tile_polygon, list) else list(self.tile_polygon)
                if coords:
                    x_coords = [c[0] for c in coords]
                    y_coords = [c[1] for c in coords]
                    bounds = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
                    print(f"Tile polygon bounds: {bounds}")
                    print(f"Tile polygon coords: {coords[:5]}...")  # 只打印前5个点

    def toggle_crosshair(self):
        """切换十字准线显示状态"""
        self.show_crosshair = not self.show_crosshair
        self.update()

    def hide_crosshair(self):
        """隐藏十字准线"""
        self.show_crosshair = False
        self.update()
        # QMessageBox.warning(self, "错误", "坐标格式不正确，请输入数字")

    def show_crosshair_display(self):
        """显示十字准线"""
        self.show_crosshair = True
        self.update()

    def set_tile_boundary(self, polygon):
        """设置tile边界polygon"""
        self.tile_polygon = polygon
        self.update()

    def toggle_tile_boundary(self):
        """切换tile边界显示状态"""
        self.show_tile_boundary = not self.show_tile_boundary
        self.update()

    def hide_tile_boundary(self):
        """隐藏tile边界"""
        self.show_tile_boundary = False
        self.tile_polygon = None
        self.update()

    def resizeEvent(self, event):
        """窗口大小改变时调整位置"""
        self.setGeometry(self.canvas.geometry())
        super().resizeEvent(event)
