from bkit import ui

from app.i18n import tr
from app.ui.components.setting_cards import SettingCard


class KelpieStopCard(SettingCard):
    def __init__(self, session, runner):
        super().__init__("stop", tr("ED2kConfig", "终止 Kelpie 进程"))
        self._session, self._runner = session, runner
        self.button = ui.Button(tr("ED2kConfig", "终止"), self._onStopClicked)
        self.setControl(self.button)
        session.networkChanged.connect(self._refresh)
        session.runsChanged.connect(self._refresh)
        self._refresh()

    def _onStopClicked(self):
        self._runner.submit(self._session.stop())

    def _refresh(self, *_):
        session = self._session
        self.button.enabled = session.network is not None and session.isIdle
        self.setContent(tr("ED2kConfig", "未运行") if session.network is None else
            tr("ED2kConfig", "开始 eD2k 任务时会自动重新启动") if session.isIdle else
            tr("ED2kConfig", "有 eD2k 任务正在下载或做种，结束后才能终止"))
