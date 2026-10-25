"""请求标头的文本形式：每行 name: value，也接受粘贴的 cURL 命令。"""
from __future__ import annotations

from shlex import split as splitShellTokens
from typing import Final

CURL_HEADER_FLAGS: Final[frozenset[str]] = frozenset({"-H", "--header"})
COMMAND_SEPARATORS: Final[frozenset[str]] = frozenset({";", "&", "&&", "|", "||"})
CURL_VALUE_FLAGS: Final[dict[str, str]] = {
    "-b": "cookie", "--cookie": "cookie",
    "-A": "user-agent", "--user-agent": "user-agent",
    "-e": "referer", "--referer": "referer",
}


def toLogicalLines(text: str) -> list[str]:
    merged = text.replace("\r\n", "\n").replace("\\\n", " ").replace("^\n", " ")
    return [line.strip() for line in merged.splitlines() if line.strip()]


def parseHeaderLine(line: str) -> tuple[str, str] | None:
    name, separator, value = line.partition(":")
    name = name.strip()
    # 名称为空是 HTTP/2 伪头，含空白是请求行——两者都不是标头，原样发出去会破坏请求
    if not separator or not name or any(char.isspace() for char in name):
        return None
    return name, value.strip()


def parseCurl(line: str) -> list[tuple[str, str]]:
    try:
        tokens = splitShellTokens(line.replace("$'", "'"))
    except ValueError:
        return []

    rows: list[tuple[str, str]] = []
    index = 1
    while index < len(tokens) - 1:
        token = tokens[index]
        # Windows 的「复制全部为 cURL」把多条命令用 & 连在同一行，到此为止
        if token in COMMAND_SEPARATORS:
            break
        if token in CURL_HEADER_FLAGS:
            row = parseHeaderLine(tokens[index + 1])
            if row:
                rows.append(row)
        elif token in CURL_VALUE_FLAGS:
            rows.append((CURL_VALUE_FLAGS[token], tokens[index + 1].strip()))
        else:
            index += 1
            continue
        index += 2
    return rows


def parseHeaders(text: str) -> list[tuple[str, str]]:
    # 逐行分派而非整段二选一，否则 cURL 后面手加的裸行会被静默吞掉
    rows: list[tuple[str, str]] = []
    hasCurl = False
    for line in toLogicalLines(text):
        if line[:5].lower() == "curl ":
            # 一份标头属于一个请求。「复制全部为 cURL」是多个请求，
            # 混在一起产出的标头集不对应任何一个真实请求，所以只认第一条。
            if hasCurl:
                continue
            hasCurl = True
            rows.extend(parseCurl(line))
            continue
        row = parseHeaderLine(line)
        if row:
            rows.append(row)
    return rows


def toHeadersText(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"{name}: {value}" if value else name for name, value in rows)


def toHeaderRows(text: str) -> list[tuple[str, str]]:
    # 字面切分、零丢弃——视图切换必须无损，清洗只发生在粘贴时
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, separator, value = line.partition(":")
        rows.append((name.strip(), value.strip()) if separator else (line.strip(), ""))
    return rows
