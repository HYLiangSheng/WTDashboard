#!/usr/bin/env bash
# =============================================================
# WTDashboard Linux 构建脚本
# 用法: bash build_linux.sh
# 产物: dist/WTDashboard_Setup_v1_0_1.AppImage
# =============================================================
set -e

APP_NAME="WTDashboard"
VERSION="1.1.0"
APPIMAGE_NAME="WTDashboard_Setup_v1_1_0"

echo "=== 清理旧构建 ==="
rm -rf build dist *.spec.bak

echo "=== PyInstaller 打包 ==="
pyinstaller --noconfirm \
    --name "$APP_NAME" \
    --windowed \
    --icon=icon.png \
    --add-data "game_icons:game_icons" \
    --add-data "locales:locales" \
    --hidden-import wtdb \
    --hidden-import wtdb.api_client \
    --hidden-import wtdb.dashboard_window \
    --hidden-import wtdb.map_widget \
    --hidden-import wtdb.sitrep_panel \
    --hidden-import wtdb.hud_feed \
    --hidden-import wtdb.unit_tracker \
    --hidden-import wtdb.styles \
    --hidden-import wtdb.config \
    --hidden-import wtdb.i18n \
    --hidden-import PyQt6.QtCore \
    --hidden-import PyQt6.QtGui \
    --hidden-import PyQt6.QtWidgets \
    --exclude-module tkinter \
    --exclude-module matplotlib \
    --exclude-module numpy \
    --exclude-module pandas \
    --exclude-module PIL.ImageQt \
    main.py

echo "=== 创建 AppDir 结构 ==="
APPDIR="dist/${APP_NAME}.AppDir"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons"
mkdir -p "$APPDIR/usr/share/applications"

# 复制构建产物
cp -R "dist/${APP_NAME}/"* "$APPDIR/usr/bin/"

# 创建启动脚本
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/WTDashboard" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# 复制图标
cp icon.png "$APPDIR/usr/share/icons/wtdashboard.png"
cp icon.png "$APPDIR/wtdashboard.png"

# 创建 .desktop 文件
cat > "$APPDIR/usr/share/applications/wtdashboard.desktop" << DESKTOP
[Desktop Entry]
Name=War Thunder Dashboard
Comment=Real-time tactical display for War Thunder
Exec=WTDashboard
Icon=wtdashboard
Type=Application
Categories=Game;Utility;
DESKTOP

# 创建符号链接（AppImage 要求）
ln -sf usr/share/applications/wtdashboard.desktop "$APPDIR/wtdashboard.desktop"
ln -sf usr/share/icons/wtdashboard.png "$APPDIR/.DirIcon"

echo "=== 打包 AppImage ==="
# 需要先安装 appimagetool: https://github.com/AppImage/AppImageKit
if command -v appimagetool &> /dev/null; then
    ARCH=x86_64 appimagetool "$APPDIR" "dist/${APPIMAGE_NAME}.AppImage"
    echo "=== 完成 ==="
    echo "产物: dist/${APPIMAGE_NAME}.AppImage"
    ls -lh "dist/${APPIMAGE_NAME}.AppImage"
else
    echo "=== AppImage 工具未安装 ==="
    echo "请安装 appimagetool 后重新运行:"
    echo "  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    echo "  chmod +x appimagetool-x86_64.AppImage"
    echo "  sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool"
    echo ""
    echo "当前产物位于: $APPDIR"
fi
