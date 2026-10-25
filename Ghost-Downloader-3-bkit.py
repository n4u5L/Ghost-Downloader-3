"""bkit 界面的入口，与 Qt 界面并行开发期间独立存在。

bkit 不在 PyPI 上：BKIT_PYTHON_PATH 指向 bkit 构建产出的 build/python/<config> 目录，
其中 _ui 扩展需与本项目的 Python 版本一致。仅支持 Windows。
"""
import ctypes
import getpass
import os
import sys
import traceback

from app.config.paths import APP_DATA_DIR, EXECUTABLE_DIR

ERROR_FILE_NOT_FOUND = 2
ERROR_ALREADY_EXISTS = 183
# 与 app/platform/instance.py 的 QLocalServer 同名：Qt 版运行时，Windows 上存在这个命名管道
QT_INSTANCE_PIPE = rf"\\.\pipe\GhostDownloader-{getpass.getuser()}"
INSTANCE_MUTEX = f"Local\\GhostDownloader-{getpass.getuser()}-bkit"


def exceptionHook(exceptionType, value, tb):
    from loguru import logger
    logger.opt(exception=(exceptionType, value, tb)).error("Unhandled application exception")
    sys.__excepthook__(exceptionType, value, tb)


def isQtInstanceRunning() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitNamedPipeW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong]
    if kernel32.WaitNamedPipeW(QT_INSTANCE_PIPE, 1):
        return True
    return ctypes.get_last_error() != ERROR_FILE_NOT_FOUND


def createInstanceMutex() -> int | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, INSTANCE_MUTEX)
    if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def loadCrx() -> bytes:
    return (EXECUTABLE_DIR / "app" / "assets" / "chrome_extension.crx").read_bytes()


def main() -> int:
    if sys.platform != "win32":
        print("bkit 界面目前只支持 Windows", file=sys.stderr)
        return 1
    if path := os.environ.get("BKIT_PYTHON_PATH"):
        sys.path.insert(0, path)
    try:
        import bkit.ui  # noqa: F401
    except ImportError:
        traceback.print_exc()
        print("无法导入 bkit：请将 BKIT_PYTHON_PATH 设为 bkit 的 build/python/<config> 目录", file=sys.stderr)
        return 1

    from loguru import logger
    logger.add(f"{APP_DATA_DIR}/GhostDownloader.log", rotation="512 KB", retention=5)
    sys.excepthook = exceptionHook

    if isQtInstanceRunning():
        print("Ghost Downloader（Qt 版）正在运行，请先退出", file=sys.stderr)
        return 1
    if createInstanceMutex() is None:
        # 已有 bkit 实例在运行：把命令行交给它，由它显示主窗口或打开链接
        from app.ui.shell.tray import requestInvocation
        requestInvocation(sys.argv[1:], os.getcwd())
        return 0

    from app.config.cfg import cfg
    from app.config.constants import VERSION
    from app.platform.hidden_subprocess import setupHiddenSubprocess
    # 过渡期：cfg 仍是 qfluentwidgets 的 QConfig，只用到它的读写与信号，不需要 QApplication
    from qfluentwidgets import qconfig

    setupHiddenSubprocess()
    qconfig.load(f"{APP_DATA_DIR}/UserConfig.json", cfg)

    from app.ui.i18n import translator
    translator.load(cfg.language.value.value)
    logger.info("Ghost Downloader v{} launched (bkit)", VERSION)

    from winloop import new_event_loop
    from app.engine import Engine
    from app.platform.shell import deleteRecoverably
    from app.services.coroutine_runner import CoroutineRunner
    from app.ui.file_watcher import FileWatcher
    from app.ui.loop import UiLoop

    uiLoop = UiLoop()
    coroutineRunner = CoroutineRunner(uiLoop.post, loop=new_event_loop())
    coroutineRunner.start()
    engine = Engine(coroutineRunner, FileWatcher(uiLoop.post), loadCrx, APP_DATA_DIR / "browser_extension",
                    deleteRecoverably)
    return startApp(uiLoop, coroutineRunner, engine)


