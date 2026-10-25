"""设置页，分组与卡片顺序同 Qt 界面。

尚未移植的卡片：界面缩放与窗口材质（bkit 窗口不支持）。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import LANGUAGE_TEXTS, addRecentFolder, cfg
from app.config.constants import (
    AUTHOR, AUTHOR_URL, CHROME_WEBSTORE_URL, EDGE_ADDONS_URL, FEEDBACK_URL, FIREFOX_ADDONS_URL, VERSION, YEAR,
)
from app.config.paths import APP_DATA_DIR, PORTABLE_DIR, USER_DATA_DIR, isPortable, migrate
from app.models.task import toTaskError
from app.platform.file_dialog import openSaveFileDialog
from app.platform.shell import openUrl, revealInFolder, setClipboardText
from app.services.port_listener import ListenStatus
from app.services.update_service import UpdateState
from app.ui.components.category_settings import CategoryRulesCard
from app.ui.components.editors import FolderPicker
from app.ui.components.info_bar import InfoBarArea, InfoBarIcon
from app.ui.components.message_box import MessageBox, MessageBoxBase
from app.ui.components.setting_card_group import SettingCardGroup
from app.ui.components.setting_cards import (
    ClipboardSettingCard, ComboBoxSettingCard, HeadersPresetSettingCard, HyperlinkCard, IdentitySettingCard, LineEditSettingCard, ProxySettingCard, PushSettingCard,
    RangeSettingCard, SettingCard, SpinBoxSettingCard, SwitchSettingCard, fixedWidth,
)
from app.ui.dialogs.extension_install import ExtensionInstallDialog
from app.ui.dialogs.pack_info import PackInfoDialog
from app.i18n import toLocalizedError, tr
from app.ui.icons import buildIconButton
from app.ui.layout import Slot, column
from app.ui.loop import UiLoop
from app.ui.pages.task_page import EmptyStatusWidget

if TYPE_CHECKING:
    from app.services.browser_service import BrowserService
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.port_listener import PortListener
    from app.services.update_service import UpdateInfo, UpdateService

KB = 1024
# 退出程序；给出的回调在服务都停下、数据写完之后运行，如迁移数据目录
Quit = Callable[..., None]


def T(text: str) -> str:
    return tr("SettingPage", text)


class SettingPage(ui.Node):

    def __init__(self, featureService: FeatureService, browserService: BrowserService, browserListener: PortListener,
                 aria2RpcListener: PortListener, coroutineRunner: CoroutineRunner, categoryService: CategoryService,
                 updateService: UpdateService, loadCrx: Callable[[], bytes], requestQuit: Quit,
                 infoBars: InfoBarArea, uiLoop: UiLoop) -> None:
        super().__init__()
        self._featureService = featureService
        self._browserService = browserService
        self._browserListener = browserListener
        self._aria2RpcListener = aria2RpcListener
        self._coroutineRunner = coroutineRunner
        self._categoryService = categoryService
        self._updateService = updateService
        self._loadCrx = loadCrx
        self._requestQuit = requestQuit
        self._infoBars = infoBars
        self._uiLoop = uiLoop
        self._post = uiLoop.post
        # 打开中的对话框；bkit 的对话框不阻塞，要有人持有它
        self._dialog: MessageBoxBase | None = None
        self._installDialog: ExtensionInstallDialog | None = None

        self.generalGroup = SettingCardGroup(T("综合下载设置"), "general")
        self.categoryGroup = SettingCardGroup(T("下载分类"), "category")
        self.associationGroup = SettingCardGroup(T("关联设置"), "association")
        self.browserGroup = SettingCardGroup(T("浏览器扩展"), "browser")
        self.aria2RpcGroup = SettingCardGroup(T("Aria2 RPC 兼容"), "aria2rpc")
        self.personalGroup = SettingCardGroup(T("个性化"), "personalization")
        self.softwareGroup = SettingCardGroup(T("应用"), "software")
        self.aboutGroup = SettingCardGroup(T("关于"), "about")

        self._initWidget()
        self._initCards()
        self._initLayout()
        self._bind()
        self._refreshBrowserStatus()
        self._refreshAria2Status()

    def _initWidget(self) -> None:
        self.vBoxLayout = column(spacing=12)
        box = ui.Box()
        box.set_padding(16, 0, 16, 16)
        box.append_child(self.vBoxLayout)
        self.scrollArea = ui.ScrollContainer()
        self.scrollArea.append_child(box)
        self.emptyStatusWidget = EmptyStatusWidget("search", T("未找到匹配的设置项"))
        self.contentSlot = Slot(self.scrollArea)
        self.append_child(self.contentSlot)

    def _initCards(self) -> None:
        post = self._post
        self.speedLimitationCard = SpinBoxSettingCard(
            "speed", T("下载限速"), T("当下载任务界面限速开关开启时，所有任务将根据此值进行限速"),
            cfg.speedLimitation, post, suffix="KB/s", unit=KB,
        )
        self.downloadFolderCard = SettingCard("folder", T("下载路径"), T("文件默认保存位置"))
        self.downloadFolderPicker = FolderPicker(lambda: cfg.downloadFolder.defaultValue, T("系统默认"), post)
        self.downloadFolderPicker.setPath(cfg.downloadFolder.value)
        self.downloadFolderCard.setControl(fixedWidth(self.downloadFolderPicker, 400))

        self.generalGroup.addSettingCards([
            RangeSettingCard(cfg.maxTaskNum, "train", T("最大任务数"), T("最多能同时进行的任务数量")),
            RangeSettingCard(cfg.preBlockNum, "cloud", T("预分配线程数"),
                             T("线程越多，下载越快。线程数大于 64 时，有触发反爬导致文件损坏的风险")),
            SwitchSettingCard("speed", T("自动提速"), T("AI 实时检测各线程效率并自动增加线程数以提高下载速度"),
                              cfg.autoSpeedUp),
            SpinBoxSettingCard("library_books", T("最小再分配大小"),
                               T("每线程剩余量大于此值时, 有线程完成或自动提速条件满足会触发重新分配"),
                               cfg.maxReassignSize, post, suffix="KB"),
            self.speedLimitationCard,
            SwitchSettingCard("history", T("保留文件修改时间"),
                              T("下载完成后将文件的修改时间设为服务器提供的 Last-Modified 值"),
                              cfg.shouldPreserveLastModified),
            SwitchSettingCard("build", T("下载时验证 SSL 证书"), T("文件无法下载时，可尝试关闭该选项"),
                              cfg.shouldVerifySsl),
            self.downloadFolderCard,
            ComboBoxSettingCard(cfg.nameConflict, "content_copy", T("同名文件"), T("下载目录中已有同名文件时的处理方式"),
                                texts=[T("保留两者"), T("覆盖"), T("询问")]),
            SwitchSettingCard("cable", T("使用系统 DNS"), T("使用操作系统的 DNS 解析，兼容 TUN、VPN 和代理等网络环境"),
                              cfg.shouldUseSystemDns),
            ProxySettingCard(cfg.proxyServer, self._featureService, post),
            IdentitySettingCard(),
            HeadersPresetSettingCard(),
        ])

        self.categoryGroup.addSettingCards([
            SwitchSettingCard("label", T("启用下载分类"), T("根据扩展名将下载任务归类，便于筛选与分发到指定文件夹"),
                              cfg.isCategoryEnabled),
            CategoryRulesCard(self._categoryService, self._uiLoop),
        ])

        self.urlSchemeCard = SwitchSettingCard(
            "link", T("允许浏览器扩展唤醒"), T("浏览器扩展可通过 ghostdownloader:// 协议启动桌面端"),
            cfg.isUrlSchemeRegistered,
        )
        associationCards: list[ui.Node] = [self.urlSchemeCard]
        for pack in self._featureService.packs:
            if pack.config is None:
                continue
            fileTypes = pack.fileTypes()
            if fileTypes and pack.config.associateFileTypes is not None:
                extensions = "/".join(ext for ft in fileTypes for ext in ft.extensions)
                associationCards.append(SwitchSettingCard(
                    "description", T("关联 {0} 文件").format(extensions),
                    T("双击 {0} 文件时用 Ghost Downloader 打开").format(extensions),
                    pack.config.associateFileTypes,
                ))
            schemes = pack.uriSchemes()
            if schemes and pack.config.associateUriSchemes is not None:
                schemeText = "/".join(s.displayName for s in schemes)
                associationCards.append(SwitchSettingCard(
                    "link", T("处理 {0} 链接").format(schemeText),
                    T("点击 {0} 链接时唤起 Ghost Downloader").format(schemeText),
                    pack.config.associateUriSchemes,
                ))
        self.associationGroup.addSettingCards(associationCards)

        self.browserEnableCard = SwitchSettingCard("cable", T("启用浏览器扩展"), "", cfg.isBrowserExtensionEnabled)
        self.browserPairTokenCard = PushSettingCard(
            T("复制令牌"), "content_copy", T("配对令牌"), cfg.browserExtensionPairToken.value, isPrimary=True)
        regenerateTokenBox, self.regenerateTokenButton = buildIconButton("sync", T("重新生成令牌"),
                                                                         variant=ui.IconButtonVariant.OUTLINED)
        self.browserPairTokenCard.insertWidget(1, regenerateTokenBox)
        self.storeInstallCard = HyperlinkCard(
            FIREFOX_ADDONS_URL, T("Firefox 商店"), "public", T("从商店安装扩展"), T("商店版扩展需等待审核后才能获得更新"))
        self.storeInstallCard.addLink(T("Edge 商店"), EDGE_ADDONS_URL)
        self.storeInstallCard.addLink(T("Chrome 商店"), CHROME_WEBSTORE_URL)
        self.chromiumInstallCard = PushSettingCard(
            T("一键安装"), "download", T("安装到 Chromium 浏览器"),
            T("自动解包扩展并引导加载（Chrome / Brave 等），扩展随桌面端更新自动升级"), isPrimary=True,
        )
        self.exportExtensionButton = ui.Button(T("导出 CRX"), lambda: self._post(self._onExportExtension),
                                               ui.ButtonStyle.TEXT)
        self.chromiumInstallCard.insertWidget(0, self.exportExtensionButton)
        self.browserPortCard = SpinBoxSettingCard(
            "terminal", T("服务端口"), T("浏览器扩展连接使用的端口"), cfg.browserExtensionPort, post)
        self.browserGroup.addSettingCards([
            self.browserEnableCard,
            SwitchSettingCard("chat", T("接管下载时进入草稿模式"),
                              T("自动接管浏览器下载时先进入草稿，方便您调整下载路径和文件名"),
                              cfg.shouldDraftTakenDownload),
            self.browserPairTokenCard,
            self.storeInstallCard,
            self.chromiumInstallCard,
            self.browserPortCard,
        ])

        self.aria2EnableCard = SwitchSettingCard("link", T("启用 Aria2 RPC 兼容"), "", cfg.isAria2RpcEnabled)
        self.aria2RpcGroup.addSettingCards([
            self.aria2EnableCard,
            SpinBoxSettingCard("public", T("监听端口"), T("Aria2 RPC 默认端口为 16800"), cfg.aria2RpcPort, post),
            LineEditSettingCard("fingerprint", T("令牌"), T("若设置，客户端需传入 token 才可创建任务"),
                                cfg.aria2RpcToken, post, placeholder=T("可选"), isPassword=True),
            SwitchSettingCard("vpn_lock", T("模拟浏览器指纹"), T("为通过 Aria2 RPC 接收的任务附加浏览器 TLS 指纹与请求头"),
                              cfg.aria2RpcEmulateFingerprint),
        ])

        self.personalGroup.addSettingCards([
            ComboBoxSettingCard(cfg.themeMode, "brush", T("应用主题"), T("更改应用程序的外观"),
                                texts=[T("浅色"), T("深色"), T("跟随系统设置")]),
            ComboBoxSettingCard(cfg.language, "language", T("语言"), T("设置界面的首选语言"),
                                texts=[LANGUAGE_TEXTS.get(lang, T("使用系统设置")) for lang in cfg.language.options]),
        ])

        self.autoRunCard = SwitchSettingCard(
            "vpn_lock", T("开机启动"), T("在系统启动时静默运行 Ghost Downloader"), cfg.shouldRunAtLogin)
        self.commandLineToolCard = PushSettingCard(
            "", "terminal", T("命令行工具"), T("安装后可在终端中使用 ghd 命令添加和管理任务"))
        self._refreshCommandLineToolCard()
        if isPortable():
            self.migrateCard = PushSettingCard(
                T("切换到用户模式"), "sync", T("数据存储模式"),
                T("当前为 Portable 模式，数据保存在程序旁: {0}").format(APP_DATA_DIR),
            )
        else:
            self.migrateCard = PushSettingCard(
                T("切换到 Portable 模式"), "sync", T("数据存储模式"),
                T("当前为用户模式，数据保存在: {0}").format(APP_DATA_DIR),
            )
        self.softwareGroup.addSettingCards([
            SwitchSettingCard("update", T("在应用程序启动时检查更新"), T("新版本将更稳定，并具有更多功能"),
                              cfg.shouldCheckUpdateAtStartup),
            self.autoRunCard,
            self.commandLineToolCard,
            ComboBoxSettingCard(cfg.closeMode, "power_settings_new", T("关闭主窗口时"),
                                T("设置关闭主窗口后程序继续在后台运行还是退出"),
                                texts=[T("关闭时询问"), T("继续在后台运行"), T("退出程序")]),
            ClipboardSettingCard(self._featureService.packs),
            self.migrateCard,
        ])

        self.feedbackCard = PushSettingCard(
            T("提供反馈"), "feedback", T("提供反馈"), T("通过提供反馈来帮助我们改进 Ghost Downloader，也可查看日志排查问题"),
            isPrimary=True,
        )
        self.openLogButton = ui.Button(T("查看日志"), self._onOpenLogClicked, ui.ButtonStyle.OUTLINED)
        self.feedbackCard.insertWidget(1, self.openLogButton)
        self.packInfoCard = PushSettingCard(T("查看详情"), "developer_board", T("功能包"), T("管理已安装的功能包"),
                                            isPrimary=True)
        self.aboutCard = PushSettingCard(T("检查更新"), "info", T("关于"),
                                         f"© Copyright {YEAR}, {AUTHOR}. Version {VERSION}", isPrimary=True)
        self.aboutGroup.addSettingCards([
            HyperlinkCard(AUTHOR_URL, T("打开作者的个人空间"), "co_present", T("了解作者"),
                          T("发现更多 {} 的作品").format(AUTHOR)),
            self.feedbackCard,
            self.packInfoCard,
            self.aboutCard,
        ])

    def _initLayout(self) -> None:
        groups = [self.generalGroup, self.categoryGroup, self.associationGroup, self.browserGroup,
                  self.aria2RpcGroup, self.personalGroup, self.softwareGroup, self.aboutGroup]
        # 对应 Qt 界面的 _restoreOrder：按保存的顺序排，没排过的按默认顺序，「关于」默认在最后
        keyToGroup = {group.key: group for group in groups}
        order = [key for key in cfg.settingGroupOrder.value if key in keyToGroup]
        rest = [group.key for group in groups if group.key not in order]
        if self.aboutGroup.key in rest:
            rest.remove(self.aboutGroup.key)
            rest.append(self.aboutGroup.key)
        self._groups = [keyToGroup[key] for key in order + rest]
        self._refreshGroups(self._groups)

    @property
    def searchPlaceholder(self) -> str:
        return T("搜索设置")

    def setSearchText(self, value: str) -> None:
        visible = [group for group in self._groups if group.setSearchText(value)]
        self._refreshGroups(visible)
        self.contentSlot.setChild(self.scrollArea if visible else self.emptyStatusWidget)

    def _refreshGroups(self, visible: list[SettingCardGroup]) -> None:
        if list(self.vBoxLayout.children) != visible:
            while self.vBoxLayout.children:
                self.vBoxLayout.remove_child(0)
            for group in visible:
                self.vBoxLayout.append_child(group)
        for index, group in enumerate(self._groups):
            group.setMoveEnabled(index > 0, index < len(self._groups) - 1)

    def _onGroupMoveRequested(self, group: SettingCardGroup, offset: int) -> None:
        index = self._groups.index(group)
        target = index + offset
        if not 0 <= target < len(self._groups):
            return
        self._groups.insert(target, self._groups.pop(index))
        self._refreshGroups(self._groups)
        # 已不存在的组的位置留着，与 Qt 界面的 _saveOrder 一致
        keys = [g.key for g in self._groups]
        cfg.set(cfg.settingGroupOrder, keys + [k for k in cfg.settingGroupOrder.value if k not in keys])

    def _bind(self) -> None:
        for group in self._groups:
            group.moveRequested.connect(self._onGroupMoveRequested)
        cfg.appRestartSig.connect(self._onRestartRequired)
        self.downloadFolderPicker.pathChanged.connect(self._onDownloadFolderChanged)
        cfg.browserExtensionPairToken.valueChanged.connect(self._refreshPairTokenCard)
        self._browserService.connectionChanged.connect(self._refreshBrowserStatus)
        self._browserListener.stateChanged.connect(self._refreshBrowserStatus)
        self._aria2RpcListener.stateChanged.connect(self._refreshAria2Status)

        self.browserPairTokenCard.clicked.connect(self._onCopyTokenClicked)
        self.regenerateTokenButton.on_click = self._onRegenerateTokenClicked
        self.chromiumInstallCard.clicked.connect(self._onChromiumInstallClicked)
        self.urlSchemeCard.checkedChanged.connect(self._onUrlSchemeChanged)
        self.autoRunCard.checkedChanged.connect(self._onRunAtLoginChanged)
        self.commandLineToolCard.clicked.connect(self._onCommandLineToolClicked)
        self.feedbackCard.clicked.connect(lambda: openUrl(FEEDBACK_URL))
        self.migrateCard.clicked.connect(self._onMigrateClicked)
        self.packInfoCard.clicked.connect(self._onPackInfoClicked)
        self.aboutCard.clicked.connect(self._onAboutCardClicked)

    def _onDownloadFolderChanged(self, path: str) -> None:
        cfg.set(cfg.downloadFolder, path)
        addRecentFolder(cfg.downloadFolder.value)

    def _onRestartRequired(self) -> None:
        self._infoBars.add(T("已配置"), T("重启软件后生效"), icon=InfoBarIcon.SUCCESS, duration=1.5)

    def _refreshPairTokenCard(self, *_args) -> None:
        self.browserPairTokenCard.setContent(cfg.browserExtensionPairToken.value)

    def _onCopyTokenClicked(self) -> None:
        token = cfg.browserExtensionPairToken.value
        setClipboardText(token)
        self._infoBars.add(T("已复制配对令牌"), token, icon=InfoBarIcon.SUCCESS, duration=2.0)

    def _onRegenerateTokenClicked(self) -> None:
        setClipboardText(self._browserService.regenerateToken())
        self._infoBars.add(T("已重新生成配对令牌"), T("新令牌已复制到剪贴板"), icon=InfoBarIcon.SUCCESS, duration=2.0)

    def _onChromiumInstallClicked(self) -> None:
        self._coroutineRunner.submit(self._browserService.install(), done=self._onExtensionExtractDone,
                                     failed=self._onExtensionExtractFailed)

    def _onExtensionExtractDone(self, path) -> None:
        self._installDialog = ExtensionInstallDialog(path, self)
        self._installDialog.open()

    def _onExtensionExtractFailed(self, error) -> None:
        self._infoBars.add(T("解包失败"), toLocalizedError(toTaskError(error)), icon=InfoBarIcon.ERROR, duration=3.0)

    def _onExportExtension(self) -> None:
        path = openSaveFileDialog(T("选择导出路径"), "Extension.crx", [("Chromium Extension", "*.crx")])
        if path:
            Path(path).write_bytes(self._loadCrx())

    def _refreshBrowserStatus(self, *_args) -> None:
        state = self._browserListener.state
        installType, version = self._browserService.connectionSummary
        if state.status == ListenStatus.OFF:
            content = T("接收来自浏览器的下载信息，请安装浏览器扩展后使用")
        elif state.status == ListenStatus.FAILED:
            content = toLocalizedError(state.error)
        elif not installType:
            content = T("未连接")
        elif installType == "development":
            content = T("已连接 v{} (桌面端自管理)").format(version)
        else:
            content = T("已连接 v{} (商店安装)").format(version)
        self.browserEnableCard.setContent(content)

    def _refreshAria2Status(self, *_args) -> None:
        state = self._aria2RpcListener.state
        if state.status == ListenStatus.OFF:
            content = T("兼容 Aria2 JSON-RPC 协议，可接收外部工具发送的下载链接")
        elif state.status == ListenStatus.FAILED:
            content = toLocalizedError(state.error)
        else:
            content = T("正在端口 {} 上监听").format(state.port)
        self.aria2EnableCard.setContent(content)

    def _onUrlSchemeChanged(self, enabled: bool) -> None:
        from app.platform.file_association import registerUrlScheme, unregisterUrlScheme
        if enabled:
            registerUrlScheme()
        else:
            unregisterUrlScheme()

    def _onRunAtLoginChanged(self, enabled: bool) -> None:
        from app.platform.run_at_login import setRunAtLogin
        setRunAtLogin(enabled)

    def _refreshCommandLineToolCard(self) -> None:
        from app.platform import cli_install
        self.commandLineToolCard.button.enabled = True
        self.commandLineToolCard.button.text = T("卸载") if cli_install.isInstalled() else T("安装")

    def _onCommandLineToolClicked(self) -> None:
        from app.platform import cli_install
        work = cli_install.delete() if cli_install.isInstalled() else cli_install.install()
        self.commandLineToolCard.button.enabled = False
        self._coroutineRunner.submit(work, done=self._onCommandLineToolDone, failed=self._onCommandLineToolFailed)

    def _onCommandLineToolDone(self, _result) -> None:
        from app.platform import cli_install
        self._refreshCommandLineToolCard()
        if not cli_install.isInstalled():
            self._infoBars.add(T("已卸载命令行工具"), icon=InfoBarIcon.SUCCESS, duration=2.0)
            return
        self._infoBars.add(T("已安装命令行工具"), T("新打开的终端即可使用 ghd"), icon=InfoBarIcon.SUCCESS)

    def _onCommandLineToolFailed(self, error) -> None:
        from app.platform import cli_install
        self._refreshCommandLineToolCard()
        title = T("卸载命令行工具失败") if cli_install.isInstalled() else T("安装命令行工具失败")
        self._infoBars.add(title, toLocalizedError(toTaskError(error)), icon=InfoBarIcon.ERROR)

    def _onMigrateClicked(self) -> None:
        target = USER_DATA_DIR if isPortable() else PORTABLE_DIR
        mode = T("用户模式") if isPortable() else T("Portable 模式")
        box = MessageBox(T("切换数据存储模式"),
                         T("确定要切换到{0}吗？\n\n数据将被复制到新位置，程序随后退出。请手动重新打开。").format(mode), self)
        box.accepted.connect(lambda: self._requestQuit(lambda: migrate(target)))
        box.open()
        self._dialog = box

    def _onPackInfoClicked(self) -> None:
        self._dialog = PackInfoDialog(self._featureService.packs, self._updateService, self)
        self._dialog.open()

    def _onAboutCardClicked(self) -> None:
        self._infoBars.add(T("检查更新"), T("正在检查更新..."), duration=1.5)
        self._updateService.changed.connect(self._onUpdateChecked)
        self._updateService.check()

    def _onUpdateChecked(self, info: UpdateInfo) -> None:
        # 只等这一次检查的结果：有新版本时主窗口另行提示
        if info.targetId != "app" or info.state not in (UpdateState.AVAILABLE, UpdateState.IDLE):
            return
        self._updateService.changed.disconnect(self._onUpdateChecked)
        if info.state != UpdateState.IDLE:
            return
        if info.error is not None:
            self._infoBars.add(T("检查更新失败"), T("无法获取最新版本信息"), icon=InfoBarIcon.ERROR, duration=3.0)
        else:
            self._infoBars.add(T("当前已是最新版本"), icon=InfoBarIcon.SUCCESS, duration=3.0)

    def _onOpenLogClicked(self) -> None:
        revealInFolder(f"{APP_DATA_DIR}/GhostDownloader.log")
