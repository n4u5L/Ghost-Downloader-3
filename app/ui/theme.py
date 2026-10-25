from __future__ import annotations

import winreg

from bkit import ui

from app.config.cfg import cfg

PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
DWM_KEY = r"Software\Microsoft\Windows\DWM"
# MD3 基线配色的 onSurface：BasicTextField 不跟随主题，默认画黑字
LIGHT_CONTENT_COLOR = 0xFF1D1B20
DARK_CONTENT_COLOR = 0xFFE6E0E9


def readUserDword(keyPath: str, name: str) -> int | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyPath) as key:
            value, kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if kind == winreg.REG_DWORD else None


def isSystemDark() -> bool:
    return readUserDword(PERSONALIZE_KEY, "AppsUseLightTheme") == 0


def systemAccentColor() -> int | None:
    # DWM 存的是 0xAABBGGRR
    value = readUserDword(DWM_KEY, "AccentColor")
    if value is None:
        return None
    red, green, blue = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
    return 0xFF000000 | (red << 16) | (green << 8) | blue


def isDark() -> bool:
    mode = cfg.themeMode.value.value
    if mode == "Auto":
        return isSystemDark()
    return mode == "Dark"


def themeModeOption(name: str):
    return next(option for option in cfg.themeMode.options if option.value == name)


def contentColor() -> int:
    return DARK_CONTENT_COLOR if isDark() else LIGHT_CONTENT_COLOR


def colorOf(node: ui.Node, role: str) -> int | None:
    """node 所在 MaterialTheme 的颜色角色，如 primary；node 不在主题之下时为 None。"""
    parent = node.parent
    while parent is not None:
        if isinstance(parent, ui.MaterialTheme):
            return parent.color_scheme[role]
        parent = parent.parent
    return None
