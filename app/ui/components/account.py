from bkit import ui

from app.i18n import tr
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.setting_cards import SettingCard
from app.ui.layout import row


class CookieCard(SettingCard):
    def __init__(self, title, load, save, clear):
        super().__init__("security", title)
        self._load, self._save, self._clear = load, save, clear
        self._dialog = None
        self.actions = row(ui.Button(tr("YtDlpConfig", "导入 Cookie"), self._onEdit),
                           ui.Button(tr("YtDlpConfig", "清除 Cookie"), self._onClear), spacing=8)
        self.setControl(self.actions)
        self.refresh()

    def refresh(self, *_):
        self.setContent(tr("YtDlpConfig", "已导入") if self._load() else tr("YtDlpConfig", "未导入"))

    def _onEdit(self):
        dialog = MessageBoxBase(self)
        dialog.dialog.set_title(tr("YtDlpConfig", "导入 Cookie"))
        edit = ui.OutlinedTextField(ui.TextFieldState(self._load()))
        edit.set_line_limits(min_lines=4, max_lines=8)
        dialog.viewLayout.append_child(edit)
        dialog.accepted.connect(lambda: self._onSaved(edit.state.text))
        self._dialog = dialog
        dialog.open()

    def _onSaved(self, value):
        self._save(value)
        self.refresh()

    def _onClear(self):
        self._clear()
        self.refresh()
