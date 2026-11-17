from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Mail:
    folder: str
    class_id: int
    entry_id: str
    internet_message_id: str
    sender_name: str
    sender_email: str
    to_list: str
    cc_list: str
    subject: str
    received_at: datetime
    unread: bool
    attachments: list[str]
    body_html: str
    body_text: str
    body_blocked: bool = False
    categories: list[str] = field(default_factory=list)
    conversation_topic: str = ""
    importance: int = 1
    flag_status: int = 0
    title_norm: str = ""

    @property
    def msg_key(self) -> str:
        """去重键：优先用 RFC Message-ID，缺失时退回 发件人+主题+时间 的哈希。"""
        mid = (self.internet_message_id or "").strip()
        if mid:
            return "mid:" + mid
        raw = f"{self.sender_email}|{self.subject}|{self.received_at.isoformat(timespec='seconds')}"
        return "sha1:" + hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()


@dataclass
class Analysis:
    category: str = "其他"
    priority: int = 3
    lang: str = "unknown"
    summary: str = ""
    translation: str | None = None
    todos: list[str] = field(default_factory=list)
    engine: str = "rule"
    title_norm: str = ""
