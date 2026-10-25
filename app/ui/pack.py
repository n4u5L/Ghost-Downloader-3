from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property, partial
from importlib import import_module
from typing import TYPE_CHECKING

from app.i18n import tr

if TYPE_CHECKING:
    from app.models.pack import FeaturePack
    from app.models.task import Task
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.runtime_status import RuntimeStatusService
    from app.services.task_service import TaskService
    from app.ui.loop import UiLoop


@dataclass(frozen=True)
class PackUiServices:
    taskService: TaskService
    categoryService: CategoryService
    coroutineRunner: CoroutineRunner
    runtimeStatusService: RuntimeStatusService
    uiLoop: UiLoop

    @cached_property
    def previewCache(self):
        from app.ui.components.media import StoryboardCache
        return StoryboardCache()


class PackUi:
    canChangeUrl = False
    editKeys = ("subworkerCount",)
    def __init__(self, pack: FeaturePack, services: PackUiServices):
        self.pack = pack
        self.services = services

    def taskCard(self, task: Task, copyUrls, openDrawer):
        from app.ui.cards.task_cards import TaskCard
        return TaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer)

    def draftCard(self, task: Task, probeConflict):
        from app.ui.cards.options import OptionsDraftCard
        return OptionsDraftCard(task, self.services.categoryService, probeConflict,
                                 self.commonOptions(task) + self.options(task))

    def commonOptions(self, task, *, includeFolder=True):
        from app.ui.components.pack_controls import TaskFolderOption, WorkerOption
        cards = [TaskFolderOption(task, self.services.uiLoop.post)] if includeFolder else []
        if task.steps and hasattr(task.steps[0], "subworkerCount"):
            cards.append(WorkerOption(task))
        return cards

    def options(self, task: Task, isEditing=False):
        return []

    def details(self, task: Task):
        return []

    def settings(self):
        return []


class PackViews:
    def __init__(self, packs, services: PackUiServices):
        self._services = services
        self._packs = {pack.packId: pack for pack in packs}
        self._fallback = PackUi(None, services)
        self._byId: dict[str, PackUi] = {}
        for pack in packs:
            folder = getattr(getattr(pack, "config", None), "installFolder", None)
            if folder:
                for runtime in pack.runtimes():
                    folder.valueChanged.connect(partial(self._onRuntimeFolderChanged, runtime))

    def _onRuntimeFolderChanged(self, runtime, _):
        self._services.runtimeStatusService.cancelInstall(runtime)
        self._services.runtimeStatusService.invalidate(runtime)

    def byTask(self, task: Task) -> PackUi:
        return self.byId(task.packId)

    def byId(self, packId: str) -> PackUi:
        if packId not in self._packs:
            return self._fallback
        if packId not in self._byId:
            pack = self._packs[packId]
            adapter = PackUi
            if pack.manifest and any((pack.manifest.folder / name).is_file() for name in ("ui.py", "ui.pyc")):
                adapter = import_module(f"{pack.manifest.name}.ui").PackUi
            self._byId[packId] = adapter(pack, self._services)
        return self._byId[packId]

    def settings(self):
        return [group for packId in self._packs for group in self.byId(packId).settings()]

    def pages(self):
        return [(tr("PackPage", page.title), page.icon, partial(self._buildPage, pack, page))
                for pack in self._packs.values() if pack.manifest for page in pack.manifest.uiPages]

    def _buildPage(self, pack, page, host):
        module = import_module(f"{pack.manifest.name}.{page.moduleName}")
        return getattr(module, page.className)(pack, self._services, host)
