from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bkit import ui

from app.client import PROFILE_FAMILY_LABELS
from app.config.cfg import cfg
from app.ui.components.editors import FolderPicker, Post
from app.ui.i18n import tr
from app.ui.icons import buildIcon
from app.ui.layout import column, row, text

ICON_SIZE = 16


def toProfileLabel(value: str) -> str:
    if value in {"", "auto"}:
        return tr("ClientProfileCard", "自动（匹配来源）")
    if value == "raw":
        return tr("ClientProfileCard", "不模拟（原样发送）")
    if value in PROFILE_FAMILY_LABELS:
        return tr("ClientProfileCard", "{0}（最新）").format(PROFILE_FAMILY_LABELS[value])
    head = value.rstrip("0123456789_")
    version = value[len(head):].replace("_", ".")
    return f"{head} {version}" if version else value


def addProfileItems(menu: ui.DropdownMenu, onPick: Callable[[str], object], *, includeAuto: bool = True) -> None:
    """TLS 指纹的选项，对应 buildProfileMenu：自动或跟随默认、不模拟，再按浏览器家族分子菜单列出各版本。"""
    from app.client import profileFamilies, profileVersions
    from app.ui.components.menu import buildMenuAction
    from app.ui.icons import loadIcon

    first = "auto" if includeAuto else ""
    item = menu.add_item(toProfileLabel(first), buildMenuAction(menu, lambda: onPick(first)))
    if includeAuto:
        item.set_leading_icon(loadIcon("bolt"))
    menu.add_item(toProfileLabel("raw"), buildMenuAction(menu, lambda: onPick("raw")))
    menu.add_divider()
    for family in profileFamilies():
        submenu = menu.add_submenu(PROFILE_FAMILY_LABELS.get(family, family))
        submenu.add_item(toProfileLabel(family), buildMenuAction(submenu, lambda f=family: onPick(f)))
        submenu.add_divider()
        for name in profileVersions(family):
            submenu.add_item(toProfileLabel(name), buildMenuAction(submenu, lambda v=name: onPick(v)))


class OptionCard(ui.Node):
    """新建任务时的一项下载设置：上方一条分隔线，一行图标、标题和控件。"""

    def __init__(self, icon: str, title: str) -> None:
        super().__init__()
        self.iconWidget = buildIcon(icon, ICON_SIZE)
        self.titleLabel = text(title)
        self.hBoxLayout = row(self.iconWidget, self.titleLabel, ui.Spacer(), spacing=16, flex=2)
        box = ui.Box()
        box.set_padding(16, 4)
        box.append_child(self.hBoxLayout)
        self.append_child(column(ui.HorizontalDivider(), box))

    def addControl(self, node: ui.Node) -> None:
        self.hBoxLayout.append_child(node)

    def options(self) -> dict:
        return {}

    def reset(self) -> None:
        pass


class OutputFolderCard(OptionCard):
    def __init__(self, post: Post, *, initial: Path | None = None) -> None:
        super().__init__("download", tr("OutputFolderCard", "选择下载路径"))
        self.folderPicker = FolderPicker(lambda: cfg.downloadFolder.value, tr("OutputFolderCard", "默认"), post)
        self.folderPicker.setPath(str(initial) if initial else cfg.downloadFolder.value)
        box = ui.Box()
        box.set_size(400, None)
        box.append_child(self.folderPicker)
        self.addControl(box)

    def options(self) -> dict:
        return {"outputFolder": Path(self.folderPicker.path())}

    def reset(self) -> None:
        self.folderPicker.setPath(cfg.downloadFolder.value)


class SubworkerCountCard(OptionCard):
    def __init__(self, initial: int = 0) -> None:
        super().__init__("cloud", tr("SubworkerCountCard", "预分配线程数"))
        minimum, maximum = cfg.preBlockNum.range
        value = initial or cfg.preBlockNum.value
        self.valueLabel = text(str(value))
        self.slider = ui.Slider(value, self._onValueChange, minimum=minimum, maximum=maximum,
                                steps=max(0, maximum - minimum - 1))
        self.slider.set_width(268)
        self.addControl(row(self.valueLabel, self.slider, spacing=8))

    def options(self) -> dict:
        return {"subworkerCount": round(self.slider.value)}

    def reset(self) -> None:
        self._onValueChange(cfg.preBlockNum.value)

    def _onValueChange(self, value: float) -> None:
        self.slider.value = value
        self.valueLabel.text = str(round(value))
