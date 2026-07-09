"""配置持久化 —— 保存/加载 UI 状态到 JSON 文件。"""

import json
import os
import sys

# 可执行文件时用 %LOCALAPPDATA%，源码运行时用项目目录
if getattr(sys, 'frozen', False):
    CONFIG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'WTDashboard')
    os.makedirs(CONFIG_DIR, exist_ok=True)
    CONFIG_PATH = os.path.join(CONFIG_DIR, 'wtdb_config.json')
else:
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wtdb_config.json")

DEFAULTS = {
    "host": "localhost",
    "port": 8111,
    "font_size": 9,
    "fullscreen": False,
    "always_on_top": False,
    "hidden_filters": [],       # [(faction, icon), ...]
    "expand_state": {},         # {icon_key: bool}
    "window_geometry": "",      # "x,y,w,h"
}


def load() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {**DEFAULTS, **data}


def save(data: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
