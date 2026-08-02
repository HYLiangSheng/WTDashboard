"""地图显示控件 —— 加载 map.img 并叠加单位位置。"""

import math
import os
import sys
import time
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPixmap, QFont, QPolygonF, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget

from .api_client import GameState, MapObject
from .unit_tracker import TrackedUnit
from .styles import (
    COLOR_FRIENDLY, COLOR_ENEMY, COLOR_SQUAD, COLOR_ENEMY_GROUND,
    COLOR_BACKGROUND, COLOR_BORDER, COLOR_ACCENT,
)
from .i18n import _

ICON_SIZE = 16
ICON_SIZE_PLAYER = 12
# 未知/地面设施类型回退小正方形的缩放比例
UNKNOWN_ICON_SCALE = 0.4
# 跑道基础长宽比（长度 / 宽度）
RUNWAY_ASPECT_RATIO = 10.0
# 跑道整体等比放大倍数（150%）
RUNWAY_SCALE = 1.5
# 跑道最低显示宽度：等比放大后仍不足时继续整体放大到该宽度
RUNWAY_MIN_WIDTH = 2.0
# 无区域坐标的机场类设施（直升机场等）兜底跑道长度
AIRFIELD_FALLBACK_LENGTH = 28

# API 图标名 → Wiki PNG 文件名
_ICON_FILE_MAP = {
    "Fighter":       "F_icon.png",
    "Assault":       "A_icon.png",
    "Bomber":        "B_icon.png",
    "AttackHelicopter": "AH_icon.png",
    "UtilityHelicopter": "UH_icon.png",
    "LightTank":     "LT_icon.png",
    "MediumTank":    "MT_icon.png",
    "HeavyTank":     "HT_icon.png",
    "TankDestroyer": "TD_icon.png",
    "SPAA":          "SPAA_icon.png",
    "SAM":           "SPAA_icon.png",
    "Destroyer":     "DD_icon.png",
    "Frigate":       "FF_icon.png",
    "LightCruiser":  "CL_icon.png",
    "HeavyCruiser":  "CA_icon.png",
    "Battlecruiser": "BC_icon.png",
    "BattleShip":    "BB_icon.png",
    "Submarine":     "SH_icon.png",
    "Ship":          "SH_icon.png",
    "Boat":          "PT_icon.png",
    "AircraftCarrier": "AC_icon.png",
    # 设施
    "__airfield__":   "GC_icon.png",
    "__facility__":   "GC_icon.png",
    "__bp__":         "BP_icon.png",
    "__cp__":         "CP_icon.png",
}

_ICON_CACHE: dict[str, QPixmap] = {}
_ICONS_LOADED = False

