from bkit import ui

from app.i18n import tr
from app.ui.cards.draft_cards import DraftCard
from app.ui.cards.task_cards import toFileIcon
from app.ui.components.media import MultiChoiceDialog, TimeRangeEditor
from app.ui.components.menu import buildMenu, buildMenuAction
from app.ui.icons import loadIcon
from app.ui.layout import column, row
from .cards import buildSelection, fetchStoryboard
from .task import audioTiers, currentAudioTier, currentVideoTier, subtitleChoices, videoTiers


def buildTrackButton(icon, title, checked, onChecked):
    button = ui.IconToggleButton(loadIcon(icon), checked, onChecked)
    box = ui.TooltipBox(button)
    box.set_plain_tooltip(title)
    return box, button


class MenuTrackButton(ui.Node):
    def __init__(self, icon, title, choices, selected, checked, save):
        super().__init__()
        self._choices, self._selected, self._save = choices, selected, save
        self._menu = None
        box, self.button = buildTrackButton(icon, title, checked, lambda _: self._onMenuClicked())
        self.append_child(box)

    def _onMenuClicked(self):
        menu = buildMenu(self.button)
        menu.add_selectable_item(tr("MenuTrackButton", "不下载"), not self.button.checked,
                                  buildMenuAction(menu, lambda: self._onPicked(None)))
        menu.add_divider()
        for value, label in self._choices:
            menu.add_selectable_item(label, self.button.checked and value == self._selected,
                buildMenuAction(menu, lambda value=value: self._onPicked(value)))
        self._menu = menu
        menu.expanded = True

    def _onPicked(self, value):
        previous = self._selected, self.button.checked
        self._selected, self.button.checked = value, value is not None
        if self._save(value) is False:
            self._selected, self.button.checked = previous

    def dispose(self):
        if self._menu:
            self._menu.dismiss_all()
            self._menu = None


