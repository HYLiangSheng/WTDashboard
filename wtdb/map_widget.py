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
    # 未知类型 → 小正方形
    s = size * 0.55
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(r, g, b, alpha))
    p.drawRect(QRectF(x - s / 2, y - s / 2, s, s))


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

        for obj in self._objects:
            if obj.is_player:
                player = obj
                continue
            if obj.obj_type not in ("aircraft", "ground_model"):
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

        # 绘制顺序：友军 → 敌军 → 小队 → 玩家
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
            # 外圈光晕
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(r, g, b, 40))
            p.drawEllipse(QPointF(int(x), int(y)), size // 2 + 2, size // 2 + 2)

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

    def _draw_labels(self, p: QPainter, ox: float, oy: float,
                     mw: float, mh: float):
        if not self._labels:
            return
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFontMetrics
        fs = max(6, QApplication.instance().font().pointSize() - 6)
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
        """绘制已消失单位的最后出现位置（半透明幽灵标记）。"""
        now = time.time()
        units = self._lost_enemies if faction == "enemy" else self._lost_friendlies
        if faction == "enemy":
            r, g, b = (250, 50, 0)
        else:
            r, g, b = (50, 160, 250)

        for unit in units:
            if self._is_hidden(faction, unit.icon):
                continue
            x = ox + unit.last_x * mw
            y = oy + unit.last_y * mh
            elapsed = now - unit.last_seen
            alpha = max(40, 180 - int(elapsed * 3))

            # 外圈光晕
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(r, g, b, max(20, alpha // 3)))
            p.drawEllipse(QPointF(int(x), int(y)), ICON_SIZE // 2 + 1, ICON_SIZE // 2 + 1)

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
