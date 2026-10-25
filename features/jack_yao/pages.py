from base64 import b64decode

from bkit import ui

from app.i18n import toLocalizedError, tr
from app.models.task import ResourceTaskOptions, toTaskError
from app.platform.shell import openUrl
from app.ui.components.message_box import MessageBoxBase
from app.ui.components.option_cards import OutputFolderCard, SubworkerCountCard
from app.ui.layout import column, row, text
from .catalog import fetchCatalog


class CatalogDownloadDialog(MessageBoxBase):
    def __init__(self, items, services, host, parse):
        super().__init__(host)
        self._items, self._services = items, services
        self._parseTask = parse
        self.dialog.set_title(tr("CatalogDownloadDialog", "选择版本"))
        self.version = ui.ExposedDropdownMenuBox(outlined=True)
        for item in items:
            self.version.add_option(item["Version"])
        self.version.selected_index = 0
        self.version.on_selected = self._onSelected
        self.version.on_expanded_change = lambda value: setattr(self.version, "expanded", value)
        self.log = ui.Text(items[0].get("Log", "") if items else "")
        self.folder = OutputFolderCard(services.uiLoop.post)
        self.workers = SubworkerCountCard()
        self.error = ui.Text("")
        for node in (self.version, self.log, self.folder, self.workers, self.error):
            self.viewLayout.append_child(node)

    def _onSelected(self, index):
        self.version.selected_index = index
        self.log.text = self._items[index].get("Log", "")

    def _onYesClicked(self):
        if not self._items:
            return
        self.yesButton.enabled = False
        options = {**self.folder.options(), **self.workers.options()}
        item = self._items[self.version.selected_index]
        self._services.coroutineRunner.submit(self._parse(item["Url"], options),
                                               done=self._onParsed, failed=self._onFailed)

    async def _parse(self, url, options):
        task = await self._parseTask(ResourceTaskOptions(url=url, outputFolder=options["outputFolder"]))
        task.setOptions(options)
        return task

    def _onParsed(self, task):
        self._services.taskService.add(task)
        self.close(True)

    def _onFailed(self, error):
        self.yesButton.enabled = True
        self.error.text = toLocalizedError(toTaskError(error))


class CatalogPage(ui.Node):
    @property
    def searchPlaceholder(self):
        return tr("CatalogPage", "搜索资源")

    def __init__(self, pack, services, host):
        super().__init__()
        self.pack, self.services, self.host = pack, services, host
        self._items, self._visible = [], []
        self._query = ""
        self._dialog = None
        self.message = ui.Text(tr("LoadingWidget", "正在加载..."))
        self.reload = ui.Button(tr("LoadingWidget", "重试"), self._fetch)
        self.list = ui.LazyColumn()
        self.list.set_item_provider(0, self._createRow)
        self.append_child(column(row(text(tr("PackPage", "资源下载"), fontSize=24), self.reload),
                                 self.message, self.list, spacing=16, flex=2))
        self._fetch()

    def _fetch(self):
        self.reload.enabled = False
        self.message.text = tr("LoadingWidget", "正在加载...")
        self.services.coroutineRunner.submit(fetchCatalog(), done=self._onFetched, failed=self._onFailed)

    def _onFetched(self, items):
        self.reload.enabled = True
        self.message.text = ""
        self._items = items
        self.setSearchText(self._query)

    def _onFailed(self, error):
        self.reload.enabled = True
        self.message.text = toLocalizedError(toTaskError(error))

    def setSearchText(self, value):
        self._query = value
        self._visible = [item for item in self._items
                         if value.lower() in (item.get("Name", "") + item.get("Intro", "")).lower()]
        self.list.notify_data_set_changed(len(self._visible))

    def _createRow(self, index):
        item = self._visible[index]
        image = ui.Image()
        image.set_size(64, 64)
        try:
            image.painter = ui.Painter.decode(b64decode(item.get("Icon", "")))
        except ValueError:
            pass
        card = ui.Card(ui.CardStyle.FILLED)
        card.set_padding(16)
        card.append_child(row(image,
            column(text(item["Name"], fontSize=20, fontWeight=600), ui.Text(item.get("Intro", "").replace(r"\n", "\n"))),
            ui.Button(tr("CatalogCard", "下载"), lambda: self._openDownload(item["List"])),
            ui.Button(tr("CatalogCard", "观看视频"), lambda: openUrl(item["Video"])), spacing=12, flex=1))
        return card

    def _openDownload(self, items):
        self._dialog = CatalogDownloadDialog(items, self.services, self.host, self.pack.parse)
        self._dialog.open()
