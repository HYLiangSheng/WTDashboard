"""War Thunder 8111 端口 API 客户端。

通过 HTTP 拉取游戏实时数据，所有端点：
  /state         — 载具状态
  /indicators    — 仪表数据
  /map_obj.json  — 地图对象
  /map_info.json — 地图元信息
  /map.img       — 地图图片
  /mission.json  — 任务信息
  /hudmsg        — HUD 消息
  /gamechat      — 游戏聊天
"""

import base64
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from .i18n import _
from urllib.request import Request, urlopen
from urllib.error import URLError

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, QMutexLocker


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class MapObject:
    """地图上的一个对象（载具 / 地面单位 / 据点等）。"""
    obj_type: str = ""
    color: str = ""
    color_rgb: tuple[int, int, int] = (128, 128, 128)
    blink: int = 0
    icon: str = ""
    icon_bg: str = ""
    x: float = 0.0
    y: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    sx: float = 0.0
    sy: float = 0.0
    ex: float = 0.0
    ey: float = 0.0

    @staticmethod
    def from_dict(d: dict) -> "MapObject":
        rgb = tuple(d.get("color[]", [128, 128, 128]))
        return MapObject(
            obj_type=d.get("type", ""),
            color=d.get("color", ""),
            color_rgb=rgb,
            blink=d.get("blink", 0),
            icon=d.get("icon", ""),
            icon_bg=d.get("icon_bg", ""),
            x=d.get("x", 0.0),
            y=d.get("y", 0.0),
            dx=d.get("dx", 0.0),
            dy=d.get("dy", 0.0),
            sx=d.get("sx", 0.0),
            sy=d.get("sy", 0.0),
            ex=d.get("ex", 0.0),
            ey=d.get("ey", 0.0),
        )

    @property
    def is_player(self) -> bool:
        return self.icon == "Player"

    @property
    def is_aircraft(self) -> bool:
        return self.obj_type == "aircraft"

    @property
    def is_ground(self) -> bool:
        return self.obj_type == "ground_model"


@dataclass
class GameState:
    """一次完整的游戏状态快照。"""
    timestamp: float = 0.0

    # /state
    state_raw: dict[str, Any] = field(default_factory=dict)
    valid: bool = False

    # /indicators
    indicators_raw: dict[str, Any] = field(default_factory=dict)

    # /map_obj.json
    map_objects: list[MapObject] = field(default_factory=list)

    # /map_info.json
    map_info: dict[str, Any] = field(default_factory=dict)

    # /map.img (bytes)
    map_image_bytes: bytes = b""

    # /mission.json
    mission_raw: dict[str, Any] = field(default_factory=dict)

    # /hudmsg
    hudmsg_raw: dict[str, Any] = field(default_factory=dict)

    # ------ 便捷属性 ------
    @property
    def has_map_image(self) -> bool:
        return len(self.map_image_bytes) > 0

    @property
    def aircraft_name(self) -> str:
        return self.indicators_raw.get("type", "")

    @property
    def speed_kmh(self) -> float:
        """IAS (指示空速) km/h。"""
        return float(self.state_raw.get("IAS, km/h", 0))

    @property
    def speed_tas(self) -> float:
        """TAS (真空速) km/h。"""
        return float(self.state_raw.get("TAS, km/h", 0))

    @property
    def altitude_m(self) -> float:
        return float(self.state_raw.get("H, m", 0))

    @property
    def heading(self) -> float:
        return float(self.indicators_raw.get("compass", 0))

    @property
    def vertical_speed(self) -> float:
        return float(self.state_raw.get("Vy, m/s", 0))

    @property
    def mach(self) -> float:
        return float(self.state_raw.get("M", 0))

    @property
    def throttle_pct(self) -> float:
        return float(self.state_raw.get("throttle 1, %", 0))

    @property
    def rpm(self) -> float:
        return float(self.state_raw.get("RPM 1", 0))

    @property
    def oil_temp(self) -> float:
        return float(self.state_raw.get("oil temp 1, C", 0))

    @property
    def water_temp(self) -> float:
        return float(self.state_raw.get("water temp 1, C", 0))

    @property
    def power_hp(self) -> float:
        return float(self.state_raw.get("power 1, hp", 0))

    @property
    def fuel_kg(self) -> float:
        return float(self.state_raw.get("Mfuel, kg", 0))

    @property
    def fuel_max_kg(self) -> float:
        return float(self.state_raw.get("Mfuel0, kg", 0))

    @property
    def g_load(self) -> float:
        return float(self.indicators_raw.get("g_meter", 0))

    @property
    def aoa(self) -> float:
        return float(self.state_raw.get("AoA, deg", 0))

    @property
    def flaps_pct(self) -> float:
        return float(self.state_raw.get("flaps, %", 0))

    @property
    def gears_pct(self) -> float:
        return float(self.state_raw.get("gears, %", 0))

    @property
    def bank_angle(self) -> float:
        return float(self.indicators_raw.get("bank", 0))

    @property
    def pitch_angle(self) -> float:
        return float(self.indicators_raw.get("aviahorizon_pitch", 0))

    @property
    def roll_angle(self) -> float:
        return float(self.indicators_raw.get("aviahorizon_roll", 0))

    def player_object(self) -> MapObject | None:
        for mo in self.map_objects:
            if mo.is_player:
                return mo
        return None

    def friendlies(self) -> list[MapObject]:
        return [mo for mo in self.map_objects
                if mo.color_rgb[2] > 200 and mo.color_rgb[0] < 100 and not mo.is_player]

    def enemies(self) -> list[MapObject]:
        return [mo for mo in self.map_objects
                if mo.color_rgb[0] > 200 and mo.color_rgb[2] < 100]

    def squad_mates(self) -> list[MapObject]:
        return [mo for mo in self.map_objects
                if mo.color_rgb[1] > 200 and mo.color_rgb[0] < 100 and mo.color_rgb[2] < 100 and not mo.is_player]


