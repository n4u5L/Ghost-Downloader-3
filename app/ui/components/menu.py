"""下拉菜单，对应 qfluentwidgets 的 RoundMenu、CheckableMenu。"""
from __future__ import annotations

from collections.abc import Callable

from bkit import ui

from app.ui.layout import column, text


def buildMenu(anchor: ui.Node) -> ui.DropdownMenu:
    """点外面或按 Esc 时收起的菜单；设 expanded = True 打开。"""
    menu = ui.DropdownMenu(anchor)
    menu.on_dismiss_request = lambda: setattr(menu, "expanded", False)
    return menu


def buildMenuAction(menu: ui.DropdownMenu, action: Callable[[], object]) -> Callable[[], None]:
    """菜单项的点击：先收起整串菜单（含子菜单），再执行动作，与 RoundMenu 的 Action 一致。"""
    def onClicked() -> None:
        menu.dismiss_all()
        action()
    return onClicked


def openMenuAt(menu: ui.DropdownMenu, anchor: ui.Node, x: float, y: float) -> None:
    """在 anchor 内 (x, y) 像素处打开菜单，对应 menu.exec(QCursor.pos())。"""
    density = anchor.density
    _, height = anchor.measured_size
    # 菜单默认在 anchor 下方，偏移量从那里算起
    menu.set_offset(x / density, (y - height) / density)
    menu.expanded = True


def openTeachingTip(anchor: ui.Node, title: str, content: str) -> ui.DropdownMenu:
    """锚在 anchor 下方的说明气泡，对应 qfluentwidgets 的 TeachingTip；点外面或按 Esc 关闭。"""
    menu = buildMenu(anchor)
    box = ui.Box()
    box.set_padding(16, 8)
    box.append_child(column(text(title, fontWeight=600), text(content, maxLines=12), spacing=8))
    menu.append_content(box)
    menu.expanded = True
    return menu
