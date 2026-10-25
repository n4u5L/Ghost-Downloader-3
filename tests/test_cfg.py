import json

from app.config.cfg import CloseMode, Language, Theme, cfg, currentHeaders


def test_load_existing_config_keeps_settings(config, tmp_path):
    file = tmp_path / "UserConfig.json"
    file.write_text(json.dumps({
        "Personalization": {"ThemeMode": "Dark", "Language": "en_US"},
        "Software": {"CloseMode": "Quit", "Geometry": "20,30,1280,800"},
        "Network": {"HeadersPresets": json.dumps([
            {"name": "custom", "headers": {"Referer": "https://example.com"}},
        ])},
    }), encoding="utf-8")

    cfg.load(file)
    cfg.save()

    assert cfg.themeMode.value == Theme.DARK
    assert cfg.language.value == Language.ENGLISH_UNITED_STATES
    assert cfg.closeMode.value == CloseMode.QUIT
    assert cfg.geometry.value == (20, 30, 1280, 800)
    assert currentHeaders() == {"Referer": "https://example.com"}
    saved = json.loads(file.read_text(encoding="utf-8"))
    assert saved["Personalization"]["ThemeMode"] == "Dark"
    assert saved["Software"]["Geometry"] == "20,30,1280,800"
    assert json.loads(saved["Network"]["HeadersPresets"])[0]["name"] == "custom"


def test_save_keeps_unloaded_pack_and_old_ui_settings(config):
    original = json.loads(cfg.file.read_text(encoding="utf-8"))
    original["UnloadedPack"] = {"Token": "keep-me"}
    original["QFluentWidgets"] = {"ThemeColor": "#ff123456"}
    cfg.file.write_text(json.dumps(original), encoding="utf-8")
    cfg.load()

    cfg.set(cfg.maxTaskNum, 5)

    saved = json.loads(cfg.file.read_text(encoding="utf-8"))
    assert saved["UnloadedPack"] == {"Token": "keep-me"}
    assert saved["QFluentWidgets"]["ThemeColor"] == "#ff123456"
    assert saved["GeneralDownload"]["MaxTaskNum"] == 5


def test_load_invalid_setting_keeps_other_settings(config):
    cfg.file.write_text(json.dumps({
        "GeneralDownload": {"MaxTaskNum": "broken", "ProxyServer": "Off"},
        "Personalization": {"Language": "unknown"},
        "Software": {"AutoRun": True},
    }), encoding="utf-8")

    cfg.load()

    assert cfg.maxTaskNum.value == cfg.maxTaskNum.defaultValue
    assert cfg.proxyServer.value == "Off"
    assert cfg.language.value == Language.AUTO
    assert cfg.shouldRunAtLogin.value is True


def test_set_corrected_value_notifies_once(config):
    received = []
    cfg.maxTaskNum.valueChanged.connect(received.append)
    try:
        cfg.set(cfg.maxTaskNum, 100)
        cfg.set(cfg.maxTaskNum, 100)
    finally:
        cfg.maxTaskNum.valueChanged.disconnect(received.append)

    assert received == [10]
    assert json.loads(cfg.file.read_text(encoding="utf-8"))["GeneralDownload"]["MaxTaskNum"] == 10


def test_set_restart_setting_requests_restart_once(config):
    received = []
    def onRestart():
        received.append(True)
    cfg.appRestartSig.connect(onRestart)
    try:
        cfg.set(cfg.language, Language.ENGLISH_UNITED_STATES)
        cfg.set(cfg.language, Language.ENGLISH_UNITED_STATES)
    finally:
        cfg.appRestartSig.disconnect(onRestart)

    assert received == [True]


def test_set_list_keeps_its_own_copy(config):
    packs = ["http"]
    cfg.set(cfg.clipboardIgnoredPacks, packs)

    packs.append("bt")

    assert cfg.clipboardIgnoredPacks.value == ["http"]
