#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/2/5 11:36
# @Author  : DAKANG
# @File    : tile_utils.py
# @Software: PyCharm
import math
from typing import Any
import enum

import numpy as np


class CoordinatesSystemType(enum.Enum):
    WGS84 = (0,)
    NDS = (1,)
    XYZ = (2,)
    MERCATOR = 3


def wgs84_to_nds(x, level, y_flag=False) -> int:
    """
    WGS84坐标转NDS坐标计算
    Parameters
    ----------
    x
    level
    y_flag

    Returns
    -------

    """
    if x == 180:
        x = 179.99999999
    v = int(x * 4294967296 / 360)
    if v < 0:
        v = v & 0xFFFFFFFF
    if y_flag:
        v = v & 0x7FFFFFFF
    return v >> (31 - level)


def nds_degree(tile_level):
    """
    NDS坐标转Tile ID计算
    :param tile_level: tile 等级
    :return: NDS坐标
    """
    return 1 * 360 / 2 ** (tile_level + 1)


def to_signed_32bit(n):
    n = n & 0xFFFFFFFF
    return n if n < 0x80000000 else n - 0x100000000


def nds_to_wgs84(x, tile_level, y_flag=False):
    """
    NDS坐标转WGS84坐标计算
    Parameters
    ----------
    x
    tile_level
    y_flag

    Returns
    -------

    """
    if not y_flag:
        # x
        v = x << (31 - tile_level)
        v = to_signed_32bit(v)
        d = v * 360 / (2**32)
    else:
        v = x << (31 - tile_level)
        v |= 2 ** (31 - tile_level - 1)
        v -= 2 ** (31 - tile_level - 1)
        if v & 2**30:
            v |= 0x80000000
        v = to_signed_32bit(v)
        d = v * 180 / (2**31)
    return d


def encode_tile_id(x, y, level=13, is_wgs84=False):
    """
    NDS、WGS84坐标转Tile ID计算
    Parameters
    ----------
    x
    y
    level
    is_wgs84

    Author DAKANG
    Returns
    -------

    """
    if is_wgs84:
        nds_x = wgs84_to_nds(x, level)
        nds_y = wgs84_to_nds(y, level, True)
    else:
        nds_x = int(x)
        nds_y = int(y)
    tile_id = 1 << (level + 16)
    # Morton code calculate

    for i in range(level + 1):
        tile_id |= ((nds_x & (1 << i)) >> i) << (2 * i)
        tile_id |= ((nds_y & (1 << i)) >> i) << (2 * i + 1)
    return tile_id


def parse_tile_id_2_nds(tile_id, tile_level=None):
    """
    解析TileID到NDS坐标
    Parameters
    ----------
    tile_id
    tile_level

    Author DAKANG
    Returns
    -------

    """
    nds_x = 0
    nds_y = 0
    morton_code = tile_id
    current_level = parse_tile_level(tile_id)
    for i in range(current_level + 1):
        move_bit = i * 2
        nds_x |= (morton_code & 1 << move_bit) >> i
        nds_y |= (morton_code & 1 << (move_bit + 1)) >> (i + 1)
    if current_level == 0 and tile_id == 65537:
        nds_x = 1
    if tile_level:
        nds_x = nds_x >> (current_level - tile_level)
        nds_y = nds_y >> (current_level - tile_level)
    return nds_x, nds_y


def parse_tile_level(tile_id):
    """
    解析Tile level
    :param tile_id:
    :return:
    """
    level = 15
    try:
        while True:
            move_bit = level + 16
            if ((tile_id & (1 << move_bit)) >> move_bit) == 1:
                return level
            level -= 1
    except Exception as e:
        print(f"Error parsing tile level: {tile_id}")
        raise e


