from __future__ import annotations

import asyncio
from pathlib import Path

from bkit import ui

from app.client import buildClient
from app.i18n import tr
from app.models.task import TaskStatus
from app.platform.filesystem import toSafeFilename
from app.ui.cards.task_cards import TaskCard
from app.ui.components.media import MultiChoiceDialog, Storyboard, TimeRangeEditor
from app.ui.components.pack_controls import ChoiceOption, ToggleOption
from app.ui.components.option_cards import OptionCard
from app.ui.dialogs.media_select import MediaSelectDialog
from app.ui.layout import column, row, text
from .choices import buildVideoTiers, buildAudioTiers, buildSubtitleChoices, buildAudioLanguageChoices
from .task import YouTubeFile, parseLanguages, probeFormats, probePlaylist


def buildSelection(task, host):
    def rename(index, name):
        file = next(file for file in task.files if file.index == index)
        file.relativePath = toSafeFilename(name + Path(file.relativePath).suffix)
    return MediaSelectDialog(task, host, rename=rename)


async def fetchStoryboard(fmt):
    columns, rows = fmt.get("columns") or 5, fmt.get("rows") or 5
    sheets, timestamps = [], []
    elapsed = 0.0
    for fragment in fmt.get("fragments") or []:
        url = fragment.get("url") or fragment.get("path")
        if not url:
            continue
        sheets.append(url)
        duration = fragment.get("duration") or 5.0
        timestamps.extend(elapsed + i * duration / (columns * rows) for i in range(columns * rows))
        elapsed += duration
    return Storyboard(sheets, timestamps, columns, rows)


class LanguageOption(OptionCard):
    def __init__(self, title, choices, selected, save):
        super().__init__("language", title)
        self._choices, self._selected, self._save = choices, selected, save
        self.button = ui.Button(title, self._onClicked)
        self.addControl(self.button)
        self._dialog = None

    def _onClicked(self):
        self._dialog = MultiChoiceDialog(self.titleLabel.text, self._choices, self._selected, self)
        self._dialog.accepted.connect(self._onAccepted)
        self._dialog.open()

    def _onAccepted(self):
        self._selected = self._dialog.selected()
        self._save(self._selected)
        self.button.text = ", ".join(self._selected) or self.titleLabel.text

    def apply(self):
        return True

    def dispose(self):
        if self._dialog and self._dialog.isOpen:
            self._dialog.close(False)
        self._dialog = None


