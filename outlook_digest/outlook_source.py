from __future__ import annotations

import logging
from datetime import datetime

from .models import Mail
from .textutil import html_to_text, normalize_space

log = logging.getLogger(__name__)

MAIL_CLASSES = {43: "mail", 53: "meeting-request", 54: "meeting-cancelled"}
DEFAULT_FOLDERS = {
    "inbox": 6,
    "收件箱": 6,
    "sent": 5,
    "sent items": 5,
    "已发送": 5,
    "已发送邮件": 5,
    "drafts": 16,
    "草稿": 16,
    "deleted": 3,
    "deleted items": 3,
    "已删除": 3,
    "垃圾邮件": 23,
    "junk": 23,
}

PR_INTERNET_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"
PR_SENDER_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001F"


class OutlookSource:
    """通过本机桌面版 Outlook 的 COM 接口读取邮件，要求 Outlook 已登录并运行。"""

    def __init__(self, include: tuple[str, ...] = ("Inbox",), max_scan: int = 2000):
        self._include = include
        self._max_scan = max_scan
        self._app = None
        self._ns = None
        # 企业策略常只放开主题/时间，正文与地址信息会抛 E_FAIL；探测一次后不再重试
        self._body_ok: bool | None = None
        self._address_ok: bool | None = None
        self._attachment_ok: bool | None = None

    @property
    def body_blocked(self) -> bool:
        return self._body_ok is False

    def __enter__(self) -> "OutlookSource":
        import win32com.client  # 延迟导入，便于无 COM 环境跑单元测试

        self._app = win32com.client.Dispatch("Outlook.Application")
        self._ns = self._app.GetNamespace("MAPI")
        log.info(
            "Outlook 已连接 version=%s 收件箱=%d",
            getattr(self._app, "Version", "?"),
            self._default_folder(6).Items.Count,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._ns = None
        self._app = None

    def _default_folder(self, folder_id: int):
        return self._ns.GetDefaultFolder(folder_id)

    def _resolve(self, path: str):
        parts = [p for p in str(path).replace("\\", "/").split("/") if p.strip()]
        if not parts:
            return None
        head = parts[0].strip().lower()
        if head in DEFAULT_FOLDERS:
            folder = self._default_folder(DEFAULT_FOLDERS[head])
        else:
            folder = self._find_child(self._ns.Folders, parts[0])
        if folder is None:
            return None
        for part in parts[1:]:
            folder = self._find_child(folder.Folders, part)
            if folder is None:
                return None
        return folder

    @staticmethod
    def _find_child(collection, name: str):
        target = name.strip().lower()
        for i in range(1, collection.Count + 1):
            try:
                folder = collection.Item(i)
                if (folder.Name or "").strip().lower() == target:
                    return folder
            except Exception:
                continue
        return None

    def iter_mails(self, since: datetime, limit: int):
        if limit <= 0:
            return
        remaining = limit
        for path in self._include:
            folder = self._resolve(path)
            if folder is None:
                log.warning("找不到文件夹: %s（已跳过）", path)
                continue
            for mail in self._iter_folder(folder, path, since):
                yield mail
                remaining -= 1
                if remaining <= 0:
                    return

    def _iter_folder(self, folder, path: str, since: datetime):
        items = folder.Items
        sorted_desc = True
        try:
            items.Sort("[ReceivedTime]", True)
        except Exception:
            sorted_desc = False
            log.warning("文件夹 %s 排序失败，将全量扫描至上限", path)

        scanned = 0
        msg = items.GetFirst()
        while msg is not None and scanned < self._max_scan:
            scanned += 1
            received = self._received_at(msg)
            if received is not None and received < since:
                if sorted_desc:
                    break
                msg = items.GetNext()
                continue
            mail = self._to_mail(msg, path, received)
            if mail is not None:
                yield mail
            msg = items.GetNext()
        log.info("文件夹 %s 扫描 %d 封", path, scanned)

    @staticmethod
    def _received_at(msg) -> datetime | None:
        try:
            rt = msg.ReceivedTime
            return datetime(rt.year, rt.month, rt.day, rt.hour, rt.minute, rt.second)
        except Exception:
            return None

    def _to_mail(self, msg, path: str, received: datetime | None) -> Mail | None:
        try:
            class_id = int(getattr(msg, "Class", 0) or 0)
        except Exception:
            return None
        if class_id not in MAIL_CLASSES:
            return None
        if received is None:
            received = datetime.now()

        body_html, body_text, body_blocked = self._read_body(msg)
        sender_name, sender_email, to_list, cc_list = self._address_fields(msg)

        attachments = self._attachment_names(msg)

        return Mail(
            folder=path,
            class_id=class_id,
            entry_id=self._safe_str(msg, "EntryID"),
            internet_message_id=self._prop(msg, PR_INTERNET_MESSAGE_ID),
            sender_name=sender_name,
            sender_email=sender_email,
            to_list=to_list,
            cc_list=cc_list,
            subject=self._safe_str(msg, "Subject"),
            received_at=received,
            unread=bool(getattr(msg, "UnRead", False)),
            attachments=attachments,
            body_html=body_html,
            body_text=body_text,
            body_blocked=body_blocked,
            categories=self._user_categories(msg),
            conversation_topic=self._safe_str(msg, "ConversationTopic"),
            importance=self._safe_int(msg, "Importance", 1),
            flag_status=self._safe_int(msg, "FlagStatus", 0),
        )

    @staticmethod
    def _user_categories(msg) -> list[str]:
        raw = OutlookSource._safe_str(msg, "Categories")
        return [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]

    @staticmethod
    def _safe_int(obj, attr: str, default: int) -> int:
        try:
            return int(getattr(obj, attr))
        except Exception:
            return default

    def _read_body(self, msg) -> tuple[str, str, bool]:
        if self._body_ok is False:
            return "", "", True
        html = ""
        try:
            html = msg.HTMLBody or ""
            self._body_ok = True
        except Exception:
            try:
                plain = msg.Body or ""
                self._body_ok = True
                return "", normalize_space(plain), False
            except Exception:
                if self._body_ok is None:
                    log.warning(
                        "邮件正文不可读（企业安全策略限制），本次仅归档主题、时间等元数据"
                    )
                self._body_ok = False
                return "", "", True
        return html, html_to_text(html), False

    def _address_fields(self, msg) -> tuple[str, str, str, str]:
        if self._address_ok is None:
            try:
                _ = msg.SenderName
                self._address_ok = True
            except Exception:
                self._address_ok = False
                log.warning("发件人/收件人不可读（企业安全策略限制），归档中将留空")
        if not self._address_ok:
            return "", "", "", ""
        return (
            self._safe_str(msg, "SenderName"),
            self._sender_email(msg),
            self._safe_str(msg, "To"),
            self._safe_str(msg, "CC"),
        )

    def _attachment_names(self, msg) -> list[str]:
        if self._attachment_ok is False:
            return []
        names: list[str] = []
        try:
            atts = msg.Attachments
            count = min(atts.Count, 20)
            self._attachment_ok = True
            for i in range(1, count + 1):
                try:
                    names.append(str(atts.Item(i).FileName))
                except Exception:
                    continue
        except Exception:
            self._attachment_ok = False
        return names

    @staticmethod
    def _safe_str(obj, attr: str) -> str:
        try:
            return (getattr(obj, attr) or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _prop(msg, prop: str) -> str:
        try:
            value = msg.PropertyAccessor.GetProperty(prop)
            return str(value).strip() if value else ""
        except Exception:
            return ""

    def _sender_email(self, msg) -> str:
        for prop in (PR_SENDER_SMTP, PR_SMTP_ADDRESS):
            value = self._prop(msg, prop)
            if "@" in value:
                return value
        raw = self._safe_str(msg, "SenderEmailAddress")
        if "@" in raw:
            return raw
        # Exchange 环境里是 /O=.../CN=... 形式的 X500 地址，换取 SMTP 地址
        try:
            recipient = self._ns.CreateRecipient(raw)
            recipient.Resolve()
            if recipient.Resolved:
                entry = recipient.AddressEntry
                try:
                    exchange_user = entry.GetExchangeUser()
                    if exchange_user:
                        return exchange_user.PrimarySmtpAddress or raw
                except Exception:
                    pass
                return entry.Address or raw
        except Exception:
            pass
        return raw
