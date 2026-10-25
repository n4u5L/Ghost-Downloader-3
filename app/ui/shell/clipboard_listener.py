"""剪贴板监听，对应 Qt 界面的 ClipboardListener。

bkit 没有剪贴板变化的通知：每隔 INTERVAL 秒比较一次剪贴板序号，变了才读取文字。
"""
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from loguru import logger

from app.platform.shell import clipboardSequenceNumber, clipboardText, setClipboardText
from app.signal import Signal
from app.ui.loop import Timer

INTERVAL = 1.0


class ClipboardListener:
    urlsDetected = Signal(list)

    def __init__(self, matchPassive: Callable[[str], bool],
                 post: Callable[[Callable[[], object], float], Timer]) -> None:
        self._matchPassive = matchPassive
        self._post = post
        self._isEnabled = False
        self._timer: Timer | None = None
        self._sequence = clipboardSequenceNumber()

    def setUrls(self, urls: list[str]) -> None:
        setClipboardText("\n".join(urls))
        # 自己复制的链接不算检测到的
        self._sequence = clipboardSequenceNumber()

    def setEnabled(self, isEnabled: bool) -> None:
        if isEnabled == self._isEnabled:
            return
        self._isEnabled = isEnabled
        if isEnabled:
            # 开启前已在剪贴板里的内容不算
            self._sequence = clipboardSequenceNumber()
            self._timer = self._post(self._onTimeout, INTERVAL)
        elif self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _onTimeout(self) -> None:
        self._timer = self._post(self._onTimeout, INTERVAL)
        sequence = clipboardSequenceNumber()
        if sequence == self._sequence:
            return
        self._sequence = sequence
        urls = self._downloadableUrls()
        if urls:
            self.urlsDetected.emit(urls)

    def _downloadableUrls(self) -> list[str]:
        urls: list[str] = []
        for line in clipboardText().splitlines():
            url = line.strip()
            if not url:
                continue
            try:
                parsed = urlparse(url)
            except ValueError as error:
                logger.warning("跳过无效剪贴板链接 {}: {}", url, error)
                continue
            if not parsed.scheme or parsed.geturl() != url:
                continue
            if self._matchPassive(url):
                urls.append(url)
        return urls
