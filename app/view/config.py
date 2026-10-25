"""仅在旧界面启动时，把共享配置连接到 QFluentWidgets 的主题状态。"""
from qfluentwidgets import Theme, qconfig
from qfluentwidgets.common.config import ColorSerializer, ColorValidator
from PySide6.QtGui import QColor

from app.config.cfg import cfg
from app.config.store import ConfigItem, EnumSerializer, OptionsValidator


def loadConfig(file) -> None:
    cfg.themeMode.validator = OptionsValidator(Theme)
    cfg.themeMode.serializer = EnumSerializer(Theme)
    cfg.themeMode.defaultValue = Theme.AUTO
    cfg.themeMode.value = Theme.AUTO
    cfg.fontFamilies = ConfigItem("QFluentWidgets", "FontFamilies",
                                  ["Segoe UI", "Microsoft YaHei", "PingFang SC"])
    cfg.themeColor = ConfigItem("QFluentWidgets", "ThemeColor", QColor("#009faa"),
                                ColorValidator("#009faa"), ColorSerializer())
    cfg.load(file)
    # QFluentWidgets 的控件通过这个实例读写配置；业务层始终使用共享 cfg。
    qconfig._cfg = cfg
    qconfig.theme = cfg.themeMode.value
    cfg.themeChanged.connect(qconfig.themeChanged.emit)
    cfg.themeColorChanged.connect(qconfig.themeColorChanged.emit)
