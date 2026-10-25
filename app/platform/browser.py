"""用本机的 Chromium 系浏览器打开链接，不依赖 Qt。"""
from __future__ import annotations

import sys
from pathlib import Path


def openChromiumUrl(url: str) -> bool:
    import shutil
    import subprocess

    def toBrowserUrl(scheme):
        if url.startswith("chrome://"):
            return f"{scheme}://{url[9:]}"
        return url

    match sys.platform:
        case "darwin":
            for app, scheme in [
                ("Google Chrome", "chrome"),
                ("Microsoft Edge", "edge"),
                ("Brave Browser", "brave"),
                ("Chromium", "chrome"),
            ]:
                if subprocess.run(
                    ["open", "-a", app, toBrowserUrl(scheme)], capture_output=True
                ).returncode == 0:
                    return True
        case "win32":
            import winreg
            for exe, scheme in [
                ("chrome.exe", "chrome"),
                ("msedge.exe", "edge"),
                ("brave.exe", "brave"),
                ("chromium.exe", "chrome"),
            ]:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}",
                    ) as key:
                        path = winreg.QueryValue(key, None)
                        if path and Path(path).is_file():
                            subprocess.Popen([path, toBrowserUrl(scheme)])
                            return True
                except OSError:
                    continue
        case _:
            for cmd, scheme in [
                ("google-chrome", "chrome"),
                ("google-chrome-stable", "chrome"),
                ("microsoft-edge-stable", "edge"),
                ("microsoft-edge", "edge"),
                ("brave-browser", "brave"),
                ("chromium-browser", "chrome"),
                ("chromium", "chrome"),
            ]:
                if shutil.which(cmd):
                    try:
                        subprocess.Popen([cmd, toBrowserUrl(scheme)])
                        return True
                    except OSError:
                        continue
    return False
