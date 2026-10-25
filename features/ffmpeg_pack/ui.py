from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import ffmpegConfig


class PackUi(BasePackUi):
    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {"installFolder": (tr("FFmpegConfig", "FFmpeg 安装目录"), "")}
        return [buildConfigGroup(ffmpegConfig, tr('FFmpegConfig', 'FFmpeg'), 'ffmpeg_pack',
                                 labels, self.services.uiLoop.post)]
