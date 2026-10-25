from __future__ import annotations

from bkit import ui

from app.platform.file_dialog import openFileDialog
from app.services.plan import PlanAction
from app.ui.components.message_box import MessageBoxBase
from app.ui.i18n import tr
from app.ui.icons import buildIconButton
from app.ui.layout import row, text
from app.ui.loop import UiLoop


def T(text: str) -> str:
    return tr("PlanTaskDialog", text)


class PlanTaskDialog(MessageBoxBase):

    def __init__(self, host: ui.Node, uiLoop: UiLoop) -> None:
        super().__init__(host)
        self._uiLoop = uiLoop
        self._action = PlanAction.SHUTDOWN
        self._radios: dict[PlanAction, ui.RadioButton] = {}
        self._initWidget()
        self._initLayout()

    def _initWidget(self) -> None:
        self.dialog.set_title(T("设置计划任务"))
        self.contentLabel = text(T("所有任务完成后执行以下操作："))
        self.yesButton.text = T("确认")
        self.cancelButton.text = T("取消")
        self.pathEdit = ui.OutlinedTextField()
        self.pathEdit.set_placeholder(T("请选择要打开的文件"))
        self.pathEdit.set_line_limits(single_line=True)
        self.browseBox, _ = buildIconButton("folder", T("选择文件"), lambda: self._uiLoop.post(self._onBrowse))
        self.pathContainer = ui.Box()

    def _initLayout(self) -> None:
        self.viewLayout.append_child(self.contentLabel)
        options = ui.Column(spacing=4)
        for action, label in ((PlanAction.SHUTDOWN, T("关机")), (PlanAction.RESTART, T("重启")),
                              (PlanAction.SLEEP, T("睡眠")), (PlanAction.OPEN_FILE, T("打开文件"))):
            radio = ui.RadioButton(action == self._action, lambda a=action: self._setAction(a))
            self._radios[action] = radio
            options.append_child(row(radio, text(label), spacing=4))
        self.viewLayout.append_child(options)
        self.viewLayout.append_child(self.pathContainer)

    def selectedAction(self) -> PlanAction:
        return self._action

    def selectedFilePath(self) -> str:
        return self.pathEdit.state.text.strip()

    def close(self, isAccepted: bool) -> None:
        if isAccepted and self._action == PlanAction.OPEN_FILE and not self.selectedFilePath():
            self.pathEdit.is_error = True
            return
        super().close(isAccepted)

    def _setAction(self, action: PlanAction) -> None:
        self._action = action
        for value, radio in self._radios.items():
            radio.selected = value == action
        isOpenFile = action == PlanAction.OPEN_FILE
        if isOpenFile and not self.pathContainer.children:
            self.pathContainer.append_child(row(self.pathEdit, self.browseBox, spacing=8, flex=0))
        elif not isOpenFile and self.pathContainer.children:
            self.pathContainer.remove_child(0)

    def _onBrowse(self) -> None:
        paths = openFileDialog(T("选择文件"))
        if paths:
            self.pathEdit.state.text = paths[0]
            self.pathEdit.is_error = False
