import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from outlook_digest.archive import rebuild_day_index, rebuild_month_index, write_mail
from outlook_digest.config import Config, General
from outlook_digest.models import Analysis, Mail
from outlook_digest.store import Store


def make_mail(subject: str = "Test mail", body_blocked: bool = False) -> Mail:
    return Mail(
        folder="Inbox",
        class_id=43,
        entry_id="E1",
        internet_message_id="<abc@example.com>",
        sender_name="张三",
        sender_email="zhang@example.com",
        to_list="me@example.com",
        cc_list="",
        subject=subject,
        received_at=datetime(2026, 11, 17, 9, 30, 15),
        unread=True,
        attachments=["a.pdf"],
        body_html="<p>hello</p>",
        body_text="hello\n请回复",
        body_blocked=body_blocked,
    )


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = Config(root=self.root, general=General())

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_mail_by_topic_and_month(self):
        path = write_mail(self.cfg, make_mail(), Analysis(category="审批", priority=2))
        self.assertEqual(
            path,
            self.root / "archive" / "topics" / "审批" / "2026-11" /
            "2026-11-17_093015_Test mail.md",
        )
        content = path.read_text(encoding="utf-8")
        self.assertIn('category: "审批"', content)
        self.assertIn("# [审批] Test mail", content)
        self.assertIn("请回复", content)

    def test_body_blocked_note(self):
        path = write_mail(self.cfg, make_mail(body_blocked=True), Analysis(category="通知"))
        self.assertIn("正文不可读", path.read_text(encoding="utf-8"))

    def test_unknown_topic_falls_back(self):
        path = write_mail(self.cfg, make_mail(), Analysis(category=""))
        self.assertIn("其他", path.parts)

    def test_duplicate_subject_gets_suffix(self):
        mail = make_mail()
        first = write_mail(self.cfg, mail, Analysis())
        second = write_mail(self.cfg, mail, Analysis())
        self.assertNotEqual(first, second)
        self.assertTrue(second.name.endswith("-2.md"))

    def test_day_and_month_index(self):
        store = Store(self.root / "data" / "mail.db")
        try:
            mail = make_mail()
            path = write_mail(self.cfg, mail, Analysis(category="审批", summary="摘要"))
            store.insert(mail, Analysis(category="审批", summary="摘要"), str(path))
            rows = store.rows_for_day("2026-11-17")
            day_index = rebuild_day_index(self.cfg, "2026-11-17", rows)
            text = day_index.read_text(encoding="utf-8")
            self.assertIn("../topics/审批/2026-11/2026-11-17_093015_Test%20mail.md", text)
            self.assertIn("共 1 封", text)

            month_index = rebuild_month_index(self.cfg, "2026-11", store.rows_for_month("2026-11"))
            self.assertEqual(month_index.name, "2026-11.md")
            self.assertIn("2026-11 月度归档", month_index.read_text(encoding="utf-8"))
        finally:
            store.close()


class StoreTests(unittest.TestCase):
    def test_dedup_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "mail.db")
            try:
                mail = make_mail()
                self.assertFalse(store.has(mail.msg_key))
                store.insert(mail, Analysis(), None)
                self.assertTrue(store.has(mail.msg_key))
                self.assertEqual(store.stats()["total"], 1)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
