#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @Email     :
# @File      : __init__.py
# @Created   : 2025/7/28 11:47
# @Desc      :


# -*- coding: utf-8 -*-
def classFactory(iface):
    from .map_export_plugin import MapExportPlugin
    return MapExportPlugin(iface)
