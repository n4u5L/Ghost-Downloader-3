from bkit import ui

from app.config.cfg import cfg
from app.i18n import tr
from app.ui.components.setting_cards import SettingCard
from app.ui.layout import column, row


class ProxySiteCard(SettingCard):
    def __init__(self, title, config, sites, customKey, runner, probe, *, autoKey=None):
        super().__init__("public", title)
        self._config, self._runner, self._probe = config, runner, probe
        self._options = ([autoKey] if autoKey is not None else []) + list(sites) + [customKey]
        self.combo = ui.ExposedDropdownMenuBox(outlined=True)
        self.combo.on_expanded_change = lambda value: setattr(self.combo, "expanded", value)
        for value in self._options:
            self.combo.add_option(tr("GitHubProxySiteCard", "自动") if value == autoKey else (
                tr("GitHubProxySiteCard", "自定义") if value == customKey else value))
        current = config.selectedSite.value
        self.combo.selected_index = self._options.index(current) if current in self._options else 0
        self.combo.on_selected = self._onSelected
        self.customEdit = ui.OutlinedTextField(ui.TextFieldState(config.customSite.value))
        self.customEdit.set_line_limits(single_line=True)
        self.customEdit.set_placeholder("https://example.com")
        self.customEdit.on_value_change = self._onCustomChanged
        self.refreshButton = ui.Button(tr("GitHubProxySiteCard", "刷新延迟"), self._onRefresh)
        self.setControl(row(self.combo, self.refreshButton, spacing=8))
        self.vBoxLayout.append_child(self.customEdit)

    def _onSelected(self, index):
        self.combo.selected_index = index
        cfg.set(self._config.selectedSite, self._options[index])

    def _onCustomChanged(self):
        value = self.customEdit.state.text.strip()
        self.customEdit.is_error = bool(value) and not self._config.customSite.validator.validate(value)
        if not self.customEdit.is_error:
            cfg.set(self._config.customSite, value)

    def _onRefresh(self):
        self.refreshButton.enabled = False
        self._runner.submit(self._probe(), done=self._onLatencies,
                            failed=lambda error: self._onFailed(error))

    def _onLatencies(self, values):
        self.refreshButton.enabled = True
        self.setContent("\n".join(f"{site}: {latency} ms" if latency >= 0 else f"{site}: —"
                                  for site, latency in values.items()))

    def _onFailed(self, error):
        self.refreshButton.enabled = True
        self.setContent(str(error))
