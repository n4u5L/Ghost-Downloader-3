from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import huggingFaceConfig


LABELS = {'isEnabled': ('启用 HuggingFace 加速', '命中 HuggingFace 链接时，自动改写为所选镜像站')}


class PackUi(BasePackUi):
    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('HuggingFaceConfig', label), tr('HuggingFaceConfig', description)) for name, (label, description) in LABELS.items()}
        group = buildConfigGroup(huggingFaceConfig, tr('HuggingFaceConfig', 'HuggingFace'), 'huggingface_pack',
                                 labels, self.services.uiLoop.post, exclude=('selectedSite', 'customSite', 'accessToken'))
        from .setting_cards import HuggingFaceProxySiteCard, HuggingFaceTokenCard
        group.addSettingCardFactory(lambda: HuggingFaceProxySiteCard(self.services.coroutineRunner))
        group.addSettingCardFactory(lambda: HuggingFaceTokenCard(self.services.uiLoop.post))
        return [group]
