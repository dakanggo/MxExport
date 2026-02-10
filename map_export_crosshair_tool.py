#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @File      : map_export_crosshair_tool.py
# @Desc      : 使用 QgsMapCanvasItem 实现原生同步的地图覆盖层

from qgis.PyQt import QtCore, QtGui
from qgis.PyQt.QtCore import Qt, QPointF, QRectF, QCoreApplication
from qgis.PyQt.QtGui import QPainter, QPen, QColor, QBrush
from qgis.gui import QgsMapCanvasItem
from qgis.core import QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRectangle
from .tile_utils import *


class CrosshairOverlay(QgsMapCanvasItem):
    """原生同步的十字准线和瓦片边界覆盖项"""

    def __init__(self, canvas, parent_widget=None):
        super(CrosshairOverlay, self).__init__(canvas)
        self.canvas = canvas
        self.parent_widget = parent_widget

        # 显示状态
        self.show_crosshair_flag = True
        self.show_tile_boundary_flag = False

        # 设置 Item 始终覆盖全屏
        self.setZValue(1000)  # 确保在最上层

    def paint(self, painter, option, widget):
        """同步绘制函数"""
        # 保存原始变换状态
        painter.save()

        # 1. 绘制十字准线 - 强制固定在屏幕物理中心
        # 重置变换矩阵，使 painter 使用窗口像素坐标，不受地图平移影响
        if self.show_crosshair_flag:
            painter.resetTransform()
            painter.setRenderHint(QPainter.Antialiasing)

            rect = self.canvas.contentsRect()
            cx = rect.width() / 2
            cy = rect.height() / 2

            self._draw_crosshair(painter, cx, cy)

        # 恢复变换状态以便后续绘制（如果需要跟随地图）
        painter.restore()

        # 2. 实时计算并绘制瓦片边界 - 跟随地图移动
        if self.show_tile_boundary_flag and self.parent_widget:
            painter.setRenderHint(QPainter.Antialiasing)
            self._draw_realtime_tile_boundary(painter)

    def _draw_crosshair(self, painter, cx, cy):
        """绘制十字准线"""
        # 线条加宽：改为 2 像素，并保持像素对齐避免横竖粗细不一致
        painter.setRenderHint(QPainter.Antialiasing, False)

        pen = QPen(QColor(255, 0, 0), 2, Qt.SolidLine)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)

        # 加宽后仍然做像素对齐，减少虚化
        ix = int(cx) + 0.5
        iy = int(cy) + 0.5

        cross_length, cross_gap = 30, 8

        # 水平线
        painter.drawLine(QPointF(ix - cross_length, iy), QPointF(ix - cross_gap, iy))
        painter.drawLine(QPointF(ix + cross_gap, iy), QPointF(ix + cross_length, iy))

        # 垂直线
        painter.drawLine(QPointF(ix, iy - cross_length), QPointF(ix, iy - cross_gap))
        painter.drawLine(QPointF(ix, iy + cross_gap), QPointF(ix, iy + cross_length))

        # 中心点（开启抗锯齿使圆点平滑）
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QBrush(QColor(255, 0, 0)))
        painter.drawEllipse(QPointF(ix, iy), 0.5, 0.5)

    def _draw_realtime_tile_boundary(self, painter):
        """实时计算并绘制瓦片边界"""
        try:
            # 从 UI 获取当前配置
            tile_type = self.parent_widget.tile_type_combo.currentText()
            level = int(self.parent_widget.level_combo.currentText())

            # 获取当前实时中心点 (WGS84)
            canvas_center = self.canvas.center()
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            wgs84_crs = QgsCoordinateReferenceSystem('EPSG:4326')

            # 转换到 WGS84 进行瓦片计算
            transform_to_wgs84 = QgsCoordinateTransform(canvas_crs, wgs84_crs, QgsProject.instance())
            center_wgs84 = transform_to_wgs84.transform(canvas_center)

            # 计算瓦片多边形 (WGS84)
            nds_str = QCoreApplication.translate("CrosshairOverlay", "NDS")
            if tile_type == nds_str or tile_type == "NDS":
                tile_id = encode_tile_id(center_wgs84.x(), center_wgs84.y(), level, is_wgs84=True)
                polygon_coords = get_tile_bounds_polygon(tile_id, tile_type=CoordinatesSystemType.NDS)
            else:
                tx, ty = latlon_to_xyz(center_wgs84.x(), center_wgs84.y(), level)
                polygon_coords = get_x_y_bounds_polygon(tx, ty, level, tile_type=CoordinatesSystemType.XYZ)

            # 准备画笔
            pen = QPen(QColor(0, 0, 204), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # 转换多边形顶点到屏幕像素
            screen_points = []

            # 画布到屏幕的转换对象
            map_to_pixel = self.canvas.getCoordinateTransform()

            # CRS 转换（如果画布不是 WGS84）
            do_crs_transform = canvas_crs.authid() != 'EPSG:4326'
            re_transform = (
                QgsCoordinateTransform(wgs84_crs, canvas_crs, QgsProject.instance()) if do_crs_transform else None
            )

            for lon, lat in polygon_coords:
                pt = QgsPointXY(lon, lat)
                if re_transform:
                    pt = re_transform.transform(pt)

                # 地图坐标 -> 屏幕像素
                pixel_pt = map_to_pixel.transform(pt)
                screen_points.append(QPointF(pixel_pt.x(), pixel_pt.y()))

            # 绘制闭合线条
            if len(screen_points) > 2:
                for i in range(len(screen_points)):
                    p1 = screen_points[i]
                    p2 = screen_points[(i + 1) % len(screen_points)]
                    painter.drawLine(p1, p2)

        except Exception:
            pass

    def boundingRect(self):
        """返回覆盖范围，必须使用 QRectF"""
        # 返回一个足够大的 QRectF 确保始终重绘
        return QRectF(-1e15, -1e15, 2e15, 2e15)

    def show_crosshair_display(self):
        self.show_crosshair_flag = True
        self.update()

    def hide_crosshair(self):
        self.show_crosshair_flag = False
        self.update()

    @property
    def show_tile_boundary(self):
        return self.show_tile_boundary_flag

    @show_tile_boundary.setter
    def show_tile_boundary(self, value):
        self.show_tile_boundary_flag = value
        self.update()

    def hide_tile_boundary(self):
        self.show_tile_boundary_flag = False
        self.update()

    def set_tile_boundary(self, polygon):
        """兼容旧接口，现在由 paint 实时计算，此方法仅占位"""
        self.update()

    def resizeEvent(self, event):
        """QWidget 时代的残留，QgsMapCanvasItem 不需要，但保留以防万一"""
        pass
