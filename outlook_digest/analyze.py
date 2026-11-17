from __future__ import annotations

import logging

from .config import Config
from .models import Analysis, Mail
from .textutil import detect_lang, find_action_lines, first_sentences, strip_quoted

log = logging.getLogger(__name__)


class RuleAnalyzer:
    """本地规则分析：不联网，用于 provider=mock 或 AI 调用失败时兜底。"""

    engine = "rule"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def analyze(self, mail: Mail) -> Analysis:
        body = strip_quoted(mail.body_text)
        subject = mail.subject or ""
        normalized = mail.title_norm or subject
        # 原文与统一标题一起参与匹配，中英文关键词共用一套规则
        haystack = f"{subject}\n{normalized}\n{mail.conversation_topic}\n{body[:3000]}".lower()

        category = "其他"
        user_categories = [c for c in mail.categories if c.strip()]
        if user_categories:
            category = user_categories[0]
        else:
            for name, keywords in self.cfg.categories.items():
                if any(kw.lower() in haystack for kw in keywords):
                    category = name
                    break

        priority = 3
        subject_lower = f"{subject} {normalized}".lower()
        if any(kw.lower() in subject_lower for kw in self.cfg.urgent_keywords):
            priority = 1
        elif any(kw.lower() in haystack for kw in self.cfg.urgent_keywords):
            priority = 2
        elif "?" in subject or "？" in subject:
            priority = 2
        if mail.importance >= 2 or mail.flag_status == 2:
            priority = min(priority, 2)

        summary = first_sentences(body, 3, 400) if body else subject

        return Analysis(
            category=category,
            priority=priority,
            lang=detect_lang(f"{subject} {body}"),
            summary=summary,
            translation=None,
            todos=find_action_lines(body),
            engine=self.engine,
            title_norm=normalized,
        )


class FallbackAnalyzer:
    """优先走 AI，失败时降级到规则分析，保证每次运行都有产出。"""

    def __init__(self, primary, fallback: RuleAnalyzer):
        self._primary = primary
        self._fallback = fallback

    def analyze(self, mail: Mail) -> Analysis:
        try:
            analysis = self._primary.analyze(mail)
            if not analysis.title_norm:
                analysis.title_norm = mail.title_norm or mail.subject
            return analysis
        except Exception as exc:
            log.warning("AI 分析失败，降级为规则分析: %s", exc)
            analysis = self._fallback.analyze(mail)
            analysis.engine = f"{self._fallback.engine}+fallback"
            return analysis


def build_analyzer(cfg: Config):
    rule = RuleAnalyzer(cfg)
    provider = (cfg.ai.provider or "mock").lower()
    if provider == "mock":
        return rule
    if provider == "openai":
        from .ai import OpenAICompatAnalyzer

        return FallbackAnalyzer(OpenAICompatAnalyzer(cfg), rule)
    raise ValueError(f"未知的 ai.provider: {cfg.ai.provider}（可选 mock / openai）")
