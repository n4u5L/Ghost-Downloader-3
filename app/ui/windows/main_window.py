from __future__ import annotations

from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING

from bkit import ui

from app.config.cfg import CloseMode, cfg
from app.config.constants import DONATE_URL, FEEDBACK_URL
from app.config.paths import APP_DATA_DIR, EXECUTABLE_DIR
from app.models.task import TaskOptions
from app.platform.shell import openUrl, revealInFolder, setClipboardText, setWindowIcon, setWindowVisible
from app.services.task_draft import TaskDraft
from app.services.update_service import UpdateState
from app.ui.components.editors import SearchLineEdit
from app.ui.components.info_bar import InfoBarArea, InfoBarIcon
from app.ui.components.message_box import MessageBox
from app.ui.components.progress_toast import ProgressToast
from app.ui.dialogs.release_info import ReleaseInfoDialog
from app.ui.dialogs.task_draft import TaskDraftDialog
from app.ui.i18n import toLocalizedError, tr
from app.ui.icons import buildButton, buildIconButton, loadIcon
from app.ui.layout import Slot, checkBox, column, overlay, row, text
from app.ui.loop import UiLoop
from app.ui.pages.setting_page import Quit, SettingPage
from app.ui.pages.task_page import TaskPage
from app.ui.theme import isDark, systemAccentColor
from app.update import fetchAssetUrl, fetchRelease

if TYPE_CHECKING:
    from app.models.task import Task, TaskError
    from app.services.browser_service import BrowserService, PairRequest
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.plan import Plan
    from app.services.port_listener import PortListener
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService
    from app.services.update_service import UpdateInfo, UpdateService
    from app.sources import Release
    from app.ui.shell.clipboard_listener import ClipboardListener

DEFAULT_SIZE = (960, 540)
LIGHT_BACKGROUND = 0xFFFEF7FF
DARK_BACKGROUND = 0xFF141218
ICON_PATH = EXECUTABLE_DIR / "app" / "assets" / "logo.ico"
SEARCH_WIDTH = 360
TASK_PAGE, ADD_TASK, SETTING_PAGE = 0, 1, 2
NAVIGATION_ICONS = ["download", "add", "settings"]


def T(text: str) -> str:
    return tr("MainWindow", text)


class WindowRoot(Slot):
    """窗口的根节点；Ctrl+F 聚焦搜索框，对应 Qt 界面的 QShortcut(StandardKey.Find)。"""

    def __init__(self, child: ui.Node, onSearchShortcut: Callable[[], object]) -> None:
        super().__init__(child)
        self._onSearchShortcut = onSearchShortcut

    def on_key_event(self, event: ui.KeyEvent, /) -> bool:
        if (event.type == ui.KeyEventType.DOWN and event.key == ui.Key.F
                and event.modifiers & ui.KeyboardModifiers.CTRL):
            self._onSearchShortcut()
            return True
        return False


