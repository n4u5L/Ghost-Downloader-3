from __future__ import annotations

import ctypes
import heapq
import itertools
import traceback
from collections import deque
from collections.abc import Callable
from ctypes import wintypes
from time import monotonic

from bkit import ui
from loguru import logger

from app.platform.process_memory import loadPrivateWorkingSet
from app.signal import Signal

WM_NULL = 0x0000
# 无定时器时也定期醒来，让 Ctrl+C 等信号得到处理
MAX_WAIT = 0.5
TITLE_INTERVAL = 0.5

user32 = ctypes.WinDLL("user32")
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL


def toStatsTitle(title: str, stats: ui.FrameStats | None, memory: int | None) -> str:
    if stats is None:
        frame = "no frame yet"
    else:
        frame = (f"frame peak {stats.frame_ms:.1f} ms | layout {stats.layout_ms:.1f} "
                 f"record {stats.record_ms:.1f} move {stats.move_ms:.1f} raster {stats.raster_ms:.1f} "
                 f"upload {stats.upload_ms:.1f} present {stats.present_ms:.1f} | {stats.pixels} px")
    workingSet = "n/a" if memory is None else f"{memory / (1024 * 1024):.1f} MiB"
    return f"{title} | {frame} | private working set {workingSet}"


class Timer:
    __slots__ = ("callback", "dueTime", "isCancelled")

    def __init__(self, callback: Callable[[], object], dueTime: float) -> None:
        self.callback = callback
        self.dueTime = dueTime
        self.isCancelled = False

    def cancel(self) -> None:
        self.isCancelled = True


class SingleShotTimer:
    """对应 QTimer(singleShot=True)：start() 重新计时，interval 秒后调用 callback。"""

    def __init__(self, post: Callable[[Callable[[], object], float], Timer], interval: float,
                 callback: Callable[[], object]) -> None:
        self._post = post
        self._interval = interval
        self._callback = callback
        self._timer: Timer | None = None

    @property
    def isActive(self) -> bool:
        return self._timer is not None

    def start(self) -> None:
        self.stop()
        self._timer = self._post(self._onTimeout, self._interval)

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _onTimeout(self) -> None:
        self._timer = None
        self._callback()


class UiLoop:
    """bkit 窗口的事件循环。post() 可在任意线程调用，回调总在 UI 线程执行。

    回调抛出的异常记入日志并以 exceptionCaught 报告，对应 Qt 界面的 signalBus.exceptionCaught。
    """

    exceptionCaught = Signal(str)

    def __init__(self) -> None:
        self._posted: deque[Timer] = deque()
        self._timers: list[tuple[float, int, Timer]] = []
        self._order = itertools.count()
        self._hwnd = 0
        self._isRunning = False

    def post(self, callback: Callable[[], object], delay: float = 0.0) -> Timer:
        timer = Timer(callback, monotonic() + delay)
        self._posted.append(timer)
        self._wake()
        return timer

    def run(self, window: ui.Window) -> None:
        self._hwnd = window.handle
        self._isRunning = True
        title = window.title
        nextTitleUpdate = monotonic() + TITLE_INTERVAL
        shownStats: ui.FrameStats | None = None
        try:
            while self._isRunning:
                self._runDue()
                try:
                    if not window.process_events(self._waitTime()):
                        break
                    now = monotonic()
                    if now >= nextTitleUpdate:
                        nextTitleUpdate = now + TITLE_INTERVAL
                        shownStats = window.take_frame_stats() or shownStats
                        # 原生标题更新不会触发 bkit 内容重绘，空闲时保留上一帧统计。
                        window.title = toStatsTitle(title, shownStats, loadPrivateWorkingSet())
                except Exception as e:
                    self._onCallbackFailed(e, "bkit callback failed")
        finally:
            self._hwnd = 0
            self._isRunning = False

    def stop(self) -> None:
        self._isRunning = False
        self._wake()

    def _wake(self) -> None:
        # process_events() 等待时不持有 GIL，一条线程消息即可结束等待
        hwnd = self._hwnd
        if hwnd:
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)

    def _runDue(self) -> None:
        while self._posted:
            timer = self._posted.popleft()
            heapq.heappush(self._timers, (timer.dueTime, next(self._order), timer))
        now = monotonic()
        while self._timers and self._timers[0][0] <= now:
            _, _, timer = heapq.heappop(self._timers)
            if timer.isCancelled:
                continue
            try:
                timer.callback()
            except Exception as e:
                self._onCallbackFailed(e, "ui callback failed")

    def _onCallbackFailed(self, error: Exception, message: str) -> None:
        logger.opt(exception=error).error(message)
        try:
            self.exceptionCaught.emit("".join(traceback.format_exception(error)).rstrip())
        except Exception as e:
            # 报告本身失败时不再报告，免得反复弹出
            logger.opt(exception=e).error("exceptionCaught handler failed")

    def _waitTime(self) -> float:
        if self._posted:
            return 0.0
        if not self._timers:
            return MAX_WAIT
        return min(MAX_WAIT, max(0.0, self._timers[0][0] - monotonic()))
