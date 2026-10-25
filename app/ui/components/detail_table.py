from bkit import ui

from app.i18n import tr
from app.ui.layout import column, row, text


class DetailTable(ui.Node):
    def __init__(self, headers):
        super().__init__()
        self._rows = []
        self.headers = headers
        self.list = ui.LazyColumn()
        self.list.set_item_provider(0, self._createRow)
        self.box = ui.Box()
        self.box.append_child(self.list)
        self.append_child(column(row(*(text(header, fontWeight=600) for header in headers), spacing=12), self.box))

    def setRows(self, rows):
        rows = [tuple(map(str, values)) for values in rows]
        if rows == self._rows:
            return
        self._rows = rows
        self.box.set_size(None, min(10, len(rows)) * 36)
        self.list.notify_data_set_changed(len(rows))

    def _createRow(self, index):
        box = ui.Box()
        box.set_size(None, 36)
        box.append_child(row(*(text(value) for value in self._rows[index]), spacing=12))
        return box