class MainWindow:
    """主窗口，对应 Qt 界面的 MSFluentWindow：左侧导航栏，右侧是页面，消息条浮在右下角。

    「新建任务」与 Qt 界面一样是不可选中的导航项；设置页在导航栏底部，第一次打开时才创建。
    关闭窗口按 cfg.closeMode 退出或隐藏到托盘。
    """

    def __init__(self, taskService: TaskService, featureService: FeatureService, browserService: BrowserService,
                 browserListener: PortListener, aria2RpcListener: PortListener, categoryService: CategoryService,
                 speedMeter: SpeedMeter, coroutineRunner: CoroutineRunner, plan: Plan, updateService: UpdateService,
                 clipboardListener: ClipboardListener, loadCrx: Callable[[], bytes], requestQuit: Quit,
                 uiLoop: UiLoop) -> None:
        self._taskService = taskService
        self._featureService = featureService
        self._browserService = browserService
        self._browserListener = browserListener
        self._aria2RpcListener = aria2RpcListener
        self._categoryService = categoryService
        self._speedMeter = speedMeter
        self._coroutineRunner = coroutineRunner
        self._plan = plan
        self._updateService = updateService
        self._clipboardListener = clipboardListener
        self._loadCrx = loadCrx
        self._requestQuit = requestQuit
        self._uiLoop = uiLoop
        self._draft = TaskDraft(coroutineRunner, featureService)
        self._settingPage: SettingPage | None = None
        self._messageBox: MessageBox | None = None
        self._dialog: ReleaseInfoDialog | None = None
        self._progressToast: ProgressToast | None = None
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.theme = ui.MaterialTheme(dark=isDark(), seed=systemAccentColor())
        self.surface = ui.Surface()
        self.navigationInterface = ui.NavigationRail(self._onNavigationSelected)
        for index, (label, icon) in enumerate(zip((T("下载任务"), T("新建任务"), T("设置")), NAVIGATION_ICONS)):
            if index == SETTING_PAGE:
                self.navigationInterface.add_flexible_space()
            # 与 MSFluentWindow 一样，每一项都显示文字
            self.navigationInterface.add_item(loadIcon(icon), label).set_always_show_label(True)
        # 对应 Qt 界面标题栏正中的搜索框，随页面换占位文字
        self.searchEdit = SearchLineEdit()
        searchBox = ui.Box()
        searchBox.set_size(SEARCH_WIDTH, None)
        searchBox.append_child(self.searchEdit)
        self.searchBar = ui.Box()
        self.searchBar.set_padding(0, 8)
        self.searchBar.set_content_alignment(ui.Alignment.CENTER, ui.Alignment.CENTER)
        self.searchBar.append_child(searchBox)
        self.searchSlot = ui.Box()
        self.infoBars = InfoBarArea(self._uiLoop)
        self.taskPage = TaskPage(self._taskService, self._categoryService, self._speedMeter, self._plan,
                                 self._clipboardListener.setUrls, self.infoBars, self._uiLoop)
        self.stackedWidget = Slot(self.taskPage)
        self._setPage(TASK_PAGE)

    def _initLayout(self) -> None:
        infoBarBox = ui.Box()
        infoBarBox.set_padding(0, 0, 16, 16)
        infoBarBox.append_child(self.infoBars.node)
        content = overlay(column(self.searchSlot, self.stackedWidget, flex=1), infoBarBox,
                          ui.Alignment.END, ui.Alignment.END)
        self.surface.append_child(row(self.navigationInterface, content, flex=1))
        self.theme.append_child(self.surface)
        self.root = WindowRoot(self.theme, self._onSearchShortcut)

        _, _, width, height = cfg.geometry.value
        if width <= 0 or height <= 0:
            width, height = DEFAULT_SIZE
        self.owner = ui.Owner(self.root)
        self.window = ui.Window(self.owner, width=width, height=height, title="Ghost Downloader",
                                background=DARK_BACKGROUND if isDark() else LIGHT_BACKGROUND)
        self.window.set_minimum_size(*DEFAULT_SIZE)
        setWindowIcon(self.window.handle, ICON_PATH)

    def _bind(self) -> None:
        self._draft.taskConfirmed.connect(self._taskService.add)
        self._updateService.changed.connect(self._onUpdateChanged)
        cfg.themeMode.valueChanged.connect(self._onThemeChanged)
        self.searchEdit.textChanged.connect(self._onSearchTextChanged)
        self.window.on_close = self._onCloseRequested

    def addUrls(self, urls: list[str]) -> None:
        dialog = self._draftDialog
        if urls:
            dialog.addUrls(urls)
        if not dialog.isOpen:
            dialog.open()

    def addTasks(self, tasks: list[Task]) -> None:
        dialog = self._draftDialog
        dialog.addParsedTasks(tasks)
        if not dialog.isOpen:
            dialog.open()

    def setVisible(self, isVisible: bool) -> None:
        setWindowVisible(self.window.handle, isVisible)

    def close(self) -> None:
        self.window.close()
        self.owner.close()

    @cached_property
    def _draftDialog(self) -> TaskDraftDialog:
        return TaskDraftDialog(self._draft, self._featureService, self._categoryService,
                               self._taskService.probeConflict, self.surface, self._uiLoop)

    def _setPage(self, index: int) -> None:
        if index == SETTING_PAGE:
            if self._settingPage is None:
                self._settingPage = SettingPage(
                    self._featureService, self._browserService, self._browserListener, self._aria2RpcListener,
                    self._coroutineRunner, self._categoryService, self._updateService, self._loadCrx,
                    self._requestQuit, self.infoBars, self._uiLoop,
                )
            page = self._settingPage
        else:
            page = self.taskPage
        self.stackedWidget.setChild(page)
        self.navigationInterface.selected_index = index
        self._updateSearchTarget(page)

    def _updateSearchTarget(self, page: TaskPage | SettingPage) -> None:
        self.searchEdit.clear()
        placeholder = getattr(page, "searchPlaceholder", None)
        if placeholder is not None:
            self.searchEdit.setPlaceholderText(placeholder)
            if not self.searchSlot.children:
                self.searchSlot.append_child(self.searchBar)
        elif self.searchSlot.children:
            self.searchSlot.remove_child(0)

    def _onSearchTextChanged(self, value: str) -> None:
        page = self.stackedWidget.children[0] if self.stackedWidget.children else None
        if hasattr(page, "setSearchText"):
            page.setSearchText(value)

    def _onSearchShortcut(self) -> None:
        if self.searchSlot.children:
            self.searchEdit.setFocus()

    def _onNavigationSelected(self, index: int) -> None:
        if index == ADD_TASK:
            self.addUrls([])
            return
        self._setPage(index)

    def onPairRequested(self, request: PairRequest) -> None:
        content = T(
            "浏览器扩展正在请求连接到 Ghost Downloader。\n\n"
            "来源: {0}\n客户端: {1}\n扩展版本: {2}\n\n"
            "仅在你刚刚点击扩展里的\"自动配对\"时允许。"
        ).format(request.peerAddress, request.clientKind or T("浏览器扩展"), request.extensionVersion or T("未知"))
        box = MessageBox(T("浏览器扩展配对请求"), content, self.surface)
        box.yesButton.text = T("允许配对")
        box.cancelButton.text = T("拒绝")
        box.accepted.connect(lambda: self._browserService.approvePair(request.requestId))
        box.rejected.connect(lambda: self._browserService.rejectPair(request.requestId))
        box.open()
        self._messageBox = box

    def onBrowserListenFailed(self, error: TaskError) -> None:
        self._onListenFailed(T("浏览器扩展服务无法启动"), error)

    def onAria2ListenFailed(self, error: TaskError) -> None:
        self._onListenFailed(T("Aria2 RPC 兼容服务无法启动"), error)

    def _onListenFailed(self, title: str, error: TaskError) -> None:
        infoBar = self.infoBars.add(title, toLocalizedError(error), icon=InfoBarIcon.ERROR, duration=None)
        infoBar.addWidget(buildButton("settings", T("前往设置"),
                                      lambda: (infoBar.close(), self._setPage(SETTING_PAGE))))

    # ── 更新 ──

    def onUpdateAvailable(self, info: UpdateInfo) -> None:
        if self._progressToast is not None:
            self._progressToast.close()
            self._progressToast = None
        infoBar = self.infoBars.add(T("检测到新版本"), T("最新版本: {0}").format(info.latestVersion),
                                    icon=InfoBarIcon.CLOUD, duration=None)
        infoBar.addWidget(buildButton("download", T("立即下载"),
                                      lambda: (infoBar.close(), self._updateService.download("app")),
                                      ui.ButtonStyle.FILLED))
        infoBar.addWidget(buildButton("chat", T("查看详情"), self._openReleaseDetails))
        infoBar.addWidget(buildButton("favorite", T("请作者喝咖啡"), lambda: openUrl(DONATE_URL)))

    def _onUpdateChanged(self, info: UpdateInfo) -> None:
        if info.targetId != "app" or info.state not in (UpdateState.DOWNLOADING, UpdateState.READY,
                                                         UpdateState.FAILED):
            return
        if self._progressToast is None:
            self._progressToast = ProgressToast(self.infoBars, lambda: self._updateService.download("app"),
                                                self._requestQuit)
        self._progressToast.setInfo(info)

    def _openReleaseDetails(self) -> None:
        self._coroutineRunner.submit(fetchRelease(), done=self._onReleaseFetched)

    def _onReleaseFetched(self, release: Release) -> None:
        dialog = ReleaseInfoDialog(release, self.surface)

        def onAccepted() -> None:
            asset = dialog.selectedAsset()
            if asset is not None:
                self._coroutineRunner.submit(fetchAssetUrl(release.version, asset.name), done=self._onAssetUrlFetched)

        dialog.accepted.connect(onAccepted)
        dialog.open()
        self._dialog = dialog

    def _onAssetUrlFetched(self, url: str) -> None:
        self._coroutineRunner.submit(self._featureService.parse(TaskOptions(url=url)), done=self._taskService.add)

    # ── 异常与关闭 ──

    def onExceptionCaught(self, message: str) -> None:
        if self._messageBox is not None and self._messageBox.isOpen:
            return
        box = MessageBox("", T("点击\"确定\"后将复制错误信息并打开反馈页面。\n\n{0}").format(message), self.surface)
        # 与 Qt 界面一样，查看日志是标题行右侧的图标按钮
        logBox, _ = buildIconButton("description", T("查看日志"), self._openLogFolder)
        box.contentLayout.insert_child(0, row(text(T("程序发生异常"), fontSize=20, fontWeight=600), logBox, flex=0))

        def onAccepted() -> None:
            setClipboardText(message)
            openUrl(FEEDBACK_URL)

        box.accepted.connect(onAccepted)
        box.open()
        self._messageBox = box

    def _openLogFolder(self) -> None:
        revealInFolder(f"{APP_DATA_DIR}/GhostDownloader.log")

    def _onThemeChanged(self, *_args) -> None:
        self.theme.set_color_scheme(dark=isDark(), seed=systemAccentColor())
        self.searchEdit.refreshColors()

    def _onCloseRequested(self) -> None:
        self._saveGeometry()
        mode = cfg.closeMode.value
        if mode == CloseMode.QUIT:
            self._requestQuit()
            return
        # 留在后台或先询问：窗口不关，由这里决定隐藏还是退出
        self.window.should_close = False
        if mode == CloseMode.BACKGROUND:
            self.setVisible(False)
            return
        if self._messageBox is not None and self._messageBox.isOpen:
            return
        box = MessageBox(T("是否完全退出程序？"), T("后台运行时可通过系统托盘图标重新打开。"), self.surface)
        box.yesButton.text = T("退出程序")
        box.cancelButton.text = T("继续在后台运行")
        rememberRow, remember = checkBox(T("记住我的选择"))
        box.viewLayout.append_child(rememberRow)

        def onClosed(mode: CloseMode) -> None:
            if remember.checked:
                cfg.set(cfg.closeMode, mode)
            if mode == CloseMode.QUIT:
                self._requestQuit()
            else:
                self.setVisible(False)

        box.accepted.connect(lambda: onClosed(CloseMode.QUIT))
        box.rejected.connect(lambda: onClosed(CloseMode.BACKGROUND))
        box.open()
        self._messageBox = box

    def _saveGeometry(self) -> None:
        width, height = self.window.size
        if width and height:
            scale = self.window.content_scale
            x, y, _, _ = cfg.geometry.value
            cfg.set(cfg.geometry, (x, y, round(width / scale), round(height / scale)))