def _get_app_dir() -> str:
    """返回应用根目录（EXE 同级或项目根）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(__file__))


def _ensure_icons():
    global _ICONS_LOADED
    if _ICONS_LOADED:
        return
    _ICONS_LOADED = True
    # 优先查找 EXE 同级目录，其次 dev 模式下的 wtdb/game_icons
    icon_dir = os.path.join(_get_app_dir(), "game_icons")
    if not os.path.isdir(icon_dir):
        icon_dir = os.path.join(os.path.dirname(__file__), "game_icons")
    if not os.path.isdir(icon_dir):
        return
    for fname in os.listdir(icon_dir):
        if fname.endswith("_icon.png"):
            path = os.path.join(icon_dir, fname)
            pm = QPixmap(path)
            if not pm.isNull():
                _ICON_CACHE[fname] = pm

def _draw_icon_shape(p: QPainter, icon: str, x: float, y: float, size: int,
                     r: int, g: int, b: int, alpha: int = 255):
    _ensure_icons()
    fname = _ICON_FILE_MAP.get(icon)
    if fname:
        pm = _ICON_CACHE.get(fname)
        if pm and not pm.isNull():
            # 缩放到目标尺寸
            scaled = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            # SourceAtop：在图标非透明区域上叠加颜色，保留 alpha
            result = QPixmap(scaled.size())
            result.fill(Qt.GlobalColor.transparent)
            pp = QPainter(result)
            pp.drawPixmap(0, 0, scaled)
            pp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            pp.fillRect(result.rect(), QColor(r, g, b, alpha))
            pp.end()
            p.drawPixmap(QPointF(x - result.width() / 2, y - result.height() / 2), result)
            return
    # 未知类型/地面设施 → 小正方形（缩小显示）
    s = size * UNKNOWN_ICON_SCALE
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(r, g, b, alpha))
    p.drawRect(QRectF(x - s / 2, y - s / 2, s, s))


def _facility_icon(obj) -> str:
    """根据设施类型返回对应的图标键（也用于筛选）。"""
    name = (obj.icon or "").lower()
    type_name = (obj.obj_type or "").lower()
    bg = (obj.icon_bg or "").lower()
    # 航母在 8111 端口以机场形式返回，无独立标签，统一按机场跑道绘制
    if is_carrier(obj):
        return "__airfield__"
    if _is_airfield_like(obj):
        return "__airfield__"
    # 出生点/重生点优先于 zone 判断，避免 respawn_zone 之类被当成战区
    if ("respawn" in name or "spawn" in name
            or "respawn" in type_name or "spawn" in type_name
            or "respawn" in bg or "spawn" in bg):
        return "__facility__"
    if ("bombing" in name or "bombing" in type_name
            or "bombing" in bg
            or "defend" in name or "defend" in type_name
            or "defend" in bg):
        return "__bp__"
    if "capture" in name or "capture" in type_name or "capture" in bg:
        return "__cp__"
    return "__facility__"


_FACILITY_ICONS = {
    "airfield", "helipad",
    "bombingzone", "bombing_point",
    "capturezone", "capturepoint", "capture_zone",
    "respawn_base", "respawn_base_tank", "respawn_base_bomber",
    "respawn_base_fighter", "air_spawn", "defending_point",
}

_AIRFIELD_ICON_NAMES = {"airfield", "helipad"}

def is_facility_icon(icon: str) -> bool:
    """判断图标名是否属于静态设施（机场、出生点、战区等）。"""
    name = (icon or "").lower()
    return (name in _FACILITY_ICONS
            or "respawn" in name or "spawn" in name
            or "airfield" in name or "helipad" in name
            or "bombing" in name or "capture" in name
            or "defend" in name or "carrier" in name)

def is_carrier(obj) -> bool:
    """航母：带有跑道属性的设施，按跑道绘制并由航母筛选控制。"""
    name = (obj.icon or "").lower()
    type_name = (obj.obj_type or "").lower()
    bg = (obj.icon_bg or "").lower()
    return "carrier" in name or "carrier" in type_name or "carrier" in bg

def is_spawn_point(obj) -> bool:
    """出生点/重生点：整体忽略，不绘制、不追踪、不生成标签。"""
    if is_carrier(obj):
        return False
    name = (obj.icon or "").lower()
    type_name = (obj.obj_type or "").lower()
    bg = (obj.icon_bg or "").lower()
    return ("respawn" in name or "spawn" in name
            or "respawn" in type_name or "spawn" in type_name
            or "respawn" in bg or "spawn" in bg)

def _has_area(obj) -> bool:
    """判断对象是否带实际区域坐标（sx/sy/ex/ey）。"""
    return any(v != 0 for v in (obj.sx, obj.sy, obj.ex, obj.ey))

def _is_airfield_like(obj) -> bool:
    """判断是否为机场类对象（type 为机场或图标匹配），区域坐标不参与判定。"""
    if (obj.obj_type or "").lower() in ("airfield", "helipad"):
        return True
    return (obj.icon or "").lower() in _AIRFIELD_ICON_NAMES

def _is_facility_type(obj) -> bool:
    """判断 type 字段是否属于静态设施（轰炸区、出生点、据点等）。"""
    t = (obj.obj_type or "").lower()
    bg = (obj.icon_bg or "").lower()
    return (any(k in t for k in ("airfield", "helipad", "bombing", "capture",
                                 "defend", "respawn", "spawn", "carrier"))
            or any(k in bg for k in ("airfield", "helipad", "bombing", "capture",
                                     "defend", "respawn", "spawn", "carrier")))


def is_facility(obj) -> bool:
    """判断是否为静态设施（机场、战区等），避免误识别无关对象。"""
    # 机场类对象
    if _is_airfield_like(obj) or _is_facility_type(obj):
        return True
    # 有区域坐标的静态区域（出生点、战区等）不能当载具处理
    if _has_area(obj):
        return True
    # 已知设施图标名
    return is_facility_icon(obj.icon)


def _draw_airfield_strip(p: QPainter, x1: float, y1: float,
                         x2: float, y2: float,
                         r: int, g: int, b: int, alpha: int = 255):
    """沿跑道两端点绘制跑道条：长度和宽度同时按 150% 等比放大，比例不变。"""
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 0:
        base_width = AIRFIELD_FALLBACK_LENGTH / RUNWAY_ASPECT_RATIO
        scale = max(RUNWAY_SCALE, RUNWAY_MIN_WIDTH / base_width)
        fallback_len = AIRFIELD_FALLBACK_LENGTH * scale
        fallback_w = base_width * scale
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(r, g, b, alpha))
        p.drawRect(QRectF(x1 - fallback_len / 2,
                          y1 - fallback_w / 2, fallback_len, fallback_w))
        return

    ux, uy = dx / length, dy / length
    # 基础宽度按固定长宽比得出；整体等比放大，宽度不足 2px 时继续放大
    base_width = length / RUNWAY_ASPECT_RATIO
    scale = max(RUNWAY_SCALE, RUNWAY_MIN_WIDTH / base_width)
    ext = length * (scale - 1) / 2
    x1 -= ux * ext
    y1 -= uy * ext
    x2 += ux * ext
    y2 += uy * ext

    # 垂直方向单位向量，把跑道中心线扩展成固定宽度的多边形
    nx, ny = -uy, ux
    hw = (base_width * scale) / 2
    poly = QPolygonF([
        QPointF(x1 + nx * hw, y1 + ny * hw),
        QPointF(x2 + nx * hw, y2 + ny * hw),
        QPointF(x2 - nx * hw, y2 - ny * hw),
        QPointF(x1 - nx * hw, y1 - ny * hw),
    ])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(r, g, b, alpha))
    p.drawPolygon(poly)


class MapWidget(QWidget):
    """地图控件：显示游戏内地图图片 + 实时单位标记。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map_pixmap: QPixmap | None = None
        self._scaled_pixmap: QPixmap | None = None  # 缓存缩放后的图片
        self._last_size: tuple[int, int] = (0, 0)
        self._objects: list[MapObject] = []
        self._player: MapObject | None = None
        self._cache_dirty: bool = True
        self._lost_enemies: list[TrackedUnit] = []
        self._lost_friendlies: list[TrackedUnit] = []
        self._hidden: set[tuple[str, str]] = set()
        self._labels: list[tuple[float, float, str, tuple[int,int,int,int]]] = []
        self.setMinimumSize(400, 400)

    def _retranslate(self):
        """语言切换时刷新（占位文字下次 paintEvent 生效）。"""
        pass  # 占位文字在 paintEvent 中每次用 _() 动态获取

    def set_labels(self, labels: list):
        self._labels = labels

    def toggle_filter(self, faction: str, icon: str):
        key = (faction, icon)
        if key in self._hidden:
            self._hidden.discard(key)
        else:
            self._hidden.add(key)
        self.update()

    def _is_hidden(self, faction: str, icon: str) -> bool:
        # 小队归入友军筛选
        check_f = "friendly" if faction == "squad" else faction
        if (check_f, icon) in self._hidden:
            return True
        # 未知类型归入 [陆] 地面设施
        if icon not in _ICON_FILE_MAP and (check_f, "__facility__") in self._hidden:
            return True
        return False

    def update_state(self, state: GameState):
        """更新地图数据。"""
        if state.map_image_bytes:
            pix = QPixmap()
            pix.loadFromData(state.map_image_bytes)
            if not pix.isNull():
                self._map_pixmap = pix
                self._cache_dirty = True

        self._objects = state.map_objects
        self._player = state.player_object()
        self.update()

    def clear(self):
        self._objects.clear()
        self._player = None
        self._lost_enemies.clear()
        self._lost_friendlies.clear()
        self.update()

    def set_lost_enemies(self, units: list):
        """接收消失敌人的追踪数据。"""
        self._lost_enemies = units

    def set_lost_friendlies(self, units: list):
        """接收消失友军的追踪数据。"""
        self._lost_friendlies = units

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cache_dirty = True  # 窗口大小变了，需要重新缩放

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 背景
        p.fillRect(0, 0, w, h, QColor(COLOR_BACKGROUND))

        # 绘制地图图片（使用缓存避免每帧缩放）
        if self._map_pixmap and not self._map_pixmap.isNull():
            # 仅在尺寸变化时重新缩放
            if self._cache_dirty or self._last_size != (w, h):
                self._scaled_pixmap = self._map_pixmap.scaled(
                    w, h, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._last_size = (w, h)
                self._cache_dirty = False

            pm = self._scaled_pixmap
            ox = (w - pm.width()) / 2
            oy = (h - pm.height()) / 2
            p.drawPixmap(int(ox), int(oy), pm)

            # 地图坐标计算：map_obj 的 x, y 是归一化坐标 [0, 1]
            self._draw_objects(p, ox, oy, pm.width(), pm.height())
            self._draw_labels(p, ox, oy, pm.width(), pm.height())
            self._draw_lost_markers(p, ox, oy, pm.width(), pm.height(), "enemy")
            self._draw_lost_markers(p, ox, oy, pm.width(), pm.height(), "friendly")
        else:
            # 无地图时显示提示
            p.setPen(QColor(COLOR_ACCENT))
            font = QFont("Segoe UI", 14)
            p.setFont(font)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       _("map.waiting"))

        p.end()

    def _draw_objects(self, p: QPainter, ox: float, oy: float,
                      mw: float, mh: float):
        """在地图坐标系中仅绘制玩家单位。"""
        player = None
        friendlies = []
        enemies = []
        squad = []
        facilities_friendly = []
        facilities_enemy = []

        for obj in self._objects:
            if obj.is_player:
                player = obj
                continue
            # 出生点/重生点直接忽略，不显示
            if is_spawn_point(obj):
                continue
            # 设施（机场、战区等：非载具类型 或 特定图标）
            if is_facility(obj):
                r, g, b = obj.color_rgb
                if b > 200 and r < 100:
                    facilities_friendly.append(obj)
                elif g > 200:
                    # 绿色（小队）也归入友方设施
                    facilities_friendly.append(obj)
                elif r > 200:
                    facilities_enemy.append(obj)
                else:
                    facilities_friendly.append(obj)
                continue
            # 确定阵营
            if obj.color_rgb[2] > 200 and obj.color_rgb[0] < 100:
                faction = "friendly"
            elif obj.color_rgb[1] > 200:
                faction = "squad"
            elif obj.color_rgb[0] > 200:
                faction = "enemy"
            else:
                faction = "friendly"
            # 阵营+机型筛选
            if self._is_hidden(faction, obj.icon):
                continue
            # 分配
            if faction == "friendly":
                friendlies.append(obj)
            elif faction == "squad":
                squad.append(obj)
            else:
                enemies.append(obj)

        # 绘制顺序：设施 → 友军 → 敌军 → 小队 → 玩家
        self._draw_facilities(p, facilities_friendly, ox, oy, mw, mh, False)
        self._draw_facilities(p, facilities_enemy, ox, oy, mw, mh, True)
        self._draw_units(p, friendlies, ox, oy, mw, mh, COLOR_FRIENDLY, ICON_SIZE)
        self._draw_units(p, enemies, ox, oy, mw, mh, COLOR_ENEMY, ICON_SIZE)
        self._draw_units(p, squad, ox, oy, mw, mh, COLOR_SQUAD, ICON_SIZE)
        if player:
            self._draw_player(p, player, ox, oy, mw, mh)

    def _draw_player(self, p: QPainter, obj: MapObject,
                     ox: float, oy: float, mw: float, mh: float):
        x = ox + obj.x * mw
        y = oy + obj.y * mh
        angle = math.degrees(math.atan2(obj.dy, obj.dx)) + 90
        s = ICON_SIZE_PLAYER

        p.save()
        p.translate(x, y)
        p.rotate(angle)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawEllipse(QPointF(0, 0), s + 2, s + 2)

        p.setPen(QPen(Qt.GlobalColor.white, 1.5))
        p.setBrush(QColor(*COLOR_SQUAD))
        tri = QPolygonF([QPointF(0, -s), QPointF(-s*0.7, s*0.7), QPointF(s*0.7, s*0.7)])
        p.drawPolygon(tri)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.GlobalColor.white)
        p.drawEllipse(QPointF(0, 0), 2, 2)
        p.restore()

    def _draw_units(self, p: QPainter, units: list[MapObject],
                    ox: float, oy: float, mw: float, mh: float,
                    color: tuple, size: int):
        r, g, b = color
        for obj in units:
            x = ox + obj.x * mw
            y = oy + obj.y * mh
            # 图标
            _draw_icon_shape(p, obj.icon, x, y, size, r, g, b)

            # 方向线（仅飞机）
            if obj.is_aircraft and (obj.dx != 0 or obj.dy != 0):
                angle = math.degrees(math.atan2(obj.dy, obj.dx)) + 90
                p.save()
                p.translate(x, y)
                p.rotate(angle)
                p.setPen(QPen(QColor(r, g, b, 180), 1.5))
                p.drawLine(0, -int(size * 0.35), 0, -size - 2)
                p.restore()

    def _draw_facilities(self, p: QPainter, facilities: list[MapObject],
                         ox: float, oy: float, mw: float, mh: float,
                         is_enemy: bool):
        """绘制静态设施：机场跑道、战区、占领区。"""
        faction = "enemy" if is_enemy else "friendly"
        r, g, b = (250, 50, 0) if is_enemy else (24, 90, 255)
        for obj in facilities:
            ficon = _facility_icon(obj)
            if self._is_hidden(faction, ficon):
                continue
            if ficon == "__airfield__":
                if _has_area(obj):
                    # 机场/航母跑道：sx/sy-ex/ey 是跑道两端点，绘制统一宽度跑道条
                    x1, y1 = ox + obj.sx * mw, oy + obj.sy * mh
                    x2, y2 = ox + obj.ex * mw, oy + obj.ey * mh
                    _draw_airfield_strip(p, x1, y1, x2, y2, r, g, b)
                else:
                    # 机场/航母无区域坐标：以 x/y 为中心画默认宽度跑道条
                    cx = ox + obj.x * mw
                    cy = oy + obj.y * mh
                    base_width = AIRFIELD_FALLBACK_LENGTH / RUNWAY_ASPECT_RATIO
                    scale = max(RUNWAY_SCALE, RUNWAY_MIN_WIDTH / base_width)
                    fallback_len = AIRFIELD_FALLBACK_LENGTH * scale
                    fallback_w = base_width * scale
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(r, g, b, 255))
                    p.drawRect(QRectF(cx - fallback_len / 2,
                                      cy - fallback_w / 2,
                                      fallback_len, fallback_w))
            else:
                # 战区、占领区：BP/CP 图标
                cx = ox + obj.x * mw
                cy = oy + obj.y * mh
                _draw_icon_shape(p, ficon, cx, cy, 18, r, g, b, 220)

    def _draw_labels(self, p: QPainter, ox: float, oy: float,
                     mw: float, mh: float):
        if not self._labels:
            return
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFontMetrics
        fs = max(5, QApplication.instance().font().pointSize() - 8)
        font = QFont("Segoe UI", fs)
        p.setFont(font)
        fm = QFontMetrics(font)
        for lx, ly, text, color in self._labels:
            x = ox + lx * mw
            y = oy + ly * mh
            tw = fm.horizontalAdvance(text) + 6
            th = fm.height()
            p.setPen(QColor(*color))
            p.drawText(QRectF(x - tw/2, y - th - 10, tw, th),
                       Qt.AlignmentFlag.AlignCenter, text)

    def _draw_lost_markers(self, p: QPainter, ox: float, oy: float,
                           mw: float, mh: float, faction: str = "enemy"):
        """绘制已消失单位的惯性导航估算位置（半透明幽灵标记）。"""
        now = time.time()
        units = self._lost_enemies if faction == "enemy" else self._lost_friendlies
        if faction == "enemy":
            r, g, b = (250, 50, 0)
        else:
            r, g, b = (50, 160, 250)

        for unit in units:
            if self._is_hidden(faction, unit.icon):
                continue
            # 惯性导航：基于最后已知航向和速度外推当前位置
            est_x, est_y = unit.estimated_position(now)
            x = ox + est_x * mw
            y = oy + est_y * mh
            elapsed = now - unit.last_seen
            alpha = max(40, 180 - int(elapsed * 3))

            # 图标
            _draw_icon_shape(p, unit.icon, x, y, ICON_SIZE, r, g, b, alpha)

            # 方向线
            if unit.obj_type == "aircraft" and (unit.last_dx != 0 or unit.last_dy != 0):
                angle = math.degrees(math.atan2(unit.last_dy, unit.last_dx)) + 90
                p.save()
                p.translate(x, y)
                p.rotate(angle)
                p.setPen(QPen(QColor(r, g, b, alpha), 1.2))
                p.drawLine(0, -int(ICON_SIZE * 0.35), 0, -ICON_SIZE - 2)
                p.restore()
