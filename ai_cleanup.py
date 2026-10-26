"""Optional local AI cleanup through Ollama; no audio or text leaves the PC."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class AICleanupError(RuntimeError):
    pass


class OllamaCleanup:
    def __init__(self, model: str = "qwen2.5:1.5b-instruct", base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = 15.0

    def _request(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise AICleanupError(f"Local AI is unavailable: {error.reason}") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise AICleanupError("Local AI returned an invalid response") from error

    def check_available(self) -> None:
        data = self._request("/api/tags", timeout=3.0)
        models = {str(model.get("name", "")) for model in data.get("models", [])}
        acceptable = {self.model, f"{self.model}:latest"}
        if not any(name in models for name in acceptable):
            raise AICleanupError(
                f"Ollama is running, but '{self.model}' is not installed. Run: ollama pull {self.model}"
            )

    @staticmethod
    def _clean_response(text: str) -> str:
        clean = text.strip()
        clean = re.sub(r"^```(?:text)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
        if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {'"', "“", "'"}:
            clean = clean[1:-1].strip()
        return clean

    def enhance(self, text: str) -> str:
        if not text.strip():
            return text
        system = (
            "You clean up English voice dictation. Correct punctuation, capitalization, grammar, "
            "and obvious recognition errors. Remove filler words and false starts only when safe. "
            "Preserve the speaker's meaning, names, numbers, tone, and formatting commands. "
            "Return only the cleaned dictation, never comments, explanations, quotes, or Markdown."
        )
        data = self._request(
            "/api/generate",
            {
                "model": self.model,
                "system": system,
                "prompt": text,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 400},
            },
        )
        cleaned = self._clean_response(str(data.get("response", "")))
        if not cleaned:
            raise AICleanupError("Local AI returned an empty response")
        if len(cleaned) > max(1000, len(text) * 4):
            raise AICleanupError("Local AI response was unexpectedly long; original dictation preserved")
        return cleaned
