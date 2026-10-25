"""System notifications load their native backend on the first notification."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from app.config.paths import EXECUTABLE_DIR
from app.format import toReadableSize
from app.i18n import toLocalizedError, tr
from app.platform.shell import openFile, revealInFolder

if TYPE_CHECKING:
    from app.models.task import Task, TaskError

ICON_PATH = (EXECUTABLE_DIR / "app" / "assets" / "logo.png").resolve()


class DesktopNotifications:
    def __init__(self, submit: Callable):
        self._submit = submit
        self._notifier = None

    async def send(self, title: str, message: str, outputPath=None):
        try:
            from desktop_notifier import Button, DesktopNotifier, Icon
            if self._notifier is None:
                self._notifier = DesktopNotifier(app_name="Ghost Downloader", app_icon=Icon(path=ICON_PATH))
            if outputPath is None:
                await self._notifier.send(title=title, message=message)
            else:
                await self._notifier.send(title=title, message=message, buttons=[
                    Button(title=tr("Notifications", "打开文件"), on_pressed=lambda: openFile(outputPath)),
                    Button(title=tr("Notifications", "打开文件夹"), on_pressed=lambda: revealInFolder(outputPath)),
                ], on_clicked=lambda: openFile(outputPath))
        except Exception as error:
            logger.opt(exception=error).warning("发送系统通知失败")

    def sendDiskSpaceInsufficient(self, free: int, needed: int):
        self._submit(self.send(tr("Notifications", "磁盘空间不足"),
            tr("Notifications", "剩余 {0}，需要 {1}，任务未自动开始").format(
                toReadableSize(free), toReadableSize(needed))))

    def sendParseFailed(self, url: str, error: TaskError):
        displayUrl = url if len(url) <= 48 else f"{url[:45]}..."
        self._submit(self.send(tr("Notifications", "链接解析失败"), f"{displayUrl}\n{toLocalizedError(error)}"))

    def sendTaskCompleted(self, task: Task):
        if task.outputPath:
            self._submit(self.send(tr("Notifications", "下载完成"), task.name, task.outputPath))
