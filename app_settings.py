"""Small, validated JSON settings store for Voice Typer."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._values: dict[str, Any] = {
            "pause_seconds": 1.4,
            "microphone_index": None,
            "ai_enabled": False,
            "ai_model": "qwen2.5:1.5b-instruct",
        }
        self.load()

    def load(self) -> None:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return
            if not isinstance(raw, dict):
                return
            pause = raw.get("pause_seconds")
            if isinstance(pause, (int, float)) and not isinstance(pause, bool) and 0.6 <= pause <= 4.0:
                self._values["pause_seconds"] = float(pause)
            microphone = raw.get("microphone_index")
            if microphone is None or (isinstance(microphone, int) and not isinstance(microphone, bool) and microphone >= 0):
                self._values["microphone_index"] = microphone
            ai_enabled = raw.get("ai_enabled")
            if isinstance(ai_enabled, bool):
                self._values["ai_enabled"] = ai_enabled
            ai_model = raw.get("ai_model")
            if isinstance(ai_model, str) and re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", ai_model):
                self._values["ai_model"] = ai_model

    def get(self, key: str) -> Any:
        with self._lock:
            return self._values[key]

    def set(self, key: str, value: Any) -> None:
        if key not in self._values:
            raise KeyError(key)
        if key == "pause_seconds":
            value = max(0.6, min(4.0, float(value)))
        if key == "microphone_index" and value is not None:
            value = int(value)
        if key == "ai_enabled":
            value = bool(value)
        if key == "ai_model":
            value = str(value).strip()
            if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", value):
                raise ValueError("Invalid Ollama model name")
        with self._lock:
            self._values[key] = value
            self._save_locked()

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._values, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)
