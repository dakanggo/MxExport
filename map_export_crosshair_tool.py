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
from qgis.core import QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem
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

    def paintEvent(self, event):
        """绘制十字准线和tile边界"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        coord = self.get_center_point()

        # 获取画布中心
        map_point = QgsPointXY(coord[0], coord[1])
        canvas_point = self.canvas.getCoordinateTransform().transform(map_point)
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
            painter.drawLine(center_x - cross_length, center_y,
                             center_x - cross_gap, center_y)
            painter.drawLine(center_x + cross_gap, center_y,
                             center_x + cross_length, center_y)

            # 绘制垂直线（上、下两段）
            painter.drawLine(center_x, center_y - cross_length,
                             center_x, center_y - cross_gap)
            painter.drawLine(center_x, center_y + cross_gap,
                             center_x, center_y + cross_length)

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
            pen = QPen(QColor(0, 0, 204), 1, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # 获取polygon的边界点
            if self.tile_polygon:
                exterior = self.tile_polygon.exterior
                coords = list(exterior.coords)

                # 转换坐标到屏幕坐标
                screen_points = []
                for coord in coords:
                    # 将WGS84坐标转换为屏幕坐标
                    map_point = QgsPointXY(coord[0], coord[1])
                    canvas_point = self.canvas.getCoordinateTransform().transform(map_point)
                    screen_points.append((int(canvas_point.x()), int(canvas_point.y())))

                # 绘制polygon边界
                if len(screen_points) > 2:
                    for i in range(len(screen_points)):
                        start_point = screen_points[i]
                        end_point = screen_points[(i + 1) % len(screen_points)]
                        painter.drawLine(start_point[0], start_point[1],
                                         end_point[0], end_point[1])

        except Exception as e:
            print(f"绘制tile边界时出错: {e}")

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
