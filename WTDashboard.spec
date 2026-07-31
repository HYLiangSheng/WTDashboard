# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('game_icons', 'game_icons'), ('locales', 'locales')],
    hiddenimports=[
        'wtdb', 'wtdb.api_client', 'wtdb.dashboard_window',
        'wtdb.map_widget', 'wtdb.sitrep_panel', 'wtdb.hud_feed',
        'wtdb.unit_tracker', 'wtdb.styles', 'wtdb.config', 'wtdb.i18n',
        'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'urllib.request', 'urllib.error', 'urllib.parse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
              'PIL.ImageQt', 'pyinstaller', 'PyInstaller', 'pillow', 'PIL',
              # Qt modules not used
              'PyQt6.QtNetwork', 'PyQt6.QtSql', 'PyQt6.QtTest',
              'PyQt6.QtWebEngine', 'PyQt6.QtWebChannel', 'PyQt6.QtWebSockets',
              'PyQt6.QtPrintSupport', 'PyQt6.QtDBus', 'PyQt6.QtSvg',
              'PyQt6.QtSvgWidgets', 'PyQt6.QtXml', 'PyQt6.QtOpenGL',
              'PyQt6.QtOpenGLWidgets', 'PyQt6.QtPdf', 'PyQt6.QtMultimedia',
              'PyQt6.QtMultimediaWidgets', 'PyQt6.QtPositioning',
              'PyQt6.QtSerialPort', 'PyQt6.QtSpatialAudio',
              'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets',
              'PyQt6.QtAxContainer', 'PyQt6.QtDesigner', 'PyQt6.QtHelp'],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WTDashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
