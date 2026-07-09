"""多语言支持模块。

特性：
  - 语言包为外部 JSON 文件（locales/ 目录），可自由添加新语言
  - 通过 Qt 信号实现动态切换，无需重启
  - 菜单式语言选择，支持任意数量语言

用法:
    from .i18n import _, set_locale, get_locale, available_locales, locale_changed

    label = QLabel(_("主机地址:"))
    locale_changed.connect(self._retranslate)   # 语言切换时自动刷新
    set_locale("en-US")   # 动态切换为英文
"""

import json
import os
import sys

from PyQt6.QtCore import QObject, pyqtSignal

# ---------------------------------------------------------------------------
# 语言显示名称（可在 JSON 中用 ____display_name____ 覆盖）
# ---------------------------------------------------------------------------

_LOCALE_NAMES: dict[str, str] = {
    "zh-CN": "简体中文",
    "en-US": "English",
}

# 自指名称：用于语言选择菜单（各自语言显示自己）
_LOCALE_SELF_NAME: dict[str, str] = {
    "zh-CN": "简体中文",
    "en-US": "English",
}

# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------

_current_locale = "zh-CN"
_translations: dict[str, dict[str, str]] = {}

# 信号发射器
_locale_emitter = QObject()

# 类级别的 pyqtSignal 不能直接挂到实例上，改用这种方式
class _LocaleNotifier(QObject):
    changed = pyqtSignal(str)

_notifier = _LocaleNotifier()
locale_changed = _notifier.changed


# ---------------------------------------------------------------------------
# 路径辅助
# ---------------------------------------------------------------------------

def _get_app_dir() -> str:
    """返回应用根目录（EXE 同级或项目根）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(__file__))


def _locales_dir() -> str:
    """返回语言包目录，优先外部文件夹，其次内置。"""
    external = os.path.join(_get_app_dir(), "locales")
    if os.path.isdir(external):
        return external
    internal = os.path.join(os.path.dirname(__file__), "locales")
    if os.path.isdir(internal):
        return internal
    return external


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def available_locales() -> list[tuple[str, str]]:
    """返回可用语言列表 [(code, display_name), ...]。

    扫描 locales/ 目录下的所有 .json 文件，自动发现新语言。
    """
    result: list[tuple[str, str]] = []
    locale_dir = _locales_dir()
    if not os.path.isdir(locale_dir):
        return [("zh-CN", "简体中文")]
    for fname in sorted(os.listdir(locale_dir)):
        if fname.endswith(".json"):
            code = fname[:-5]
            name = _LOCALE_NAMES.get(code, code)
            result.append((code, name))
    if not any(c == "zh-CN" for c, _ in result):
        result.insert(0, ("zh-CN", "简体中文"))
    return result


def set_locale(locale: str):
    """切换当前语言，发出 locale_changed 信号。"""
    global _current_locale
    if locale == "zh-CN" or locale in _translations:
        _current_locale = locale
        _notifier.changed.emit(locale)


def get_locale() -> str:
    """返回当前语言代码。"""
    return _current_locale


def _(text: str) -> str:
    """翻译字符串。zh-CN 时返回原文，其他语言查表。"""
    if _current_locale == "zh-CN":
        return text
    return _translations.get(_current_locale, {}).get(text, text)


# ---------------------------------------------------------------------------
# 自动加载
# ---------------------------------------------------------------------------

def reload_locales():
    """重新扫描并加载所有语言文件。"""
    global _translations
    _translations.clear()
    locale_dir = _locales_dir()
    if not os.path.isdir(locale_dir):
        return
    for fname in os.listdir(locale_dir):
        if fname.endswith(".json"):
            code = fname[:-5]
            path = os.path.join(locale_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "____display_name____" in data:
                    _LOCALE_NAMES[code] = data.pop("____display_name____")
                _translations[code] = data
            except Exception:
                pass


reload_locales()
