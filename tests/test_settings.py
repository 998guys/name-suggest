import json
import tempfile
import unittest
from pathlib import Path

from app_settings import SettingsStore


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "settings.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_when_missing(self):
        settings = SettingsStore(self.path)
        self.assertEqual(settings.get("pause_seconds"), 1.4)
        self.assertIsNone(settings.get("microphone_index"))

    def test_settings_persist(self):
        settings = SettingsStore(self.path)
        settings.set("pause_seconds", 2.2)
        settings.set("microphone_index", 4)
        restored = SettingsStore(self.path)
        self.assertEqual(restored.get("pause_seconds"), 2.2)
        self.assertEqual(restored.get("microphone_index"), 4)

    def test_corrupt_file_falls_back_safely(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(SettingsStore(self.path).get("pause_seconds"), 1.4)

    def test_invalid_values_are_ignored(self):
        self.path.write_text(json.dumps({"pause_seconds": 100, "microphone_index": -2}), encoding="utf-8")
        settings = SettingsStore(self.path)
        self.assertEqual(settings.get("pause_seconds"), 1.4)
        self.assertIsNone(settings.get("microphone_index"))

    def test_pause_is_clamped_and_unknown_keys_rejected(self):
        settings = SettingsStore(self.path)
        settings.set("pause_seconds", 99)
        self.assertEqual(settings.get("pause_seconds"), 4.0)
        with self.assertRaises(KeyError):
            settings.set("unknown", True)

    def test_ai_is_private_and_disabled_by_default(self):
        settings = SettingsStore(self.path)
        self.assertFalse(settings.get("ai_enabled"))
        self.assertEqual(settings.get("ai_model"), "qwen2.5:1.5b-instruct")

    def test_ai_settings_persist(self):
        settings = SettingsStore(self.path)
        settings.set("ai_enabled", True)
        settings.set("ai_model", "llama3.2:3b")
        restored = SettingsStore(self.path)
        self.assertTrue(restored.get("ai_enabled"))
        self.assertEqual(restored.get("ai_model"), "llama3.2:3b")

    def test_invalid_ai_model_is_rejected(self):
        settings = SettingsStore(self.path)
        with self.assertRaises(ValueError):
            settings.set("ai_model", "bad model; rm something")


if __name__ == "__main__":
    unittest.main()
