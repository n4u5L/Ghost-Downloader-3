"""旧 Qt 入口的通用界面；功能包专用界面由 bkit 宿主加载。"""
from app.config.store import ConfigItem, OptionsConfigItem, RangeConfigItem
from app.services.feature_service import FeatureService


class QtFeatureService(FeatureService):
    def taskCard(self, task, parent=None):
        from app.view.cards.task_cards import TaskCard, MultiFileTaskCard
        card = MultiFileTaskCard if len(task.files or []) > 1 else TaskCard
        return card(task, self._taskService, self, self._categoryService, parent)

    def draftCard(self, task, parent=None):
        from app.view.cards.draft_cards import DraftCard, MultiFileDraftCard
        card = MultiFileDraftCard if len(task.files or []) > 1 else DraftCard
        return card(task, self._categoryService, self._coroutineRunner, self._taskService.probeConflict, parent)

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard, SubworkerCountCard
        return [OutputFolderCard(parent, initial=task.outputFolder), SubworkerCountCard(parent)]

    def createEditDialog(self, task, parent=None):
        from app.view.dialogs.edit_task import LiveEditDialog
        return LiveEditDialog(task, self.optionCards(task, parent), self._coroutineRunner, self, self._taskService, parent)

    def detailCards(self, task, parent=None):
        return []

    def pages(self):
        return []

    def createPage(self, pageClass, parent=None):
        return pageClass(parent)

    def settingGroups(self, parent=None):
        from qfluentwidgets import ComboBoxSettingCard, FluentIcon, RangeSettingCard, SwitchSettingCard
        from app.view.components.setting_card_group import CollapsibleSettingCardGroup
        from app.view.components.setting_cards import LineEditSettingCard, RuntimeCard
        groups = []
        for pack in self.packs:
            group = CollapsibleSettingCardGroup(pack.packId, pack.packId, parent)
            for item in vars(type(pack.config)).values() if pack.config else []:
                if not isinstance(item, ConfigItem):
                    continue
                if isinstance(item.value, bool):
                    card = SwitchSettingCard(FluentIcon.INFO, item.name, "", item, group)
                elif isinstance(item, OptionsConfigItem):
                    card = ComboBoxSettingCard(item, FluentIcon.INFO, item.name, "",
                                               texts=[str(value) for value in item.options], parent=group)
                elif isinstance(item, RangeConfigItem):
                    card = RangeSettingCard(item, FluentIcon.INFO, item.name, "", group)
                elif isinstance(item.value, str):
                    card = LineEditSettingCard(FluentIcon.INFO, item.name, "", item, group)
                else:
                    continue
                group.addSettingCard(card)
            for runtime in pack.runtimes():
                card = RuntimeCard(self._runtimeStatusService, runtime, group)
                group.addSettingCard(card)
                card.refreshStatus()
            groups.append(group)
        return groups
