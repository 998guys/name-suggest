import tempfile
import unittest
from pathlib import Path

from voice_typer_core import WordPredictor, format_dictation, is_undo_command


class PredictorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "my_words.txt"
        self.model = WordPredictor(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_and_loads_starter_file(self):
        self.model.load()
        self.assertTrue(self.path.exists())
        self.assertIn("i want to go", self.path.read_text(encoding="utf-8"))

    def test_trigram_is_preferred(self):
        self.model.learn("I need to finish")
        self.model.learn("I need to finish")
        self.model.learn("I need to rest")
        self.model.record_typed("I need")
        self.assertEqual(self.model.predict(1), ["to"])
        self.model.record_typed("to")
        self.assertEqual(self.model.predict(2), ["finish", "rest"])

    def test_remember_persists_unicode(self):
        self.model.load()
        self.model.remember("Please email Chloé about naïve plans")
        contents = self.path.read_text(encoding="utf-8")
        self.assertIn("Chloé", contents)
        self.assertIn("chloé", self.model.recognition_prompt())

    def test_comments_do_not_affect_model(self):
        self.path.write_text("# secret prediction\nopen the report\n", encoding="utf-8")
        self.model.load()
        self.model.record_typed("secret")
        self.assertNotEqual(self.model.predict(1), ["prediction"])

    def test_prediction_is_deterministic(self):
        self.model.learn("one two three")
        self.model.record_typed("one two")
        self.assertEqual(self.model.predict(), self.model.predict())


class FormattingTests(unittest.TestCase):
    def test_spoken_punctuation(self):
        self.assertEqual(format_dictation("hello comma world period"), "hello, world. ")
        self.assertEqual(format_dictation("is this right question mark"), "is this right? ")

    def test_new_paragraph(self):
        self.assertEqual(format_dictation("first line new paragraph second line"), "first line\n\nsecond line ")
        self.assertEqual(format_dictation("new paragraph"), "\n\n")

    def test_whisper_punctuation_spacing(self):
        self.assertEqual(format_dictation("Hello , world !"), "Hello, world! ")

    def test_empty_input(self):
        self.assertEqual(format_dictation("   "), "")

    def test_undo_commands(self):
        self.assertTrue(is_undo_command("Undo that."))
        self.assertTrue(is_undo_command("scratch that"))
        self.assertFalse(is_undo_command("undo the document"))


if __name__ == "__main__":
    unittest.main()
