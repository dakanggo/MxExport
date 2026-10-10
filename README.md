# MxExport QGIS Plugin

[中文](README.zh-CN.md)

![dakang_icon.png](dakang_icon.png)

MxExport is a QGIS plugin for GIS professionals. It provides coordinate positioning and marking, NDS/XYZ/TMS tile information, WKT/GeoJSON import, and layer management, so geographic workflows stay shorter and easier to repeat.

## Features

![img_1.png](static/img_1.png)

### Coordinate positioning and marking

- Precise coordinate positioning, with one-click coordinate copy
- Live display of the map center coordinates
- Input labels switch automatically with the coordinate format (NDS TileID, XYZ Tile, TMS Tile, WGS84, EPSG:3857)
- The current coordinates are filled back in when the format changes or the map is panned
- Jump to a location in one step, adapted to the current map CRS

### Tile information and boundaries

- NDS, XYZ, and TMS tiles, with x, y, and z parameters
- Tile boundaries drawn on the map for spatial analysis
- Adjustable zoom level
- Jump directly by entering tile coordinates
- TMS and XYZ share X and Z; the Y axis is flipped
- When the coordinate format matches the tile panel type, panning the map echoes Z at the selected tile level

### Crosshair

- Show or hide the screen-center crosshair at any time; the overlay refreshes immediately
- Two styles: a short cross at the screen center, and full-screen horizontal and vertical lines

![img_2.png](static/img_2.png)

### Data import and layer management

- Import WKT and GeoJSON quickly, create a layer, and display the geometry
- GeoJSON properties are kept and can be viewed and edited in the layer attribute table
- Multi geometries, polygons with interior rings, and GeometryCollections are supported
- Built-in WKT editing templates for quick marking and layer creation
- Layer creation window tracking, so the target layer is easy to find

## Changelog

### v2.5

- **Added**: TMS tile positioning and boundary display. TMS shares X and Z with XYZ, and the Y axis is flipped
- **Added**: When the coordinate format is XYZ Tile or TMS Tile and the tile panel uses the same type, panning the map echoes Z at the selected tile level
- **Added**: Two crosshair styles: a short cross at the screen center, and full-screen horizontal and vertical lines
- **Fixed**: The crosshair overlay refreshes immediately when shown or hidden
- **Fixed**: WKT/GeoJSON import no longer drops parts of Multi geometries, polygons with interior rings, or GeometryCollections
- **Improved**: Coordinate action layout; the WKT/GeoJSON panel height adapts with a minimum height so the bottom buttons stay visible

### v2.4

- **Fixed**: The plugin could not be used after it was closed and opened again
- **Enhanced**: Layer rendering supports multiple instance inputs
- **Improved**: Tile boundary display

### v2.3

- **Improved**: Interface layout and usability
- **Improved**: NDS and XYZ tile coordinate calculation precision
- **Enhanced**: Compatibility with more EPSG coordinate systems
- **Fixed**: Coordinate display and positioning accuracy
- **Improved**: Plugin loading and data processing speed

### v2.2

- **Added**: GeoJSON properties
  - Properties are saved when GeoJSON is imported
  - Original data can be viewed and edited in the layer attribute table
- **Added**: Dynamic coordinate input labels
  - Label text switches automatically with the selected coordinate format
  - Supports NDS TileID, XYZ Tile, WGS84, and EPSG:3857
- **Added**: Automatic coordinate echo
  - Switching the coordinate format fills in the current value for that format
  - Coordinates update as the map extent changes
- **Added**: Simplified Chinese, Traditional Chinese, and Japanese UI translations
- **Fixed**: Several GeoJSON processing issues
  - Fixed the shapely `unary_union` call
  - Improved CRS transformation and symbol styling

### v2.1

- **Added**: Quick jump by tile coordinates
  - Jump to a tile by entering X and Y
  - Supports NDS and XYZ tile systems
  - Adapts to the current map CRS (EPSG:4326, EPSG:3857, and others)
- **Fixed**: WKT/GeoJSON import jumped to the wrong place under EPSG:3857
- **Improved**: CRS transformation so results stay accurate across coordinate systems

### v2.0

- Initial release
- Coordinate transformation
- Tile boundary display
- WKT/GeoJSON data support

## License

This project is licensed under the [Apache-2.0 license](LICENSE).
