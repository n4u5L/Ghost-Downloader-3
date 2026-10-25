from __future__ import annotations

from datetime import datetime

from bkit import ui

from app.format import toReadableSize
from app.services.name_conflict_queue import NameConflict, NameConflictQueue
from app.services.task_service import NameConflictChoice
from app.ui.components.message_box import MessageBox
from app.ui.i18n import tr
from app.ui.layout import checkBox


def T(text: str) -> str:
    return tr("NameConflictDialog", text)


def toContentText(conflict: NameConflict) -> str:
    modified = datetime.fromtimestamp(conflict.modifiedAt).strftime("%Y-%m-%d %H:%M")
    if conflict.isFolder:
        existing = T("现有文件夹：{0} 修改").format(modified)
    else:
        existing = T("现有文件：{0}，{1} 修改").format(toReadableSize(conflict.existingSize), modified)
    newSize = toReadableSize(conflict.task.fileSize) if conflict.task.fileSize > 0 else T("未知大小")
    return "\n".join([existing, T("新文件：{0}").format(newSize), T("覆盖时，旧文件会移到回收站。")])


class NameConflictDialog(MessageBox):

    def __init__(self, conflict: NameConflict, queue: NameConflictQueue, host: ui.Node) -> None:
        super().__init__(T("下载目录中已有 {0}").format(conflict.takenPath.name), toContentText(conflict), host)
        self._conflict = conflict
        self._queue = queue
        self._choice = NameConflictChoice.KEEP_BOTH
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.yesButton.text = T("保留两者")
        self.cancelButton.text = T("取消")
        self.restRow, self.restCheckBox = checkBox(
            T("对其余 {0} 个冲突执行相同操作").format(self._conflict.restCount))

    def _initLayout(self) -> None:
        if self._conflict.restCount > 0:
            self.viewLayout.append_child(self.restRow)
        self.overwriteButton = self.insertButton(1, T("覆盖"), self._onOverwriteClicked)

    def _bind(self) -> None:
        self.accepted.connect(self._onAccepted)
        self.rejected.connect(self._onRejected)

    def _onOverwriteClicked(self) -> None:
        self._choice = NameConflictChoice.OVERWRITE
        self.close(True)

    def _onAccepted(self) -> None:
        self._queue.setChoice(self._conflict.task.taskId, self._choice, self.restCheckBox.checked)

    def _onRejected(self) -> None:
        self._queue.cancel(self._conflict.task.taskId)


class NameConflictPrompt:
    """队列给出冲突时弹出对话框；冲突换了或没了，旧的对话框随之关闭。"""

    def __init__(self, queue: NameConflictQueue, host: ui.Node) -> None:
        self._queue = queue
        self._host = host
        self._dialog: NameConflictDialog | None = None
        queue.conflictChanged.connect(self._onConflictChanged)

    def _onConflictChanged(self, conflict: NameConflict | None) -> None:
        if self._dialog is not None and self._dialog.isOpen:
            # 冲突已由队列处理，关掉旧对话框时不再回报选择
            self._dialog.accepted.disconnect()
            self._dialog.rejected.disconnect()
            self._dialog.close(False)
        self._dialog = None
        if conflict is None:
            return
        self._dialog = NameConflictDialog(conflict, self._queue, self._host)
        self._dialog.open()
