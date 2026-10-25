from dataclasses import dataclass

from bkit import ui

from app.i18n import tr
from app.ui.components.media import parseTime, toTime
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.setting_cards import fixedWidth
from app.ui.layout import column, row, text


@dataclass
class MediaFileEdit:
    file: object
    name: str
    start: int
    end: int


class MediaSelectDialog(MessageBoxBase):
    def __init__(self, task, host, *, rename=None, update=None, groups=None, renameGroup=None):
        super().__init__(host)
        self.task, self._rename, self._update = task, rename, update
        self._renameGroup = renameGroup
        self._groupNames = {}
        self._selected = {file.index for file in task.files or [] if file.selected}
        self._edits: dict[int, MediaFileEdit] = {}
        self._files = list(task.files or [])
        self._rows = []
        self._invalid = set()
        self.dialog.set_title(tr("VideoSelectDialog", "选择文件与截取片段"))
        self.dialog.platform_default_width = 760
        self.summary = text()
        self.warning = text()
        self.viewLayout.append_child(row(
            ui.Button(tr("SelectDialog", "全选"), lambda: self._setAll(True)),
            ui.Button(tr("SelectDialog", "全不选"), lambda: self._setAll(False)),
            ui.Button(tr("SelectDialog", "反选"), self._invert), self.summary, spacing=8))
        for label, files in groups or [("", self._files)]:
            if label:
                self._rows.append((label, files))
            self._rows.extend((None, [file]) for file in files)
        self.list = ui.LazyColumn()
        self.list.set_item_provider(len(self._rows), self._createRow)
        box = ui.Box()
        box.set_size(None, min(480, 64 * len(self._rows)))
        box.append_child(self.list)
        self.viewLayout.append_child(box)
        self.viewLayout.append_child(self.warning)
        self._refreshSummary()

    def _createRow(self, index):
        label, files = self._rows[index]
        if label is not None:
            box = ui.Checkbox(all(file.index in self._selected for file in files))
            box.on_checked_change = lambda checked: self._setGroup(files, checked)
            if self._renameGroup:
                key = tuple(file.index for file in files)
                edit = ui.OutlinedTextField(ui.TextFieldState(self._groupNames.get(key, (files, label))[1]))
                edit.set_line_limits(single_line=True)
                edit.on_value_change = lambda: self._groupNames.__setitem__(key, (files, edit.state.text))
                return row(box, edit, spacing=8, flex=1)
            return row(box, text(label, fontWeight=600), spacing=8)
        file = files[0]
        selected = ui.Checkbox(file.index in self._selected)
        selected.on_checked_change = lambda checked: self._setFile(selected, file.index, checked)
        edit = self._edits.get(file.index)
        name = edit.name if edit else self.task.toDisplayPath(file)
        start = edit.start if edit else getattr(file, "startTime", 0)
        end = edit.end if edit else getattr(file, "endTime", 0)
        nameEdit = ui.OutlinedTextField(ui.TextFieldState(name))
        nameEdit.set_line_limits(single_line=True)
        startEdit = ui.OutlinedTextField(ui.TextFieldState(toTime(start)))
        endEdit = ui.OutlinedTextField(ui.TextFieldState(toTime(end)))
        for edit in (startEdit, endEdit):
            edit.set_line_limits(single_line=True)
        nameEdit.on_value_change = lambda: self._setName(file, nameEdit.state.text)
        startEdit.on_value_change = lambda: self._setTime(file, startEdit, "start")
        endEdit.on_value_change = lambda: self._setTime(file, endEdit, "end")
        return row(selected, nameEdit, fixedWidth(startEdit, 100), fixedWidth(endEdit, 100), spacing=8, flex=1)

    def _editByFile(self, file):
        if file.index not in self._edits:
            self._edits[file.index] = MediaFileEdit(file, self.task.toDisplayPath(file),
                getattr(file, "startTime", 0), getattr(file, "endTime", 0))
        return self._edits[file.index]

    def _setName(self, file, value):
        self._editByFile(file).name = value.strip()

    def _setTime(self, file, edit, position):
        try:
            value = parseTime(edit.state.text)
            duration = getattr(file, "duration", getattr(file, "_duration", 0))
            edit.is_error = bool(duration and value > duration)
            if not edit.is_error:
                setattr(self._editByFile(file), position, value)
        except ValueError:
            edit.is_error = True
        if edit.is_error:
            self._invalid.add((file.index, position))
        else:
            self._invalid.discard((file.index, position))

    def _setFile(self, box, index, checked):
        box.checked = checked
        self._selected.add(index) if checked else self._selected.discard(index)
        self._refreshSummary()

    def _setGroup(self, files, checked):
        for file in files:
            self._selected.add(file.index) if checked else self._selected.discard(file.index)
        self.list.notify_data_set_changed(len(self._rows))
        self._refreshSummary()

    def _setAll(self, checked):
        self._setGroup(self._files, checked)

    def _invert(self):
        self._selected = {file.index for file in self._files if file.index not in self._selected}
        self.list.notify_data_set_changed(len(self._rows))
        self._refreshSummary()

    def _refreshSummary(self):
        self.summary.text = f"{len(self._selected)}/{len(self._files)}"

    def _onYesClicked(self):
        if self._invalid:
            self.warning.text = tr("RangeSlider", "请修正时间输入")
            return
        if not self._selected:
            self.warning.text = tr("SelectDialog", "请至少选择一个文件")
            return
        for edit in self._edits.values():
            if edit.end and edit.end <= edit.start:
                self.warning.text = tr("RangeSlider", "结束时间必须晚于开始时间")
                return
        for edit in self._edits.values():
            edit.file.startTime, edit.file.endTime = edit.start, edit.end
            if self._rename and edit.name:
                self._rename(edit.file.index, edit.name)
        self.task.setSelection(self._selected)
        for files, name in self._groupNames.values():
            if name.strip():
                self._renameGroup(files, name)
        if self._update:
            self._update()
        self.close(True)

    def close(self, isAccepted):
        if not self.isOpen:
            return
        super().close(isAccepted)
        self.list.notify_data_set_changed(0)
        self._rows.clear()
        self._files.clear()
        self._edits.clear()
        self._groupNames.clear()
        self._selected.clear()
        self._invalid.clear()
        self.task = self._rename = self._update = self._renameGroup = None
