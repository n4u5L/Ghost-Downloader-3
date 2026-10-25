from __future__ import annotations

import json
from functools import partial
from collections.abc import Callable

from bkit import ui

from app.config.cfg import cfg
from app.config.store import OptionsConfigItem, RangeConfigItem
from app.i18n import toLocalizedError, tr
from app.models.task import toTaskError
from app.platform.file_dialog import openFileDialog
from app.ui.components.editors import FolderPicker
from app.ui.components.option_cards import OptionCard, OutputFolderCard, addProfileItems, toProfileLabel
from app.ui.components.setting_cards import (
    ComboBoxSettingCard, LineEditSettingCard, SettingCard, SpinBoxSettingCard, SwitchSettingCard, fixedWidth,
)
from app.ui.components.setting_card_group import SettingCardGroup
from app.ui.layout import column, row, text


class TextOption(OptionCard):
    def __init__(self, title, value, save: Callable, *, parse=str, multiline=False):
        super().__init__("edit", title)
        self._save, self._parse = save, parse
        self.edit = ui.OutlinedTextField(ui.TextFieldState(str(value)))
        self.edit.set_line_limits(single_line=not multiline, min_lines=1, max_lines=4 if multiline else 1)
        self.addControl(fixedWidth(self.edit, 340))

    def apply(self) -> bool:
        try:
            value = self._parse(self.edit.state.text)
            self._save(value)
        except (ValueError, TypeError) as error:
            self.edit.is_error = True
            self.edit.set_supporting_text(str(error))
            return False
        self.edit.is_error = False
        return True


class TaskFolderOption(OutputFolderCard):
    def __init__(self, task, post):
        self._task, self._initial = task, task.outputFolder
        super().__init__(post, initial=task.outputFolder)

    def overrides(self):
        value = self.options()
        return value if value["outputFolder"] != self._initial else {}

    def apply(self):
        self._task.setOptions(self.overrides())
        return True


class WorkerOption(TextOption):
    def __init__(self, task):
        self._task = task
        self._initial = task.steps[0].subworkerCount
        super().__init__(tr("SubworkerCountCard", "预分配线程数"), self._initial,
                          lambda value: task.setOptions({"subworkerCount": value}), parse=self._parseCount)

    def _parseCount(self, value):
        count = int(value)
        if not 1 <= count <= 256:
            raise ValueError("1–256")
        return count

    def overrides(self):
        value = self._parseCount(self.edit.state.text)
        return {"subworkerCount": value} if value != self._initial else {}

    def apply(self):
        try:
            self._task.setOptions(self.overrides())
            self.edit.is_error = False
            return True
        except ValueError:
            self.edit.is_error = True
            return False


class ProfileOption(OptionCard):
    def __init__(self, task):
        super().__init__("smart_toy", tr("ClientProfileCard", "模拟身份"))
        self.task = task
        step = task.steps[0]
        self._value, self._userAgent = step.clientProfile, step.userAgent
        self.button = ui.Button(toProfileLabel(self._value), self._onMenu)
        self.addControl(self.button)
        self.menu = None

    def _onMenu(self):
        from app.ui.components.menu import buildMenu, buildMenuAction
        self.menu = buildMenu(self.button)
        addProfileItems(self.menu, self._setProfile)
        for preset in cfg.identityPresets.value:
            self.menu.add_item(preset["name"], buildMenuAction(self.menu, lambda preset=preset: self._setPreset(preset)))
        self.menu.expanded = True

    def _setProfile(self, value):
        self._value, self._userAgent = value, ""
        self.button.text = toProfileLabel(value)
        self.apply()

    def _setPreset(self, preset):
        self._value, self._userAgent = preset["clientProfile"], preset["userAgent"]
        self.button.text = preset["name"]
        self.apply()

    def apply(self):
        self.task.setOptions({"clientProfile": self._value, "userAgent": self._userAgent})
        return True


class ChoiceOption(OptionCard):
    def __init__(self, title, choices, current, save: Callable):
        super().__init__("select", title)
        self._choices, self._save = choices, save
        self.combo = ui.ExposedDropdownMenuBox()
        for value, label in choices:
            self.combo.add_option(str(label))
        self.combo.selected_index = next((i for i, (value, _) in enumerate(choices) if value == current), 0)
        self.combo.on_selected = self._onSelected
        self.combo.on_expanded_change = lambda expanded: setattr(self.combo, "expanded", expanded)
        self.addControl(self.combo)

    def _onSelected(self, index):
        self.combo.selected_index = index
        self.apply()

    def apply(self) -> bool:
        if self._choices:
            self._save(self._choices[self.combo.selected_index][0])
        return True


class FileOption(TextOption):
    def __init__(self, title, value, save, post):
        super().__init__(title, value, save)
        self._post = post
        self.addControl(ui.Button(tr("SelectFileCard", "浏览"), lambda: post(self._onBrowse)))

    def _onBrowse(self):
        paths = openFileDialog(self.titleLabel.text)
        if paths:
            self.edit.state.text = paths[0]
            self.apply()


def parseHeaders(value):
    data = json.loads(value)
    if not isinstance(data, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in data.items()):
        raise ValueError(tr("HeadersEditCard", "请求头必须为名称和值组成的 JSON 对象"))
    return data


