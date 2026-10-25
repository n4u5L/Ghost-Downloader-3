from __future__ import annotations

import json
from copy import deepcopy
from enum import Enum
from pathlib import Path

from loguru import logger

from app.signal import Signal


class Theme(Enum):
    LIGHT = "Light"
    DARK = "Dark"
    AUTO = "Auto"


class ConfigValidator:
    def validate(self, value) -> bool:
        return True

    def correct(self, value):
        return value


class OptionsValidator(ConfigValidator):
    def __init__(self, options):
        self.options = list(options)
        if not self.options:
            raise ValueError("Config options cannot be empty")

    def validate(self, value) -> bool:
        return value in self.options

    def correct(self, value):
        return value if self.validate(value) else self.options[0]


class BoolValidator(OptionsValidator):
    def __init__(self):
        super().__init__([True, False])

    def validate(self, value) -> bool:
        return isinstance(value, bool)


class RangeValidator(ConfigValidator):
    def __init__(self, minimum, maximum):
        self.min, self.max = minimum, maximum
        self.range = (minimum, maximum)

    def validate(self, value) -> bool:
        return isinstance(value, (int, float)) and self.min <= value <= self.max

    def correct(self, value):
        if not isinstance(value, (int, float)):
            raise ValueError("Config value must be a number")
        return min(max(self.min, value), self.max)


class FolderValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, str) and Path(value).is_dir()

    def correct(self, value) -> str:
        path = Path(value)
        path.mkdir(parents=True, exist_ok=True)
        return path.absolute().as_posix()


class FolderListValidator(ConfigValidator):
    def validate(self, value) -> bool:
        return isinstance(value, list) and all(FolderValidator().validate(folder) for folder in value)

    def correct(self, value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [Path(folder).absolute().as_posix() for folder in value
                if FolderValidator().validate(folder)]


class ConfigSerializer:
    def serialize(self, value):
        return value

    def deserialize(self, value):
        return value


class EnumSerializer(ConfigSerializer):
    def __init__(self, enumClass):
        self.enumClass = enumClass

    def serialize(self, value):
        return value.value

    def deserialize(self, value):
        return self.enumClass(value)


class ConfigItem:
    valueChanged = Signal(object)

    def __init__(self, group, name, default, validator=None, serializer=None, restart=False):
        self.group, self.name = group, name
        self.validator = validator or ConfigValidator()
        self.serializer = serializer or ConfigSerializer()
        self.restart = restart
        self.defaultValue = self.validator.correct(deepcopy(default))
        self._value = deepcopy(self.defaultValue)

    @property
    def key(self) -> str:
        return f"{self.group}.{self.name}" if self.name else self.group

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        value = self.validator.correct(value)
        if self._value != value:
            self._value = value
            self.valueChanged.emit(value)

    def serialize(self):
        return self.serializer.serialize(self.value)

    def deserializeFrom(self, value):
        self.value = self.serializer.deserialize(value)


class OptionsConfigItem(ConfigItem):
    @property
    def options(self):
        return self.validator.options


class RangeConfigItem(ConfigItem):
    @property
    def range(self):
        return self.validator.range


class ConfigStore:
    appRestartSig = Signal()
    themeChanged = Signal(object)
    themeColorChanged = Signal(object)

    def __init__(self):
        self.file = Path("config/config.json")
        self._data = {}

    def items(self) -> dict[str, ConfigItem]:
        return {item.key: item for name in dir(self)
                if isinstance(item := getattr(self, name), ConfigItem)}

    def get(self, item):
        return item.value

    def set(self, item, value, save=True, copy=True):
        value = item.validator.correct(deepcopy(value) if copy else value)
        if item.value == value:
            return
        item.value = value
        if save:
            self.save()
        if item.restart:
            self.appRestartSig.emit()
        if item is getattr(self, "themeMode", None):
            self.themeChanged.emit(value)
        elif item is getattr(self, "themeColor", None):
            self.themeColorChanged.emit(value)

    def toDict(self, serialize=True) -> dict:
        # 未加载的功能包和旧界面的设置仍须随文件保存。
        data = deepcopy(self._data)
        for item in self.items().values():
            value = item.serialize() if serialize else item.value
            if not item.name:
                data[item.group] = value
                continue
            if not isinstance(data.get(item.group), dict):
                data[item.group] = {}
            data[item.group][item.name] = value
        return data

    def load(self, file=None):
        if file is not None:
            self.file = Path(file)
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self._data = data if isinstance(data, dict) else {}
        for item in self.items().values():
            group = self._data.get(item.group, {})
            if item.name and (not isinstance(group, dict) or item.name not in group):
                continue
            if not item.name and item.group not in self._data:
                continue
            try:
                item.deserializeFrom(group[item.name] if item.name else group)
            except (ValueError, TypeError, OSError, AttributeError):
                logger.warning("Ignoring invalid config value: {}", item.key)
                item.value = deepcopy(item.defaultValue)

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        pending = self.file.with_suffix(self.file.suffix + ".tmp")
        pending.write_text(json.dumps(self.toDict(), ensure_ascii=False, indent=4), encoding="utf-8")
        pending.replace(self.file)