def startApp(uiLoop, coroutineRunner, engine) -> int:
    """对应 Qt 版的 startApp：创建窗口、托盘和各项服务，把服务的通知接到窗口上，运行到退出。"""
    from collections.abc import Callable

    from app.cli import Cli, isSilent
    from app.config.cfg import cfg
    from app.platform.desktop_keepalive import hold, release
    from app.platform.instance import Invocation
    from app.platform.shell import openFile
    from app.services.plan import Plan
    from app.services.port_listener import ListenStatus
    from app.services.update_service import UpdateService, UpdateState
    from app.startup import checkUpdateAtStartup, deleteBackupDir, loadPacks
    from app.ui.components.info_bar import InfoBarIcon
    from app.ui.dialogs.name_conflict import NameConflictPrompt
    from app.ui.i18n import tr
    from app.ui.shell.clipboard_listener import ClipboardListener
    from app.ui.shell.desktop_notification import (
        init, notifyDiskSpaceInsufficient, notifyParseFailed, notifyTaskCompleted,
    )
    from app.ui.shell.tray import SystemTrayIcon
    from app.ui.windows.main_window import ICON_PATH, MainWindow

    taskService, featureService, browserService = engine.taskService, engine.featureService, engine.browserService
    deleteBackupDir()
    updateService = UpdateService(coroutineRunner)
    loadPacks(featureService, coroutineRunner, engine.speedMeter)

    plan = Plan(allCompleted=lambda: taskService.runningCount() == 0, openFile=openFile)
    taskService.tasksAllCompleted.connect(plan.trigger)

    clipboardListener = ClipboardListener(featureService.matchPassive, uiLoop.post)
    cfg.isClipboardListenerEnabled.valueChanged.connect(clipboardListener.setEnabled)
    clipboardListener.setEnabled(cfg.isClipboardListenerEnabled.value)

    isSilentLaunch = isSilent(sys.argv[1:])
    isOobeShown = not cfg.hasCompletedOobe.value and not isSilentLaunch
    if isOobeShown:
        # 首次启动：服务先就绪，主窗口等引导结束后按最终配置创建
        runOobe(uiLoop, coroutineRunner, engine)

    afterQuit: list[Callable[[], object]] = []

    def requestQuit(then: Callable[[], object] | None = None) -> None:
        if then is not None:
            afterQuit.append(then)
        uiLoop.stop()

    window = MainWindow(taskService, featureService, browserService, engine.browserListener, engine.aria2RpcListener,
                        engine.categoryService, engine.speedMeter, coroutineRunner, plan, updateService,
                        clipboardListener, loadCrx, requestQuit, uiLoop)
    nameConflictPrompt = NameConflictPrompt(engine.nameConflictQueue, window.surface)  # noqa: F841
    if isSilentLaunch:
        # 开机自启等静默启动：只留托盘图标
        window.setVisible(False)

    def show() -> MainWindow:
        window.setVisible(True)
        return window

    tray = SystemTrayIcon(taskService, engine.speedMeter, ICON_PATH, uiLoop.post)
    tray.activationRequested.connect(show)
    tray.quitRequested.connect(requestQuit)
    tray.add()

    def onExtensionUpdated(version: str) -> None:
        show().infoBars.add(tr("MainWindow", "浏览器扩展已更新"), f"v{version}", icon=InfoBarIcon.SUCCESS,
                            duration=3.0)

    def onUpdateChanged(info) -> None:
        if info.targetId == "app" and info.state == UpdateState.AVAILABLE:
            show().onUpdateAvailable(info)
        elif info.targetId != "app" and info.state == UpdateState.AVAILABLE:
            updateService.download(info.targetId)
        elif info.targetId != "app" and info.state == UpdateState.READY:
            window.infoBars.add(tr("MainWindow", "功能包更新"),
                                tr("MainWindow", "{0} 将在下次启动时生效").format(info.label),
                                icon=InfoBarIcon.SUCCESS)

    browserService.taskDraftRequested.connect(lambda tasks: show().addTasks(tasks))
    browserService.extensionUpdated.connect(onExtensionUpdated)
    engine.aria2RpcService.taskDraftRequested.connect(lambda tasks: show().addTasks(tasks))
    browserService.pairRequestChanged.connect(lambda request: request and show().onPairRequested(request))
    engine.browserListener.stateChanged.connect(
        lambda state: state.status == ListenStatus.FAILED and show().onBrowserListenFailed(state.error))
    engine.aria2RpcListener.stateChanged.connect(
        lambda state: state.status == ListenStatus.FAILED and show().onAria2ListenFailed(state.error))
    clipboardListener.urlsDetected.connect(lambda urls: show().addUrls(urls))
    uiLoop.exceptionCaught.connect(lambda message: show().onExceptionCaught(message))
    coroutineRunner.submit(init(coroutineRunner.submit))
    taskService.taskCompleted.connect(notifyTaskCompleted)
    taskService.diskSpaceInsufficient.connect(notifyDiskSpaceInsufficient)
    engine.aria2RpcService.parseFailed.connect(notifyParseFailed)
    taskService.taskStarted.connect(lambda _: hold())
    taskService.tasksAllCompleted.connect(release)
    updateService.changed.connect(onUpdateChanged)

    if not isOobeShown:
        engine.start()
    checkUpdateAtStartup(updateService)

    cli = Cli(taskService, featureService.parse, coroutineRunner.submit,
              open=lambda uris: show().addUrls(uris), activate=show)
    tray.invocationRequested.connect(lambda argv, cwd: cli.run(Invocation(argv, cwd)))
    cli.run(Invocation(sys.argv[1:], os.getcwd()))
    try:
        uiLoop.run(window.window)
    finally:
        # 顺序同 Qt 版的 aboutToQuit：先停服务、应用已下载的更新，再停协程
        engine.stop()
        updateService.apply()
        coroutineRunner.stop()
        clipboardListener.setEnabled(False)
        tray.remove()
        window.close()
    for action in afterQuit:
        action()
    return 0


def runOobe(uiLoop, coroutineRunner, engine) -> None:
    from app.ui.windows.oobe_window import OobeWindow

    engine.start()
    oobe = OobeWindow(engine.browserService, engine.browserListener, coroutineRunner, engine.featureService,
                      engine.runtimeStatusService, uiLoop)

    def onPairRequestChanged(request) -> None:
        if request is not None:
            oobe.onPairRequested(request)

    engine.browserService.pairRequestChanged.connect(onPairRequestChanged)
    oobe.finished.connect(uiLoop.stop)
    try:
        uiLoop.run(oobe.window)
    finally:
        engine.browserService.pairRequestChanged.disconnect(onPairRequestChanged)
        oobe.close()


if __name__ == "__main__":
    sys.exit(main())
