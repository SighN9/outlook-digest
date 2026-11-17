from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

from .config import Config
from .models import Analysis, Mail
from .textutil import strip_quoted

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是邮件助理。阅读一封邮件，输出严格的 JSON 对象，不要输出任何 JSON 以外的文字。

字段要求：
- lang: 邮件正文主语言，取值 zh / en / other
- category: 从给定分类列表中选一个最贴切的；都不合适则用 "其他"
- priority: 整数 1-3，1=需立即处理，2=今日/本周需跟进，3=仅供参考
- summary: 2-3 句中文摘要，说明谁在问什么、需要做什么。若原文是英文也用中文写摘要
- translation: 若原文不是中文，给出正文的中文译文（保留段落，可略去签名与免责声明）；若原文是中文则返回 null
- todos: 字符串数组，列出需要收件人采取的行动，没有则返回 []

以 JSON 输出示例：
{"lang":"en","category":"审批","priority":2,"summary":"...","translation":"...","todos":["..."]}"""


class AIError(RuntimeError):
    pass


class OpenAICompatAnalyzer:
    """任意兼容 /v1/chat/completions 的服务：DeepSeek、OpenAI、通义、自建网关等。"""

    engine = "openai"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        api_key = os.environ.get(cfg.ai.api_key_env, "").strip()
        if not api_key:
            raise AIError(
                f"环境变量 {cfg.ai.api_key_env} 未设置，无法启用 AI（可先用 ai.provider = \"mock\"）"
            )
        self._api_key = api_key
        self._endpoint = cfg.ai.base_url.rstrip("/") + "/chat/completions"
        self._categories = list(cfg.categories.keys()) + ["其他"]

    def analyze(self, mail: Mail) -> Analysis:
        body = strip_quoted(mail.body_text)[: self.cfg.ai.max_chars]
        payload = {
            "model": self.cfg.ai.model,
            "temperature": self.cfg.ai.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "categories": self._categories,
                            "subject": mail.subject,
                            "from": f"{mail.sender_name} <{mail.sender_email}>",
                            "received_at": mail.received_at.isoformat(timespec="minutes"),
                            "body": body,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.cfg.ai.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise AIError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AIError(f"网络错误: {exc.reason}") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError(f"响应结构异常: {str(data)[:300]}") from exc
        return self._parse(content)

    def _parse(self, content: str) -> Analysis:
        text = content.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError(f"模型未返回合法 JSON: {text[:300]}") from exc

        category = str(obj.get("category") or "其他").strip()
        if category not in self._categories:
            category = "其他"
        try:
            priority = int(obj.get("priority") or 3)
        except (TypeError, ValueError):
            priority = 3
        priority = min(3, max(1, priority))

        translation = obj.get("translation")
        translation = str(translation).strip() if translation else None
        todos = obj.get("todos") or []
        if not isinstance(todos, list):
            todos = [str(todos)]

        return Analysis(
            category=category,
            priority=priority,
            lang=str(obj.get("lang") or "unknown"),
            summary=str(obj.get("summary") or "").strip()[:1000],
            translation=translation,
            todos=[str(t).strip() for t in todos if str(t).strip()][:10],
            engine=self.engine,
        )
