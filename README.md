# MxExport QGIS 插件
![dakang_icon.png](dakang_icon.png)
一个功能强大的QGIS插件，用于坐标转换、瓦片边界显示和WKT/GeoJSON数据导入导出。

## 功能特性
![img_1.png](static/img_1.png)
### 🌍 坐标转换
- 支持多种坐标系统转换（WGS84、EPSG:3857等）
- 经纬度与Web Mercator坐标系互转
- 实时坐标转换显示
- 一键跳转到指定坐标位置
- 支持EPSG:3857坐标系的准确跳转

### 🗺️ 瓦片边界显示
- 支持多种瓦片类型（NDS、XYZ）
- 可调节缩放级别显示
- 屏幕中心位置信息显示
- 瓦片ID信息查看
- **新增**：直接输入Tile X,Y坐标快速跳转
  - 支持NDS Tile坐标
  - 支持XYZ Tile坐标
  - 自动根据选择的Tile类型和级别计算跳转位置

![img_2.png](static/img_2.png)

### 📊 数据导入导出
- WKT (Well-Known Text) 格式支持
- GeoJSON 格式支持
- 批量数据处理
- 图层管理功能

## 更新日志

### v2.2
- ✨ **新增**：GeoJSON Properties 支持
  - 导入 GeoJSON 时自动保存 properties 数据
  - 在图层属性表中查看和编辑原始数据
- ✨ **新增**：动态坐标输入标签
  - 根据选择的坐标格式自动切换标签文本
  - 支持 NDS TileID、XYZ Tile、WGS84、EPSG:3857
- ✨ **新增**：坐标自动回显
  - 切换坐标格式时自动显示当前对应的坐标值
  - 地图范围改变时实时更新坐标显示
- 🐛 **修复**：GeoJSON 处理的多处逻辑问题
  - 修复 shapely unary_union 的调用错误
  - 改进坐标系转换和符号样式设置


### v2.1
- ✨ **新增**：Tile坐标快速跳转功能
  - 支持通过输入X,Y坐标直接跳转到指定Tile
  - 支持NDS和XYZ两种Tile坐标系统
  - 自动适配当前地图坐标系（EPSG:4326、EPSG:3857等）
- 🐛 修复：EPSG:3857坐标系下WKT/GeoJSON导入跳转位置错误
- 🎯 改进：优化坐标系转换逻辑，确保在不同坐标系下的准确性

### v2.0
- ✨ 初始版本发布
- 🌍 坐标转换功能
- 🗺️ 瓦片边界显示
- 📊 WKT/GeoJSON数据支持

## 许可证

本项目采用 [Apache-2.0 license](LICENSE) - 详见LICENSE文件

