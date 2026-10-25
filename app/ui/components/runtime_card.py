from __future__ import annotations

from typing import TYPE_CHECKING

from bkit import ui

from app.i18n import toLocalizedError, tr
from app.platform.shell import revealInFolder
from app.ui.components.setting_cards import SettingCard
from app.ui.components.message_box import MessageBox
from app.ui.icons import CATEGORY_ICONS, buildIconButton
from app.ui.layout import row
from app.update import isNewer

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime
    from app.services.runtime_status import RuntimeStatus, RuntimeStatusService


def T(text: str) -> str:
    return tr("RuntimeCard", text)


class RuntimeCard(SettingCard):
    def __init__(self, runtimeStatusService: RuntimeStatusService, runtime: BinaryRuntime) -> None:
        self._service = runtimeStatusService
        self._runtime = runtime
        super().__init__(CATEGORY_ICONS.get(runtime.icon, "build"), runtime.name)
        self.installButton = ui.Button(T("一键安装"), self._onInstallClicked)
        refreshBox, self.refreshButton = buildIconButton("sync", T("刷新"), self.refreshStatus)
        folderBox, _ = buildIconButton("folder_open", T("安装目录"), self._onOpenFolderClicked)
        deleteBox, self.deleteButton = buildIconButton("delete", T("卸载"), self._onDeleteClicked)
        self._dialog = None
        self.controls = row(refreshBox, folderBox, deleteBox, spacing=8)
        if runtime.canInstall:
            self.controls.insert_child(0, self.installButton)
        self.setControl(self.controls)
        self._service.statusChanged.connect(self._onStatusChanged)
        self._onStatusChanged(self._service.status(runtime))
        self.refreshStatus()

    def refreshStatus(self) -> None:
        if not self._service.status(self._runtime).isInstalling:
            self._service.invalidate(self._runtime)

    def _onStatusChanged(self, status: RuntimeStatus) -> None:
        if status.runtimeId != self._runtime.runtimeId:
            return
        self.refreshButton.enabled = not status.isBusy and not status.isInstalling
        self.installButton.enabled = not status.isBusy
        self.deleteButton.enabled = (self._runtime.isAppManaged() and not status.isBusy and not status.isInstalling)
        if status.isInstalling:
            self.installButton.text = T("取消安装")
            self.setContent(T("正在安装...") if status.progress >= 100 else
                            T("正在下载... {0}%").format(status.progress) if status.progress else T("正在准备..."))
            return
        isUpdateAvailable = (status.path and status.latestVersion
                             and (not status.version or isNewer(status.version, status.latestVersion)))
        self.installButton.text = T("更新") if isUpdateAvailable else T("一键安装")
        if status.isBusy:
            self.setContent(T("正在检测运行时..."))
        elif status.error:
            self.setContent(toLocalizedError(status.error))
        elif status.path:
            version = T("版本: {0}").format(status.version) if status.version else ""
            self.setContent(f"{version}\n{T('路径: {0}').format(status.path)}".strip())
        else:
            self.setContent(T("未检测到可用的 {0}").format(self._runtime.name))

    def _onInstallClicked(self) -> None:
        if self._service.status(self._runtime).isInstalling:
            self._service.cancelInstall(self._runtime)
        else:
            self._service.install(self._runtime)

    def _onOpenFolderClicked(self) -> None:
        revealInFolder(self._runtime.installFolder())

    def _onDeleteClicked(self):
        self._dialog = MessageBox(T("确认卸载"), T("确定要卸载 {0} 吗？").format(self._runtime.name), self)
        self._dialog.accepted.connect(self._deleteRuntime)
        self._dialog.open()

    def _deleteRuntime(self):
        self.deleteButton.enabled = False
        self._service.delete(self._runtime)