def get_adjacent_tiles(p, meters=50):
    """
    获取周边Tile
    Args:
        p: 点坐标 (x, y) 元组或包含 x, y 属性的对象
        meters:

    Returns:

    """
    # 支持元组或对象
    if isinstance(p, tuple):
        px, py = p
    else:
        px, py = p.x, p.y

    degree_m = meters * 1e-5 / 2
    left_top = px - degree_m, py + degree_m
    left_bottom = px - degree_m, py - degree_m
    right_top = px + degree_m, py + degree_m
    right_bottom = px + degree_m, py - degree_m

    tiles = set()
    tiles.add(encode_tile_id(*left_top, is_wgs84=True))
    tiles.add(encode_tile_id(*left_bottom, is_wgs84=True))
    tiles.add(encode_tile_id(*right_top, is_wgs84=True))
    tiles.add(encode_tile_id(*right_bottom, is_wgs84=True))
    return tiles


def get_around_tiles(tile_id, tile_level=None) -> list:
    if tile_level is None:
        tile_level = parse_tile_level(tile_id)

    x, y = parse_tile_id_2_nds(tile_id, tile_level)

    tile_ids = [
        encode_tile_id(x + 1, y + 1, tile_level),
        encode_tile_id(x + 1, y, tile_level),
        encode_tile_id(x + 1, y - 1, tile_level),
        encode_tile_id(x, y + 1, tile_level),
        encode_tile_id(x, y - 1, tile_level),
        encode_tile_id(x - 1, y + 1, tile_level),
        encode_tile_id(x - 1, y, tile_level),
        encode_tile_id(x - 1, y - 1, tile_level),
    ]

    return tile_ids


def get_tile_boundary_polygon(tile_id, xyz=False, expand=(0, 0), expand_percent=True):
    """
    获取Tile边界（返回坐标列表）
    :param tile_id:
    :param xyz:
    :param expand: 外扩
    :param expand_percent: 外扩为百分比
    :return: 坐标列表 [(x1, y1), (x2, y2), ...]

    Args:
        xyz:  标记是否是xyz坐标 false 是wgs84坐标
    """
    longitudes_min, longitudes_max, latitudes_min, latitudes_max = get_tile_boundary(
        tile_id, xyz, expand, expand_percent
    )
    # 返回坐标列表（闭合多边形）
    poly_coords = [
        (longitudes_min, latitudes_min),
        (longitudes_max, latitudes_min),
        (longitudes_max, latitudes_max),
        (longitudes_min, latitudes_max),
        (longitudes_min, latitudes_min),
    ]

    return poly_coords


def get_tile_bounds_polygon(
    tile_id,
    tile_type=CoordinatesSystemType.NDS,
    out_type=CoordinatesSystemType.WGS84,
    extent=4096,
    expand_bounds=(0, 0),
):
    """
    获取Tile边界多边形（返回坐标列表）

    Parameters
    ----------
    tile_id
    tile_type
    out_type
    extent
    expand_bounds

    Returns
    -------
    坐标列表 [(x1, y1), (x2, y2), ...]
    """
    x_min, y_min, x_max, y_max = get_tile_bounds(tile_id, tile_type, out_type, extent, expand_bounds)
    # 返回坐标列表（闭合多边形）
    poly_coords = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max), (x_min, y_min)]

    return poly_coords


def get_x_y_bounds_polygon(
    x,
    y,
    tile_level,
    tile_type=CoordinatesSystemType.NDS,
    out_type=CoordinatesSystemType.WGS84,
    extent=4096,
    expand_bounds=(0, 0),
):
    """
    获取XY边界多边形（返回坐标列表）

    Parameters
    ----------
    x
    y
    tile_level
    tile_type
    out_type
    extent
    expand_bounds

    Returns
    -------
    坐标列表 [(x1, y1), (x2, y2), ...]
    """
    x_min, y_min, x_max, y_max = get_x_y_bounds(x, y, tile_level, tile_type, out_type, extent, expand_bounds)
    # 返回坐标列表（闭合多边形）
    poly_coords = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max), (x_min, y_min)]

    return poly_coords


