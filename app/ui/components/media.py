from __future__ import annotations

import asyncio
from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass, field

from bkit import ui
from loguru import logger

from app.i18n import tr
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.range_slider import RangeSlider
from app.ui.layout import row, text
from app.ui.loop import SingleShotTimer
from app.ui.theme import isDark

MAX_ENCODED_BYTES = 2 * 1024 * 1024
MAX_THUMBNAIL_BYTES = 1024 * 1024


def parseTime(value: str) -> int:
    parts = value.strip().split(":")
    if not value.strip():
        return 0
    result = 0
    for part in parts:
        result = result * 60 + int(part)
    if result < 0:
        raise ValueError(tr("RangeSlider", "时间不能为负数"))
    return result


def toTime(value: int) -> str:
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


@dataclass(frozen=True)
class Storyboard:
    sheets: list[str]
    timestamps: list[float]
    columns: int
    rows: int
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StoryboardThumbnail:
    encoded: bytes
    bitmap: bytes


@dataclass(frozen=True)
class ThumbnailKey:
    url: str
    columns: int
    rows: int
    cell: int
    width: int
    height: int


class StoryboardCache:
    def __init__(self):
        self._encoded = OrderedDict()
        self._thumbnails = OrderedDict()

    def encodedByUrl(self, url):
        value = self._encoded.get(url)
        if value is not None:
            self._encoded.move_to_end(url)
        return value

    def thumbnailByKey(self, key):
        value = self._thumbnails.get(key)
        if value is not None:
            self._thumbnails.move_to_end(key)
        return value

    def setEncoded(self, url, encoded):
        if len(encoded) > MAX_ENCODED_BYTES:
            return
        self._encoded[url] = encoded
        self._encoded.move_to_end(url)
        while len(self._encoded) > 2 or sum(map(len, self._encoded.values())) > MAX_ENCODED_BYTES:
            self._encoded.popitem(last=False)

    def setThumbnail(self, key, painter):
        self._thumbnails[key] = painter
        self._thumbnails.move_to_end(key)
        while (len(self._thumbnails) > 16 or
               sum(key.width * key.height * 4 for key in self._thumbnails) > MAX_THUMBNAIL_BYTES):
            self._thumbnails.popitem(last=False)

    def removeSources(self, urls):
        for url in urls:
            self._encoded.pop(url, None)
        sources = set(urls)
        for key in list(self._thumbnails):
            if key.url in sources:
                del self._thumbnails[key]


async def fetchStoryboardThumbnail(url, headers, encoded, columns, rows, cell, width, height):
    from app.platform.thumbnail import toSpriteThumbnail

    if encoded is None:
        from app.client import buildClient
        client = buildClient(headers=headers)
        try:
            response = await client.get(url)
            try:
                response.raise_for_status()
                encoded = bytes(await response.bytes())
            finally:
                response.close()
        finally:
            client.close()
    bitmap = await asyncio.to_thread(toSpriteThumbnail, encoded, columns, rows, cell, width, height)
    return StoryboardThumbnail(encoded, bitmap)


