# MxExport.pro
# QGIS插件翻译项目文件 - 增强版
# 自动生成时间: 1753871351.8222885
# 支持UI文件翻译提取
 
# 项目信息
TARGET = MxExport
VERSION = 1.0.0
 
# Qt模块 - 确保pylupdate5正确识别所有控件
QT += core gui widgets
 
# Python源文件 - 包含tr()调用的文件
SOURCES = ../map_export_dockwidget.py \
          ../tile_utils.py \
          ../__init__.py \
          ../map_export_plugin.py \
          ../map_export_crosshair_tool.py
 
# UI表单文件 - 重要：pylupdate5从这些文件提取翻译文本
FORMS = ../map_export_dockwidget_base.ui
 
# 资源文件 - 如果包含可翻译文本
RESOURCES = ../resources.qrc
 
# 翻译目标文件 - 支持的语言
TRANSLATIONS = MxExport_zh_CN.ts \
               MxExport_en_US.ts
 
# 编码设置 - 确保正确处理中文字符
CODECFORTR = UTF-8
CODECFORSRC = UTF-8
 
# 包含路径
INCLUDEPATH += ..
 
# 插件特定定义
DEFINES += PLUGIN_NAME=\"MxExport\"
DEFINES += PLUGIN_VERSION=\"1.0.0\"
 
# pylupdate5 选项
# 以下注释是给pylupdate5的指令
# -verbose : 显示详细输出
# -noobsolete : 不包含过时的翻译

# UI文件翻译分析:
# map_export_dockwidget_base.ui: 0 个可翻译文本
