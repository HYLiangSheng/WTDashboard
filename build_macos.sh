#!/usr/bin/env bash
# =============================================================
# WTDashboard macOS 构建脚本
# 用法: bash build_macos.sh
# 产物: dist/WTDashboard_Setup_v1_0_1.dmg
# =============================================================
set -e

APP_NAME="WTDashboard"
VERSION="1.1.1"
PKG_NAME="WTDashboard_Setup_v1_1_0"

echo "=== 清理旧构建 ==="
rm -rf build dist *.spec.bak

echo "=== PyInstaller 打包 ==="
pyinstaller --noconfirm \
    --name "$APP_NAME" \
    --windowed \
    --icon=icon.icns \
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
    --osx-bundle-identifier com.wtdashboard.app \
    main.py

echo "=== 创建 pkg 安装包（支持自动覆盖旧版本） ==="
pkgbuild --install-location /Applications \
    --component "dist/${APP_NAME}.app" \
    --identifier com.wtdashboard.app \
    --version "$VERSION" \
    "dist/${PKG_NAME}.pkg"

echo "=== 完成 ==="
echo "产物: dist/${PKG_NAME}.pkg"
ls -lh "dist/${PKG_NAME}.pkg"
