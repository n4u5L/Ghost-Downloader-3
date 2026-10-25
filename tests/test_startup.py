import os
import subprocess
import sys
from pathlib import Path


def test_load_engine_and_all_packs_without_qt(tmp_path):
    root = Path(__file__).parents[1]
    source = '''
import asyncio
import importlib.abc
import sys
from pathlib import Path

class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"PySide6", "PyQt6", "qfluentwidgets", "qframelesswindow", "shiboken6"}:
            raise ImportError("Qt import blocked: " + name)

sys.meta_path.insert(0, BlockQt())
from app.cli import Cli
from app.config.cfg import cfg
from app.config.paths import FEATURES_DIR
from app.engine import Engine
from app.i18n import translator, toLocalizedError
from app.models.pack import PackServices
from app.models.task import TaskError
from app.services.coroutine_runner import CoroutineRunner
from app.signal_bus import signalBus
from app.startup import loadPacks
from tests.conftest import FakeFileWatcher

cfg.load(Path(sys.argv[1]) / "UserConfig.json")
loop = asyncio.new_event_loop()
engine = Engine(CoroutineRunner(lambda callback: callback(), loop=loop), FakeFileWatcher(), bytes,
                Path(sys.argv[1]), lambda path: False)
loadPacks(engine.featureService, engine.coroutineRunner, engine.speedMeter)
expected = {folder.name for folder in FEATURES_DIR.iterdir() if (folder / "manifest.toml").is_file()}
loaded = {pack.manifest.name for pack in engine.featureService.packs}
assert loaded == expected, (loaded, expected)
translator.load("en_US")
assert toLocalizedError(TaskError("端口 {port} 被占用，请更换端口", port=14370))
assert all(name.split(".")[0] not in {"PySide6", "qfluentwidgets", "shiboken6"} for name in sys.modules)
loop.close()
print("Qt-free startup passed")
'''
    result = subprocess.run([sys.executable, "-c", source, str(tmp_path)], cwd=root,
                            env={**os.environ, "GHOST_DOWNLOADER_DATA_DIR": str(tmp_path)},
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Qt-free startup passed" in result.stdout
