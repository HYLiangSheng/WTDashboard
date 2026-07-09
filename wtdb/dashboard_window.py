"""主 Dashboard 窗口 —— 组合地图、仪表、HUD 面板。"""

import sys
import time
import re
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QFont, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QStatusBar, QLabel, QMenuBar, QMenu, QApplication, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox,
    QPushButton, QScrollArea, QToolButton, QRadioButton, QButtonGroup,
)

VERSION = "1.0.1"

from .api_client import FetchWorker, GameState
from .map_widget import MapWidget
from .hud_feed import HudFeed
from .unit_tracker import UnitTracker
from .sitrep_panel import SitrepPanel
from .styles import DARK_THEME_QSS
from .i18n import _, set_locale, get_locale, available_locales, locale_changed
from .i18n import _LOCALE_SELF_NAME
from . import config


# ---------------------------------------------------------------------------
# 连接设置对话框
# ---------------------------------------------------------------------------

class ConnectDialog(QDialog):
    """连接设置对话框 —— 支持本地/远程模式切换。"""

    def __init__(self, current_host: str = "localhost", current_port: int = 8111,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("dialog.connect.title"))
        self.setMinimumWidth(420)
        # 继承全局字体，不硬编码字号
        qss = re.sub(r'font-size:\s*\d+px;?', '', DARK_THEME_QSS)
        self.setStyleSheet(qss)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 16, 20, 16)

        # 说明文字
        hint = QLabel(
            _("dialog.connect.hint")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaaacc; margin-bottom: 4px;")
        root.addWidget(hint)

        # 本地 / 远程 单选
        self._local_radio = QRadioButton(_("dialog.connect.local"))
        self._remote_radio = QRadioButton(_("dialog.connect.remote"))
        self._local_radio.setChecked(current_host in ("localhost", "127.0.0.1"))
        self._remote_radio.setChecked(current_host not in ("localhost", "127.0.0.1"))
        group = QButtonGroup(self)
        group.addButton(self._local_radio)
        group.addButton(self._remote_radio)

        radio_style = "color: #7ec8e3; font-size: 11px; spacing: 6px;"
        self._local_radio.setStyleSheet(radio_style)
        self._remote_radio.setStyleSheet(radio_style)
        self._local_radio.toggled.connect(self._on_mode_changed)

        root.addWidget(self._local_radio)
        root.addWidget(self._remote_radio)

        # 主机地址
        host_layout = QFormLayout()
        host_layout.setSpacing(8)
        self._host_edit = QLineEdit(current_host)
        self._host_edit.setPlaceholderText(_("dialog.connect.placeholder"))
        self._host_edit.setMinimumHeight(28)
        host_layout.addRow(_("dialog.connect.host"), self._host_edit)

        # 端口
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(current_port)
        self._port_spin.setMinimumHeight(28)
        self._port_spin.setToolTip(_("dialog.connect.port_tooltip"))
        host_layout.addRow(_("dialog.connect.port"), self._port_spin)
        root.addLayout(host_layout)

        self._on_mode_changed(self._local_radio.isChecked())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_mode_changed(self, is_local: bool):
        """本地模式锁定 localhost，远程模式允许自由输入。"""
        if is_local:
            self._host_edit.setText("localhost")
            self._host_edit.setReadOnly(True)
            self._host_edit.setStyleSheet("color: #666; background: #111;")
        else:
            self._host_edit.setReadOnly(False)
            self._host_edit.setStyleSheet("")

    @property
    def host(self) -> str:
        return self._host_edit.text().strip() or "localhost"

    @property
    def port(self) -> int:
        return self._port_spin.value()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class DashboardWindow(QMainWindow):
    """War Thunder Dashboard 主窗口。"""

    REFRESH_INTERVAL_MS = 100  # 10 Hz

    def __init__(self, host: str = "localhost", port: int = 8111,
                 refresh_ms: int = 100, remote: bool = False):
        super().__init__()
        self._current_host = host
        self._current_port = port
        self._refresh_ms = refresh_ms

        # 加载配置（远程模式不覆盖命令行指定的 host/port）
        self._cfg = config.load()
        if not remote:
            self._current_host = self._cfg.get("host", host)
            self._current_port = self._cfg.get("port", port)

        # 初始化语言
        saved_locale = self._cfg.get("locale", "zh-CN")
        if saved_locale in ("zh-CN", "en-US"):
            set_locale(saved_locale)

        self.setWindowTitle("War Thunder Dashboard")
        self._set_app_icon()
        self.setMinimumSize(1100, 650)
        self.resize(1400, 800)

        # 恢复窗口位置
        geo = self._cfg.get("window_geometry", "")
        if geo:
            parts = geo.split(",")
            if len(parts) == 4:
                try:
                    self.setGeometry(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
                except ValueError:
                    pass

        # ---------- 中央控件 ----------
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 4, 4, 4)
        root_layout.setSpacing(0)

        # 左侧边栏菜单
        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        # 左右分栏（信息面板 + 筛选条 + 地图）
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：态势 + HUD
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 0, 4, 0)
        left_layout.setSpacing(4)

        left_splitter = QSplitter(Qt.Orientation.Vertical)

        self._sitrep_panel = SitrepPanel()
        left_splitter.addWidget(self._sitrep_panel)

        self._hud_feed = HudFeed()
        left_splitter.addWidget(self._hud_feed)

        left_splitter.setSizes([400, 150])
        left_layout.addWidget(left_splitter)

        splitter.addWidget(left_panel)

        # 地图 + 筛选条
        map_area = QWidget()
        map_layout = QHBoxLayout(map_area)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)

        # 筛选条（地图左侧）
        filter_bar = self._build_filter_bar()
        map_layout.addWidget(filter_bar)

        self._map_widget = MapWidget()
        map_layout.addWidget(self._map_widget, 1)

        splitter.addWidget(map_area)
        splitter.setSizes([340, 900])
        root_layout.addWidget(splitter, 1)

        # ---------- 状态栏 ----------
        self._status_label = QLabel(_("status.connecting").format(self._current_host, self._current_port))
        self._status_label.setStyleSheet("color: #7ec8e3; padding: 2px 8px;")
        self.statusBar().addWidget(self._status_label)

        # 地址标签（可点击）
        self._addr_label = QLabel(f"[{self._current_host}:{self._current_port}]")
        self._addr_label.setStyleSheet(
            "color: #7ec8e3; padding: 2px 8px; "
            "border: 1px solid #3a3a5c; border-radius: 3px;"
        )
        self._addr_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._addr_label.mousePressEvent = lambda e: self._show_connect_dialog()
        self._addr_label.setToolTip(_("tooltip.addr"))
        self.statusBar().addPermanentWidget(self._addr_label)

        self._fps_label = QLabel("")
        self._fps_label.setStyleSheet("color: #8888aa; padding: 2px 8px;")
        self.statusBar().addPermanentWidget(self._fps_label)

        # ---------- 菜单（侧边栏代替） ----------
        self.menuBar().setVisible(False)
        # ---------- 数据拉取 ----------
        self._worker: FetchWorker | None = None
        self._timer = QTimer()
        self._frame_count = 0
        self._fps_frame_count = 0
        self._last_fps_time = time.time()
        self._current_hz = 0.0
        self._last_data_version = -1  # 追踪实际数据更新
        self._tracker = UnitTracker()
        self._sitrep_panel.set_tracker(self._tracker)

        # 连接语言切换信号
        locale_changed.connect(self._retranslate)

        self._apply_saved_state()
        self._setup_fetch_thread()

    def _apply_saved_state(self):
        saved_fs = self._cfg.get("font_size", 9)
        current_fs = QApplication.instance().font().pointSize()
        if saved_fs != current_fs and abs(saved_fs - current_fs) > 0:
            self._adjust_zoom(saved_fs - current_fs)

        for item in self._cfg.get("hidden_filters", []):
            if isinstance(item, list) and len(item) == 2:
                self._map_widget._hidden.add(tuple(item))
        self._sync_filter_buttons()

        for k, v in self._cfg.get("expand_state", {}).items():
            self._sitrep_panel._expand_state[k] = v

        if self._cfg.get("always_on_top"):
            self._toggle_always_on_top(True)

    # ------------------------------------------------------------------
    # 窗口图标
    # ------------------------------------------------------------------

    def _set_app_icon(self):
        """绘制雷达风格窗口图标。"""
        from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = 32, 32
        r = 28
        p.setPen(QPen(QColor("#3a3a5c"), 2))
        p.setBrush(QColor("#1a1a2e"))
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.setPen(QPen(QColor("#3a3a5c"), 1))
        p.drawLine(cx - r, cy, cx + r, cy)
        p.drawLine(cx, cy - r, cx, cy + r)
        from PyQt6.QtGui import QConicalGradient
        grad = QConicalGradient(cx, cy, 45)
        grad.setColorAt(0, QColor(126, 200, 227, 80))
        grad.setColorAt(0.15, QColor(126, 200, 227, 20))
        grad.setColorAt(1, QColor(126, 200, 227, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPie(cx - r + 2, cy - r + 2, (r - 2) * 2, (r - 2) * 2, 0, 90 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#7ec8e3"))
        p.drawEllipse(cx - 3, cy - 3, 6, 6)
        p.setPen(QPen(QColor("#e94560"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        p.save()
        p.translate(cx, cy - 8)
        tri = QPolygonF([QPointF(0, -6), QPointF(-4, 4), QPointF(4, 4)])
        p.drawPolygon(tri)
        p.restore()
        p.end()
        self.setWindowIcon(QIcon(pm))

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(80)
        sidebar.setStyleSheet("""
            QWidget { background: #0f1a2e; border-right: 1px solid #3a3a5c; }
            QPushButton {
                background: transparent; border: none; color: #7ec8e3;
                font-size: 16px; padding: 8px 4px; border-radius: 4px;
            }
            QPushButton:hover { background: #1a2a4a; }
            QPushButton:pressed { background: #2a3a5a; }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)

        self._sidebar_buttons: list[tuple[QPushButton, str, str]] = []

        def btn(label_key: str, tip_key: str, slot):
            b = QPushButton(_(label_key))
            b.setToolTip(_(tip_key))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton { background: transparent; border: none; color: #7ec8e3;
                    font-size: 11px; padding: 6px 2px; border-radius: 4px; }
                QPushButton:hover { background: #1a2a4a; }
                QPushButton:pressed { background: #2a3a5a; }
            """)
            b.clicked.connect(slot)
            layout.addWidget(b)
            self._sidebar_buttons.append((b, label_key, tip_key))

        self._lang_btn = QToolButton()
        self._lang_btn.setText("Lang")
        self._lang_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_btn.setStyleSheet("""
            QToolButton { background: transparent; border: 1px solid #3a3a5c;
                color: #7ec8e3; font-size: 8px; padding: 2px 6px; border-radius: 3px; }
            QToolButton:hover { background: #1a2a4a; }
            QToolButton::menu-indicator { image: none; width: 0px; }
        """)
        self._lang_menu = QMenu(self._lang_btn)
        self._lang_menu.setStyleSheet("""
            QMenu { background: #0f1a2e; color: #7ec8e3; border: 1px solid #3a3a5c;
                font-size: 10px; padding: 2px; }
            QMenu::item { padding: 4px 16px; }
            QMenu::item:selected { background: #2a4a6a; }
        """)
        self._populate_language_menu()
        self._lang_btn.setMenu(self._lang_menu)
        layout.addWidget(self._lang_btn)

        layout.addSpacing(6)

        btn("sidebar.connect", "tooltip.connect", self._show_connect_dialog)
        btn("sidebar.pin", "tooltip.pin", lambda: self._toggle_always_on_top(True))
        btn("sidebar.fullscreen", "tooltip.fullscreen", self._toggle_fullscreen)

        zoom_row = QWidget()
        zoom_row.setStyleSheet("background: transparent;")
        zl = QHBoxLayout(zoom_row)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.setSpacing(1)

        def _zbtn(label_key: str, tip_key: str, slot):
            zb = QPushButton(_(label_key))
            zb.setToolTip(_(tip_key))
            zb.setCursor(Qt.CursorShape.PointingHandCursor)
            zb.setStyleSheet("""
                QPushButton { background: transparent; border: none; color: #7ec8e3;
                    font-size: 10px; padding: 4px 1px; border-radius: 3px; }
                QPushButton:hover { background: #1a2a4a; }
                QPushButton:pressed { background: #2a3a5a; }
            """)
            zb.clicked.connect(slot)
            zl.addWidget(zb)
            self._sidebar_buttons.append((zb, label_key, tip_key))

        _zbtn("sidebar.zoom_out", "tooltip.zoom_out", self._zoom_out)
        _zbtn("sidebar.zoom_in", "tooltip.zoom_in", self._zoom_in)
        layout.addWidget(zoom_row)

        layout.addStretch()
        btn("sidebar.about", "sidebar.about", self._show_about)
        btn("sidebar.exit", "tooltip.exit", self.close)

        return sidebar

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("filter_bar")
        bar.setMinimumWidth(200)
        bar.setStyleSheet("background: #111a2e; border: 1px solid #3a3a5c; border-radius: 4px;")

        self._filter_buttons: list[QPushButton] = []
        self._filter_button_keys: dict[int, tuple[str, str]] = {}
        self._filter_label_keys: dict[int, str] = {}   # button id → Chinese label key
        self._filter_section_labels: list[tuple[QLabel, str, str]] = []  # (label, title_key, color)
        self._known_icons: set[str] = set()
        self._master_buttons: list[QPushButton] = []
        self._master_label_keys: dict[int, str] = {}   # button id → Chinese label key

        types = [
            ("filter.air.fighter", "Fighter"), ("filter.air.attacker", "Assault"), ("filter.air.bomber", "Bomber"),
            ("filter.air.atk_heli", "AttackHelicopter"), ("filter.air.heli", "UtilityHelicopter"),
            ("filter.ground.light_tank", "LightTank"), ("filter.ground.med_tank", "MediumTank"), ("filter.ground.heavy_tank", "HeavyTank"),
            ("filter.ground.td", "TankDestroyer"), ("filter.ground.spaa", "SPAA"), ("filter.ground.sam", "SAM"),
            ("filter.ground.facility", "__facility__"),
            ("filter.sea.destroyer", "Destroyer"), ("filter.sea.frigate", "Frigate"),
            ("filter.sea.light_cruiser", "LightCruiser"), ("filter.sea.heavy_cruiser", "HeavyCruiser"),
            ("filter.sea.battlecruiser", "Battlecruiser"), ("filter.sea.battleship", "BattleShip"),
            ("filter.sea.submarine", "Submarine"), ("filter.sea.ship", "Ship"), ("filter.sea.boat", "Boat"),
        ]
        air_keys = ["Fighter", "Assault", "Bomber", "AttackHelicopter", "UtilityHelicopter"]
        land_keys = ["LightTank", "MediumTank", "HeavyTank", "TankDestroyer", "SPAA", "SAM",
                     "__facility__"]
        sea_keys = ["Destroyer", "Frigate", "LightCruiser", "HeavyCruiser", "Battlecruiser",
                    "BattleShip", "Submarine", "Ship", "Boat"]

        # 两列：左友军、右敌军
        columns = QHBoxLayout(bar)
        columns.setContentsMargins(2, 4, 2, 4)
        columns.setSpacing(2)

        def build_side(faction: str, title_key: str, title_color: str) -> QWidget:
            side = QWidget()
            side.setStyleSheet("background: transparent;")
            lay = QVBoxLayout(side)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(1)

            title = QLabel(_(title_key))
            title.setStyleSheet(f"color: {title_color}; font-weight: bold; font-size: 10px; padding: 2px 2px 4px;")
            lay.addWidget(title)
            self._filter_section_labels.append((title, title_key, title_color))

            # 主开关行
            mr = QHBoxLayout()
            mr.setSpacing(1)
            for label_key, keys in [("filter.master_all", air_keys+land_keys+sea_keys),
                                    ("filter.master_air", air_keys), ("filter.master_ground", land_keys), ("filter.master_sea", sea_keys)]:
                b = QPushButton(_(label_key))
                b.setFixedSize(26, 18)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(
                    "QPushButton { font-size: 9px; background: #1a2a4a; border: none; "
                    "color: #7ec8e3; border-radius: 2px; } "
                    "QPushButton:hover { background: #2a4a6a; }")
                b.clicked.connect(lambda checked, f=faction, k=keys: self._toggle_master(f, k))
                mr.addWidget(b)
                self._master_buttons.append(b)
                self._master_label_keys[id(b)] = label_key
            mr.addStretch()
            lay.addLayout(mr)

            # 类型按钮
            for label_key, key in types:
                b = QPushButton(_(label_key))
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setCheckable(True)
                b.setChecked(True)
                b.setFixedHeight(18)
                b.setStyleSheet("""
                    QPushButton { background: transparent; border: none; color: #7ec8e3;
                        font-size: 9px; text-align: left; padding-left: 4px; border-radius: 2px; }
                    QPushButton:hover { background: #1a2a4a; }
                    QPushButton:checked { background: #2a4a6a; color: #fff; }
                    QPushButton:!checked { background: transparent; color: #444; }
                """)
                b.clicked.connect(lambda checked, f=faction, k=key: self._on_filter_click(f, k))
                lay.addWidget(b)
                self._filter_buttons.append(b)
                self._filter_button_keys[id(b)] = (faction, key)
                self._filter_label_keys[id(b)] = label_key
                self._known_icons.add(key)

            lay.addStretch()
            return side

        columns.addWidget(build_side("friendly", "filter.friendly", "#185AFF"))
        columns.addWidget(build_side("enemy", "filter.enemy", "#fa3200"))

        # 存储友军/敌军标签引用用于 retranslate
        # (这些在 build_side 内部创建，通过 findChildren 查找)

        # 保存引用，用于动态添加新类型
        self._filter_layout = None  # 不再使用单一 layout
        self._ftoggle_fn = None

        return bar

    def _ensure_icons_covered(self):
        """扫描追踪器中的单位，为未覆盖的图标类型动态添加筛选按钮。"""
        # 已有完整静态列表，此方法保留作为安全网但通常无需操作
        pass

    def _build_map_labels(self) -> list:
        abbr = {
            "Fighter":"F","Assault":"A","Bomber":"B",
            "AttackHelicopter":"AH","UtilityHelicopter":"UH",
            "LightTank":"LT","MediumTank":"MT","HeavyTank":"HT",
            "TankDestroyer":"TD",
            "SPAA":"SP","SAM":"SA",
            "Destroyer":"DD",
            "LightCruiser":"CL","HeavyCruiser":"CA",
            "Battlecruiser":"BC","BattleShip":"BB",
            "Frigate":"FF",
            "Submarine":"SB","Ship":"SH","Boat":"BT",
            "__facility__":"G",
        }
        hidden = self._map_widget._hidden

        def faction_of(u) -> str:
            """根据颜色判断阵营（与 map_widget._draw_objects 一致）。"""
            r, g, b = u.color_rgb
            if b > 200 and r < 100:
                return "friendly"
            elif g > 200:
                return "squad"
            elif r > 200:
                return "enemy"
            return "friendly"

        labels = []
        # 敌军（先活跃后消失，序号连续）
        counters_e: dict[str, int] = {}
        for u in self._tracker.active_enemies:
            if ("enemy", u.icon) not in hidden and not (
                u.icon not in abbr and ("enemy", "__facility__") in hidden):
                code = abbr.get(u.icon, "G")
                counters_e[code] = counters_e.get(code, 0) + 1
                n = counters_e[code]
                spd = f" {u.speed_kmh_est:.0f}" if u.speed_kmh_est > 10 else ""
                c = u.color_rgb
                labels.append((u.last_x, u.last_y, f"{code}{n:02d}{spd}", (*c, 220)))
        for u in self._tracker.lost_enemies:
            if ("enemy", u.icon) not in hidden and not (
                u.icon not in abbr and ("enemy", "__facility__") in hidden):
                code = abbr.get(u.icon, "G")
                counters_e[code] = counters_e.get(code, 0) + 1
                n = counters_e[code]
                elapsed = time.time() - u.last_seen
                c = u.color_rgb
                labels.append((u.last_x, u.last_y,
                              f"{code}{n:02d} {elapsed:.0f}s", (*c, 120)))
        # 友军（含小队，按单位实际阵营匹配筛选）
        counters_f: dict[str, int] = {}
        for u in self._tracker.active_friendlies:
            f = faction_of(u)
            check_f = "friendly" if f == "squad" else f
            if (check_f, u.icon) in hidden or (
                u.icon not in abbr and (check_f, "__facility__") in hidden):
                continue
            code = abbr.get(u.icon, "G")
            counters_f[code] = counters_f.get(code, 0) + 1
            n = counters_f[code]
            spd = f" {u.speed_kmh_est:.0f}" if u.speed_kmh_est > 10 else ""
            c = u.color_rgb
            labels.append((u.last_x, u.last_y, f"{code}{n:02d}{spd}", (*c, 220)))
        for u in self._tracker.lost_friendlies:
            f = faction_of(u)
            check_f = "friendly" if f == "squad" else f
            if (check_f, u.icon) in hidden or (
                u.icon not in abbr and (check_f, "__facility__") in hidden):
                continue
            code = abbr.get(u.icon, "G")
            counters_f[code] = counters_f.get(code, 0) + 1
            n = counters_f[code]
            elapsed = time.time() - u.last_seen
            c = u.color_rgb
            labels.append((u.last_x, u.last_y,
                          f"{code}{n:02d} {elapsed:.0f}s", (*c, 120)))
        return labels

    def _on_filter_click(self, faction: str, icon: str):
        """单个筛选按钮点击：只改数据，UI 由 _sync 统一刷新。"""
        self._map_widget.toggle_filter(faction, icon)
        self._sync_filter_buttons()

    def _sync_filter_buttons(self):
        """根据 _hidden 统一刷新所有筛选按钮的选中状态。"""
        m = self._map_widget
        for b in self._filter_buttons:
            key = self._filter_button_keys.get(id(b))
            if key:
                faction, icon = key
                b.blockSignals(True)
                b.setChecked((faction, icon) not in m._hidden)
                b.blockSignals(False)

    def _toggle_master(self, faction: str, keys: list[str]):
        m = self._map_widget
        all_hidden = all((faction, k) in m._hidden for k in keys)
        for k in keys:
            if all_hidden:
                m._hidden.discard((faction, k))
            else:
                m._hidden.add((faction, k))
        self._sync_filter_buttons()
        m.update()

    def _zoom_in(self):
        self._adjust_zoom(+1)

    def _zoom_out(self):
        self._adjust_zoom(-1)

    def _adjust_zoom(self, delta: int):
        app = QApplication.instance()
        font = app.font()
        new_size = font.pointSize() + delta
        if new_size < 6:
            return
        font.setPointSize(new_size)
        app.setFont(font)
        # 全局 QSS
        base = DARK_THEME_QSS
        base = re.sub(r'\n?\* \{ font-size: \d+px !important; \}\n?', '', base)
        app.setStyleSheet(base + f"\n* {{ font-size: {new_size}px !important; }}")
        # 逐个控件
        for widget in self.findChildren(QWidget):
            ss = widget.styleSheet()
            if ss and 'font-size' in ss:
                widget.setStyleSheet(
                    re.sub(r'font-size:\s*\d+px', f'font-size: {new_size}px', ss)
                )
        # 缩放筛选栏
        bh = max(16, new_size + 8)
        for b in getattr(self, '_filter_buttons', []):
            b.setFixedHeight(bh)
        self._resize_filter_master_buttons(new_size)
        self._resize_filter_bar()

        # 缩放左侧边栏 —— 取最宽按钮的实际渲染宽度
        sidebar = self.findChild(QWidget, "sidebar")
        if sidebar and self._sidebar_buttons:
            max_w = self._lang_btn.sizeHint().width() if hasattr(self, '_lang_btn') else 40
            for b, _, _ in self._sidebar_buttons:
                max_w = max(max_w, b.sizeHint().width())
            sidebar.setFixedWidth(max_w + 12)
        # 语言按钮
        lang_fs = max(6, new_size - 1)
        if hasattr(self, '_lang_btn'):
            self._lang_btn.setStyleSheet(
                self._lang_btn.styleSheet().replace(
                    re.search(r'font-size:\s*\d+px', self._lang_btn.styleSheet()).group(),
                    f'font-size: {lang_fs}px'))
            self._lang_btn.setMinimumHeight(max(16, new_size + 8))
        # 侧边栏按钮
        sb_pad = max(2, new_size // 3)
        for b, _, _ in self._sidebar_buttons:
            ss = b.styleSheet()
            b.setStyleSheet(
                re.sub(r'padding:\s*\d+px \d+px', f'padding: {sb_pad // 2}px 2px', ss))
            b.setMinimumHeight(max(18, new_size + 10))

        # 态势面板展开/收起按钮
        eb = self._sitrep_panel._expand_btn
        eb.setFixedHeight(max(16, new_size + 8))
        eb.setMinimumWidth(eb.sizeHint().width() + 8)

    def _resize_filter_master_buttons(self, font_size: int):
        """根据主开关按钮的实际渲染宽度调整大小。"""
        mh = max(16, font_size + 5)
        for b in getattr(self, '_master_buttons', []):
            b.setMinimumWidth(b.sizeHint().width() + 4)
            b.setFixedHeight(mh)

    def _resize_filter_bar(self):
        """根据类型按钮实际渲染宽度调整筛选栏最小宽度。"""
        max_w = 80
        for b in getattr(self, '_filter_buttons', []):
            max_w = max(max_w, b.sizeHint().width() + 4)
        fb = self.findChild(QWidget, "filter_bar")
        if fb:
            fb.setMinimumWidth(max_w * 2 + 4)  # 左友军 + 右敌军
            fb.updateGeometry()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    # 语言切换
    # ------------------------------------------------------------------

    def _populate_language_menu(self):
        """填充语言菜单。条目名称用各自语言显示。"""
        self._lang_menu.clear()
        for code, _name in available_locales():
            display = _LOCALE_SELF_NAME.get(code, code)
            action = self._lang_menu.addAction(display)
            action.setData(code)
            action.triggered.connect(self._on_language_changed)

    def _on_language_changed(self):
        """用户从菜单中选择新语言（延迟执行以避开菜单事件处理）。"""
        action = self.sender()
        if action and isinstance(action, QAction):
            code = action.data()
            if code and code != get_locale():
                # 延迟到下一个事件循环，避免在 QMenu 事件处理中触发布局重建
                QTimer.singleShot(0, lambda c=code: self._apply_locale(c))

    def _apply_locale(self, code: str):
        """实际执行语言切换（已离开菜单事件上下文）。"""
        self._cfg["locale"] = code
        config.save(self._cfg)
        set_locale(code)

    def _retranslate(self, _locale: str = ""):
        """重新翻译所有 UI 文字（由 locale_changed 信号触发）。"""
        if getattr(self, '_retranslating', False):
            return
        self._retranslating = True
        try:
            # 侧边栏按钮
            for b, lk, tk in self._sidebar_buttons:
                b.setText(_(lk))
                b.setToolTip(_(tk))
            # 侧边栏宽度重算（英文可能比中文宽）
            sidebar = self.findChild(QWidget, "sidebar")
            if sidebar and self._sidebar_buttons:
                max_w = self._lang_btn.sizeHint().width() if hasattr(self, '_lang_btn') else 40
                for b, _lk, _tk in self._sidebar_buttons:
                    max_w = max(max_w, b.sizeHint().width())
                sidebar.setFixedWidth(max_w + 12)
            # 过滤栏标题
            for lbl, lk, color in self._filter_section_labels:
                lbl.setText(_(lk))
            # 过滤栏类型按钮
            for b in self._filter_buttons:
                lk = self._filter_label_keys.get(id(b))
                if lk:
                    b.setText(_(lk))
            # 过滤栏主开关按钮
            for b in self._master_buttons:
                lk = self._master_label_keys.get(id(b))
                if lk:
                    b.setText(_(lk))
            # 过滤栏自适应（英文文字宽度不同）
            app_font = QApplication.instance().font().pointSize()
            self._resize_filter_master_buttons(app_font)
            self._resize_filter_bar()
            # 状态栏
            if self._worker is not None:
                self._status_label.setText(_("status.connected"))
            self._addr_label.setToolTip(_("tooltip.addr"))
            # 子面板
            self._sitrep_panel._retranslate()
            self._map_widget._retranslate()
            self._hud_feed._retranslate()
            # 重绘地图（占位文字可能变化）
            self._map_widget.update()
        finally:
            self._retranslating = False

    def _toggle_always_on_top(self, checked: bool):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()  # 重新 show 使标志生效

    def _show_about(self):
        """显示关于对话框（含版本号、项目链接、社区邀请）。"""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl

        text = _(
            "dialog.about.text"
        ).format(version=VERSION)

        msg = QMessageBox(self)
        msg.setWindowTitle(_("dialog.about.title"))
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(text)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setMinimumWidth(420)
        msg.exec()

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def _show_connect_dialog(self):
        dlg = ConnectDialog(self._current_host, self._current_port, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_host = dlg.host
            new_port = dlg.port
            if new_host != self._current_host or new_port != self._current_port:
                self._reconnect(new_host, new_port)

    def _setup_fetch_thread(self):
        """创建 worker（自带 daemon 轮询线程）+ 定时器（只读缓存）。"""
        self._worker = FetchWorker()
        self._worker.BASE_URL = f"http://{self._current_host}:{self._current_port}"

        self._timer.timeout.connect(self._worker.fetch_all)
        self._timer.setInterval(self._refresh_ms)

        self._worker.data_ready.connect(self._on_data_ready)
        self._worker.connection_error.connect(self._on_connection_error)
        self._worker.connection_restored.connect(self._on_connection_restored)

        self._timer.start()

    def _teardown_fetch_thread(self):
        """停止 worker 和定时器。"""
        self._timer.stop()
        self._timer.timeout.disconnect()

        if self._worker is not None:
            try:
                self._worker.data_ready.disconnect()
                self._worker.connection_error.disconnect()
                self._worker.connection_restored.disconnect()
            except TypeError:
                pass
            if hasattr(self._worker, 'stop'):
                self._worker.stop()

        self._worker = None
        self._map_widget.clear()
        self._frame_count = 0

    def _reconnect(self, host: str, port: int):
        """断开当前连接，重新连接到新的主机。"""
        self._teardown_fetch_thread()

        self._current_host = host
        self._current_port = port
        self._addr_label.setText(f"🖥 {host}:{port}")
        self._status_label.setText(_("status.connecting").format(host, port))
        self._status_label.setStyleSheet("color: #7ec8e3; padding: 2px 8px;")

        self._setup_fetch_thread()

    # ------------------------------------------------------------------
    # 数据拉取
    # ------------------------------------------------------------------

    def _on_data_ready(self, state: GameState):
        """收到新数据时更新所有面板。"""
        self._frame_count += 1
        # 仅在新数据时更新 Hz（基于缓存版本号）
        ver = getattr(self._worker, '_cache_version', 0)
        if ver != self._last_data_version:
            self._last_data_version = ver
            self._fps_frame_count += 1
        if self._frame_count % 2 == 0:
            self._map_widget.update_state(state)
        else:
            self._map_widget._objects = state.map_objects
            self._map_widget._player = state.player_object()

        self._hud_feed.update_state(state)

        # 追踪器每帧更新，态势面板每 3 帧刷新 UI
        self._tracker.update(state.map_objects, state.map_info)
        if self._frame_count % 3 == 0:
            self._ensure_icons_covered()  # 动态发现新图标类型
            self._sitrep_panel.refresh()
            self._map_widget.set_lost_enemies(self._tracker.lost_enemies)
            self._map_widget.set_lost_friendlies(self._tracker.lost_friendlies)
            # 构建地图标签（序号+速度）
            labels = self._build_map_labels()
            self._map_widget.set_labels(labels)

        # 状态栏（精简）
        self._status_label.setText(_("status.connected"))
        now = time.time()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._current_hz = self._fps_frame_count / elapsed
            self._fps_frame_count = 0
            self._last_fps_time = now
        self._fps_label.setText(f"{self._current_hz:.1f} Hz")

    def _on_connection_error(self, msg: str):
        self._status_label.setText(f"⚠ {_(msg)}")
        self._status_label.setStyleSheet("color: #f0a500; padding: 2px 8px;")
        # 重置地图图片标记（可能换了新局）
        if self._worker is not None:
            self._worker.reset_map_image()
        self._map_widget.clear()

    def _on_connection_restored(self):
        self._status_label.setStyleSheet("color: #7ec8e3; padding: 2px 8px;")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._teardown_fetch_thread()
        # 保存 UI 状态
        geo = self.geometry()
        self._cfg["window_geometry"] = f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}"
        self._cfg["host"] = self._current_host
        self._cfg["port"] = self._current_port
        self._cfg["font_size"] = QApplication.instance().font().pointSize()
        self._cfg["hidden_filters"] = [[f, i] for f, i in self._map_widget._hidden]
        self._cfg["expand_state"] = dict(self._sitrep_panel._expand_state)
        self._cfg["always_on_top"] = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        config.save(self._cfg)
        super().closeEvent(event)
