"""设置卡片，对应 qfluentwidgets 的 SettingCard 一族和 app/view/components/setting_cards.py。

构造参数的顺序沿用各自的 Qt 原型。输入框没有 SpinBox 的步进按钮，停止输入片刻后校验并保存；
Qt 界面在鼠标离开时保存的代理地址也改为输入停顿后保存。
"""
from __future__ import annotations

from collections.abc import Callable
from re import compile
from urllib.parse import urlsplit

from bkit import ui

from app.config.cfg import cfg, currentHeaders, currentHeadersPresetIndex, proxy
from app.platform.shell import openUrl
from app.signal import Signal
from app.i18n import tr
from app.ui.icons import buildButton, buildIcon, buildIconButton, loadIcon
from app.ui.layout import ClickArea, checkBox, column, row, text
from app.ui.loop import SingleShotTimer, Timer

TRANSPARENT = 0x00000000
CONTROL_WIDTH = 220
FIELD_WIDTH = 180
SAVE_DELAY = 0.5
HOST_PATTERN = compile(
    r"^(?:(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
    r"|(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6})$"
)
PORT_PATTERN = compile(r"^\d{1,5}$")

Post = Callable[[Callable[[], object], float], Timer]


def fixedWidth(node: ui.Node, width: float) -> ui.Box:
    box = ui.Box()
    box.set_size(width, None)
    box.append_child(node)
    return box


class SettingCard(ui.Node):
    """图标、标题、说明和右侧控件的一行。title、content 供设置搜索匹配。"""

    def __init__(self, icon: str, title: str, content: str = "") -> None:
        super().__init__()
        self.title = title
        self.content = ""
        self.item = ui.ListItem(title)
        # 卡片组自带底色，行本身透明
        self.item.set_container_color(TRANSPARENT)
        self.item.set_leading_content(buildIcon(icon))
        self.setContent(content)
        self.vBoxLayout = column(self.item)
        self.append_child(self.vBoxLayout)

    def setContent(self, content: str) -> None:
        self.content = content
        self.item.set_supporting(content or None)

    def setControl(self, control: ui.Node) -> None:
        self.item.set_trailing_content(control)


class CollapsibleSettingCard(SettingCard):
    """对应 Qt 界面的 CollapsibleSettingCard：标题行右侧是 addWidget() 加的控件和展开按钮，
    点标题行展开下方 addGroupWidget() 加的内容，各段之间有分隔线。
    """

    def __init__(self, icon: str, title: str, content: str = "") -> None:
        super().__init__(icon, title, content)
        self.isExpand = False
        self.expandButton = ui.IconButton(loadIcon("keyboard_arrow_down"), self._onExpandClicked)
        self.hBoxLayout = row(self.expandButton, spacing=8)
        self.setControl(self.hBoxLayout)
        self.viewLayout = column()
        self.vBoxLayout.remove_child(0)
        self.vBoxLayout.append_child(ClickArea(self.item, self._onExpandClicked))

    def addWidget(self, node: ui.Node) -> None:
        self.hBoxLayout.insert_child(len(self.hBoxLayout.children) - 1, node)

    def addGroupWidget(self, node: ui.Node) -> None:
        if self.viewLayout.children:
            self.viewLayout.append_child(ui.HorizontalDivider())
        box = ui.Box()
        box.set_padding(56, 8, 24, 8)
        box.append_child(node)
        self.viewLayout.append_child(box)

    def setExpand(self, isExpand: bool) -> None:
        if self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        if isExpand:
            self.vBoxLayout.append_child(self.viewLayout)
        else:
            self.vBoxLayout.remove_child(self.vBoxLayout.children.index(self.viewLayout))
        self.expandButton.icon = loadIcon("keyboard_arrow_up" if isExpand else "keyboard_arrow_down")

    def _onExpandClicked(self) -> None:
        self.setExpand(not self.isExpand)


class SwitchSettingCard(SettingCard):
    checkedChanged = Signal(bool)

    def __init__(self, icon: str, title: str, content: str, configItem) -> None:
        super().__init__(icon, title, content)
        self._configItem = configItem
        self.switchButton = ui.Switch(bool(configItem.value), self._onCheckedChange)
        self.setControl(self.switchButton)
        configItem.valueChanged.connect(self._onValueChanged)

    def setEnabled(self, isEnabled: bool) -> None:
        self.switchButton.enabled = isEnabled

    def _onCheckedChange(self, checked: bool) -> None:
        self.switchButton.checked = checked
        cfg.set(self._configItem, checked)
        self.checkedChanged.emit(checked)

    def _onValueChanged(self, value) -> None:
        self.switchButton.checked = bool(value)


