import unittest
from datetime import datetime
from pathlib import Path

from outlook_digest.cli import _skip_reason
from outlook_digest.config import Config, Filters
from outlook_digest.models import Mail


def make_mail(subject: str, title_norm: str = "") -> Mail:
    return Mail(
        folder="Inbox",
        class_id=43,
        entry_id="E1",
        internet_message_id="",
        sender_name="",
        sender_email="",
        to_list="",
        cc_list="",
        subject=subject,
        received_at=datetime(2026, 11, 17, 9, 30, 15),
        unread=True,
        attachments=[],
        body_html="",
        body_text="",
        body_blocked=True,
        title_norm=title_norm,
    )


class SkipReasonTests(unittest.TestCase):
    def test_exclude_keyword_matches_normalized_title(self):
        cfg = Config(
            root=Path("."), filters=Filters(skip_subject_keywords=("简报",))
        )
        mail = make_mail("Weekly newsletter", "每周简报")
        self.assertIn("简报", _skip_reason(mail, cfg))

    def test_include_keyword_matches_normalized_title(self):
        cfg = Config(
            root=Path("."), filters=Filters(include_keywords=("审批", "approval"))
        )
        mail = make_mail("Invoice approval needed", "发票 审批 需要")
        self.assertIsNone(_skip_reason(mail, cfg))

    def test_include_keyword_miss_skips(self):
        cfg = Config(root=Path("."), filters=Filters(include_keywords=("审批",)))
        self.assertEqual(
            _skip_reason(make_mail("Lunch menu"), cfg), "未命中包含关键词"
        )

    def test_exclude_wins_over_include(self):
        cfg = Config(
            root=Path("."),
            filters=Filters(
                skip_subject_keywords=("简报",), include_keywords=("审批", "简报")
            ),
        )
        mail = make_mail("Weekly newsletter", "每周简报")
        self.assertIn("简报", _skip_reason(mail, cfg))

    def test_no_rules_no_skip(self):
        self.assertIsNone(_skip_reason(make_mail("Hello"), Config(root=Path("."))))


if __name__ == "__main__":
    unittest.main()