class TimeRangeEditor(ui.Node):
    preferredHeight = 50

    def __init__(self, duration, start, end, save, post):
        super().__init__()
        self.previewImage = ui.Image()
        self.previewImage.set_size(160, 90)
        self.previewImage.content_scale = ui.ContentScale.FILL_BOUNDS
        frame = ui.Box()
        frame.set_padding(2)
        frame.set_size(164, 94)
        frame.set_corner_radius(6)
        frame.set_background(0xFF323232 if isDark() else 0xFFF9F9F9)
        frame.set_border(1, 0x1EFFFFFF if isDark() else 0x19000000)
        frame.append_child(self.previewImage)
        self.previewBox = ui.TooltipBox(ui.Spacer(1, 1), frame, is_persistent=True)
        self.previewBox.set_spacing(6)
        self.previewBox.set_user_input_enabled(False)
        self.slider = RangeSlider(0, duration, start, end or duration, save, self._onHover, self.previewBox, post)
        self.append_child(self.slider)
        self._data = None
        self._cache = None
        self._runner = None
        self._workId = self._imageWorkId = ""
        self._previewTimer = SingleShotTimer(post, 0.08, self._fetchFrame)
        self._showTimer = SingleShotTimer(post, 0.016, self._showPreview)
        self._version = 0
        self._hoverTime = None
        self._requestedKey = self._failedKey = self._shownKey = None

    def on_place(self):
        super().on_place()
        if (self._hoverTime is not None and self._shownKey is not None and
                not self.previewBox.visible and not self._showTimer.isActive):
            self._showTimer.start()

    def loadStoryboard(self, runner, fetch, cache):
        self._runner = runner
        self._cache = cache
        self._workId = runner.submit(fetch(), done=self._onStoryboardFetched,
                                     failed=self._onStoryboardFailed, version=self._version)

    def _onStoryboardFetched(self, data, version):
        if version != self._version:
            return
        self._workId = ""
        if data and data.sheets:
            self._data = data
            self._refreshPreview()

    def _onStoryboardFailed(self, error, version):
        if version == self._version:
            self._workId = ""

    def _onHover(self, seconds):
        self._hoverTime = seconds
        if seconds is None:
            self._failedKey = None
            self._requestedKey = None
            self._shownKey = None
            if self._previewTimer:
                self._previewTimer.stop()
                self._showTimer.stop()
            self.previewBox.dismiss()
            self.previewImage.painter = None
        else:
            self._refreshPreview()

    def _refreshPreview(self):
        if not self._data or self._hoverTime is None:
            return
        data = self._data
        count = data.columns * data.rows
        frame = min(len(data.sheets) * count - 1, max(0, bisect_right(data.timestamps, self._hoverTime) - 1))
        sheet, cell = divmod(frame, count)
        key = ThumbnailKey(data.sheets[sheet], data.columns, data.rows, cell,
            min(640, max(1, round(self.dp(160)))), min(360, max(1, round(self.dp(90)))))
        self._requestedKey = key
        painter = self._cache.thumbnailByKey(key)
        if painter is not None:
            self._previewTimer.stop()
            self._showFrame(key, painter)
        elif key != self._failedKey and not self._imageWorkId and not self._previewTimer.isActive:
            self._previewTimer.start()

    def _showFrame(self, key, painter):
        if self._hoverTime is None or not self.is_attached:
            return
        if key != self._shownKey:
            self.previewImage.painter = painter
            self._shownKey = key
        self._showPreview()

    def _showPreview(self):
        if (self._hoverTime is not None and self._shownKey is not None and
                self.previewBox.is_placed and not self.previewBox.visible):
            self.previewBox.show(ui.MutatePriority.USER_INPUT)

    def _fetchFrame(self):
        key = self._requestedKey
        if self._imageWorkId or key is None or not self._data or key == self._failedKey:
            return
        painter = self._cache.thumbnailByKey(key)
        if painter is not None:
            self._showFrame(key, painter)
            return
        self._imageWorkId = self._runner.submit(fetchStoryboardThumbnail(
            key.url, self._data.headers, self._cache.encodedByUrl(key.url),
            key.columns, key.rows, key.cell, key.width, key.height),
            done=self._onFrameFetched, failed=self._onFrameFailed, key=key, version=self._version)

    def _onFrameFetched(self, result, key, version):
        if version != self._version:
            return
        self._imageWorkId = ""
        self._cache.setEncoded(key.url, result.encoded)
        try:
            painter = ui.Painter.decode(result.bitmap)
        except ValueError as error:
            logger.warning("Storyboard thumbnail could not be decoded: {}", error)
            self._onFrameFailed(error, key, version)
            return
        self._cache.setThumbnail(key, painter)
        if self._requestedKey is not None:
            # Keep a preview visible while the latest cursor position loads.
            current = self._cache.thumbnailByKey(self._requestedKey)
            self._showFrame(self._requestedKey if current is not None else key,
                            current if current is not None else painter)
            self._refreshPreview()

    def _onFrameFailed(self, error, key, version):
        if version != self._version:
            return
        self._imageWorkId = ""
        self._failedKey = key
        self._refreshPreview()

    def dispose(self):
        self._version += 1
        self.slider.dispose()
        if self._previewTimer:
            self._previewTimer.stop()
            self._showTimer.stop()
        for workId in (self._workId, self._imageWorkId):
            if workId:
                self._runner.cancel(workId)
        self._workId = self._imageWorkId = ""
        self.previewBox.dismiss()
        self.previewImage.painter = None
        if self._data:
            self._cache.removeSources(self._data.sheets)
        self._data = self._requestedKey = self._shownKey = self._hoverTime = None
        self._cache = None
        self._runner = self._previewTimer = self._showTimer = None

    def apply(self):
        self.slider.flush()
        return True


class MultiChoiceDialog(MessageBoxBase):
    def __init__(self, title, choices, selected, host):
        super().__init__(host)
        self.dialog.set_title(title)
        self._choices = choices
        self._selected = set(selected)
        self.list = ui.LazyColumn()
        self.list.set_item_provider(len(choices), self._createRow)
        body = ui.Box()
        body.set_size(None, min(360, 48 * len(choices)))
        body.append_child(self.list)
        self.viewLayout.append_child(body)

    def _createRow(self, index):
        value, label = self._choices[index]
        box = ui.Checkbox(value in self._selected)
        box.on_checked_change = lambda checked: self._setSelected(value, box, checked)
        return row(box, text(label), spacing=8)

    def _setSelected(self, value, box, checked):
        box.checked = checked
        if checked:
            self._selected.add(value)
        else:
            self._selected.discard(value)

    def selected(self):
        return [value for value, _ in self._choices if value in self._selected]

    def close(self, isAccepted):
        super().close(isAccepted)
        self.list.notify_data_set_changed(0)
