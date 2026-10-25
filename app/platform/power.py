"""计划任务的关机、重启和睡眠，不依赖 Qt。"""
from __future__ import annotations

import sys


def shutdown() -> None:
    from subprocess import Popen
    match sys.platform:
        case "win32":
            Popen(["shutdown", "/s", "/t", "0"])
        case "darwin":
            Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
        case _:
            Popen(["shutdown", "-h", "now"])


def restart() -> None:
    from subprocess import Popen
    match sys.platform:
        case "win32":
            Popen(["shutdown", "/r", "/t", "0"])
        case "darwin":
            Popen(["osascript", "-e", 'tell app "System Events" to restart'])
        case _:
            Popen(["shutdown", "-r", "now"])


def sleep() -> None:
    from subprocess import Popen
    match sys.platform:
        case "win32":
            Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"])
        case "darwin":
            Popen(["pmset", "sleepnow"])
        case _:
            Popen(["systemctl", "suspend"])