class ToggleOption(OptionCard):
    def __init__(self, title, value, save: Callable):
        super().__init__("check", title)
        self._save = save
        self.switch = ui.Switch(bool(value), self._onChecked)
        self.addControl(self.switch)

    def _onChecked(self, checked):
        self.switch.checked = checked
        self._save(checked)

    def apply(self) -> bool:
        self._save(self.switch.checked)
        return True


class FolderConfigCard(SettingCard):
    def __init__(self, item, title, post, changed=None):
        super().__init__("folder", title)
        self.picker = FolderPicker(lambda: item.defaultValue, tr("OutputFolderCard", "默认"), post)
        self.picker.setPath(item.value)
        self.picker.pathChanged.connect(lambda path: cfg.set(item, path))
        if changed:
            self.picker.pathChanged.connect(lambda _: changed())
        self.setControl(self.picker)


class ListConfigCard(SettingCard):
    def __init__(self, item, title, description="", *, isJson=False):
        super().__init__("edit", title, description)
        self._item, self._isJson = item, isJson
        value = json.dumps(item.value, ensure_ascii=False, indent=2) if isJson else "\n".join(item.value)
        self.edit = ui.OutlinedTextField(ui.TextFieldState(value))
        self.edit.set_line_limits(min_lines=2, max_lines=5)
        self.edit.on_value_change = self._onChanged
        self.vBoxLayout.append_child(self.edit)

    def _onChanged(self):
        try:
            value = json.loads(self.edit.state.text) if self._isJson else self.edit.state.text.splitlines()
            if not self._item.validator.validate(value):
                raise ValueError("Invalid value")
            cfg.set(self._item, value)
            self.edit.is_error = False
        except (ValueError, TypeError):
            self.edit.is_error = True


class FileConfigCard(LineEditSettingCard):
    def __init__(self, item, title, description, post):
        super().__init__("description", title, description, item, post)
        self.vBoxLayout.append_child(ui.Button(tr("SelectFileCard", "浏览"), lambda: post(self._onBrowse)))

    def _onBrowse(self):
        paths = openFileDialog(self.title)
        if paths:
            self.lineEdit.state.text = paths[0]
            cfg.set(self._configItem, paths[0])


def buildConfigGroup(config, title, key, labels, post, *, exclude=(), choices=None, units=None):
    group = SettingCardGroup(title, key)
    for name, item in vars(type(config)).items():
        if name in exclude or name in {"associateFileTypes", "associateUriSchemes"} or not hasattr(item, "validator"):
            continue
        caption, description = labels.get(name, (item.name, ""))
        group.addSettingCardFactory(partial(buildConfigCard, item, name, caption, description, post, choices, units))
    return group


def buildConfigCard(item, name, caption, description, post, choices, units):
    if isinstance(item.value, bool):
        card = SwitchSettingCard("check", caption, description, item)
    elif isinstance(item, OptionsConfigItem):
        card = ComboBoxSettingCard(item, "select", caption, description,
                                   texts=(choices or {}).get(name) or
                                   [str(getattr(value, "value", value)) for value in item.options])
    elif isinstance(item, RangeConfigItem):
        unit, suffix = (units or {}).get(name, (1, ""))
        card = SpinBoxSettingCard("edit", caption, description, item, post, unit=unit, suffix=suffix)
    elif "folder" in name.lower():
        card = FolderConfigCard(item, caption, post)
    elif name.lower().endswith("path"):
        card = FileConfigCard(item, caption, description, post)
    elif isinstance(item.value, list):
        card = ListConfigCard(item, caption, description,
                              isJson=any(not isinstance(value, str) for value in item.value))
    else:
        card = LineEditSettingCard("edit", caption, description, item, post,
                                   isPassword=any(word in name.lower() for word in ("token", "password", "secret")))
    return card


class BootstrapListCard(SettingCard):
    def __init__(self, title, subscription, sources, runner, *, custom=None, probe=None):
        super().__init__("public", title)
        self._subscription, self._runner, self._probe = subscription, runner, probe
        self.refreshButton = ui.Button(tr("BootstrapList", "更新"), self._onRefresh)
        self.setControl(self.refreshButton)
        self.vBoxLayout.append_child(ListConfigCard(sources, tr("BootstrapList", "订阅地址")))
        if custom:
            if isinstance(custom.value, str):
                customCard = SettingCard("edit", tr("BootstrapList", "自定义列表"))
                edit = ui.OutlinedTextField(ui.TextFieldState(custom.value))
                edit.set_line_limits(min_lines=2, max_lines=5)
                edit.on_value_change = lambda: cfg.set(custom, edit.state.text)
                customCard.vBoxLayout.append_child(edit)
                self.vBoxLayout.append_child(customCard)
        self._showStatus()

    def _showStatus(self, *_):
        self.refreshButton.enabled = True
        statuses = self._subscription.statuses()
        self.setContent("\n".join(f"{s.url}: {s.error or str(s.count or 0)}" for s in statuses))
        if self._probe:
            self._runner.submit(self._probe(), done=self._onProbed)

    def _onProbed(self, result):
        message, params = result
        if message:
            self.setContent(self.content + "\n" + tr("BootstrapList", message).format_map(params))

    def _onRefresh(self):
        self.refreshButton.enabled = False
        self._runner.submit(self._subscription.refresh(), done=self._showStatus,
                            failed=lambda error: self._showError(error))

    def _showError(self, error):
        self.refreshButton.enabled = True
        self.setContent(toLocalizedError(toTaskError(error)))
