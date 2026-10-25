"""首次启动的引导窗口，页面与顺序同 Qt 界面的 OobeWindow。

它有自己的 Owner 和 Window：入口先用 UiLoop 运行它，结束后再创建主窗口，对应 Qt 版的嵌套 QEventLoop。
Qt 界面的安装演示动图是 Qt 资源，这里显示同名的静态图片。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import LANGUAGE_TEXTS, cfg
from app.config.constants import CHROME_WEBSTORE_URL, EDGE_ADDONS_URL, FIREFOX_ADDONS_URL, LATEST_EXTENSION_VERSION
from app.config.paths import EXECUTABLE_DIR
from app.models.task import toTaskError
from app.platform.browser import openChromiumUrl
from app.platform.file_association import registerUrlScheme, unregisterUrlScheme
from app.platform.file_dialog import openFolderDialog
from app.platform.run_at_login import setRunAtLogin
from app.platform.shell import openUrl, revealInFolder, setClipboardText, setWindowIcon
from app.services.port_listener import ListenStatus
from app.signal import Signal
from app.ui.components.info_bar import InfoBarIcon
from app.ui.i18n import toLocalizedError, tr, translator
from app.ui.icons import CATEGORY_ICONS, buildIcon, buildImage
from app.ui.layout import Slot, column, row, text
from app.ui.loop import UiLoop
from app.ui.theme import isDark, systemAccentColor

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime
    from app.services.browser_service import BrowserService, PairRequest
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.port_listener import PortListener
    from app.services.runtime_status import RuntimeStatusService

WINDOW_SIZE = (960, 600)
PREVIEW_SIZE = (592, 333)
STORE_COLUMN_WIDTH = 280
ASSETS_DIR = EXECUTABLE_DIR / "app" / "assets"
PREVIEW_PATH = ASSETS_DIR / "install_chrome_extension_guidance.png"
LOGO_PATH = ASSETS_DIR / "logo.png"
SUCCESS_COLOR = 0xFF0F7B46
LIGHT_BACKGROUND = 0xFFFEF7FF
DARK_BACKGROUND = 0xFF141218
# (主题, 预览的底色, 预览的前景色)
THEME_PREVIEWS = [("Light", 0xFFF3F3F3, 0xFFFFFFFF), ("Dark", 0xFF202020, 0xFF2D2D2D), ("Auto", 0xFF8A8A8A, 0xFFD0D0D0)]


def centered(node: ui.Node) -> ui.Box:
    box = ui.Box()
    box.set_content_alignment(ui.Alignment.CENTER, ui.Alignment.CENTER)
    box.append_child(node)
    return box


class PageHeader(ui.Node):
    def __init__(self, title: str, desc: str) -> None:
        super().__init__()
        self.append_child(column(text(title, fontSize=24, fontWeight=600), text(desc, maxLines=2), spacing=6))


class Banner(ui.Node):
    """页面内的提示条，对应 InfoBarPosition.NONE 的 InfoBar。"""

    def __init__(self, icon: InfoBarIcon, title: str) -> None:
        super().__init__()
        iconName, color = icon.value
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.set_padding(16, 10)
        card.append_child(row(buildIcon(iconName, tint=color), text(title, maxLines=2), spacing=12, flex=1))
        self.append_child(card)


class WelcomePage(ui.Node):
    startClicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        def T(text: str) -> str:
            return tr("WelcomePage", text)

        startButton = ui.Button(T("开始配置"), self.startClicked.emit, ui.ButtonStyle.FILLED)
        startBox = ui.Box()
        startBox.set_size(200, None)
        startBox.append_child(startButton)
        self.append_child(centered(column(
            buildImage(LOGO_PATH, (88, 88)),
            ui.Spacer(0, 16),
            text(T("欢迎使用 Ghost Downloader"), fontSize=28, fontWeight=600),
            text(T("快速、智能的下载管理器。\n接下来的几步将帮助你完成基本配置。"), maxLines=3),
            ui.Spacer(0, 28),
            startBox,
            spacing=8, isCrossFilled=False,
        )))


class BasicSettingsPage(ui.Node):
    languageChanged = Signal()

    def __init__(self, post: Callable[[Callable[[], object], float], object]) -> None:
        super().__init__()
        self._post = post
        self._themeCards: list[tuple[ui.Button, str]] = []
        self._initWidget()
        self._initLayout()
        self._refreshThemeCards()

    def _initWidget(self) -> None:
        def T(text: str) -> str:
            return tr("BasicSettingsPage", text)

        self.header = PageHeader(T("基本设置"), T("选择你喜欢的外观，设置下载文件的保存位置"))
        for (name, background, foreground), label in zip(THEME_PREVIEWS, (T("浅色"), T("深色"), T("跟随系统"))):
            preview = ui.Box()
            preview.set_size(220, 120)
            preview.set_corner_radius(8)
            preview.set_background(background)
            preview.set_padding(16)
            window = ui.Box()
            window.set_size(150, 80)
            window.set_corner_radius(6)
            window.set_background(foreground)
            preview.append_child(window)
            card = ui.Button([column(preview, centered(text(label)), spacing=10, isCrossFilled=False)],
                             lambda n=name: self._onThemePicked(n), ui.ButtonStyle.OUTLINED)
            card.set_content_padding(14, 14, 14, 12)
            self._themeCards.append((card, name))
        self.langCombo = ui.ExposedDropdownMenuBox(outlined=True)
        options = list(cfg.language.options)
        for language in options:
            self.langCombo.add_option(LANGUAGE_TEXTS.get(language, T("使用系统设置")))
        self.langCombo.selected_index = options.index(cfg.language.value)
        self.langCombo.on_expanded_change = lambda isExpanded: setattr(self.langCombo, "expanded", isExpanded)
        self.langCombo.on_selected = self._onLanguageSelected
        self.folderItem = ui.ListItem(T("下载保存位置"))
        self.folderItem.set_leading_content(buildIcon("folder"))
        self.folderItem.set_supporting(str(cfg.downloadFolder.value))
        self.folderItem.set_trailing_content(
            ui.Button(T("浏览..."), lambda: self._post(self._onBrowse, 0.0), ui.ButtonStyle.OUTLINED))
        self.languageItem = ui.ListItem(T("界面语言"))
        self.languageItem.set_leading_content(buildIcon("language"))
        self.languageItem.set_supporting(T("更改立即生效"))
        langBox = ui.Box()
        langBox.set_size(220, None)
        langBox.append_child(self.langCombo)
        self.languageItem.set_trailing_content(langBox)

    def _initLayout(self) -> None:
        themeRow = ui.Row(spacing=14)
        for card, _ in self._themeCards:
            themeRow.append_child(card)
        settingsCard = ui.Card(ui.CardStyle.FILLED)
        settingsCard.set_padding(0, 8)
        settingsCard.append_child(column(text(tr("BasicSettingsPage", "偏好"), fontWeight=600), self.languageItem,
                                         self.folderItem))
        self.append_child(column(self.header, centered(themeRow), settingsCard, spacing=24))

    def _onThemePicked(self, name: str) -> None:
        cfg.set(cfg.themeMode, next(option for option in cfg.themeMode.options if option.value == name))
        self._refreshThemeCards()

    def _refreshThemeCards(self) -> None:
        current = cfg.themeMode.value.value
        for card, name in self._themeCards:
            card.set_style(ui.ButtonStyle.FILLED_TONAL if name == current else ui.ButtonStyle.OUTLINED)

    def _onLanguageSelected(self, index: int) -> None:
        self.langCombo.selected_index = index
        options = list(cfg.language.options)
        if options[index] != cfg.language.value:
            cfg.set(cfg.language, options[index])
            self.languageChanged.emit()

    def _onBrowse(self) -> None:
        folder = openFolderDialog(tr("BasicSettingsPage", "选择下载目录"), str(cfg.downloadFolder.value))
        if folder:
            cfg.set(cfg.downloadFolder, folder)
            self.folderItem.set_supporting(folder)


class ActionCard(ui.Node):
    """可点的一行：图标、标题和说明、右箭头。推荐项用填充色突出，对应 Qt 界面的主题色描边。"""

    def __init__(self, icon: str, title: str, onClick: Callable[[], object], hint: str = "",
                 isRecommended: bool = False) -> None:
        super().__init__()
        textColumn = column(text(title), spacing=2)
        if hint:
            textColumn.append_child(text(hint, fontSize=12, maxLines=2))
        button = ui.Button([row(buildIcon(icon, 24), textColumn, ui.Icon(ui.MaterialIcon.KEYBOARD_ARROW_RIGHT),
                                spacing=12, flex=1)],
                           onClick, ui.ButtonStyle.FILLED_TONAL if isRecommended else ui.ButtonStyle.OUTLINED)
        button.set_content_padding(14, 8)
        self.append_child(button)


class BrowserExtensionPage(ui.Node):

    def __init__(self, browserService: BrowserService, browserListener: PortListener,
                 coroutineRunner: CoroutineRunner) -> None:
        super().__init__()
        self._browserService = browserService
        self._browserListener = browserListener
        self._coroutineRunner = coroutineRunner
        self._isPaired = False
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        def T(text: str) -> str:
            return tr("BrowserExtensionPage", text)

        self.header = PageHeader(T("安装浏览器扩展"), T("让浏览器中的下载自动接管到 Ghost Downloader"))
        self.previewLabel = buildImage(PREVIEW_PATH, PREVIEW_SIZE)
        self.bannerSlot = ui.Box()
        self.hintLabel = text(maxLines=2)
        self.manualCard = ActionCard("download", T("手动安装"), self._onManualInstallClicked,
                                     T("随桌面端自动更新，适用于所有 Chromium 浏览器"), isRecommended=True)
        self.storeCards = [ActionCard("public", title, lambda u=url: openUrl(u)) for title, url in (
            (T("Chrome 商店"), CHROME_WEBSTORE_URL),
            (T("Edge 商店"), EDGE_ADDONS_URL),
            (T("Firefox 商店"), FIREFOX_ADDONS_URL),
        )]
        self.footnote = text(T("商店版更新需等待审核，可能滞后于桌面端"), fontSize=12, maxLines=2)

    def _initLayout(self) -> None:
        left = column(self.previewLabel, self.bannerSlot, self.hintLabel, spacing=10, isCrossFilled=False)
        right = column(self.manualCard, *self.storeCards, self.footnote, spacing=10)
        rightBox = ui.Box()
        rightBox.set_size(STORE_COLUMN_WIDTH, None)
        rightBox.append_child(right)
        self.append_child(column(self.header, row(left, rightBox, spacing=16), spacing=24))

    def _bind(self) -> None:
        self._browserService.connectionChanged.connect(self._onConnectionChanged)
        self._browserService.protocolMismatched.connect(self._onProtocolMismatched)
        self._browserListener.stateChanged.connect(self._onListenStateChanged)

    def _setBanner(self, icon: InfoBarIcon, title: str) -> None:
        if self.bannerSlot.children:
            self.bannerSlot.remove_child(0)
        banner = Banner(icon, title)
        box = ui.Box()
        box.set_size(PREVIEW_SIZE[0], None)
        box.append_child(banner)
        self.bannerSlot.append_child(box)

    def refreshListenState(self) -> None:
        if self._isPaired:
            return
        state = self._browserListener.state
        if state.status == ListenStatus.OFF:
            self._setBanner(InfoBarIcon.WARNING, tr("BrowserExtensionPage", "浏览器扩展未启用，可稍后在设置中开启"))
        elif state.status == ListenStatus.FAILED:
            self._setBanner(InfoBarIcon.WARNING, toLocalizedError(state.error))
        else:
            self._setBanner(InfoBarIcon.INFO,
                            tr("BrowserExtensionPage", "正在端口 {} 上等待扩展连接").format(state.port))

    def _setConnectedBanner(self, version: str) -> None:
        if version:
            title = tr("BrowserExtensionPage", "已连接扩展 v{}，最新版本为 v{}").format(version, LATEST_EXTENSION_VERSION)
        else:
            title = tr("BrowserExtensionPage", "已连接扩展，最新版本为 v{}").format(LATEST_EXTENSION_VERSION)
        self._setBanner(InfoBarIcon.SUCCESS, title)

    def _onConnectionChanged(self) -> None:
        installType, version = self._browserService.connectionSummary
        if installType or version:
            self._isPaired = True
            self._setConnectedBanner(version)
        else:
            self._isPaired = False
            self.refreshListenState()

    def _onManualInstallClicked(self) -> None:
        self._coroutineRunner.submit(self._browserService.install(), done=self._onExtensionExtracted,
                                     failed=self._onExtensionExtractFailed)

    def _onExtensionExtracted(self, path: Path) -> None:
        revealInFolder(path)
        if not openChromiumUrl("chrome://extensions"):
            setClipboardText("chrome://extensions")
            self.hintLabel.text = (f"{tr('BrowserExtensionPage', '请手动打开浏览器')}："
                                   f"{tr('BrowserExtensionPage', 'chrome://extensions 已复制到剪贴板')}")

    def _onExtensionExtractFailed(self, error) -> None:
        self.hintLabel.text = f"{tr('BrowserExtensionPage', '解包失败')}：{toLocalizedError(toTaskError(error))}"

    def onPairRequested(self, request: PairRequest) -> None:
        self._browserService.approvePair(request.requestId)
        self._isPaired = True
        self._setConnectedBanner(request.extensionVersion)

    def _onListenStateChanged(self, _state) -> None:
        if self.is_attached:
            self.refreshListenState()

    def _onProtocolMismatched(self) -> None:
        self._setBanner(InfoBarIcon.WARNING, tr("BrowserExtensionPage", "协议版本不匹配，商店版可能滞后，请尝试手动安装"))


class RuntimeInstallPage(ui.Node):

    def __init__(self, featureService: FeatureService) -> None:
        super().__init__()
        self._featureService = featureService
        self._checkBoxes: list[tuple[ui.Checkbox, BinaryRuntime]] = []
        self._isMounted = False
        self.groupLayout = column()
        card = ui.Card(ui.CardStyle.FILLED)
        card.set_padding(0, 8)
        card.append_child(column(text(tr("RuntimeInstallPage", "推荐组件"), fontWeight=600), self.groupLayout))
        self.append_child(column(
            PageHeader(tr("RuntimeInstallPage", "安装推荐组件"),
                       tr("RuntimeInstallPage", "点击下一步将自动安装勾选的组件，稍后可在设置中管理")),
            card, spacing=24,
        ))

    def mount(self) -> None:
        if self._isMounted:
            return
        self._isMounted = True
        entries = [rt for rt in self._featureService.runtimes() if rt.canInstall and rt.title]
        entries.sort(key=lambda rt: not rt.isRecommended)
        for runtime in entries:
            trailing = ui.Row(spacing=12, cross_alignment=ui.Alignment.CENTER)
            trailing.append_child(text(runtime.name, fontSize=12))
            if runtime.path():
                trailing.append_child(ui.Text(tr("RuntimeInstallPage", "已安装"), color=SUCCESS_COLOR))
            else:
                checkBox = ui.Checkbox(runtime.isRecommended)
                checkBox.on_checked_change = lambda checked, box=checkBox: setattr(box, "checked", checked)
                trailing.append_child(checkBox)
                self._checkBoxes.append((checkBox, runtime))
            item = ui.ListItem(tr("BinaryRuntime", runtime.title))
            item.set_leading_content(buildIcon(CATEGORY_ICONS.get(runtime.icon, "apps")))
            item.set_supporting(tr("BinaryRuntime", runtime.description))
            item.set_trailing_content(trailing)
            self.groupLayout.append_child(item)

    def selectedRuntimes(self) -> list[BinaryRuntime]:
        return [runtime for box, runtime in self._checkBoxes if box.checked]


class OptionCard(ui.Node):
    def __init__(self, icon: str, title: str, desc: str, isChecked: bool) -> None:
        super().__init__()
        self.switchButton = ui.Switch(isChecked)
        self.switchButton.on_checked_change = lambda checked: setattr(self.switchButton, "checked", checked)
        item = ui.ListItem(title)
        item.set_leading_content(buildIcon(icon))
        item.set_supporting(desc)
        item.set_trailing_content(self.switchButton)
        card = ui.Card(ui.CardStyle.OUTLINED)
        card.append_child(item)
        self.append_child(card)

    def isChecked(self) -> bool:
        return self.switchButton.checked


class AdvancedOptionsPage(ui.Node):

    def __init__(self, featureService: FeatureService) -> None:
        super().__init__()
        self._featureService = featureService

        def T(text: str) -> str:
            return tr("AdvancedOptionsPage", text)

        self.runAtLoginCard = OptionCard("power_settings_new", T("开机自启"), T("登录系统时自动在后台启动，随时接管下载"),
                                         cfg.shouldRunAtLogin.value)
        self.clipboardCard = OptionCard("content_paste", T("剪贴板监听"), T("复制下载链接时自动弹出新任务提示"),
                                        cfg.isClipboardListenerEnabled.value)
        self.categoryCard = OptionCard("label", T("自动分类保存"), T("按文件类型自动保存到 视频、音频、文档 等子文件夹"),
                                       cfg.isCategoryEnabled.value)
        self.fileAssocCard = OptionCard("description", T("关联文件类型"), T("双击 .torrent 等文件时用 Ghost Downloader 打开"),
                                        featureService.isFileAssociationEnabled())
        self.uriSchemeCard = OptionCard("link", T("处理协议链接"), T("点击 Magnet/eD2k/FTP 链接时唤起 Ghost Downloader"),
                                        featureService.isUriSchemeAssociationEnabled())
        self.urlSchemeCard = OptionCard("public", T("允许浏览器扩展唤醒"),
                                        T("浏览器扩展可通过 ghostdownloader:// 协议启动桌面端"),
                                        cfg.isUrlSchemeRegistered.value)
        self.aria2Card = OptionCard("terminal", T("Aria2 RPC 兼容"),
                                    T("让支持 Aria2 的工具和网站把下载任务发给 Ghost Downloader"), cfg.isAria2RpcEnabled.value)
        cards = [self.runAtLoginCard, self.clipboardCard, self.categoryCard, self.fileAssocCard, self.uriSchemeCard,
                 self.urlSchemeCard, self.aria2Card]
        scroll = ui.ScrollContainer()
        scroll.append_child(column(*cards, spacing=8))
        self.append_child(column(PageHeader(T("更多选项"), T("按需开启以下功能，也可以稍后在设置中修改")), scroll,
                                 spacing=24, flex=1))

    def save(self) -> None:
        if self.runAtLoginCard.isChecked() != cfg.shouldRunAtLogin.value:
            setRunAtLogin(self.runAtLoginCard.isChecked())
            cfg.set(cfg.shouldRunAtLogin, self.runAtLoginCard.isChecked())
        cfg.set(cfg.isClipboardListenerEnabled, self.clipboardCard.isChecked())
        cfg.set(cfg.isCategoryEnabled, self.categoryCard.isChecked())
        for pack in self._featureService.packs:
            config = pack.config
            if config is not None and config.associateFileTypes is not None:
                cfg.set(config.associateFileTypes, self.fileAssocCard.isChecked())
            if config is not None and config.associateUriSchemes is not None:
                cfg.set(config.associateUriSchemes, self.uriSchemeCard.isChecked())
        if self.urlSchemeCard.isChecked():
            registerUrlScheme()
        else:
            unregisterUrlScheme()
        cfg.set(cfg.isUrlSchemeRegistered, self.urlSchemeCard.isChecked())
        cfg.set(cfg.isAria2RpcEnabled, self.aria2Card.isChecked())


class CompletePage(ui.Node):
    finishClicked = Signal()

    def __init__(self) -> None:
        super().__init__()

        def T(text: str) -> str:
            return tr("CompletePage", text)

        finishBox = ui.Box()
        finishBox.set_size(200, None)
        finishBox.append_child(ui.Button(T("开始使用"), self.finishClicked.emit, ui.ButtonStyle.FILLED))
        self.append_child(centered(column(
            buildIcon("check_circle", 80, tint=SUCCESS_COLOR),
            ui.Spacer(0, 16),
            text(T("一切就绪"), fontSize=28, fontWeight=600),
            text(T("Ghost Downloader 已准备好为你工作。\n你可以随时在设置中调整所有选项。"), maxLines=3),
            ui.Spacer(0, 28),
            finishBox,
            spacing=8, isCrossFilled=False,
        )))


class OobeWindow:
    finished = Signal()

    PAGE_COUNT = 6

    def __init__(self, browserService: BrowserService, browserListener: PortListener,
                 coroutineRunner: CoroutineRunner, featureService: FeatureService,
                 runtimeStatusService: RuntimeStatusService, uiLoop: UiLoop) -> None:
        self._browserService = browserService
        self._browserListener = browserListener
        self._coroutineRunner = coroutineRunner
        self._featureService = featureService
        self._runtimeStatusService = runtimeStatusService
        self._uiLoop = uiLoop
        self._currentIndex = 0
        self._isFinished = False
        self._initWidget()
        self._initContent()
        self._initLayout()
        self._bind()
        self._refreshNavigation()

    def _initWidget(self) -> None:
        self.theme = ui.MaterialTheme(dark=isDark(), seed=systemAccentColor())
        self.surface = ui.Surface()
        self.content = Slot()

    def _initContent(self) -> None:
        """页面和导航按钮；换语言后整个重建，文字随之更新。"""
        self.welcomePage = WelcomePage()
        self.basicSettingsPage = BasicSettingsPage(self._uiLoop.post)
        self.browserExtensionPage = BrowserExtensionPage(self._browserService, self._browserListener,
                                                         self._coroutineRunner)
        self.runtimeInstallPage = RuntimeInstallPage(self._featureService)
        self.advancedOptionsPage = AdvancedOptionsPage(self._featureService)
        self.completePage = CompletePage()
        self.pages: list[ui.Node] = [self.welcomePage, self.basicSettingsPage, self.browserExtensionPage,
                                     self.runtimeInstallPage, self.advancedOptionsPage, self.completePage]
        self.stackedWidget = Slot(self.pages[self._currentIndex])

        def T(text: str) -> str:
            return tr("OobeWindow", text)

        self.backButton = ui.Button(T("上一步"), self._onBackClicked, ui.ButtonStyle.OUTLINED)
        self.skipButton = ui.Button(T("跳过全部"), self._finish, ui.ButtonStyle.TEXT)
        self.nextButton = ui.Button(T("下一步"), self._onNextClicked, ui.ButtonStyle.FILLED)
        self.leftBox = ui.Row(spacing=8)
        self.rightBox = ui.Row(spacing=8)
        self.pipsPager = ui.Row(spacing=8, cross_alignment=ui.Alignment.CENTER)
        left = ui.Box()
        left.set_size(240, None)
        left.append_child(self.leftBox)
        right = ui.Box()
        right.set_size(240, None)
        right.set_content_alignment(ui.Alignment.END, ui.Alignment.CENTER)
        right.append_child(self.rightBox)
        navBox = ui.Box()
        navBox.set_padding(0, 14, 0, 0)
        navBox.append_child(row(left, centered(self.pipsPager), right, flex=1))
        self.content.setChild(column(self.stackedWidget, navBox, flex=0))

        self.welcomePage.startClicked.connect(self._onNextClicked)
        self.basicSettingsPage.languageChanged.connect(self._onLanguageChanged)
        self.completePage.finishClicked.connect(self._finish)

    def _initLayout(self) -> None:
        box = ui.Box()
        box.set_padding(36, 24, 36, 16)
        box.append_child(self.content)
        self.surface.append_child(box)
        self.theme.append_child(self.surface)
        self.root = Slot(self.theme, fallback=WINDOW_SIZE)
        self.owner = ui.Owner(self.root)
        self.window = ui.Window(self.owner, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1], title="Ghost Downloader",
                                background=DARK_BACKGROUND if isDark() else LIGHT_BACKGROUND)
        self.window.set_minimum_size(*WINDOW_SIZE)
        setWindowIcon(self.window.handle, ASSETS_DIR / "logo.ico")

    def _bind(self) -> None:
        cfg.themeMode.valueChanged.connect(self._onThemeChanged)
        self.window.on_close = self._onCloseRequested

    def close(self) -> None:
        cfg.themeMode.valueChanged.disconnect(self._onThemeChanged)
        self.window.close()
        self.owner.close()

    def onPairRequested(self, request: PairRequest) -> None:
        self.browserExtensionPage.onPairRequested(request)

    def _onThemeChanged(self, *_args) -> None:
        self.theme.set_color_scheme(dark=isDark(), seed=systemAccentColor())

    def _onLanguageChanged(self) -> None:
        translator.load(cfg.language.value.value)
        self._initContent()
        self._refreshNavigation()

    def _refreshNavigation(self) -> None:
        index = self._currentIndex
        isFirst, isLast = index == 0, index == self.PAGE_COUNT - 1
        self.stackedWidget.setChild(self.pages[index])
        for box, buttons in ((self.leftBox, [self.skipButton] if isFirst else [] if isLast else [self.backButton]),
                             (self.rightBox, [] if isFirst or isLast else [self.nextButton])):
            while box.children:
                box.remove_child(0)
            for button in buttons:
                box.append_child(button)
        scheme = self.theme.color_scheme
        while self.pipsPager.children:
            self.pipsPager.remove_child(0)
        for i in range(self.PAGE_COUNT):
            pip = ui.Badge()
            color = scheme["primary"] if i == index else scheme["outline_variant"]
            pip.set_colors(color, color)
            self.pipsPager.append_child(pip)

    def _onNextClicked(self) -> None:
        if self._currentIndex >= self.PAGE_COUNT - 1:
            return
        if self._currentIndex == 3:
            self._installSelectedRuntimes()
        self._currentIndex += 1
        self._refreshNavigation()
        if self._currentIndex == 2:
            self.browserExtensionPage.refreshListenState()
        elif self._currentIndex == 3:
            self.runtimeInstallPage.mount()

    def _onBackClicked(self) -> None:
        if self._currentIndex <= 0:
            return
        self._currentIndex -= 1
        self._refreshNavigation()

    def _installSelectedRuntimes(self) -> None:
        for runtime in self.runtimeInstallPage.selectedRuntimes():
            if not runtime.path():
                self._runtimeStatusService.install(runtime)

    def _finish(self) -> None:
        if self._isFinished:
            return
        self._isFinished = True
        self.advancedOptionsPage.save()
        cfg.set(cfg.hasCompletedOobe, True)
        self.finished.emit()

    def _onCloseRequested(self) -> None:
        # 从标题栏关掉也算完成引导，但不保存「更多选项」，与 Qt 界面的 closeEvent 一致
        if not self._isFinished:
            self._isFinished = True
            cfg.set(cfg.hasCompletedOobe, True)
            self.finished.emit()