class BilibiliDraftCard(DraftCard):
    def __init__(self, task, categoryService, probeConflict, services):
        self._services = services
        self._rangeEditor = None
        self._subtitleDialog = None
        self._isSizeEstimated = False
        if not task.hasAudio and len(task.files or []) <= 1:
            task.isAudioEnabled = False
            task.update()
        super().__init__(task, categoryService, probeConflict)
        self._refreshButtons()

    def _initWidget(self):
        super()._initWidget()
        task = self._task
        video = videoTiers(task) or [("best", tr("BilibiliDraftCard", "最佳画质"))]
        audio = audioTiers(task) or [("best", tr("BilibiliDraftCard", "最佳音质"))]
        self.videoButton = MenuTrackButton("videocam", tr("BilibiliDraftCard", "视频"), video,
            currentVideoTier(task) or video[0][0], task.isVideoEnabled, self._onVideoPicked)
        self.audioButton = MenuTrackButton("music_note", tr("BilibiliDraftCard", "音频"), audio,
            currentAudioTier(task) or audio[0][0], task.isAudioEnabled, self._onAudioPicked)
        self.subtitleBox, self.subtitleButton = buildTrackButton("subtitles", tr("BilibiliDraftCard", "字幕"),
            bool(task.subtitleLanguages), self._onSubtitleClicked)
        self.coverBox, self.coverButton = buildTrackButton("photo", tr("BilibiliDraftCard", "封面"),
            task.isCoverEnabled, self._onCoverChanged)
        self.trimBox, self.trimButton = buildTrackButton("content_cut", tr("BilibiliDraftCard", "截取片段"),
            False, self._onTrimChanged)
        self._selectFilesBox = self.selectFilesSlot.children[0] if self.selectFilesSlot.children else None
        if self._selectFilesBox:
            self._selectFilesBox.set_plain_tooltip(tr("BilibiliDraftCard", "选择合集" if task.isSeason else "选择分P"))
        self.rangeSlot = column()

    def _initLayout(self):
        super()._initLayout()
        tracks = row(self.videoButton, self.audioButton, self.subtitleBox, self.coverBox, spacing=2)
        index = self.hBoxLayout.children.index(self.selectFilesSlot)
        self.hBoxLayout.insert_child(index, tracks)
        self.hBoxLayout.append_child(self.trimBox)
        body = self.remove_child(0)
        self.append_child(column(body, self.rangeSlot))

    def _canDisable(self, name):
        return any(getattr(self._task, key) for key in ("isVideoEnabled", "isAudioEnabled", "isCoverEnabled")
                   if key != name)

    def _onVideoPicked(self, value):
        if value is None and not self._canDisable("isVideoEnabled"):
            return False
        task = self._task
        task.isVideoEnabled = value is not None
        if value and value != "best":
            self._isSizeEstimated = True
            task.setVideoQuality(*map(int, value.split("-")))
        else:
            task.update()
        self._refreshSummary()

    def _onAudioPicked(self, value):
        if value is None and not self._canDisable("isAudioEnabled"):
            return False
        task = self._task
        task.isAudioEnabled = value is not None
        if value and value != "best":
            self._isSizeEstimated = True
            task.setAudioQuality(int(value))
        else:
            task.update()
        self._refreshSummary()

    def _onCoverChanged(self, checked):
        if not checked and not self._canDisable("isCoverEnabled"):
            return
        self._task.isCoverEnabled = checked
        self._task.update()
        self._refreshSummary()

    def _onSubtitleClicked(self, _):
        self._subtitleDialog = MultiChoiceDialog(tr("SubtitleSelectDialog", "选择字幕"),
            subtitleChoices(self._task), self._task.subtitleLanguages, self)
        self._subtitleDialog.accepted.connect(self._onSubtitlesPicked)
        self._subtitleDialog.rejected.connect(self._onSubtitlesClosed)
        self._subtitleDialog.open()

    def _onSubtitlesPicked(self):
        self._task.setSubtitleLanguages(self._subtitleDialog.selected())
        self._refreshSummary()
        self._subtitleDialog = None

    def _onSubtitlesClosed(self):
        self._subtitleDialog = None

    def _onTrimChanged(self, checked):
        self.trimButton.checked = checked
        page = self._task.files[0] if self._task.files else None
        if checked and self._rangeEditor is None and page:
            duration = page._duration if len(self._task.files) == 1 and page._duration > 0 else 100
            self._rangeEditor = TimeRangeEditor(duration, 0, duration, self._setRange, self._services.uiLoop.post)
            box = ui.Box()
            box.set_padding(10, 2, 10, 0)
            box.append_child(self._rangeEditor)
            self.rangeSlot.append_child(box)
            self._rangeEditor.loadStoryboard(self._services.coroutineRunner,
                lambda: fetchStoryboard(self._task), self._services.previewCache)
        elif not checked and self._rangeEditor:
            self._rangeEditor.dispose()
            self.rangeSlot.remove_child(0)
            self._rangeEditor = None
            page.startTime = page.endTime = 0
            self._task.update()
            self._refreshSummary()
        self.preferredHeight = 48 + (self._rangeEditor.preferredHeight + 2 if self._rangeEditor else 0)
        self.heightChanged.emit()

    def _setRange(self, start, end):
        page = self._task.files[0]
        page.startTime, page.endTime = start, end
        self._task.update()
        self._refreshSummary()

    def _onSelectFilesClicked(self):
        self._fileSelectDialog = buildSelection(self._task, self)
        self._fileSelectDialog.accepted.connect(self._refreshSummary)
        self._fileSelectDialog.open()

    def _refreshSummary(self):
        self.nameEdit.state.text = self._task.name
        self.sizeLabel.text = ("~" if self._isSizeEstimated else "") + self._summaryText()
        self.iconLabel.icon = loadIcon(toFileIcon(self._task, self._categoryService))
        self._refreshConflictIcon()
        self._refreshButtons()

    def _refreshButtons(self):
        task = self._task
        hasMedia = task.isVideoEnabled or task.isAudioEnabled
        self.videoButton.button.checked = task.isVideoEnabled
        self.audioButton.button.checked = task.isAudioEnabled
        self.audioButton.button.enabled = task.hasAudio or len(task.files or []) > 1
        self.coverButton.enabled = bool(task.coverUrl)
        self.coverButton.checked = task.isCoverEnabled
        self.subtitleButton.enabled = hasMedia and bool(subtitleChoices(task))
        self.subtitleButton.checked = hasMedia and bool(task.subtitleLanguages)
        if self._selectFilesBox:
            if hasMedia and not self.selectFilesSlot.children:
                self.selectFilesSlot.append_child(self._selectFilesBox)
            elif not hasMedia and self.selectFilesSlot.children:
                self.selectFilesSlot.remove_child(0)

    def applyOptions(self):
        return self._rangeEditor.apply() if self._rangeEditor else True

    def overrides(self):
        return {}

    def dispose(self):
        if self._rangeEditor:
            self._rangeEditor.dispose()
            self._rangeEditor = None
        if self._subtitleDialog and self._subtitleDialog.isOpen:
            self._subtitleDialog.close(False)
        self._subtitleDialog = None
        self.videoButton.dispose()
        self.audioButton.dispose()
        super().dispose()
