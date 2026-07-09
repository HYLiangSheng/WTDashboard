"""单位追踪器 —— 跨帧匹配单位并记录其状态变化。

功能：
- 通过颜色 + 类型 + 邻近匹配，跨帧追踪同一单位
- 记录每个单位的位置历史，估算速度
- 当单位从地图上消失时，保留最后已知位置和消失时间
- 统计活跃/已消失的敌我单位数量
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field

from .api_client import MapObject

# 匹配阈值：两帧之间同一单位最大移动距离（归一化坐标）
MATCH_THRESHOLD = 0.08
# 消失确认帧数（需连续消失 N 帧才算真正消失）
LOST_CONFIRM_FRAMES = 3
# 保留消失单位的时间（秒），超时彻底清除
GHOST_TTL = 30.0
# 保留位置历史的最大帧数
MAX_POS_HISTORY = 3  # 3 个不同位置足够算速度（约 1 个 daemon 周期后就有结果）


@dataclass
class TrackedUnit:
    """一个被追踪的单位。"""
    uid: int                          # 内部唯一 ID
    obj_type: str                     # aircraft / ground_model
    icon: str                         # Fighter / Bomber / Assault / ...
    color_rgb: tuple[int, int, int]   # RGB 颜色
    is_enemy: bool
    is_friendly: bool

    first_seen: float                 # 首次发现时间 (time.time())
    last_seen: float                  # 最后出现时间
    last_x: float = 0.0
    last_y: float = 0.0
    last_dx: float = 0.0
    last_dy: float = 0.0
    speed_norm: float = 0.0           # 归一化坐标/秒 的速度
    speed_kmh_est: float = 0.0        # 估算 km/h (基于 map_info)
    is_active: bool = True            # 当前帧是否可见
    disappear_count: int = 0          # 连续消失帧数

    # 位置历史 [(timestamp, x, y), ...]
    pos_history: list[tuple[float, float, float]] = field(default_factory=list)


class UnitTracker:
    """管理所有追踪单位的生命周期。"""

    def __init__(self):
        self._next_uid = 1
        self._units: dict[int, TrackedUnit] = {}      # uid → TrackedUnit
        self._map_width_m: float = 10000.0              # 地图实际宽度（米）
        self._map_height_m: float = 10000.0             # 地图实际高度（米）

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def update(self, objects: list[MapObject], map_info: dict | None = None) -> None:
        """处理一帧的地图对象，匹配并更新追踪状态。"""
        now = time.time()
        self._update_map_scale(map_info)

        # 分类当前帧的敌方/友方单位（排除玩家、机场、据点等）
        current_enemies: list[MapObject] = []
        current_friendlies: list[MapObject] = []
        for obj in objects:
            if not obj.is_aircraft and not obj.is_ground:
                continue
            if obj.is_player:
                continue
            if obj.color_rgb[0] > 200 and obj.color_rgb[2] < 100:
                current_enemies.append(obj)
            elif obj.color_rgb[2] > 200 and obj.color_rgb[0] < 100:
                current_friendlies.append(obj)
            elif obj.color_rgb[1] > 200:
                current_friendlies.append(obj)   # 绿色小队归入友方追踪

        # 匹配并更新
        matched_ids: set[int] = set()
        self._match_and_update(current_enemies, now, matched_ids, is_enemy=True)
        self._match_and_update(current_friendlies, now, matched_ids, is_enemy=False)

        # 标记未匹配的单位（需连续消失 LOST_CONFIRM_FRAMES 帧）
        for uid, unit in self._units.items():
            if uid not in matched_ids:
                unit.disappear_count += 1
                if unit.is_active and unit.disappear_count >= LOST_CONFIRM_FRAMES:
                    unit.is_active = False
            else:
                unit.disappear_count = 0
                unit.is_active = True

        # 清理超时的幽灵单位
        self._purge_expired(now)

    def reset(self) -> None:
        """清空所有追踪数据（新一局开始）。"""
        self._units.clear()
        self._next_uid = 1

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def active_enemies(self) -> list[TrackedUnit]:
        return [u for u in self._units.values()
                if u.is_enemy and u.is_active]

    @property
    def active_friendlies(self) -> list[TrackedUnit]:
        return [u for u in self._units.values()
                if u.is_friendly and u.is_active]

    @property
    def lost_enemies(self) -> list[TrackedUnit]:
        """已消失的敌方单位（最近消失的排前面）。"""
        return sorted(
            [u for u in self._units.values() if u.is_enemy and not u.is_active],
            key=lambda u: u.last_seen, reverse=True,
        )

    @property
    def lost_friendlies(self) -> list[TrackedUnit]:
        return sorted(
            [u for u in self._units.values() if u.is_friendly and not u.is_active],
            key=lambda u: u.last_seen, reverse=True,
        )

    @property
    def all_units(self) -> list[TrackedUnit]:
        """所有单位，活跃的排前面。"""
        return sorted(self._units.values(),
                      key=lambda u: (not u.is_active, -u.last_seen))

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _update_map_scale(self, map_info: dict | None):
        """根据 map_info 更新地图实际尺寸（用于速度估算）。"""
        if not map_info:
            return
        try:
            grid_steps = [float(x) for x in map_info.get("grid_steps", [])]
            grid_zero = [float(x) for x in map_info.get("grid_zero", [])]
            map_max = [float(x) for x in map_info.get("map_max", [])]
            map_min = [float(x) for x in map_info.get("map_min", [])]
            self._map_width_m = map_max[0] - map_min[0]
            self._map_height_m = map_max[1] - map_min[1]
        except (IndexError, ValueError):
            pass

    def _match_and_update(self, current_objs: list[MapObject], now: float,
                          matched_ids: set[int], is_enemy: bool):
        """将当前帧的对象匹配到已有追踪单位，或创建新追踪记录。"""
        # 获取同阵营所有已有单位作为候选
        candidates = [
            u for u in self._units.values()
            if u.is_enemy == is_enemy and u.is_active
        ]
        used_uids: set[int] = set()

        for obj in current_objs:
            best_uid: int | None = None
            best_dist = MATCH_THRESHOLD

            for unit in candidates:
                if unit.uid in used_uids:
                    continue
                # 至少类型相同（空/地分开）
                if unit.obj_type != obj.obj_type:
                    continue
                dist = math.hypot(obj.x - unit.last_x, obj.y - unit.last_y)
                if dist < best_dist:
                    best_dist = dist
                    best_uid = unit.uid

            if best_uid is not None:
                # 匹配成功 —— 更新已有单位
                unit = self._units[best_uid]
                used_uids.add(best_uid)
                matched_ids.add(best_uid)
                self._update_unit(unit, obj, now)
            else:
                # 新单位
                uid = self._next_uid
                self._next_uid += 1
                unit = self._create_unit(uid, obj, now, is_enemy)
                self._units[uid] = unit
                matched_ids.add(uid)

    def _create_unit(self, uid: int, obj: MapObject, now: float,
                     is_enemy: bool) -> TrackedUnit:
        unit = TrackedUnit(
            uid=uid,
            obj_type=obj.obj_type,
            icon=obj.icon,
            color_rgb=obj.color_rgb,
            is_enemy=is_enemy,
            is_friendly=not is_enemy,
            first_seen=now,
            last_seen=now,
            last_x=obj.x,
            last_y=obj.y,
            last_dx=obj.dx,
            last_dy=obj.dy,
            is_active=True,
        )
        unit.pos_history.append((now, obj.x, obj.y))
        return unit

    def _update_unit(self, unit: TrackedUnit, obj: MapObject, now: float):
        unit.last_seen = now
        unit.is_active = True
        unit.disappear_count = 0

        # 仅在位置变化时记录（避免缓存重复帧填满历史）
        if unit.last_x == obj.x and unit.last_y == obj.y:
            return

        # 位置历史
        unit.pos_history.append((now, obj.x, obj.y))
        if len(unit.pos_history) > MAX_POS_HISTORY:
            unit.pos_history.pop(0)

        # 速度估算（用位置历史的首尾）
        if len(unit.pos_history) >= 2:
            t0, x0, y0 = unit.pos_history[0]
            t1, x1, y1 = unit.pos_history[-1]
            dt_hist = t1 - t0
            if dt_hist > 0.05:
                dist = math.hypot(x1 - x0, y1 - y0)
                unit.speed_norm = dist / dt_hist
                avg_map_m = max((self._map_width_m + self._map_height_m) / 2, 1000)
                unit.speed_kmh_est = unit.speed_norm * avg_map_m * 3.6

        unit.last_x = obj.x
        unit.last_y = obj.y
        unit.last_dx = obj.dx
        unit.last_dy = obj.dy

    def _purge_expired(self, now: float):
        expired = [
            uid for uid, u in self._units.items()
            if not u.is_active and (now - u.last_seen) > GHOST_TTL
        ]
        for uid in expired:
            del self._units[uid]
