"""态势感知面板 —— 按机型分类显示追踪单位的实时状态。"""

import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QHeaderView, QPushButton,
)

from .unit_tracker import UnitTracker, TrackedUnit
from .styles import COLOR_BACKGROUND, COLOR_BORDER, COLOR_ACCENT
from .i18n import _

# 类型分组（按显示顺序）
TYPE_GROUPS = [
    ("Fighter",     "战斗机",   "空"),
    ("Assault",     "攻击机",   "空"),
    ("Bomber",      "轰炸机",   "空"),
    ("LightTank",   "轻型坦克", "陆"),
    ("MediumTank",  "中型坦克", "陆"),
    ("HeavyTank",   "重型坦克", "陆"),
    ("TankDestroyer","坦歼",    "陆"),
    ("Tracked",     "履带车辆", "陆"),
    ("Wheeled",     "轮式车辆", "陆"),
    ("SPAA",        "自行防空", "陆"),
    ("Airdefence",  "防空",     "陆"),
    ("SAM",         "防空导弹", "陆"),
    ("MLRS",        "火箭炮",   "陆"),
    ("TBMLauncher", "战术导弹", "陆"),
    ("Radar",       "雷达",     "陆"),
    ("Destroyer",   "驱逐舰",   "海"),
    ("MissileDestroyer","导弹驱逐","海"),
    ("LightCruiser","轻巡洋舰", "海"),
    ("MissileLightCruiser","导弹轻巡","海"),
    ("HeavyCruiser","重巡洋舰", "海"),
    ("MissileHeavyCruiser","导弹重巡","海"),
    ("BattleShip",  "战列舰",   "海"),
    ("MissileBattleship","导弹战列","海"),
    ("Frigate",     "护卫舰",   "海"),
    ("MissileFrigate","导弹护卫","海"),
    ("Corvette",    "护卫艇",   "海"),
    ("MissileCorvette","导弹护卫艇","海"),
    ("Boat",        "小艇",     "海"),
    ("MissileBoat", "导弹艇",   "海"),
    ("AircraftCarrier","航母",  "海"),
    ("Submarine",   "潜艇",     "海"),
    ("Ship",        "舰船",     "海"),
]

ABBR = {
    "Fighter":"F","Assault":"A","Bomber":"B",
    "LightTank":"LT","MediumTank":"MT","HeavyTank":"HT",
    "TankDestroyer":"TD","Tracked":"TK","Wheeled":"WH",
    "SPAA":"SP","Airdefence":"AD","SAM":"SA",
    "MLRS":"MR","TBMLauncher":"TB","Radar":"RD",
    "Destroyer":"DD","MissileDestroyer":"MD",
    "LightCruiser":"CL","MissileLightCruiser":"ML",
    "HeavyCruiser":"CA","MissileHeavyCruiser":"MH",
    "BattleShip":"BB","MissileBattleship":"MS",
    "Frigate":"FF","MissileFrigate":"MF",
    "Corvette":"CV","MissileCorvette":"MC",
    "Boat":"BT","MissileBoat":"MB",
    "AircraftCarrier":"AC","Submarine":"SB",
    "Ship":"SH",
}


