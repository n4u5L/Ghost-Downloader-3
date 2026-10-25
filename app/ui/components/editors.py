from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bkit import ui

from app.config.cfg import cfg
from app.platform.file_dialog import openFolderDialog
from app.signal import Signal
from app.ui.components.menu import buildMenu, buildMenuAction
from app.i18n import tr
from app.ui.icons import buildIcon, buildIconButton
from app.ui.layout import row, text
from app.ui.loop import SingleShotTimer, Timer
from app.ui.theme import colorOf

EDIT_DELAY = 0.5

Post = Callable[[Callable[[], object], float], Timer]


def T(text: str) -> str:
    return tr("FolderPicker", text)


class FolderPicker(ui.Node):
    """路径输入框、常用文件夹菜单和浏览按钮。

    pinnedPath 是菜单第一项（如默认下载路径），pinnedLabel 是它的说明。输入停顿后若是存在的目录，
    或从菜单、浏览对话框选了目录，发出 pathChanged。
    """

    pathChanged = Signal(str)

    def __init__(self, pinnedPath: Callable[[], str], pinnedLabel: str, post: Post) -> None:
        super().__init__()
        self._pinnedPath = pinnedPath
        self._pinnedLabel = pinnedLabel
        self._post = post
        self._isSettingPath = False
        self._editTimer = SingleShotTimer(post, EDIT_DELAY, self._onEditingFinished)
        self._menu: ui.DropdownMenu | None = None
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.lineEdit = ui.OutlinedTextField()
        self.lineEdit.set_line_limits(single_line=True)
        self.menuButton = ui.IconButton(ui.MaterialIcon.ARROW_DROP_DOWN, self._openMenu)
        menuBox = ui.TooltipBox(self.menuButton)
        menuBox.set_plain_tooltip(T("常用文件夹"))
        self.lineEdit.set_trailing_content(menuBox)
        self.browseBox, self.browseButton = buildIconButton("folder", T("浏览文件夹"))

    def _initLayout(self) -> None:
        self.append_child(row(self.lineEdit, self.browseBox, spacing=8, flex=0))

    def _bind(self) -> None:
        self.lineEdit.on_value_change = self._onValueChange
        self.lineEdit.on_keyboard_action = self._onEditingFinished
        # 系统对话框有自己的模态循环，放到 bkit 的回调之外运行
        self.browseButton.on_click = lambda: self._post(self._onBrowse, 0.0)

    def path(self) -> str:
        return self.lineEdit.state.text.strip()

    def setPath(self, path: str) -> None:
        self._isSettingPath = True
        try:
            self.lineEdit.state.text = path
        finally:
            self._isSettingPath = False
        self.lineEdit.is_error = False

    def _onPathPicked(self, path: str) -> None:
        self.setPath(path)
        self.pathChanged.emit(path)

    def _onValueChange(self) -> None:
        if not self._isSettingPath:
            self._editTimer.start()

    def _onEditingFinished(self) -> None:
        self._editTimer.stop()
        path = self.path()
        self.lineEdit.is_error = not path or not Path(path).is_dir()
        if not self.lineEdit.is_error:
            self.pathChanged.emit(path)

    def _onBrowse(self) -> None:
        folder = openFolderDialog(T("选择文件夹"), self.path())
        if folder:
            self._onPathPicked(folder)

    def _openMenu(self) -> None:
        menu = buildMenu(self.lineEdit)
        pinned = self._pinnedPath()
        item = menu.add_item(pinned, buildMenuAction(menu, lambda: self._onPathPicked(pinned)))
        item.label.overflow = ui.TextOverflow.MIDDLE_ELLIPSIS
        item.set_trailing_text(self._pinnedLabel)
        for folder in cfg.recentFolders.value:
            if Path(folder) == Path(pinned):
                continue
            item = menu.add_item(folder, buildMenuAction(menu, lambda f=folder: self._onPathPicked(f)))
            item.label.overflow = ui.TextOverflow.MIDDLE_ELLIPSIS
            deleteButton = ui.IconButton(ui.MaterialIcon.CLOSE, lambda f=folder: self._onRecentFolderDeleted(f))
            deleteBox = ui.TooltipBox(deleteButton)
            deleteBox.set_plain_tooltip(T("从常用文件夹中移除"))
            item.set_trailing_content(deleteBox)
        self._menu = menu
        menu.expanded = True

    def _onRecentFolderDeleted(self, folder: str) -> None:
        cfg.set(cfg.recentFolders, [item for item in cfg.recentFolders.value if item != folder])
        if self._menu is not None:
            self._menu.dismiss_all()
        self._openMenu()


class SearchLineEdit(ui.Node):
    """对应 qfluentwidgets 的 SearchLineEdit，画成 MD3 的搜索栏：圆角底色、占位文字、清除按钮和搜索图标。

    BasicTextField 不跟随主题，颜色在挂上主题后和换主题时由 refreshColors() 取主题的角色色。
    """

    textChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.lineEdit = ui.BasicTextField()
        self.lineEdit.set_line_limits(single_line=True)
        self.placeholderLabel = text()
        self.placeholderSlot = ui.Box()
        self.placeholderSlot.append_child(self.placeholderLabel)
        self.clearButton = ui.IconButton(ui.MaterialIcon.CLOSE, self.clear)
        self.clearSlot = ui.Box()
        self.searchIcon = buildIcon("search", 20)

    def _initLayout(self) -> None:
        stack = ui.Box()
        stack.set_content_alignment(ui.Alignment.START, ui.Alignment.CENTER)
        # 单子节点的 row 撑满宽度、高度随内容，点在空白处也能聚焦
        stack.append_child(row(self.lineEdit, flex=0))
        stack.append_child(self.placeholderSlot)
        self.box = ui.Box()
        self.box.set_padding(16, 0, 8, 0)
        self.box.set_min_size(0, 40)
        # 最小高度比内容高，Box 默认顶部对齐，要竖直居中
        self.box.set_content_alignment(ui.Alignment.START, ui.Alignment.CENTER)
        self.box.set_corner_radius(20)
        self.box.append_child(row(stack, self.clearSlot, self.searchIcon, spacing=4, flex=0))
        self.append_child(self.box)

    def _bind(self) -> None:
        self.lineEdit.on_value_change = self._onValueChange

    def text(self) -> str:
        return self.lineEdit.state.text

    def setPlaceholderText(self, value: str) -> None:
        self.placeholderLabel.text = value

    def clear(self) -> None:
        self.lineEdit.state.text = ""

    def setFocus(self) -> None:
        self.lineEdit.request_focus()
        self.lineEdit.state.edit(lambda buffer: buffer.select_all())

    def refreshColors(self) -> None:
        textColor = colorOf(self, "on_surface")
        if textColor is None:
            return
        self.lineEdit.set_text_color(textColor)
        self.lineEdit.set_cursor_color(colorOf(self, "primary") or textColor)
        self.placeholderLabel.set_color(colorOf(self, "on_surface_variant") or textColor)
        self.box.set_background(colorOf(self, "surface_container_high") or 0)

    def on_attach(self) -> None:
        super().on_attach()
        self.refreshColors()

    def _onValueChange(self) -> None:
        isEmpty = not self.lineEdit.state.text
        if isEmpty and not self.placeholderSlot.children:
            self.placeholderSlot.append_child(self.placeholderLabel)
            self.clearSlot.remove_child(0)
        elif not isEmpty and self.placeholderSlot.children:
            self.placeholderSlot.remove_child(0)
            self.clearSlot.append_child(self.clearButton)
        self.textChanged.emit(self.lineEdit.state.text)
