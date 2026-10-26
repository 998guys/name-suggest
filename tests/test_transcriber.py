import tempfile
import unittest
from pathlib import Path

from voice_typer_core import WhisperTranscriber, WordPredictor


class TranscriberCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.predictor = WordPredictor(self.root / "words.txt")
        self.transcriber = WhisperTranscriber("base.en", self.root / "models", self.predictor)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_cache_requests_normal_download(self):
        self.assertIsNone(self.transcriber._cached_model_path())

    def test_minimal_faster_whisper_cache_is_used_locally(self):
        snapshot = self.root / "models" / "models--Systran--faster-whisper-base.en" / "snapshots" / "abc123"
        snapshot.mkdir(parents=True)
        for filename in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
            (snapshot / filename).write_bytes(b"test")
        self.assertEqual(self.transcriber._cached_model_path(), str(snapshot))

    def test_incomplete_cache_is_not_used(self):
        snapshot = self.root / "models" / "models--Systran--faster-whisper-base.en" / "snapshots" / "abc123"
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_bytes(b"test")
        self.assertIsNone(self.transcriber._cached_model_path())


if __name__ == "__main__":
    unittest.main()
