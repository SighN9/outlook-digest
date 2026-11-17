from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Config
from .models import Analysis, Mail
from .render import render_index, render_mail
from .textutil import slugify


def topic_of(analysis: Analysis) -> str:
    category = (analysis.category or "").strip()
    if not category or category == "no-subject":
        return "其他"
    return slugify(category, 30)


def write_mail(cfg: Config, mail: Mail, analysis: Analysis) -> Path:
    """归档路径：archive/topics/<主题分类>/<年-月>/<时间>_<主题>.md"""
    topic_dir = (
        cfg.archive_root
        / "topics"
        / topic_of(analysis)
        / f"{mail.received_at:%Y-%m}"
    )
    topic_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{mail.received_at:%Y-%m-%d_%H%M%S}_{slugify(mail.subject, 40)}"
    path = topic_dir / f"{stem}.md"
    counter = 2
    while path.exists():
        path = topic_dir / f"{stem}-{counter}.md"
        counter += 1
    path.write_text(render_mail(mail, analysis), encoding="utf-8")
    return path


def rebuild_day_index(cfg: Config, day: str, rows) -> Path:
    return _write_index(cfg, f"{day}.md", f"{day} 邮件归档", rows)


def rebuild_month_index(cfg: Config, month: str, rows) -> Path:
    return _write_index(cfg, f"{month}.md", f"{month} 月度归档", rows)


def _write_index(cfg: Config, filename: str, title: str, rows) -> Path:
    index_dir = cfg.archive_root / "timeline"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / filename

    items = []
    for row in rows:
        md_path = row["md_path"] or ""
        rel = ""
        if md_path:
            try:
                rel = Path(os.path.relpath(Path(md_path), index_dir)).as_posix()
            except ValueError:
                rel = md_path
        todos = _loads(row["todos"])
        items.append(
            {
                "time": (row["received_at"] or "")[11:16],
                "priority": row["priority"] or 3,
                "category": row["category"] or "其他",
                "subject": row["subject"] or "(无主题)",
                "norm": row["title_norm"] or "",
                "sender": row["sender_name"] or row["sender_email"] or "",
                "summary": (row["summary"] or "；".join(todos)) or "",
                "rel_path": rel or "#",
            }
        )
    index_path.write_text(render_index(title, items), encoding="utf-8")
    return index_path


def _loads(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []
