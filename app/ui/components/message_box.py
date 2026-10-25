"""对话框，对应 qfluentwidgets 的 MessageBoxBase 和 MessageBox。

bkit 的 AlertDialog 不阻塞：exec() 的返回值改由 accepted、rejected 信号送出。
按钮行放在正文里而不用 AlertDialog 的两个按钮槽，布局同 Qt：确认在前、取消在后，各按钮等宽撑满一行，
也能像 Qt 一样插入第三个按钮。正文可滚动，按钮行始终可见。默认按钮文字与 qfluentwidgets 一样是 OK / Cancel。
"""
from __future__ import annotations

from collections.abc import Callable

from bkit import ui

from app.signal import Signal
from app.ui.i18n import tr
from app.ui.layout import EqualRow, column


def T(text: str) -> str:
    return tr("MessageBox", text)


class MessageBoxBase:
    accepted = Signal()
    rejected = Signal()

    def __init__(self, host: ui.Node) -> None:
        self._isOpen = False
        self.dialog = ui.AlertDialog(host, self._onCancelClicked)
        self.viewLayout = column(spacing=12)
        self.yesButton = ui.Button(T("OK"), self._onYesClicked, ui.ButtonStyle.FILLED)
        self.cancelButton = ui.Button(T("Cancel"), self._onCancelClicked, ui.ButtonStyle.OUTLINED)
        self.buttonLayout = EqualRow(self.yesButton, self.cancelButton, spacing=12)
        scroll = ui.ScrollContainer()
        scroll.append_child(self.viewLayout)
        # 标题行可插到 contentLayout 最前，按钮行可移除，对应 Qt 对话框各自的布局
        self.contentLayout = column(scroll, self.buttonLayout, spacing=16, flex=0, isMainFilled=False)
        self.dialog.set_text_content(self.contentLayout)

    @property
    def isOpen(self) -> bool:
        return self._isOpen

    def insertButton(self, index: int, label: str, onClick: Callable[[], object],
                     style: ui.ButtonStyle = ui.ButtonStyle.OUTLINED) -> ui.Button:
        """对应 buttonLayout.insertWidget(index, button)：0 是最左边，确认按钮的位置。"""
        button = ui.Button(label, onClick, style)
        self.buttonLayout.insert_child(index, button)
        return button

    def open(self) -> None:
        self._isOpen = True
        self.dialog.show()

    def close(self, isAccepted: bool) -> None:
        if not self._isOpen:
            return
        self._isOpen = False
        if self.dialog.is_open:
            self.dialog.close()
        if isAccepted:
            self.accepted.emit()
        else:
            self.rejected.emit()

    def _onYesClicked(self) -> None:
        self.close(True)

    def _onCancelClicked(self) -> None:
        self.close(False)


class MessageBox(MessageBoxBase):
    def __init__(self, title: str, content: str, host: ui.Node) -> None:
        super().__init__(host)
        if title:
            self.dialog.set_title(title)
        self.contentLabel = ui.Text(content)
        self.viewLayout.append_child(self.contentLabel)


def openMessageBox(title: str, content: str, host: ui.Node, onAccepted: Callable[[], object],
                   onRejected: Callable[[], object] | None = None) -> MessageBox:
    box = MessageBox(title, content, host)
    box.accepted.connect(onAccepted)
    if onRejected is not None:
        box.rejected.connect(onRejected)
    box.open()
    return box
