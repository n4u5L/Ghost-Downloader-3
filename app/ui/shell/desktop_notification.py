"""系统通知，对应 app/platform/desktop_notification.py；图标取自 app/assets，不经 Qt 资源和图标提供器。

通知在协程线程里发送，按钮回调也在那里运行，只做与线程无关的打开文件操作。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from app.config.paths import EXECUTABLE_DIR
from app.format import toReadableSize
from app.platform.shell import openFile, revealInFolder
from app.i18n import toLocalizedError, tr

if TYPE_CHECKING:
    from desktop_notifier import DesktopNotifier

    from app.models.task import Task, TaskError

# 源码运行时 EXECUTABLE_DIR 是相对路径 "."，而 WinRT 后端要把图标写成 file URI，必须用绝对路径
ICON_PATH = (EXECUTABLE_DIR / "app" / "assets" / "logo.png").resolve()

notifier: DesktopNotifier | None = None
submit: Callable | None = None


def T(text: str) -> str:
    return tr("Notifications", text)


async def init(submitWork: Callable) -> None:
    global notifier, submit
    from desktop_notifier import DesktopNotifier, Icon
    submit = submitWork
    notifier = DesktopNotifier(app_name="Ghost Downloader", app_icon=Icon(path=ICON_PATH))


def send(**kwargs) -> None:
    if notifier is None or submit is None:
        return
    try:
        submit(notifier.send(**kwargs))
    except Exception as e:
        logger.opt(exception=e).warning("发送系统通知失败")


def notifyDiskSpaceInsufficient(free: int, needed: int) -> None:
    send(title=T("磁盘空间不足"),
         message=T("剩余 {0}，需要 {1}，任务未自动开始").format(toReadableSize(free), toReadableSize(needed)))


def notifyParseFailed(url: str, error: TaskError) -> None:
    displayUrl = url if len(url) <= 48 else f"{url[:45]}..."
    send(title=T("链接解析失败"), message=f"{displayUrl}\n{toLocalizedError(error)}")


def notifyTaskCompleted(task: Task) -> None:
    outputPath = task.outputPath
    if not outputPath:
        return
    from desktop_notifier import Button
    send(
        title=T("下载完成"),
        message=task.name,
        buttons=[
            Button(title=T("打开文件"), on_pressed=lambda: openFile(outputPath)),
            Button(title=T("打开文件夹"), on_pressed=lambda: revealInFolder(outputPath)),
        ],
        on_clicked=lambda: openFile(outputPath),
    )
