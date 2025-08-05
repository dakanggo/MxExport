#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author    : dakang
# @Email     :
# @File      : map_export_plugin.py
# @Created   : 2025/7/28 11:47
# @Desc      :


import os
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject
from .map_export_dockwidget import MapExportDockWidget


class MapExportPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = '地图导出工具'
        self.toolbar = self.iface.addToolBar('MapExportPlugin')
        self.toolbar.setObjectName('MapExportPlugin')

        self.pluginIsActive = False
        self.dockwidget = None

    def add_action(self, icon_path, text, callback, enabled_flag=True, add_to_menu=True,
                   add_to_toolbar=True, status_tip=None, whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'dakang_icon.png')
        self.add_action(
            icon_path,
            text='地图导出工具',
            callback=self.run,
            parent=self.iface.mainWindow())

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu('地图导出工具', action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        if not self.pluginIsActive:
            self.pluginIsActive = True

            if self.dockwidget is None:
                self.dockwidget = MapExportDockWidget()

            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()
