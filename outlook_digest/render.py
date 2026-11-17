from __future__ import annotations

import json

from .models import Analysis, Mail

MAX_BODY_CHARS = 8000


def _yaml_str(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def render_mail(mail: Mail, analysis: Analysis) -> str:
    attachments = "、".join(mail.attachments) if mail.attachments else "无"
    lines = [
        "---",
        f"received_at: {mail.received_at.isoformat(timespec='seconds')}",
        f"subject: {_yaml_str(mail.subject)}",
        f"from_name: {_yaml_str(mail.sender_name)}",
        f"from_email: {_yaml_str(mail.sender_email)}",
        f"folder: {_yaml_str(mail.folder)}",
        f"category: {_yaml_str(analysis.category)}",
        f"priority: {analysis.priority}",
        f"lang: {_yaml_str(analysis.lang)}",
        f"engine: {_yaml_str(analysis.engine)}",
        f"title_norm: {_yaml_str(mail.title_norm)}",
        f"msg_key: {_yaml_str(mail.msg_key)}",
        "---",
        "",
        f"# [{analysis.category}] {mail.subject or '(无主题)'}",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| 发件人 | {_cell(mail.sender_name)} <{_cell(mail.sender_email)}> |",
        f"| 收件人 | {_cell(mail.to_list) or '—'} |",
        f"| 抄送 | {_cell(mail.cc_list) or '—'} |",
        f"| 时间 | {mail.received_at.strftime('%Y-%m-%d %H:%M')} |",
        f"| 文件夹 | {_cell(mail.folder)} |",
        f"| 优先级 | P{analysis.priority} |",
        f"| 语言 | {analysis.lang} |",
        f"| 附件 | {_cell(attachments)} |",
    ]
    norm = (mail.title_norm or "").strip()
    if norm and norm != (mail.subject or "").strip():
        lines.append(f"| 归一标题 | {_cell(norm)} |")
    lines.extend(
        [
            "",
            "## 摘要",
            "",
            analysis.summary or "（正文为空）",
            "",
            "## 译文",
            "",
            analysis.translation
            if analysis.translation
            else "（未生成：原文为中文，或正文不可读/AI 未启用）",
            "",
            "## 待办",
            "",
        ]
    )
    if analysis.todos:
        lines.extend(f"- [ ] {todo}" for todo in analysis.todos)
    else:
        lines.append("（无显式行动项）")
    lines.extend(["", "## 原文", "", "~~~text"])
    if mail.body_blocked:
        lines.append("（正文不可读：Outlook 编程访问被企业安全策略限制，仅归档了可读的元数据）")
    else:
        body = mail.body_text or ""
        lines.append(body[:MAX_BODY_CHARS])
        if len(body) > MAX_BODY_CHARS:
            lines.append(f"……（已截断，原文共 {len(body)} 字符）")
    lines.extend(["~~~", ""])
    return "\n".join(lines)


def _cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def render_index(title: str, items: list[dict]) -> str:
    lines = [f"# {title}", "", f"共 {len(items)} 封", ""]
    if not items:
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| 时间 | 优先级 | 分类 | 主题 | 发件人 | 摘要 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        subject = _cell(item["subject"]) or "(无主题)"
        norm = _cell(item.get("norm", ""))
        if norm and norm != (item["subject"] or "").strip():
            subject = f"{subject} <sub>{norm}</sub>"
        lines.append(
            "| {time} | P{priority} | {category} | [{subject}]({path}) | {sender} | {summary} |".format(
                time=item["time"],
                priority=item["priority"],
                category=_cell(item["category"]),
                subject=subject.replace("[", "\\["),
                path=item["rel_path"].replace(" ", "%20"),
                sender=_cell(item["sender"]),
                summary=_cell(item["summary"])[:80],
            )
        )
    return "\n".join(lines) + "\n"
