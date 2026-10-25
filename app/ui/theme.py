from __future__ import annotations

import winreg

from bkit import ui

from app.config.cfg import cfg

PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
# MD3 蓝色主色调的种子色：主色、背景、文字、错误色等全部按 MD3 动态配色（Tonal Spot）由它生成，
# 浅色下 primary 为 #36618E，深色下为 #A0CAFD
SEED_COLOR = 0xFF0061A4
# MD3 没有成功、警告角色，按 MD3 自定义颜色的做法由各自的种子色生成色调盘，取与 primary 相同的色调
STATUS_SEEDS = {"success": 0xFF2E7D32, "warning": 0xFFC8A050}

# 按种子色和深浅色缓存的配色，主题以外的节点用它取色
schemes: dict[tuple[int, bool], dict[str, int]] = {}


def readUserDword(keyPath: str, name: str) -> int | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyPath) as key:
            value, kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if kind == winreg.REG_DWORD else None


def isSystemDark() -> bool:
    return readUserDword(PERSONALIZE_KEY, "AppsUseLightTheme") == 0


def isDark() -> bool:
    mode = cfg.themeMode.value.value
    if mode == "Auto":
        return isSystemDark()
    return mode == "Dark"


def themeModeOption(name: str):
    return next(option for option in cfg.themeMode.options if option.value == name)


def createTheme() -> ui.MaterialTheme:
    return ui.MaterialTheme(dark=isDark(), seed=SEED_COLOR)


def applyColorScheme(theme: ui.MaterialTheme) -> None:
    """换主题后按当前深浅色重新生成 theme 的配色。"""
    theme.set_color_scheme(dark=isDark(), seed=SEED_COLOR)


def schemeOf(seed: int, dark: bool | None = None) -> dict[str, int]:
    if dark is None:
        dark = isDark()
    scheme = schemes.get((seed, dark))
    if scheme is None:
        scheme = schemes[seed, dark] = ui.MaterialTheme(dark=dark, seed=seed).color_scheme
    return scheme


def schemeColor(role: str, dark: bool | None = None) -> int:
    """当前深浅色（或指定深浅色）配色的颜色角色，如 primary、error；用于还没挂到主题下的节点。"""
    return schemeOf(SEED_COLOR, dark)[role]


def statusColor(status: str, dark: bool | None = None) -> int:
    """success、warning 或 error 的颜色：error 是配色的 error 角色，另两种是自定义颜色。"""
    if status == "error":
        return schemeColor("error", dark)
    return schemeOf(STATUS_SEEDS[status], dark)["primary"]


def contentColor() -> int:
    # BasicTextField 不跟随主题，默认画黑字
    return schemeColor("on_surface")


def colorOf(node: ui.Node, role: str) -> int | None:
    """node 所在 MaterialTheme 的颜色角色，如 primary；node 不在主题之下时为 None。"""
    parent = node.parent
    while parent is not None:
        if isinstance(parent, ui.MaterialTheme):
            return parent.color_scheme[role]
        parent = parent.parent
    return None
