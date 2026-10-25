"""批量链接模板：[1-100] 数字范围、[a-z] 字母范围、{a,b} 枚举，展开为全部组合。"""
from __future__ import annotations

import re
from itertools import product
from string import ascii_lowercase, ascii_uppercase

RANGE_PATTERN = re.compile(r"\[([^\]]+)\]")
LIST_PATTERN = re.compile(r"\{([^}]+)\}")
TOKEN_PATTERN = re.compile(r"(\[[^\]]+\]|\{[^}]+\})")


def expandTemplate(template: str) -> list[str]:
    tokens = TOKEN_PATTERN.split(template)
    if len(tokens) == 1:
        return [template] if template.strip() else []

    segments: list[list[str]] = []
    for token in tokens:
        m_list = LIST_PATTERN.fullmatch(token)
        if m_list:
            segments.append([v.strip() for v in m_list.group(1).split(",") if v.strip()])
            continue

        m_range = RANGE_PATTERN.fullmatch(token)
        if m_range:
            values = _expandRange(m_range.group(1))
            if values is not None:
                segments.append(values)
                continue

        segments.append([token])

    return ["".join(combo) for combo in product(*segments)]


def _expandRange(spec: str) -> list[str] | None:
    parts = spec.split(":")
    if len(parts) > 2:
        return None

    rangePart = parts[0]
    step = 1
    if len(parts) == 2:
        try:
            step = int(parts[1])
        except ValueError:
            return None
        if step < 1:
            return None

    halves = rangePart.split("-", 1)
    if len(halves) != 2:
        return None

    start, end = halves[0].strip(), halves[1].strip()
    if not start or not end:
        return None

    if start.isdigit() and end.isdigit():
        width = len(start) if start[0] == "0" and len(start) > 1 else 0
        s, e = int(start), int(end)
        if s > e:
            return None
        return [str(i).zfill(width) for i in range(s, e + 1, step)]

    if len(start) == 1 and len(end) == 1 and start.isalpha() and end.isalpha():
        if start.islower() and end.islower():
            alphabet = ascii_lowercase
        elif start.isupper() and end.isupper():
            alphabet = ascii_uppercase
        else:
            return None
        si, ei = alphabet.index(start), alphabet.index(end)
        if si > ei:
            return None
        return list(alphabet[si:ei + 1:step])

    return None
