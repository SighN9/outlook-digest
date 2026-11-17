import unittest
from datetime import datetime
from pathlib import Path

from outlook_digest.analyze import FallbackAnalyzer, RuleAnalyzer
from outlook_digest.config import AI, Config, General
from outlook_digest.models import Mail


def make_mail(subject: str, body: str, sender: str = "a@example.com") -> Mail:
    return Mail(
        folder="Inbox",
        class_id=43,
        entry_id="E1",
        internet_message_id="<mid@example.com>",
        sender_name="Sender",
        sender_email=sender,
        to_list="me@example.com",
        cc_list="",
        subject=subject,
        received_at=datetime(2026, 11, 17, 9, 30),
        unread=True,
        attachments=[],
        body_html="",
        body_text=body,
    )


def make_config(**kwargs) -> Config:
    return Config(
        root=Path("."),
        general=kwargs.get("general", General()),
        ai=kwargs.get("ai", AI()),
        categories=kwargs.get(
            "categories",
            {
                "会议": ("会议", "meeting"),
                "审批": ("审批", "approval"),
                "财务": ("发票", "invoice"),
            },
        ),
        urgent_keywords=kwargs.get("urgent_keywords", ("紧急", "urgent", "asap")),
    )


class RuleAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = RuleAnalyzer(make_config())

    def test_category_from_body(self):
        mail = make_mail("合同审批", "请审批附件中的合同，谢谢。\n麻烦今天回复")
        analysis = self.analyzer.analyze(mail)
        self.assertEqual(analysis.category, "审批")
        self.assertEqual(analysis.lang, "zh")

    def test_urgent_in_subject_is_p1(self):
        analysis = self.analyzer.analyze(make_mail("紧急：服务器故障", "请立即处理"))
        self.assertEqual(analysis.priority, 1)

    def test_question_marks_are_p2(self):
        analysis = self.analyzer.analyze(make_mail("请问报销流程?", "想问下流程"))
        self.assertEqual(analysis.priority, 2)

    def test_default_is_p3_and_other_category(self):
        analysis = self.analyzer.analyze(make_mail("Lunch", "See you at noon."))
        self.assertEqual(analysis.priority, 3)
        self.assertEqual(analysis.category, "其他")
        self.assertIsNone(analysis.translation)
        self.assertEqual(analysis.engine, "rule")

    def test_todos_extracted(self):
        analysis = self.analyzer.analyze(make_mail("安排", "请周三前确认会议室"))
        self.assertTrue(analysis.todos)


class FallbackTests(unittest.TestCase):
    def test_degrades_to_rule(self):
        class Boom:
            def analyze(self, mail):
                raise RuntimeError("api down")

        fallback = FallbackAnalyzer(Boom(), RuleAnalyzer(make_config()))
        analysis = fallback.analyze(make_mail("会议邀请", "明天上午十点开会"))
        self.assertEqual(analysis.engine, "rule+fallback")
        self.assertEqual(analysis.category, "会议")


if __name__ == "__main__":
    unittest.main()
