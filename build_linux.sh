#!/usr/bin/env bash
# =============================================================
# WTDashboard Linux 构建脚本
# 用法: bash build_linux.sh
# 产物: dist/WTDashboard_Setup_v1_1_0.deb
# =============================================================
set -e

APP_NAME="WTDashboard"
VERSION="1.1.1"
DEB_NAME="WTDashboard_Setup_v1_1_0"

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

echo "=== 创建 deb 安装包结构（支持自动覆盖旧版本） ==="
DEB_ROOT="dist/${APP_NAME}_deb"
mkdir -p "$DEB_ROOT/DEBIAN"
mkdir -p "$DEB_ROOT/usr/bin"
mkdir -p "$DEB_ROOT/usr/share/applications"
mkdir -p "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps"

# 复制程序
cp -R "dist/${APP_NAME}/"* "$DEB_ROOT/usr/bin/"

# 启动脚本
cat > "$DEB_ROOT/usr/bin/wtdashboard" << 'EOF'
#!/bin/bash
exec /usr/bin/WTDashboard "$@"
EOF
chmod +x "$DEB_ROOT/usr/bin/wtdashboard"

# 图标
cp icon.png "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps/wtdashboard.png"

# .desktop
cat > "$DEB_ROOT/usr/share/applications/wtdashboard.desktop" << EOF
[Desktop Entry]
Name=War Thunder Dashboard
Comment=Real-time tactical display for War Thunder
Exec=/usr/bin/wtdashboard
Icon=wtdashboard
Type=Application
Categories=Game;Utility;
EOF

# DEBIAN control
cat > "$DEB_ROOT/DEBIAN/control" << EOF
Package: wtdashboard
Version: $VERSION
Section: games
Priority: optional
Architecture: amd64
Maintainer: WTDashboard
Description: War Thunder Dashboard
 Real-time tactical display for War Thunder.
 Displays live map, unit tracking, situation report, and HUD messages.
EOF

dpkg-deb --build "$DEB_ROOT" "dist/${DEB_NAME}.deb"
rm -rf "$DEB_ROOT"

echo "=== 完成 ==="
echo "产物: dist/${DEB_NAME}.deb"
ls -lh "dist/${DEB_NAME}.deb"
