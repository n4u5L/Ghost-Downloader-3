from __future__ import annotations

import re
from pathlib import Path

from bkit import ui

from app.platform.file_dialog import openFolderDialog
from app.services.category_service import Category
from app.ui.components.category_settings import toCategoryName
from app.ui.components.message_box import MessageBoxBase
from app.ui.i18n import tr
from app.ui.icons import buildIconButton
from app.ui.layout import row, text
from app.ui.loop import UiLoop

WIDTH = 480
EXTENSION_SEPARATOR = re.compile(r"[\s,，;；]+")


def T(text: str) -> str:
    return tr("CategoryEditDialog", text)


class CategoryEditDialog(MessageBoxBase):
    """添加或编辑分类。Qt 界面的 TokenLineEdit 改为一个输入框，扩展名以空格或逗号分隔。"""

    ICON_CHOICES = [
        "DOCUMENT", "MUSIC", "VIDEO", "ZIP_FOLDER", "APPLICATION",
        "LIBRARY", "ALBUM", "PHOTO", "MOVIE", "MEDIA",
        "GAME", "CODE", "EDUCATION", "LANGUAGE", "BRUSH",
        "FOLDER", "CHAT", "MAIL", "PRINT", "GLOBE",
        "CAMERA", "IMAGE_EXPORT", "MUSIC_FOLDER", "MARKET", "HELP",
    ]

    def __init__(self, host: ui.Node, uiLoop: UiLoop, *, category: Category | None = None) -> None:
        super().__init__(host)
        self._category = category
        self._uiLoop = uiLoop
        self._initWidget()
        self._initLayout()
        self._populate()

    def _initWidget(self) -> None:
        self.dialog.set_title(T("编辑分类") if self._category else T("添加分类"))
        self.dialog.platform_default_width = WIDTH
        self.yesButton.text = T("确定")
        self.cancelButton.text = T("取消")
        self.nameEdit = ui.OutlinedTextField()
        self.nameEdit.set_placeholder(T("分类名称"))
        self.nameEdit.set_line_limits(single_line=True)
        self.iconCombo = ui.ExposedDropdownMenuBox(outlined=True)
        for name in self.ICON_CHOICES:
            self.iconCombo.add_option(name)
        self.iconCombo.selected_index = 0
        self.iconCombo.on_expanded_change = lambda isExpanded: setattr(self.iconCombo, "expanded", isExpanded)
        self.iconCombo.on_selected = lambda index: setattr(self.iconCombo, "selected_index", index)
        self.extensionsEdit = ui.OutlinedTextField()
        self.extensionsEdit.set_placeholder(T("输入扩展名后按回车添加"))
        self.extensionsEdit.set_line_limits(single_line=True)
        self.folderEdit = ui.OutlinedTextField()
        self.folderEdit.set_placeholder(T("留空则使用默认下载路径；可用 {default} 代表默认下载文件夹"))
        self.folderEdit.set_line_limits(single_line=True)
        self.folderBrowseBox, _ = buildIconButton("folder", T("选择文件夹"),
                                                  lambda: self._uiLoop.post(self._onBrowse))

    def _initLayout(self) -> None:
        for label, node in ((T("名称"), self.nameEdit), (T("图标"), self.iconCombo),
                            (T("扩展名"), self.extensionsEdit),
                            (T("下载文件夹"), row(self.folderEdit, self.folderBrowseBox, spacing=8, flex=0))):
            self.viewLayout.append_child(text(label))
            self.viewLayout.append_child(node)

    def _populate(self) -> None:
        if self._category is None:
            return
        self.nameEdit.state.text = toCategoryName(self._category)
        self.extensionsEdit.state.text = " ".join(self._category.extensions)
        self.folderEdit.state.text = self._category.folder or ""
        if self._category.icon in self.ICON_CHOICES:
            self.iconCombo.selected_index = self.ICON_CHOICES.index(self._category.icon)

    def _onBrowse(self) -> None:
        start = self.folderEdit.state.text.strip() or str(Path.home())
        if selected := openFolderDialog(T("选择下载文件夹"), start):
            self.folderEdit.state.text = selected

    def category(self) -> Category:
        name = self.nameEdit.state.text.strip() or "未命名分类"
        extensions: list[str] = []
        for token in EXTENSION_SEPARATOR.split(self.extensionsEdit.state.text):
            if (ext := token.strip().lstrip(".").lower()) and ext not in extensions:
                extensions.append(ext)
        folder = self.folderEdit.state.text.strip() or None
        index = self.iconCombo.selected_index
        icon = self.ICON_CHOICES[index] if index >= 0 else "DOCUMENT"

        if self._category is None:
            return Category(name=name, icon=icon, extensions=extensions, folder=folder)
        # 显示名未被改动时保留原文名，避免把译文烘焙进持久化数据
        if name == toCategoryName(self._category):
            name = self._category.name
        return Category(categoryId=self._category.categoryId, name=name, icon=icon, extensions=extensions,
                        folder=folder)