def get_x_y_bounds(
    nds_x,
    nds_y,
    tile_level,
    tile_type=CoordinatesSystemType.NDS,
    out_type=CoordinatesSystemType.WGS84,
    extent=4096,
    expand_bounds=(0, 0),
) -> tuple[Any, Any, Any, Any]:
    x_min, y_min, x_max, y_max, z = 0, 0, 0, 0, 0

    if tile_type == CoordinatesSystemType.NDS:
        x_min = nds_to_wgs84(nds_x, tile_level)
        y_min = nds_to_wgs84(nds_y, tile_level, True)
        d = nds_degree(tile_level)
        x_max = x_min + d
        y_max = y_min + d
    elif tile_type == CoordinatesSystemType.XYZ and out_type == CoordinatesSystemType.WGS84:
        x_min, y_max = xyz_tile_to_lonlat(nds_x, nds_y, tile_level)
        x_max, y_min = xyz_tile_to_lonlat(nds_x + 1, nds_y + 1, tile_level)
    elif tile_type == CoordinatesSystemType.XYZ and out_type == CoordinatesSystemType.MERCATOR:
        x_min, y_max = tile_to_mercator(nds_x, nds_y, tile_level)
        x_max, y_min = tile_to_mercator(nds_x + 1, nds_y + 1, tile_level)

    if expand_bounds[0] != 0 or expand_bounds[1] != 0:
        x_step = (x_max - x_min) / extent
        y_step = (y_max - y_min) / extent
        x_min -= x_step * expand_bounds[0]
        x_max += x_step * expand_bounds[0]
        y_min -= y_step * expand_bounds[1]
        y_max += y_step * expand_bounds[1]

    if out_type == CoordinatesSystemType.WGS84:
        x_min = round(x_min, 7)
        y_min = round(y_min, 7)
        x_max = round(x_max, 7)
        y_max = round(y_max, 7)
    else:
        x_min = round(x_min, 2)
        y_min = round(y_min, 2)
        x_max = round(x_max, 2)
        y_max = round(y_max, 2)
    return x_min, y_min, x_max, y_max


def get_tile_bounds(
    tile_id,
    tile_type=CoordinatesSystemType.NDS,
    out_type=CoordinatesSystemType.WGS84,
    extent=4096,
    expand_bounds=(0, 0),
) -> tuple[Any, Any, Any, Any]:
    x_min, y_min, x_max, y_max, z = 0, 0, 0, 0, 0
    tile_level = parse_tile_level(tile_id)
    nds_x, nds_y = parse_tile_id_2_nds(tile_id)

    if tile_type == CoordinatesSystemType.NDS:
        x_min = nds_to_wgs84(nds_x, tile_level)
        y_min = nds_to_wgs84(nds_y, tile_level, True)
        d = nds_degree(tile_level)
        x_max = x_min + d
        y_max = y_min + d
    elif tile_type == CoordinatesSystemType.XYZ and out_type == CoordinatesSystemType.WGS84:
        x_min, y_max = xyz_tile_to_lonlat(nds_x, nds_y, tile_level)
        x_max, y_min = xyz_tile_to_lonlat(nds_x + 1, nds_y + 1, tile_level)
    elif tile_type == CoordinatesSystemType.XYZ and out_type == CoordinatesSystemType.MERCATOR:
        x_min, y_max = tile_to_mercator(nds_x, nds_y, tile_level)
        x_max, y_min = tile_to_mercator(nds_x + 1, nds_y + 1, tile_level)

    if expand_bounds[0] != 0 or expand_bounds[1] != 0:
        x_step = (x_max - x_min) / extent
        y_step = (y_max - y_min) / extent
        x_min -= x_step * expand_bounds[0]
        x_max += x_step * expand_bounds[0]
        y_min -= y_step * expand_bounds[1]
        y_max += y_step * expand_bounds[1]

    if out_type == CoordinatesSystemType.WGS84:
        x_min = round(x_min, 7)
        y_min = round(y_min, 7)
        x_max = round(x_max, 7)
        y_max = round(y_max, 7)
    else:
        x_min = round(x_min, 2)
        y_min = round(y_min, 2)
        x_max = round(x_max, 2)
        y_max = round(y_max, 2)
    return x_min, y_min, x_max, y_max