class YouTubeOptions(ui.Node):
    preferredHeight = 570

    def __init__(self, task, runner, post, previewCache):
        super().__init__()
        self.task, self.runner = task, runner
        self._post = post
        self._previewCache = previewCache
        self.cards = []
        self.status = text(tr("YtDlpDraftCard", "正在获取视频信息…"))
        self.retryButton = ui.Button(tr("YtDlpDraftCard", "重试"), self._fetchInfo)
        self.content = column(self.status)
        self.append_child(self.content)
        self._selection = None
        self._isFetchingPlaylist = False
        self._workIds = []
        info = getattr(task, "_mediaInfo", {})
        if info.get("formats"):
            self._setInfo(info)
        else:
            self._fetchInfo()

    def _fetchInfo(self):
        self.status.text = tr("YtDlpDraftCard", "正在获取视频信息…")
        self.retryButton.enabled = False
        self._workIds.append(self.runner.submit(asyncio.to_thread(probeFormats, self.task.url),
                                                done=self._setInfo, failed=self._onFailed))

    def dispose(self):
        for workId in self._workIds:
            self.runner.cancel(workId)
        self._workIds.clear()
        for card in self.cards:
            if hasattr(card, "dispose"):
                card.dispose()

    def _onFailed(self, error):
        self.status.text = str(error)
        self.retryButton.enabled = True
        if not self.retryButton.parent:
            self.content.append_child(self.retryButton)

    def _setInfo(self, info):
        task = self.task
        task._mediaInfo = info
        if info.get("title"):
            extension = "mp4" if task.isVideoEnabled else "m4a" if task.isAudioEnabled else "jpg"
            task.setName(toSafeFilename(f"{info['title']}.{extension}"))
        if info.get("thumbnail") and info["thumbnail"] != task.coverUrl:
            task.setCoverUrl(info["thumbnail"])
        def track(name):
            def save(value):
                values = {"isVideoEnabled": task.isVideoEnabled, "isAudioEnabled": task.isAudioEnabled,
                          "isCoverEnabled": task.isCoverEnabled}
                values[name] = value
                task.setTracks(**values)
            return save
        self.cards = [
            ToggleOption(tr("YtDlpDraftCard", "视频"), task.isVideoEnabled, track("isVideoEnabled")),
            ToggleOption(tr("YtDlpDraftCard", "音频"), task.isAudioEnabled, track("isAudioEnabled")),
            ToggleOption(tr("YtDlpDraftCard", "封面"), task.isCoverEnabled, track("isCoverEnabled")),
        ]
        self.cards.extend([
            ChoiceOption(tr("YtDlpDraftCard", "画质"), buildVideoTiers(info, tr("YtDlpDraftCard", "最佳画质")),
                         str(task.maxVideoHeight), lambda value: setattr(task, "maxVideoHeight", int(value))),
            ChoiceOption(tr("YtDlpDraftCard", "音质"), buildAudioTiers(info, tr("YtDlpDraftCard", "最佳音质")),
                         str(task.maxAudioBitrate), lambda value: setattr(task, "maxAudioBitrate", int(value))),
        ])
        languages = buildAudioLanguageChoices(info)
        if languages:
            self.cards.append(LanguageOption(tr("YtDlpDraftCard", "音频语言"), languages,
                list(parseLanguages(task.audioLanguages)), lambda values: task.setAudioLanguages(",".join(values))))
        subtitles, autoLanguages = buildSubtitleChoices(info, tr("YtDlpDraftCard", "自动"))
        if subtitles:
            self.cards.append(LanguageOption(tr("YtDlpDraftCard", "字幕"), subtitles,
                list(parseLanguages(task.subtitleLanguages)), lambda values: task.setSubtitleLanguages(
                    ",".join(values), bool(set(values) & autoLanguages))))
        if not task.isPlaylist:
            if not task.files:
                task.files = [YouTubeFile(index=0, relativePath=task.name, videoId=info.get("id", ""),
                                          duration=int(info.get("duration") or 0))]
            file = task.files[0]
            duration = file.duration or int(info.get("duration") or 0)
            def saveRange(start, end):
                file.startTime, file.endTime = start, 0 if start == 0 and end == duration else end
            editor = TimeRangeEditor(duration, file.startTime, file.endTime, saveRange, self._post)
            self.cards.append(editor)
            formats = [fmt for fmt in info.get("formats") or []
                       if fmt.get("format_note") == "storyboard" and fmt.get("columns") and fmt.get("rows")]
            if formats:
                fmt = max(formats, key=lambda fmt: fmt.get("width") or 0)
                editor.loadStoryboard(self.runner, lambda: fetchStoryboard(fmt), self._previewCache)
        while self.content.children:
            self.content.remove_child(0)
        for card in self.cards:
            self.content.append_child(card)
        if task.isPlaylist:
            self.playlistButton = ui.Button(tr("YtDlpDraftCard", "选择视频"), self._onSelectVideos)
            self.content.append_child(self.playlistButton)
        self.content.append_child(self.status)
        self.status.text = ""

    def _onSelectVideos(self):
        if not self.task.files:
            if self._isFetchingPlaylist:
                return
            self._isFetchingPlaylist = True
            self._workIds.append(self.runner.submit(asyncio.to_thread(probePlaylist, self.task.url),
                                done=self._onPlaylist, failed=self._onPlaylistFailed))
            return
        self._selection = buildSelection(self.task, self)
        self._selection.open()

    def _onPlaylist(self, videos):
        self._isFetchingPlaylist = False
        if not videos:
            self.status.text = tr("YtDlpDraftCard", "未找到播放列表")
            return
        self.task.setVideos(videos)
        self._onSelectVideos()

    def _onPlaylistFailed(self, error):
        self._isFetchingPlaylist = False
        self.status.text = str(error)

    def apply(self):
        if not self.cards:
            return True
        result = all([card.apply() for card in self.cards])
        if result:
            self.task.updateSteps()
        return result


class YtDlpTaskCard(TaskCard):
    def _onSelectFilesClicked(self):
        self._fileSelectDialog = buildSelection(self._task, self)
        self._fileSelectDialog.accepted.connect(lambda: self._taskService.updateSelection(
            self._task, {file.index for file in self._task.files or [] if file.selected}))
        self._fileSelectDialog.open()

    def _refreshInfo(self, task, speed, received):
        super()._refreshInfo(task, speed, received)
        step = next((step for step in task.steps if step.status == TaskStatus.RUNNING), None)
        if step:
            labels = {"YouTubeExtractStep": "提取信息", "YouTubeMergeStep": "合并",
                      "YouTubeSubtitleStep": "下载字幕", "YouTubeResourceStep": "下载音视频"}
            self._setStatus(tr("YtDlpTaskCard", labels.get(type(step).__name__, "下载中")))
