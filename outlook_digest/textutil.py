from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "tr", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "section", "article", "blockquote", "hr", "pre", "ul", "ol",
}
_SKIP_TAGS = {"script", "style", "head", "title"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def normalize_space(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    blank = False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif out and not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    return normalize_space(text)


_QUOTE_MARKERS = (
    re.compile(r"^-{2,}\s*(original message|原始邮件|转发的邮件|forwarded message)", re.I),
    re.compile(r"^_{8,}\s*$"),
    re.compile(r"^on .+ wrote:$", re.I),
    re.compile(r"^在\s*.+写道[:：]?$"),
    re.compile(r"^(from|发件人)\s*[:：]\s*.+$", re.I),
)


def strip_quoted(text: str) -> str:
    """截掉回复中引用的历史内容，保留前 6 行不判，避免误伤正文。"""
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if idx < 6:
            continue
        stripped = line.strip()
        if any(p.search(stripped) for p in _QUOTE_MARKERS):
            return "\n".join(lines[:idx]).rstrip()
    return text


_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_lang(text: str) -> str:
    sample = (text or "")[:4000]
    cjk = len(_CJK.findall(sample))
    latin = len(_LATIN.findall(sample))
    if cjk and cjk >= latin * 0.25:
        return "zh"
    if latin >= 10:
        return "en"
    return "other" if (cjk or latin) else "unknown"


_ILLEGAL_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(text: str, maxlen: int = 40) -> str:
    text = _ILLEGAL_FILENAME.sub(" ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:maxlen].strip() or "no-subject"


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])|(?<=[.!?;])\s+|\n+")


def first_sentences(text: str, count: int = 3, maxlen: int = 400) -> str:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text or "") if p.strip()]
    out = ""
    for part in parts[:count]:
        candidate = f"{out} {part}".strip()
        if len(candidate) > maxlen:
            return candidate[:maxlen].rstrip() + "…"
        out = candidate
    return out or (text or "")[:maxlen].strip()


_ACTION_WORDS = re.compile(
    r"(请|麻烦|需要|务必|尽快|截止|回复|确认|安排|deadline|due|asap|please|could you|"
    r"action required|need you|approve|review)",
    re.I,
)


def find_action_lines(text: str, limit: int = 5) -> list[str]:
    found: list[str] = []
    for line in (text or "").split("\n"):
        line = line.strip(" \t-•·*>0123456789.、)）")
        if 4 <= len(line) <= 200 and _ACTION_WORDS.search(line):
            found.append(line)
        if len(found) >= limit:
            break
    return found