def get_tile_boundary(tile_id, xyz=False, expand=(0, 0), expand_percent=True):
    """
    获取Tile边界
    :param tile_id:
    :param xyz:
    :param expand:
    :param expand_percent:
    :return:

    """
    tile_level = parse_tile_level(tile_id)
    nds_x, nds_y = parse_tile_id_2_nds(tile_id)
    if not xyz:
        longitudes_min = nds_to_wgs84(nds_x, tile_level)
        latitudes_min = nds_to_wgs84(nds_y, tile_level)
        d = nds_degree(tile_level)
        longitudes_max = longitudes_min + d
        latitudes_max = latitudes_min + d
    else:
        longitudes_min, latitudes_max = xyz_tile_to_lonlat(nds_x, nds_y, tile_level)
        longitudes_max, latitudes_min = xyz_tile_to_lonlat(nds_x + 1, nds_y + 1, tile_level)

    if expand[0] != 0 or expand[1] != 0:
        lon_expand = expand[0]
        alt_expand = expand[1]
        if expand_percent:
            lon_expand = (longitudes_max - longitudes_min) * expand[0]
            alt_expand = (latitudes_max - latitudes_min) * expand[1]

        longitudes_min -= lon_expand
        longitudes_max += lon_expand
        latitudes_min -= alt_expand
        latitudes_max += alt_expand

    return (round(longitudes_min, 7), round(longitudes_max, 7), round(latitudes_min, 7), round(latitudes_max, 7))


def get_gridding_coordinate(x, y, x_min, x_max, y_min, y_max, turn_y_axis=True, extent=4096):
    """
    获取分格坐标
    Args:
        x:
        y:
        x_min:
        x_max:
        y_min:
        y_max:
        turn_y_axis:
        extent:

    Returns:
        相对于圆点坐标
    """

    lat_step = (y_max - y_min) / extent
    lon_step = (x_max - x_min) / extent
    x = int(round((x - x_min) / lon_step, 0))
    y = int(round((y - y_min) / lat_step, 0))
    if turn_y_axis:
        y = extent - y
    return x, y


def get_gridding_coordinate_by_wgs84(
    wgs84_x,
    wgs84_y,
    extent=4096,
    latitudes_min=None,
    latitudes_max=None,
    longitudes_min=None,
    longitudes_max=None,
    turn_y_axis=True,
):
    """
    获取分格坐标
    Args:
        wgs84_x:
        wgs84_y:
        extent:
        latitudes_min:
        latitudes_max:
        longitudes_min:
        longitudes_max:
        turn_y_axis:

    Returns:
        相对于圆点坐标
    """
    if latitudes_min is None or latitudes_max is None or longitudes_min is None or longitudes_max is None:
        longitudes_min, longitudes_max, latitudes_min, latitudes_max = get_tile_boundary(
            encode_tile_id(wgs84_x, wgs84_y, is_wgs84=True)
        )
    lat_step = (latitudes_max - latitudes_min) / extent
    lon_step = (longitudes_max - longitudes_min) / extent
    x = round((wgs84_x - longitudes_min) / lon_step, 0)
    y = round((wgs84_y - latitudes_min) / lat_step, 0)
    if turn_y_axis:
        y = extent - y
    return x, y


def get_xyz_gridding_coordinate_by_wgs84(
    wgs84_x,
    wgs84_y,
    extent=4096,
    latitudes_min=None,
    latitudes_max=None,
    longitudes_min=None,
    longitudes_max=None,
    turn_y_axis=True,
):
    """
    获取分格坐标
    Args:
        wgs84_x:
        wgs84_y:
        extent:
        latitudes_min:
        latitudes_max:
        longitudes_min:
        longitudes_max:
        turn_y_axis:

    Returns:
        相对于圆点坐标
    """
    if latitudes_min is None or latitudes_max is None or longitudes_min is None or longitudes_max is None:
        longitudes_min, longitudes_max, latitudes_min, latitudes_max = get_tile_boundary(
            encode_tile_id(wgs84_x, wgs84_y, is_wgs84=True)
        )
    lat_step = (latitudes_max - latitudes_min) / extent
    lon_step = (longitudes_max - longitudes_min) / extent
    x = round((wgs84_x - longitudes_min) / lon_step, 0)
    y = round((wgs84_y - latitudes_min) / lat_step, 0)
    if turn_y_axis:
        y = extent - y
    return x, y


