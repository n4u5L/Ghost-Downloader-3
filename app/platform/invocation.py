from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Reply:
    output: str
    exitCode: int


@dataclass(frozen=True)
class Invocation:
    argv: list[str]
    cwd: str
    reply: Callable[[Reply], None] = lambda _: None
