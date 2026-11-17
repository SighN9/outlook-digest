from __future__ import annotations

import logging
import re

from .config import Config
from .textutil import detect_lang

log = logging.getLogger(__name__)


class NullTranslator:
    """关闭统一标题转换。"""

    engine = "off"

    def translate(self, text: str) -> str:
        return text or ""


class GlossaryTranslator:
    """用中英术语表把标题归一化为中文，纯离线，可预测。

    只做整词替换：`meeting` 会命中，`meetings` 里的 `meeting` 不会误伤；
    中文原样保留，因此同一套关键词规则可以同时命中中英文标题。
    """

    engine = "glossary"

    def __init__(self, glossary: dict[str, str]):
        self._map = {
            term.strip().lower(): zh for term, zh in glossary.items() if term.strip()
        }
        if self._map:
            terms = sorted(self._map, key=len, reverse=True)
            self._pattern = re.compile(
                r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % "|".join(map(re.escape, terms)),
                re.I,
            )
        else:
            self._pattern = None

    def translate(self, text: str) -> str:
        if not text or self._pattern is None:
            return text or ""
        result = self._pattern.sub(lambda m: self._map[m.group(0).lower()], text)
        return re.sub(r"\s{2,}", " ", result).strip()


_REPLY_PREFIX = re.compile(r"^\s*(?:re|fw|fwd|回复|转发)\s*[:：]\s*", re.I)
_BRACKET_PAIRS = {"【": "】", "[": "]", "(": ")", "（": "）", "<": ">", "《": "》"}
_DEGENERATE = re.compile(r"(.)\1{7,}")


def _clean_title(text: str) -> str:
    text = _REPLY_PREFIX.sub("", text or "").strip()
    while len(text) >= 2:
        head, tail = text[0], text[-1]
        if head in _BRACKET_PAIRS and tail == _BRACKET_PAIRS[head]:
            text = text[1:-1].strip()
        else:
            break
    return text


def _cjk_count(text: str) -> int:
    return sum(1 for ch in text or "" if "\u4e00" <= ch <= "\u9fff")


def _plausible(original: str, translated: str) -> bool:
    """挡掉离线小模型的典型退化输出：乱码重复、空结果、异常变短。"""
    if not translated or not _cjk_count(translated):
        return False
    if _DEGENERATE.search(translated):
        return False
    if len(translated) > len(original) * 3 + 10:
        return False
    if len(original) >= 12 and len(translated) < len(original) * 0.2:
        return False
    return True


class _WholeTextSentencizer:
    """把整段文本当作一句，跳过 argos 打包的 stanza 分词器。

    语言包里的 stanza 资源缺 mwt 模型，首次翻译会尝试联网下载，
    企业网络下会失败；标题本身很短，不需要分句。
    """

    def split_sentences(self, text: str) -> list[str]:
        return [text]


class ArgosTranslator:
    """本地离线神经翻译（argostranslate + ctranslate2），不联网。

    只翻译非中文文本（目标语言统一为中文）；中文标题原样返回，
    翻译后再套一遍术语表，统一缩写与专有名词的写法。
    """

    engine = "argos"

    def __init__(self, glossary: dict[str, str]):
        from argostranslate import translate as argos  # 延迟导入，未装时不拖慢其它命令

        self._glossary = GlossaryTranslator(glossary)
        languages = {lang.code: lang for lang in argos.get_installed_languages()}
        source = languages.get("en")
        target = languages.get("zh")
        translation = source.get_translation(target) if source and target else None
        if translation is None:
            raise RuntimeError(
                "缺少 en→zh 离线语言包，请先运行："
                ".venv\\Scripts\\python.exe scripts/install_argos_model.py"
            )
        base = getattr(translation, "underlying", translation)
        if hasattr(base, "sentencizer"):
            base.sentencizer = _WholeTextSentencizer()
        self._translation = translation

    def translate(self, text: str) -> str:
        cleaned = _clean_title(text)
        if not cleaned:
            return ""
        if detect_lang(cleaned) == "zh":
            return self._glossary.translate(cleaned)
        try:
            translated = self._translation.translate(cleaned)
        except Exception as exc:
            log.warning("离线翻译失败，回退到术语表: %s", exc)
            return self._glossary.translate(cleaned)
        translated = self._glossary.translate(translated).strip()
        if not _plausible(cleaned, translated):
            log.debug("离线翻译结果不可靠，保留原文: %s -> %s", cleaned, translated)
            return self._glossary.translate(cleaned)
        return translated


def build_translator(cfg: Config):
    engine = (cfg.translate.engine or "off").lower()
    if engine in ("off", "none", ""):
        return NullTranslator()
    if engine == "glossary":
        return GlossaryTranslator(cfg.glossary)
    if engine == "argos":
        return ArgosTranslator(cfg.glossary)
    raise ValueError(
        f"未知的 translate.engine: {cfg.translate.engine}（可选 off / glossary / argos）"
    )