def get_wgs84_coordinate_by_grid(x, y, latitudes_min, latitudes_max, longitudes_min, longitudes_max, extent=4096):
    """
    获取分格坐标
    Args:
        x:
        y:
        latitudes_min:
        latitudes_max:
        longitudes_min:
        longitudes_max:
        extent:

    Returns:
        wgs84坐标
    """
    lat_step = (latitudes_max - latitudes_min) / extent
    lon_step = (longitudes_max - longitudes_min) / extent
    wgs84_x = lon_step * x + longitudes_min
    wgs84_y = lat_step * (extent - y) + latitudes_min
    return wgs84_x, wgs84_y


def lon2tile(lon, zoom):
    return math.floor((lon + 180) / 360 * math.pow(2, zoom))


def lat2tile(lat, zoom):
    return math.floor(
        (1 - math.log(math.tan(lat * math.pi / 180) + 1 / math.cos(lat * math.pi / 180)) / math.pi)
        / 2
        * math.pow(2, zoom)
    )


originShift = 2 * math.pi * 6378137 / 2.0


def LatLonToMeters(lat, lon):
    mx = lon * originShift / 180.0
    my = math.log(math.tan((90 + lat) * math.pi / 360.0)) / (math.pi / 180.0)

    my = my * originShift / 180.0
    return mx, my


def latlon_to_mercator(lat, lon):
    # 将纬度转换为弧度
    if lon < -179.9999999:
        lon = -179.9999999
    if lon > 179.9999999:
        lon = 179.9999999
    x = lon * originShift / 180

    if lat < -85.0511287:
        lat = -85.0511287
    if lat > 85.0511287:
        lat = 85.0511287

    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y = y * originShift / 180

    return x, y


def lonlat_to_mercator(lon, lat):
    return latlon_to_mercator(lat, lon)


def mercator_to_tile(x, y, z):
    # 计算瓦片坐标
    tile_x = int((x + originShift) / (2 * originShift / (2**z)))
    tile_y = int((originShift - y) / (2 * originShift / (2**z)))

    return tile_x, tile_y


def latlon_to_xyz(lon, lat, zoom):
    x, y = latlon_to_mercator(lat, lon)
    tile_x, tile_y = mercator_to_tile(x, y, zoom)
    return tile_x, tile_y


def tile_to_mercator(x, y, z):
    # 计算 Web Mercator 坐标
    mx = (x / (2**z)) * 2 * originShift - originShift
    my = originShift - (y / (2**z)) * 2 * originShift
    return mx, my


def mercator_to_latlon(mx, my):
    # 将 Web Mercator 坐标转换为经纬度
    lon = mx * 180 / originShift
    lat = math.atan(math.exp(my * math.pi / originShift)) * 360 / math.pi - 90
    return lat, lon


def xyz_tile_to_lonlat(x, y, z):
    # 将瓦片坐标转换为 Web Mercator 坐标
    mx, my = tile_to_mercator(x, y, z)

    # 将 Web Mercator 坐标转换为 WGS84 经纬度
    lat, lon = mercator_to_latlon(mx, my)

    return lon, lat


def latlon_to_xyz_old(lon, lat, zoom):
    """
    将WGS84坐标（经纬度）转换为TMS的切图坐标（x, y, z）

     :param lat: 纬度
     :param lon: 经度
     :param zoom: 缩放级别
     :return: (z, x, y) TMS切图坐标
    """
    return lon2tile(lon, zoom), lat2tile(lat, zoom)


def get_xyz_cover_tiles(x, y, z):
    """
    获取xyz坐标的瓦片ID
    :param x:
    :param y:
    :param z:
    :return:
    """
    xyz_tile_id = encode_tile_id(x, y, z)
    longitudes_min, longitudes_max, latitudes_min, latitudes_max = get_tile_boundary(xyz_tile_id, True)

    lon_mid = (longitudes_min + longitudes_max) / 2

    tile_ids_arr = set()
    _z = z - 1
    # 其实应该就俩

    tile_ids_arr.add(encode_tile_id(lon_mid, latitudes_min, _z, is_wgs84=True))
    tile_ids_arr.add(encode_tile_id(lon_mid, latitudes_max, _z, is_wgs84=True))

    return list(tile_ids_arr)


