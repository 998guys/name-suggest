import json
import unittest
from unittest.mock import MagicMock, patch

from ai_cleanup import AICleanupError, OllamaCleanup


def response(data):
    mock = MagicMock()
    mock.read.return_value = json.dumps(data).encode("utf-8")
    mock.__enter__.return_value = mock
    return mock


class OllamaCleanupTests(unittest.TestCase):
    def setUp(self):
        self.cleanup = OllamaCleanup("qwen2.5:1.5b-instruct")

    @patch("ai_cleanup.urllib.request.urlopen")
    def test_availability_accepts_installed_model(self, urlopen):
        urlopen.return_value = response({"models": [{"name": "qwen2.5:1.5b-instruct"}]})
        self.cleanup.check_available()

    @patch("ai_cleanup.urllib.request.urlopen")
    def test_missing_model_has_actionable_error(self, urlopen):
        urlopen.return_value = response({"models": []})
        with self.assertRaisesRegex(AICleanupError, "ollama pull"):
            self.cleanup.check_available()

    @patch("ai_cleanup.urllib.request.urlopen")
    def test_cleanup_uses_private_local_endpoint(self, urlopen):
        urlopen.return_value = response({"response": "This is clean dictation."})
        result = self.cleanup.enhance("uh this is clean dictation")
        self.assertEqual(result, "This is clean dictation.")
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.startswith("http://127.0.0.1:11434/"))
        payload = json.loads(request.data)
        self.assertEqual(payload["prompt"], "uh this is clean dictation")
        self.assertFalse(payload["stream"])

    @patch("ai_cleanup.urllib.request.urlopen")
    def test_strips_model_wrappers(self, urlopen):
        urlopen.return_value = response({"response": "```text\nHello, world.\n```"})
        self.assertEqual(self.cleanup.enhance("hello world"), "Hello, world.")

    @patch("ai_cleanup.urllib.request.urlopen")
    def test_empty_response_is_rejected(self, urlopen):
        urlopen.return_value = response({"response": ""})
        with self.assertRaises(AICleanupError):
            self.cleanup.enhance("hello")

    def test_empty_input_is_not_sent(self):
        self.assertEqual(self.cleanup.enhance("  "), "  ")


if __name__ == "__main__":
    unittest.main()