# ---------------------------------------------------------------------------
# 工作线程
# ---------------------------------------------------------------------------

class FetchWorker(QObject):
    """后台轮询 + 缓存：daemon 线程持续拉取，fetch_all() 瞬间返回缓存。"""

    data_ready = pyqtSignal(GameState)
    connection_error = pyqtSignal(str)
    connection_restored = pyqtSignal()

    BASE_URL = "http://localhost:8111"
    TIMEOUT = 1.0

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._cache: GameState | None = None
        self._cache_lock = threading.Lock()
        self._cache_version = 0
        self._last_read_version = -1
        self._running = False
        self._last_evt = 0
        self._last_dmg = 0
        self._map_img_fetched = False
        self._error_emitted = False

        self._running = True
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)
        self._poller.start()

    def fetch_all(self) -> None:
        """从缓存读取状态，带上版本号供调用方判断是否更新。"""
        with self._cache_lock:
            state = self._cache
            ver = self._cache_version
        if state is not None and ver != self._last_read_version:
            self._last_read_version = ver
        if state is not None:
            self.data_ready.emit(state)

    def reset_map_image(self) -> None:
        self._map_img_fetched = False

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # 后台轮询（daemon 线程）
    # ------------------------------------------------------------------

    def _poll_loop(self):
        """统一轮询：每轮都并行拉取全部端点。"""
        while self._running:
            try:
                state = self._do_fetch_full()
                with self._cache_lock:
                    self._cache = state
                    self._cache_version += 1
            except Exception:
                pass

    def _do_fetch_full(self) -> GameState:
        """并行拉取所有端点（state + map + indicators + mission + hudmsg）。"""
        state = GameState(timestamp=time.time())

        tasks = {
            "/state": "state",
            "/map_obj.json": "map_objects",
            "/map_info.json": "map_info",
            "/indicators": "indicators",
            "/mission.json": "mission",
            f"/hudmsg?lastEvt={self._last_evt}&lastDmg={self._last_dmg}": "hudmsg",
        }
        if not self._map_img_fetched:
            tasks["/map.img"] = "map_image"

        results = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {}
            for path, key in tasks.items():
                if key == "map_image":
                    futures[pool.submit(self._get_bytes, path)] = key
                else:
                    futures[pool.submit(self._get, path)] = key
            for future in as_completed(futures, timeout=self.TIMEOUT + 5):
                try:
                    results[futures[future]] = future.result()
                except Exception:
                    pass

        state.state_raw = results.get("state") or {}
        state.valid = state.state_raw.get("valid", False)
        if not state.valid:
            self._map_img_fetched = False  # 断连时重置，下次重连重新下载地图
            if not self._error_emitted:
                self.connection_error.emit("status.waiting")
                self._error_emitted = True
            return state
        if self._error_emitted:
            self.connection_restored.emit()
            self._error_emitted = False
            self._map_img_fetched = False  # 重连后强制重新下载地图

        state.indicators_raw = results.get("indicators") or {}
        state.map_info = results.get("map_info") or {}
        raw = results.get("map_objects") or []
        if isinstance(raw, list):
            state.map_objects = [MapObject.from_dict(d) for d in raw]
        state.mission_raw = results.get("mission") or {}

        hud = results.get("hudmsg") or {}
        state.hudmsg_raw = hud
        if hud.get("damage"):
            try:
                self._last_dmg = hud["damage"][-1]["id"]
            except (IndexError, KeyError):
                pass

        img = results.get("map_image")
        if img and not self._map_img_fetched:
            state.map_image_bytes = img
            self._map_img_fetched = True

        return state

    # ------------------------------------------------------------------
    # HTTP 请求
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        try:
            req = Request(
                f"{self.BASE_URL}{path}",
                headers={"User-Agent": "WTDashboard/1.1.1"},
            )
            with urlopen(req, timeout=self.TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    def _get_bytes(self, path: str) -> bytes | None:
        try:
            req = Request(
                f"{self.BASE_URL}{path}",
                headers={"User-Agent": "WTDashboard/1.1.1"},
            )
            with urlopen(req, timeout=3.0) as resp:
                return resp.read()
        except Exception:
            return None
