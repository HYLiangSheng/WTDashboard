"""全局样式表与主题定义。"""

DARK_THEME_QSS = """
/* ========== 全局 ========== */
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}

/* ========== 分组框 ========== */
QGroupBox {
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: #7ec8e3;
    background-color: #16213e;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ========== 标签 ========== */
QLabel {
    background: transparent;
    border: none;
}

/* ========== 滚动条 ========== */
QScrollBar:vertical {
    border: none;
    background: #1a1a2e;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3a3a5c;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    border: none;
    background: #1a1a2e;
    height: 8px;
}

QScrollBar::handle:horizontal {
    background: #3a3a5c;
    border-radius: 4px;
    min-width: 20px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ========== 状态栏 ========== */
QStatusBar {
    background: #0f3460;
    color: #7ec8e3;
    border-top: 1px solid #3a3a5c;
}

QStatusBar::item {
    border: none;
}
"""

# 颜色常量
COLOR_FRIENDLY = (24, 90, 255)       # #185AFF 蓝
COLOR_ENEMY = (250, 50, 0)           # #fa3200 红
COLOR_SQUAD = (36, 217, 33)          # #24D921 绿
COLOR_ENEMY_GROUND = (240, 30, 0)    # #f01E00 红
COLOR_BACKGROUND = "#1a1a2e"
COLOR_PANEL_BG = "#16213e"
COLOR_BORDER = "#3a3a5c"
COLOR_ACCENT = "#7ec8e3"
COLOR_WARNING = "#f0a500"
COLOR_DANGER = "#e94560"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_DIM = "#8888aa"
