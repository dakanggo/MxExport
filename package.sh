#!/bin/bash

# QGIS插件源码打包脚本
# 功能：仅打包源码文件，排除编译文件、缓存文件等

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_NAME="MxExport"

# 获取版本号（从metadata.txt中提取）
VERSION=$(grep "^version=" "$SCRIPT_DIR/metadata.txt" | cut -d'=' -f2)

# 设置输出目录和文件名
OUTPUT_DIR="$SCRIPT_DIR/dist"
PACKAGE_NAME="${PLUGIN_NAME}_v${VERSION}.zip"

echo "开始打包 $PLUGIN_NAME 插件源码..."
echo "版本: $VERSION"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 如果已存在同名包，询问是否覆盖
if [ -f "$OUTPUT_DIR/$PACKAGE_NAME" ]; then
    read -p "包 $PACKAGE_NAME 已存在，是否覆盖？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消打包操作"
        exit 1
    fi
    rm -f "$OUTPUT_DIR/$PACKAGE_NAME"
fi

# 进入插件目录
cd "$SCRIPT_DIR"

# 创建临时目录
TEMP_DIR=$(mktemp -d)
TEMP_PLUGIN_DIR="$TEMP_DIR/$PLUGIN_NAME"
mkdir -p "$TEMP_PLUGIN_DIR"

echo "正在复制源码文件..."

# 定义需要包含的文件和目录
INCLUDE_FILES=(
    "__init__.py"
    "*.py"
    "*.ui"
    "*.qrc"
    "*.png"
    "metadata.txt"
    "LICENSE"
    "README.md"
)

INCLUDE_DIRS=(
    "i18n"
    "static"
)

# 复制指定的文件
for pattern in "${INCLUDE_FILES[@]}"; do
    if ls $pattern 1> /dev/null 2>&1; then
        cp $pattern "$TEMP_PLUGIN_DIR/" 2>/dev/null || true
    fi
done

# 复制指定的目录
for dir in "${INCLUDE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "复制目录: $dir"
        cp -r "$dir" "$TEMP_PLUGIN_DIR/"
        
        # 清理目录中的缓存文件
        find "$TEMP_PLUGIN_DIR/$dir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
        find "$TEMP_PLUGIN_DIR/$dir" -name "*.pyc" -type f -delete 2>/dev/null || true
        find "$TEMP_PLUGIN_DIR/$dir" -name "*.pyo" -type f -delete 2>/dev/null || true
        find "$TEMP_PLUGIN_DIR/$dir" -name ".DS_Store" -type f -delete 2>/dev/null || true
    fi
done

# 进入临时目录进行打包
cd "$TEMP_DIR"

echo "正在创建压缩包..."
zip -r "$OUTPUT_DIR/$PACKAGE_NAME" "$PLUGIN_NAME" -x \
    "*.pyc" \
    "*.pyo" \
    "*/__pycache__/*" \
    "*/.DS_Store" \
    "*/.git/*" \
    "*/.gitignore" \
    "*/Thumbs.db" \
    "*/.pytest_cache/*" \
    "*/.coverage" \
    "*/coverage.xml" \
    "*/htmlcov/*"

# 清理临时目录
rm -rf "$TEMP_DIR"

# 检查打包结果
if [ -f "$OUTPUT_DIR/$PACKAGE_NAME" ]; then
    PACKAGE_SIZE=$(du -h "$OUTPUT_DIR/$PACKAGE_NAME" | cut -f1)
    echo ""
    echo "✅ 打包成功！"
    echo "📦 包名: $PACKAGE_NAME"
    echo "📁 位置: $OUTPUT_DIR/$PACKAGE_NAME"
    echo "📏 大小: $PACKAGE_SIZE"
    echo ""
    echo "包含的文件列表："
    unzip -l "$OUTPUT_DIR/$PACKAGE_NAME"
else
    echo "❌ 打包失败！"
    exit 1
fi

echo ""
echo "✨ 源码打包完成！"