class SitrepPanel(QWidget):
    """态势面板 — 按机型分组。"""

    COL_TYPE = 0
    COL_SPEED = 1
    COL_STATUS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracker: UnitTracker | None = None
        self._expanded = False
        self._expand_state: dict[str, bool] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 标题行 + 展开/收起按钮
        header = QHBoxLayout()
        title = QLabel(_("战场态势"))
        title.setStyleSheet("color: #7ec8e3; font-weight: bold; font-size: 12px;")
        header.addWidget(title)
        header.addStretch()
        self._expand_btn = QPushButton(_("展开"))
        self._expand_btn.setMinimumWidth(36)
        self._expand_btn.setFixedHeight(20)
        self._expand_btn.setStyleSheet(
            "QPushButton { font-size: 10px; background: #1a2a4a; border: none; "
            "color: #7ec8e3; border-radius: 2px; padding: 0px 4px; }"
            "QPushButton:hover { background: #2a4a6a; }")
        self._expand_btn.clicked.connect(self._toggle_expand_all)
        header.addWidget(self._expand_btn)
        layout.addLayout(header)

        # 友军表
        friendly_label = QLabel(_("友军"))
        friendly_label.setStyleSheet("color: #185AFF; font-weight: bold; font-size: 10px; padding: 2px 4px;")
        layout.addWidget(friendly_label)
        self._friendly_tree = self._create_tree()
        layout.addWidget(self._friendly_tree)

        # 敌军表
        enemy_label = QLabel(_("敌军"))
        enemy_label.setStyleSheet("color: #fa3200; font-weight: bold; font-size: 10px; padding: 2px 4px;")
        layout.addWidget(enemy_label)
        self._enemy_tree = self._create_tree()
        layout.addWidget(self._enemy_tree)

    def _create_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels([_("分组/单位"), _("速度"), _("状态")])
        tree.setAlternatingRowColors(True)
        tree.setIndentation(10)
        tree.itemExpanded.connect(lambda item: self._on_item_toggle(item, True))
        tree.itemCollapsed.connect(lambda item: self._on_item_toggle(item, False))
        tree.setStyleSheet(f"""
            QTreeWidget {{ background: {COLOR_BACKGROUND}; border: 1px solid {COLOR_BORDER};
                border-radius: 4px; color: #e0e0e0; font-size: 10px; alternate-background-color: #1a1a30; }}
            QTreeWidget::item {{ padding: 1px 4px; border-bottom: 1px solid #222244; }}
            QHeaderView::section {{ background: #16213e; color: #7ec8e3; border: none;
                border-bottom: 1px solid {COLOR_BORDER}; padding: 2px 4px; font-size: 9px; font-weight: bold; }}
        """)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 55)
        header.resizeSection(2, 55)
        return tree

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    def set_tracker(self, tracker: UnitTracker):
        self._tracker = tracker

    def refresh(self):
        if self._tracker is None:
            return
        now = time.time()
        self._populate_tree(self._enemy_tree, True, now)
        self._populate_tree(self._friendly_tree, False, now)
        self._equalize_cols()

    def _toggle_expand_all(self):
        self._expanded = not self._expanded
        self._expand_btn.setText(_("收起") if self._expanded else _("展开"))
        for k in self._expand_state:
            self._expand_state[k] = self._expanded
        for tree in (self._enemy_tree, self._friendly_tree):
            for i in range(tree.topLevelItemCount()):
                tree.topLevelItem(i).setExpanded(self._expanded)

    def _retranslate(self):
        """语言切换时刷新所有 UI 文字。"""
        self._expand_btn.setText(_("收起") if self._expanded else _("展开"))
        self._expand_btn.setMinimumWidth(self._expand_btn.sizeHint().width() + 8)
        self._friendly_tree.setHeaderLabels([_("分组/单位"), _("速度"), _("状态")])
        self._enemy_tree.setHeaderLabels([_("分组/单位"), _("速度"), _("状态")])
        # 强制刷新树内容（重新翻译 TYPE_GROUPS 标签）
        self.refresh()

    def _equalize_cols(self):
        """速度列和状态列自适应等宽：先按内容展开，取较宽者，固定。"""
        max_w = 0
        for tree in (self._enemy_tree, self._friendly_tree):
            tree.header().resizeSections(QHeaderView.ResizeMode.ResizeToContents)
            w1 = tree.header().sectionSize(1)
            w2 = tree.header().sectionSize(2)
            max_w = max(max_w, w1, w2)
        for tree in (self._enemy_tree, self._friendly_tree):
            tree.header().resizeSection(1, max_w)
            tree.header().resizeSection(2, max_w)

    def _on_item_toggle(self, item: QTreeWidgetItem, expanded: bool):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self._expand_state[key] = expanded

    def _populate_tree(self, tree: QTreeWidget, is_enemy: bool, now: float):
        units = self._tracker.active_enemies if is_enemy else self._tracker.active_friendlies
        lost = self._tracker.lost_enemies if is_enemy else self._tracker.lost_friendlies

        groups: dict[str, list[TrackedUnit]] = {}
        for u in units:
            groups.setdefault(u.icon, []).append(u)
        for u in lost:
            groups.setdefault(u.icon, []).append(u)

        # 使用持久化的展开状态
        tree.setUpdatesEnabled(False)
        tree.clear()
        for icon_key, label, emoji in TYPE_GROUPS:
            if icon_key in groups:
                group_item = self._add_group(tree, emoji, label, groups.pop(icon_key), now, icon_key)
                group_item.setExpanded(self._expand_state.get(icon_key, False))
        for icon_key, group in groups.items():
            group_item = self._add_group(tree, "", icon_key, group, now)
            group_item.setExpanded(self._expand_state.get(icon_key, False))
        tree.setUpdatesEnabled(True)

    def _add_group(self, tree: QTreeWidget, emoji: str, label: str,
                   group: list[TrackedUnit], now: float,
                   icon_key: str = "") -> QTreeWidgetItem:
        active_n = sum(1 for u in group if u.is_active)
        lost_n = len(group) - active_n
        parts = [f"[{emoji}] {_(label)}", str(len(group))]
        if lost_n > 0:
            parts.append(f"({lost_n}{_('消失')})")
        parent = QTreeWidgetItem([f"{'  '.join(parts)}"])
        parent.setData(0, Qt.ItemDataRole.UserRole, icon_key or label)
        parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
        parent.setForeground(0, QBrush(QColor(COLOR_ACCENT)))
        font = parent.font(0)
        font.setBold(True)
        parent.setFont(0, font)
        tree.addTopLevelItem(parent)

        sorted_units = sorted(group, key=lambda u: (not u.is_active, -u.last_seen))
        for idx, unit in enumerate(sorted_units, 1):
            parent.addChild(self._make_item(unit, now, label, idx))
        return parent

    def _make_item(self, unit: TrackedUnit, now: float,
                   label: str = "", idx: int = 0) -> QTreeWidgetItem:
        code = ABBR.get(unit.icon, unit.icon[:2].upper())
        name = f"{code}{idx:02d}" if code else ""

        if unit.speed_kmh_est > 10:
            spd = f"{unit.speed_kmh_est:.0f} km/h"
        else:
            spd = "--"

        if unit.is_active:
            status = "●"
            sc = QColor("#24D921")
        else:
            elapsed = now - unit.last_seen
            status = f"○ {elapsed:.0f}s" if elapsed < 60 else f"○ {elapsed/60:.1f}min"
            sc = QColor("#8888aa")

        item = QTreeWidgetItem([name, spd, status])
        item.setForeground(2, QBrush(sc))
        return item
