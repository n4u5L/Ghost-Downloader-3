from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
import json


class PackUi(BasePackUi):
    canChangeUrl = True
    editKeys = ("headers", "clientProfile", "userAgent", "subworkerCount")
    def taskCard(self, task, copyUrls, openDrawer):
        from .cards import HttpTaskCard
        return HttpTaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer,
                             uiLoop=self.services.uiLoop)

    def options(self, task, isEditing=False):
        from app.ui.components.pack_controls import TextOption, ProfileOption, parseHeaders
        step = task.steps[0] if task.steps else None
        if step is None:
            return []
        return [TextOption(tr("HeadersEditCard", "请求头"), json.dumps(step.headers, ensure_ascii=False, indent=2),
                           lambda value: task.setOptions({"headers": value}), parse=parseHeaders, multiline=True),
                ProfileOption(task)]