def rasterize_polygon(polygon_coords, resolution: float):
    """
    将多边形栅格化，返回按指定分辨率生成的点列表。
    Args:
        polygon_coords: 多边形坐标列表 [(x1, y1), (x2, y2), ...]
        resolution (float): 栅格化步长，即每个像素（点）间距
    Returns:
        List[Tuple[float, float]]: 多边形内采样的点列表
    """
    # 计算边界框
    x_coords_list = [coord[0] for coord in polygon_coords]
    y_coords_list = [coord[1] for coord in polygon_coords]
    minx, maxx = min(x_coords_list), max(x_coords_list)
    miny, maxy = min(y_coords_list), max(y_coords_list)

    x_coords = np.arange(minx, maxx, resolution)
    y_coords = np.arange(miny, maxy, resolution)

    # 创建 QgsGeometry 用于点包含测试
    from qgis.core import QgsGeometry, QgsPointXY

    # 创建多边形几何 - 使用 QgsGeometry.fromPolygonXY 更可靠
    points = [QgsPointXY(x, y) for x, y in polygon_coords]
    # 确保多边形闭合（第一个点和最后一个点相同）
    if len(points) > 0 and points[0] != points[-1]:
        points.append(points[0])
    poly_geom = QgsGeometry.fromPolygonXY([points])

    filter_points = []
    for x in x_coords:
        for y in y_coords:
            pt = QgsPointXY(x, y)
            pt_geom = QgsGeometry.fromPointXY(pt)
            if poly_geom.contains(pt_geom):
                filter_points.append((x, y))

    return filter_points


def get_tiles_by_tile_id(
    tile_id,
    input_tile_schema=CoordinatesSystemType.NDS,
    output_tile_schema=CoordinatesSystemType.XYZ,
    output_tile_level=13,
):
    """
    获取瓦片ID
    :param tile_id:
    :param input_tile_schema:
    :param output_tile_schema:
    :param output_tile_level:
    :return:
    """
    poly_coords = get_tile_bounds_polygon(tile_id, tile_type=input_tile_schema)
    points = rasterize_polygon(poly_coords, 0.005 * (2 ** (13 - output_tile_level)))
    tiles = set()
    for point in points:
        x, y = point
        if output_tile_schema == CoordinatesSystemType.NDS:
            tile_id = encode_tile_id(x, y, output_tile_level, is_wgs84=True)
        elif output_tile_schema == CoordinatesSystemType.XYZ:
            tile_x, tile_y = latlon_to_xyz(x, y, output_tile_level + 1)
            tile_id = encode_tile_id(tile_x, tile_y, output_tile_level + 1)
        else:
            return []
        tiles.add(tile_id)
    return tiles


def get_tiles_by_tile_id_v2(
    tile_id, input_tile_schema=CoordinatesSystemType.NDS, output_tile_schema=CoordinatesSystemType.XYZ
):
    """
    获取瓦片ID
    :param tile_id:
    :param input_tile_schema:
    :param output_tile_schema:
    :return:
    """
    x_min, y_min, x_max, y_max = get_tile_bounds(tile_id, tile_type=input_tile_schema)
    lv = parse_tile_level(tile_id)
    if output_tile_schema == CoordinatesSystemType.XYZ:
        lv = lv + 1
    x_mid = (x_min + x_max) / 2
    y_arr = np.linspace(y_min, y_max, 20)
    if output_tile_schema == CoordinatesSystemType.XYZ:
        tiles = set([encode_tile_id(*latlon_to_xyz(x_mid, x, lv), lv) for x in y_arr])
    else:
        tiles = set([encode_tile_id(x_mid, x, lv, is_wgs84=True) for x in y_arr])
    return tiles


if __name__ == '__main__':
    print(parse_tile_level(557546954))
