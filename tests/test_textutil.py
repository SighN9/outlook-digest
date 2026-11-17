import unittest

from outlook_digest.textutil import (
    detect_lang,
    find_action_lines,
    first_sentences,
    html_to_text,
    slugify,
    strip_quoted,
)


class HtmlToTextTests(unittest.TestCase):
    def test_blocks_and_scripts(self):
        html = "<p>Hello <b>world</b></p><script>bad()</script><div>Line2</div>"
        self.assertEqual(html_to_text(html), "Hello world\n\nLine2")

    def test_entities_and_nbsp(self):
        self.assertEqual(html_to_text("A&nbsp;&amp;&nbsp;B"), "A & B")

    def test_empty(self):
        self.assertEqual(html_to_text(""), "")


class StripQuotedTests(unittest.TestCase):
    def test_cuts_reply_history(self):
        text = "\n".join([f"line{i}" for i in range(1, 8)] + ["-----Original Message-----", "quoted"])
        self.assertEqual(strip_quoted(text), "\n".join(f"line{i}" for i in range(1, 8)))

    def test_keeps_short_mail(self):
        text = "please review\nFrom: x@y.com"
        self.assertEqual(strip_quoted(text), text)


class LangTests(unittest.TestCase):
    def test_chinese(self):
        self.assertEqual(detect_lang("请审批这份合同，明天需要反馈"), "zh")

    def test_english(self):
        self.assertEqual(
            detect_lang("Please review the attached document before Friday."), "en"
        )


class SlugTests(unittest.TestCase):
    def test_illegal_chars(self):
        self.assertEqual(slugify('Re: <urgent>/meeting?'), "Re urgent meeting")

    def test_truncation(self):
        self.assertLessEqual(len(slugify("x" * 100, 20)), 20)

    def test_empty(self):
        self.assertEqual(slugify(""), "no-subject")


class SentenceTests(unittest.TestCase):
    def test_first_sentences(self):
        text = "第一句。第二句！第三句？第四句。"
        self.assertEqual(first_sentences(text, 2), "第一句。 第二句！")

    def test_maxlen(self):
        self.assertTrue(first_sentences("a" * 50, 1, 20).endswith("…"))


class ActionTests(unittest.TestCase):
    def test_finds_action_lines(self):
        text = "请于周五前提交报告\n无关的一行\n麻烦确认预算"
        self.assertEqual(find_action_lines(text), ["请于周五前提交报告", "麻烦确认预算"])

    def test_limit(self):
        text = "\n".join(f"请处理第{i}项" for i in range(10))
        self.assertEqual(len(find_action_lines(text, 3)), 3)


if __name__ == "__main__":
    unittest.main()