class RangeSettingCard(SettingCard):
    def __init__(self, configItem, icon: str, title: str, content: str = "") -> None:
        super().__init__(icon, title, content)
        self._configItem = configItem
        minimum, maximum = configItem.range
        self.valueLabel = text(str(configItem.value))
        self.slider = ui.Slider(configItem.value, self._onValueChange, minimum=minimum, maximum=maximum,
                                steps=max(0, maximum - minimum - 1))
        self.slider.set_width(268)
        self.slider.on_value_change_finished = self._onValueChangeFinished
        self.setControl(row(self.valueLabel, self.slider, spacing=6))

    def _onValueChange(self, value: float) -> None:
        self.slider.value = value
        self.valueLabel.text = str(round(value))

    def _onValueChangeFinished(self) -> None:
        cfg.set(self._configItem, round(self.slider.value))


class ComboBoxSettingCard(SettingCard):
    """下拉框选项与 configItem.options 一一对应，texts 是它们的显示文字。"""

    def __init__(self, configItem, icon: str, title: str, content: str, texts: list[str]) -> None:
        super().__init__(icon, title, content)
        self._configItem = configItem
        self._options = list(configItem.options)
        self.comboBox = ui.ExposedDropdownMenuBox(outlined=True)
        for label in texts:
            self.comboBox.add_option(label)
        self._refreshSelection(configItem.value)
        self.comboBox.on_expanded_change = self._onExpandedChange
        self.comboBox.on_selected = self._onSelected
        self.setControl(fixedWidth(self.comboBox, CONTROL_WIDTH))
        configItem.valueChanged.connect(self._refreshSelection)

    def _refreshSelection(self, value) -> None:
        if value in self._options:
            self.comboBox.selected_index = self._options.index(value)

    def _onExpandedChange(self, isExpanded: bool) -> None:
        self.comboBox.expanded = isExpanded

    def _onSelected(self, index: int) -> None:
        self.comboBox.selected_index = index
        cfg.set(self._configItem, self._options[index])


