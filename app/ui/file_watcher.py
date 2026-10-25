from __future__ import annotations

from collections.abc import Callable

from app.platform.filesystem import isExisting
from app.signal import Signal
from app.ui.loop import Timer

INTERVAL = 3.0


class FileWatcher:
    """QFileSystemWatcher 的轮询替代。只报告消失的文件：TaskService 只关心这一种变化。"""

    fileChanged = Signal(str)

    def __init__(self, post: Callable[[Callable[[], object], float], Timer]) -> None:
        self._post = post
        self._paths: set[str] = set()
        self._timer: Timer | None = None

    def addPath(self, path: str) -> bool:
        # 与 QFileSystemWatcher 一致：不存在的路径不监视
        if not isExisting(path):
            return False
        self._paths.add(path)
        if self._timer is None:
            self._timer = self._post(self._refresh, INTERVAL)
        return True

    def removePath(self, path: str) -> bool:
        if path not in self._paths:
            return False
        self._paths.discard(path)
        return True

    def _refresh(self) -> None:
        self._timer = None
        for path in [p for p in self._paths if not isExisting(p)]:
            self._paths.discard(path)
            self.fileChanged.emit(path)
        if self._paths:
            self._timer = self._post(self._refresh, INTERVAL)
