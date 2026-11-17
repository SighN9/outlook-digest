import unittest
from pathlib import Path

from outlook_digest.config import Config, Translate
from outlook_digest.translate import (
    GlossaryTranslator,
    NullTranslator,
    build_translator,
)

GLOSSARY = {
    "meeting": "会议",
    "invite": "邀请",
    "access request": "访问申请",
}


class GlossaryTranslatorTests(unittest.TestCase):
    def test_whole_word_only(self):
        translator = GlossaryTranslator(GLOSSARY)
        self.assertEqual(translator.translate("Meeting on meetings"), "会议 on meetings")

    def test_longest_phrase_first(self):
        translator = GlossaryTranslator(GLOSSARY)
        self.assertEqual(translator.translate("New access request"), "New 访问申请")

    def test_chinese_and_unknown_kept(self):
        translator = GlossaryTranslator(GLOSSARY)
        self.assertEqual(translator.translate("会议 invite 张三"), "会议 邀请 张三")

    def test_empty_glossary_is_passthrough(self):
        translator = GlossaryTranslator({})
        self.assertEqual(translator.translate("Meeting"), "Meeting")

    def test_empty_text(self):
        self.assertEqual(GlossaryTranslator(GLOSSARY).translate(""), "")


class BuildTranslatorTests(unittest.TestCase):
    def test_off(self):
        cfg = Config(root=Path("."), translate=Translate(engine="off"))
        self.assertIsInstance(build_translator(cfg), NullTranslator)

    def test_glossary(self):
        cfg = Config(
            root=Path("."), translate=Translate(engine="glossary"), glossary=GLOSSARY
        )
        translator = build_translator(cfg)
        self.assertIsInstance(translator, GlossaryTranslator)
        self.assertEqual(translator.translate("Meeting"), "会议")

    def test_unknown_engine(self):
        cfg = Config(root=Path("."), translate=Translate(engine="bogus"))
        with self.assertRaises(ValueError):
            build_translator(cfg)


class ArgosTranslatorTests(unittest.TestCase):
    def test_offline_translation(self):
        from outlook_digest.translate import ArgosTranslator

        try:
            translator = ArgosTranslator(GLOSSARY)
        except Exception as exc:
            self.skipTest(f"argos 未就绪: {exc}")
        result = translator.translate("Meeting invitation")
        self.assertIn("会议", result)
        self.assertNotIn("Meeting", result)


if __name__ == "__main__":
    unittest.main()