class SpinBoxSettingCard(SettingCard):
    """数值输入框；保存的值是输入值乘以 unit，如 KB 输入、字节保存时 unit 为 1024。"""

    def __init__(self, icon: str, title: str, content: str, configItem, post: Post, *,
                 suffix: str = "", unit: int = 1) -> None:
        super().__init__(icon, title, content)
        self._configItem = configItem
        self._unit = unit
        self._saveTimer = SingleShotTimer(post, SAVE_DELAY, self._save)
        self.lineEdit = ui.OutlinedTextField(ui.TextFieldState(str(configItem.value // unit)))
        self.lineEdit.set_line_limits(single_line=True)
        self.lineEdit.set_keyboard_options(keyboard_type=ui.KeyboardType.NUMBER)
        if suffix:
            self.lineEdit.set_trailing_content(text(suffix))
        self.lineEdit.on_value_change = self._saveTimer.start
        self.lineEdit.on_keyboard_action = self._save
        self.setControl(fixedWidth(self.lineEdit, FIELD_WIDTH))
        configItem.valueChanged.connect(self._onValueChanged)

    def _onValueChanged(self, value) -> None:
        # 正在输入时不覆盖，免得打断用户
        if not self.lineEdit.has_focus:
            self.lineEdit.state.text = str(value // self._unit)

    def _save(self) -> None:
        self._saveTimer.stop()
        value = self.lineEdit.state.text.strip()
        minimum, maximum = self._configItem.range
        self.lineEdit.is_error = not value.isdigit() or not minimum <= int(value) * self._unit <= maximum
        if not self.lineEdit.is_error:
            cfg.set(self._configItem, int(value) * self._unit)


class LineEditSettingCard(SettingCard):
    def __init__(self, icon: str, title: str, content: str, configItem, post: Post, *,
                 placeholder: str = "", isPassword: bool = False) -> None:
        super().__init__(icon, title, content)
        self._configItem = configItem
        self._saveTimer = SingleShotTimer(post, SAVE_DELAY, self._save)
        state = ui.TextFieldState(str(configItem.value))
        self.lineEdit = ui.OutlinedSecureTextField(state) if isPassword else ui.OutlinedTextField(state)
        self.lineEdit.set_line_limits(single_line=True)
        if placeholder:
            self.lineEdit.set_placeholder(placeholder)
        self.lineEdit.on_value_change = self._saveTimer.start
        self.lineEdit.on_keyboard_action = self._save
        self.setControl(fixedWidth(self.lineEdit, CONTROL_WIDTH))

    def _save(self) -> None:
        self._saveTimer.stop()
        cfg.set(self._configItem, self.lineEdit.state.text.strip())


def buildRadio(label: str, onClick: Callable[[], object]) -> tuple[ui.Node, ui.RadioButton]:
    """带文字的单选按钮，对应 qfluentwidgets 的 RadioButton(text)。"""
    button = ui.RadioButton(False, onClick)
    return row(button, text(label), spacing=4), button


def buildLineEdit(placeholder: str, *, isPassword: bool = False) -> ui.TextField:
    edit = ui.OutlinedSecureTextField() if isPassword else ui.OutlinedTextField()
    edit.set_placeholder(placeholder)
    edit.set_line_limits(single_line=True)
    return edit


class ProxySettingCard(CollapsibleSettingCard):
    """代理：不使用、自动检测系统代理或自定义，结构同 Qt 界面。"""

    PROTOCOLS = ["socks4", "socks5", "socks5h", "http", "https"]

    def __init__(self, configItem, featureService, post: Post) -> None:
        def T(value: str) -> str:
            return tr("ProxySettingCard", value)

        super().__init__("public", T("代理"), T("设置下载时希望使用的代理"))
        self._configItem = configItem
        self._featureService = featureService
        self._saveTimer = SingleShotTimer(post, SAVE_DELAY, self._save)
        self._isLoading = False
        self.choiceLabel = text()

        self.offRow, self.offRadio = buildRadio(T("不使用代理"), lambda: self._onRadioClicked(self.offRadio))
        self.autoRow, self.autoRadio = buildRadio(T("自动检测系统代理"), lambda: self._onRadioClicked(self.autoRadio))
        self.customRow, self.customRadio = buildRadio(T("使用自定义代理"),
                                                      lambda: self._onRadioClicked(self.customRadio))
        self._radioTexts = {id(self.offRadio): T("不使用代理"), id(self.autoRadio): T("自动检测系统代理"),
                            id(self.customRadio): T("使用自定义代理")}
        self.protocolCombo = ui.ExposedDropdownMenuBox(outlined=True)
        for protocol in self.PROTOCOLS:
            self.protocolCombo.add_option(protocol)
        self.protocolCombo.on_expanded_change = lambda isExpanded: setattr(self.protocolCombo, "expanded", isExpanded)
        self.protocolCombo.on_selected = self._onProtocolSelected
        self.ipEdit = buildLineEdit(T("代理 IP 地址"))
        self.portEdit = buildLineEdit(T("端口"))
        self.userEdit = buildLineEdit(T("用户名（可选）"))
        self.passEdit = buildLineEdit(T("密码（可选）"), isPassword=True)
        for edit in (self.ipEdit, self.portEdit, self.userEdit, self.passEdit):
            edit.on_value_change = self._onProxyFieldChanged
        self.compatLabel = text(maxLines=2)
        self.compatBanner = ui.Card(ui.CardStyle.OUTLINED)
        self.compatBanner.set_padding(10, 8)
        self.compatBanner.append_child(row(buildIcon("info", 16), self.compatLabel, spacing=8, flex=1))
        self.compatSlot = ui.Box()

        self.addWidget(self.choiceLabel)
        self.addGroupWidget(self.compatSlot)
        self.addGroupWidget(column(self.offRow, self.autoRow, self.customRow, spacing=12))
        self.addGroupWidget(row(
            text(T("编辑代理服务器: ")), ui.Spacer(), fixedWidth(self.protocolCombo, 140), text("://"),
            fixedWidth(self.ipEdit, 200), text(":"), fixedWidth(self.portEdit, 100),
            spacing=6, flex=1,
        ))
        self.addGroupWidget(row(
            text(T("认证信息: ")), ui.Spacer(), fixedWidth(self.userEdit, 160), text(" : "),
            fixedWidth(self.passEdit, 160),
            spacing=6, flex=1,
        ))
        self._loadProxy()

    def setExpand(self, isExpand: bool) -> None:
        super().setExpand(isExpand)
        if not isExpand:
            self._loadProxy()

    def _loadProxy(self) -> None:
        value = self._configItem.value
        if value == "Auto":
            self._onRadioClicked(self.autoRadio)
        elif value == "Off":
            self._onRadioClicked(self.offRadio)
        else:
            self._showProxyUrl(value)
            self._onRadioClicked(self.customRadio)

    def _onRadioClicked(self, button: ui.RadioButton) -> None:
        for radio in (self.offRadio, self.autoRadio, self.customRadio):
            radio.selected = radio is button
        self.choiceLabel.text = self._radioTexts[id(button)]
        isCustom = button is self.customRadio
        for edit in (self.ipEdit, self.portEdit, self.userEdit, self.passEdit):
            edit.enabled = isCustom
        self.protocolCombo.enabled = isCustom

        if button is self.autoRadio:
            cfg.set(self._configItem, "Auto")
            self._showProxyUrl(proxy())
        elif button is self.offRadio:
            cfg.set(self._configItem, "Off")
        else:
            if self.ipEdit.state.text == tr("ProxySettingCard", "未检测到代理"):
                self._setFieldText(self.ipEdit, "")
            self._onProxyFieldChanged()
        self._refreshCompatBanner()

    def _setFieldText(self, edit: ui.TextField, value: str) -> None:
        self._isLoading = True
        try:
            edit.state.text = value
        finally:
            self._isLoading = False

    def _showProxyUrl(self, url: str | None) -> None:
        if not url:
            self.protocolCombo.selected_index = -1
            values = [tr("ProxySettingCard", "未检测到代理"), "", "", ""]
        else:
            parsed = urlsplit(url)
            if parsed.scheme in self.PROTOCOLS:
                self.protocolCombo.selected_index = self.PROTOCOLS.index(parsed.scheme)
            values = [parsed.hostname or "", str(parsed.port or ""), parsed.username or "", parsed.password or ""]
        for edit, value in zip((self.ipEdit, self.portEdit, self.userEdit, self.passEdit), values):
            self._setFieldText(edit, value)

    def _onProtocolSelected(self, index: int) -> None:
        self.protocolCombo.selected_index = index
        self._onProxyFieldChanged()

    def _protocol(self) -> str:
        index = self.protocolCombo.selected_index
        return self.PROTOCOLS[index] if index >= 0 else ""

    def _refreshCompatBanner(self) -> None:
        if self.offRadio.selected:
            scheme = ""
        elif self.autoRadio.selected:
            url = proxy()
            scheme = urlsplit(url).scheme.lower() if url else ""
        else:
            scheme = self._protocol()
        incompatible = [p.packId.upper() for p in self._featureService.packs
                        if scheme and p.proxySchemes is not None and scheme not in p.proxySchemes]
        if incompatible:
            self.compatLabel.text = tr("ProxySettingCard", "{0} 不支持当前代理协议，将直连；使用 SOCKS5 可兼容全部下载方式").format(
                "、".join(incompatible))
            if not self.compatSlot.children:
                self.compatSlot.append_child(self.compatBanner)
        elif self.compatSlot.children:
            self.compatSlot.remove_child(0)

    def _buildProxyUrl(self) -> str:
        user, password = self.userEdit.state.text, self.passEdit.state.text
        cred = f"{user}:{password}@" if user or password else ""
        return f"{self._protocol()}://{cred}{self.ipEdit.state.text}:{self.portEdit.state.text}"

    def _onProxyFieldChanged(self) -> None:
        if self._isLoading:
            return
        if not self.customRadio.selected:
            self.ipEdit.is_error = self.portEdit.is_error = False
            return
        url = self._buildProxyUrl()
        if cfg.proxyServer.validator.validate(url):
            self.choiceLabel.text = url
            self.ipEdit.is_error = self.portEdit.is_error = False
            self._saveTimer.start()
        else:
            self.choiceLabel.text = self._radioTexts[id(self.customRadio)]
            ip, port = self.ipEdit.state.text.strip(), self.portEdit.state.text.strip()
            self.ipEdit.is_error = bool(ip) and not HOST_PATTERN.match(ip)
            self.portEdit.is_error = bool(port) and not PORT_PATTERN.match(port)
        self._refreshCompatBanner()

    def _save(self) -> None:
        self._saveTimer.stop()
        url = self._buildProxyUrl()
        if self.customRadio.selected and cfg.proxyServer.validator.validate(url):
            cfg.set(self._configItem, url)


class PushSettingCard(SettingCard):
    """右侧一个按钮，对应 PushSettingCard；isPrimary 时是 PrimaryPushSettingCard。"""

    clicked = Signal()

    def __init__(self, text: str, icon: str, title: str, content: str = "", *, isPrimary: bool = False) -> None:
        super().__init__(icon, title, content)
        style = ui.ButtonStyle.FILLED if isPrimary else ui.ButtonStyle.OUTLINED
        self.button = ui.Button(text, self.clicked.emit, style)
        self.hBoxLayout = row(self.button, spacing=8)
        self.setControl(self.hBoxLayout)

    def insertWidget(self, index: int, node: ui.Node) -> None:
        self.hBoxLayout.insert_child(index, node)


class HyperlinkCard(PushSettingCard):
    def __init__(self, url: str, text: str, icon: str, title: str, content: str = "") -> None:
        super().__init__(text, icon, title, content)
        self.button.set_style(ui.ButtonStyle.TEXT)
        self.clicked.connect(lambda: openUrl(url))

    def addLink(self, text: str, url: str) -> None:
        self.insertWidget(0, ui.Button(text, lambda: openUrl(url), ui.ButtonStyle.TEXT))


class ClipboardSettingCard(CollapsibleSettingCard):
    """剪贴板监听开关，展开后逐个功能包勾选是否接管它能识别的链接。"""

    def __init__(self, packs: list) -> None:
        super().__init__("content_paste", tr("ClipboardSettingCard", "剪贴板监听"),
                         tr("ClipboardSettingCard", "剪贴板监听器将自动检测剪贴板中的链接并添加下载任务"))
        self._packs = [pack for pack in packs if pack.capturedLinks]
        self.switchButton = ui.Switch(cfg.isClipboardListenerEnabled.value, self._onCheckedChange)
        self.addWidget(self.switchButton)
        self.checkBoxes: dict[str, ui.Checkbox] = {}
        packLayout = column(spacing=12)
        for pack in self._packs:
            packRow, box = checkBox(tr(type(pack).__name__, pack.capturedLinks),
                                    pack.packId not in cfg.clipboardIgnoredPacks.value)
            box.on_checked_change = self._buildPackToggle(box)
            self.checkBoxes[pack.packId] = box
            packLayout.append_child(packRow)
        self.addGroupWidget(packLayout)
        self._onEnabledChanged(cfg.isClipboardListenerEnabled.value)
        cfg.isClipboardListenerEnabled.valueChanged.connect(self._onEnabledChanged)

    def _buildPackToggle(self, box: ui.Checkbox):
        def onCheckedChange(checked: bool) -> None:
            box.checked = checked
            cfg.set(cfg.clipboardIgnoredPacks,
                    [packId for packId, item in self.checkBoxes.items() if not item.checked])
        return onCheckedChange

    def _onCheckedChange(self, checked: bool) -> None:
        cfg.set(cfg.isClipboardListenerEnabled, checked)

    def _onEnabledChanged(self, isEnabled: bool) -> None:
        self.switchButton.checked = bool(isEnabled)
        for box in self.checkBoxes.values():
            box.enabled = bool(isEnabled)


class PresetRowWidget(ui.Node):
    """一个身份预设：名称，下面是匹配的 Host、指纹与 User-Agent，右侧是启用开关、编辑和删除。"""

    def __init__(self, index: int, preset: dict, onToggled: Callable[[int, bool], object],
                 onEdit: Callable[[int], object], onRemove: Callable[[int], object]) -> None:
        super().__init__()
        from app.ui.components.option_cards import toProfileLabel
        self.switchButton = ui.Switch(preset.get("isEnabled", True))

        def onCheckedChange(checked: bool) -> None:
            self.switchButton.checked = checked
            onToggled(index, checked)

        self.switchButton.on_checked_change = onCheckedChange
        editBox, _ = buildIconButton("edit", tr("PresetRowWidget", "编辑"), lambda: onEdit(index),
                                     ui.IconButtonVariant.FILLED)
        removeBox, _ = buildIconButton("delete", tr("PresetRowWidget", "删除"), lambda: onRemove(index),
                                       ui.IconButtonVariant.OUTLINED)
        descLayout = ui.Row(spacing=8, cross_alignment=ui.Alignment.CENTER)
        hosts = preset.get("hosts", [])
        if hosts:
            descLayout.append_child(row(buildIcon("public", 12), text(", ".join(hosts[:3]), fontSize=12), spacing=4))
        if profile := preset.get("clientProfile", ""):
            descLayout.append_child(row(buildIcon("fingerprint", 12), text(toProfileLabel(profile), fontSize=12),
                                        spacing=4))
        if userAgent := preset.get("userAgent", ""):
            display = userAgent if len(userAgent) <= 24 else userAgent[:21] + "..."
            descLayout.append_child(row(buildIcon("person", 12), text(display, fontSize=12), spacing=4))
        self.append_child(row(
            buildIcon("vpn_lock", 16), column(text(preset.get("name", ""), fontWeight=600), descLayout, spacing=2),
            self.switchButton, editBox, removeBox,
            spacing=12, flex=1,
        ))


class IdentitySettingCard(CollapsibleSettingCard):
    """模拟身份：全局默认的 TLS 指纹，以及按 Host 匹配的身份预设。"""

    def __init__(self) -> None:
        from app.ui.components.option_cards import toProfileLabel
        super().__init__("smart_toy", tr("IdentitySettingCard", "模拟身份"),
                         tr("IdentitySettingCard", "TLS 指纹与 User-Agent 预设"))
        self._dialog = None
        self._menu: ui.DropdownMenu | None = None
        self.choiceLabel = text(toProfileLabel(cfg.clientProfile.value))
        self.addWidget(self.choiceLabel)
        # 对应 DropDownPushButton：当前指纹加下拉箭头
        self.profileLabel = ui.Text(toProfileLabel(cfg.clientProfile.value))
        self.profileButton = ui.Button([self.profileLabel, buildIcon("keyboard_arrow_down", 16)],
                                       self._onProfileClicked, ui.ButtonStyle.OUTLINED)
        self.addGroupWidget(row(
            buildIcon("smart_toy", 16),
            column(text(tr("IdentitySettingCard", "全局默认")),
                   text(tr("IdentitySettingCard", "未被预设匹配时使用"), fontSize=12), spacing=2),
            fixedWidth(self.profileButton, 200),
            spacing=12, flex=1,
        ))
        self.rowLayout = column(spacing=12)
        self.addButton = buildButton("add", tr("IdentitySettingCard", "添加预设"), self._onAddClicked,
                                     ui.ButtonStyle.FILLED)
        self.addGroupWidget(column(self.rowLayout, row(ui.Spacer(), self.addButton, flex=0), spacing=8))
        cfg.clientProfile.valueChanged.connect(self._onProfileChanged)
        self._reload()

    def _onProfileClicked(self) -> None:
        from app.ui.components.menu import buildMenu
        from app.ui.components.option_cards import addProfileItems
        menu = buildMenu(self.profileButton)
        addProfileItems(menu, lambda value: cfg.set(cfg.clientProfile, value), includeAuto=True)
        self._menu = menu
        menu.expanded = True

    def _onProfileChanged(self, value: str) -> None:
        from app.ui.components.option_cards import toProfileLabel
        self.choiceLabel.text = toProfileLabel(value)
        self.profileLabel.text = toProfileLabel(value)

    def _reload(self) -> None:
        while self.rowLayout.children:
            self.rowLayout.remove_child(0)
        for index, preset in enumerate(cfg.identityPresets.value):
            self.rowLayout.append_child(PresetRowWidget(index, preset, self._onToggled, self._onEditClicked,
                                                        self._onRemoveClicked))

    def _onAddClicked(self) -> None:
        from app.ui.dialogs.preset_edit import PresetEditDialog
        dialog = PresetEditDialog(self)

        def onAccepted() -> None:
            self._savePresets([*cfg.identityPresets.value, dialog.preset()])
            self.setExpand(True)

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._dialog = dialog

    def _onEditClicked(self, index: int) -> None:
        from app.ui.dialogs.preset_edit import PresetEditDialog
        presets = list(cfg.identityPresets.value)
        if not 0 <= index < len(presets):
            return
        dialog = PresetEditDialog(self, preset=presets[index])

        def onAccepted() -> None:
            presets[index] = dialog.preset()
            self._savePresets(presets)

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._dialog = dialog

    def _onToggled(self, index: int, checked: bool) -> None:
        presets = list(cfg.identityPresets.value)
        if 0 <= index < len(presets):
            presets[index] = {**presets[index], "isEnabled": checked}
            cfg.set(cfg.identityPresets, presets)

    def _onRemoveClicked(self, index: int) -> None:
        from app.ui.components.message_box import MessageBox
        presets = list(cfg.identityPresets.value)
        if not 0 <= index < len(presets):
            return
        name = presets[index].get("name", tr("IdentitySettingCard", "未命名预设"))
        box = MessageBox(tr("IdentitySettingCard", "删除预设"),
                         tr("IdentitySettingCard", "确定要删除 {0} 吗？").format(name), self)
        box.accepted.connect(lambda: self._savePresets(presets[:index] + presets[index + 1:]))
        box.open()
        self._dialog = box

    def _savePresets(self, presets: list[dict]) -> None:
        cfg.set(cfg.identityPresets, presets)
        self._reload()


class HeadersPresetSettingCard(CollapsibleSettingCard):
    """请求标头预设：单选当前预设，可增删改；至少保留一个。"""

    def __init__(self) -> None:
        super().__init__("menu_book", tr("HeadersPresetSettingCard", "请求标头预设"),
                         tr("HeadersPresetSettingCard", "新建任务的标头起点"))
        self._dialog = None
        self.choiceLabel = text()
        self.addWidget(self.choiceLabel)
        self.rowLayout = column(spacing=12)
        self.addButton = buildButton("add", tr("HeadersPresetSettingCard", "添加预设"), self._onAddClicked,
                                     ui.ButtonStyle.FILLED)
        self.addGroupWidget(column(self.rowLayout, row(ui.Spacer(), self.addButton, flex=0), spacing=8))
        self._reload()

    def _reload(self) -> None:
        while self.rowLayout.children:
            self.rowLayout.remove_child(0)
        presets = cfg.headersPresets.value
        current = currentHeadersPresetIndex()
        for index, preset in enumerate(presets):
            radio = ui.RadioButton(index == current, lambda i=index: self._onPick(i))
            editBox, _ = buildIconButton("edit", tr("HeadersPresetRow", "编辑"),
                                         lambda i=index: self._onEditClicked(i), ui.IconButtonVariant.FILLED)
            removeBox, removeButton = buildIconButton("delete", tr("HeadersPresetRow", "删除"),
                                                      lambda i=index: self._onRemoveClicked(i),
                                                      ui.IconButtonVariant.OUTLINED)
            removeButton.enabled = len(presets) > 1
            self.rowLayout.append_child(row(
                radio, text(preset["name"]), ui.Spacer(),
                text(tr("HeadersPresetRow", "{0} 条标头").format(len(preset["headers"])), fontSize=12),
                editBox, removeBox,
                spacing=12, flex=2,
            ))
        self.choiceLabel.text = presets[current]["name"]

    def _onPick(self, index: int) -> None:
        cfg.set(cfg.currentHeadersPreset, index)
        self._reload()

    def _onAddClicked(self) -> None:
        from app.ui.dialogs.headers_preset_edit import HeadersPresetEditDialog
        dialog = HeadersPresetEditDialog(self, preset={"name": "", "headers": currentHeaders()})

        def onAccepted() -> None:
            cfg.set(cfg.headersPresets, [*cfg.headersPresets.value, dialog.preset()])
            self._reload()
            self.setExpand(True)

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._dialog = dialog

    def _onEditClicked(self, index: int) -> None:
        from app.ui.dialogs.headers_preset_edit import HeadersPresetEditDialog
        presets = list(cfg.headersPresets.value)
        dialog = HeadersPresetEditDialog(self, preset=presets[index])

        def onAccepted() -> None:
            presets[index] = dialog.preset()
            cfg.set(cfg.headersPresets, presets)
            self._reload()

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._dialog = dialog

    def _onRemoveClicked(self, index: int) -> None:
        from app.ui.components.message_box import MessageBox
        presets = list(cfg.headersPresets.value)
        name = presets[index].get("name", tr("HeadersPresetSettingCard", "未命名预设"))
        box = MessageBox(tr("HeadersPresetSettingCard", "删除预设"),
                         tr("HeadersPresetSettingCard", "确定要删除 {0} 吗？").format(name), self)

        def onAccepted() -> None:
            presets.pop(index)
            cfg.set(cfg.headersPresets, presets)
            current = cfg.currentHeadersPreset.value
            if index <= current:
                cfg.set(cfg.currentHeadersPreset, max(0, current - 1))
            self._reload()

        box.accepted.connect(onAccepted)
        box.open()
        self._dialog = box
