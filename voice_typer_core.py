"""Core speech, formatting, and prediction logic for Voice Typer."""

from __future__ import annotations

import collections
import logging
import os
import re
import threading
from pathlib import Path

APP_NAME = "Voice Typer"
LOGGER = logging.getLogger(__name__)


def data_directory() -> Path:
    """Return a writable per-user data directory, independent of the launch folder."""
    override = os.environ.get("VOICE_TYPER_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif os.name == "nt" and os.environ.get("APPDATA"):
        path = Path(os.environ["APPDATA"]) / APP_NAME
    else:
        path = Path.home() / ".voice-typer"
    path.mkdir(parents=True, exist_ok=True)
    return path


STARTER_WORDS = """# Add sentences you often say, one per line. Comments are ignored.
i want to go
i need to finish
i would like to
can you please
could you please
let me check
i am going to
we should start
finish the report
send an email
start the meeting
"""


class WordPredictor:
    """A thread-safe bigram/trigram model trained on the user's own phrases."""

    def __init__(self, words_file: Path):
        self.words_file = Path(words_file)
        self._lock = threading.RLock()
        self._pairs: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
        self._triples: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(collections.Counter)
        self._words: collections.Counter[str] = collections.Counter()
        self._recent: collections.deque[str] = collections.deque(maxlen=2)
        self._vocabulary: set[str] = set()

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text.casefold(), re.UNICODE)

    def learn(self, text: str) -> None:
        words = self.tokenize(text)
        if not words:
            return
        with self._lock:
            self._vocabulary.update(words)
            self._words.update(words)
            sequence = ["<start>"] + words
            for index, word in enumerate(words):
                self._pairs[sequence[index]][word] += 1
                if index:
                    self._triples[(sequence[index - 1], sequence[index])][word] += 1

    def load(self) -> None:
        with self._lock:
            if not self.words_file.exists():
                self.words_file.parent.mkdir(parents=True, exist_ok=True)
                self.words_file.write_text(STARTER_WORDS, encoding="utf-8")
            lines = self.words_file.read_text(encoding="utf-8-sig").splitlines()
        for line in lines:
            if line.strip() and not line.lstrip().startswith("#"):
                self.learn(line)

    def remember(self, text: str) -> None:
        """Persist a dictated phrase, then immediately use it for predictions."""
        clean = text.strip()
        if not clean:
            return
        with self._lock:
            self.words_file.parent.mkdir(parents=True, exist_ok=True)
            with self.words_file.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(clean + "\n")
            self.learn(clean)

    def record_typed(self, text: str) -> None:
        with self._lock:
            self._recent.extend(self.tokenize(text))

    def predict(self, count: int = 3) -> list[str]:
        with self._lock:
            context = list(self._recent)
            guesses: list[str] = []
            if len(context) == 2:
                guesses.extend(word for word, _ in self._triples[tuple(context)].most_common(count))
            if len(guesses) < count and context:
                for word, _ in self._pairs[context[-1]].most_common():
                    if word not in guesses:
                        guesses.append(word)
                    if len(guesses) == count:
                        break
            if len(guesses) < count:
                for word, _ in self._words.most_common():
                    if word not in guesses:
                        guesses.append(word)
                    if len(guesses) == count:
                        break
            return guesses

    def recognition_prompt(self, limit: int = 120) -> str:
        """Supply vocabulary as a hint to Whisper instead of rewriting recognized words."""
        with self._lock:
            preferred = sorted(self._vocabulary, key=lambda word: (-self._words[word], word))
            return ", ".join(preferred[:limit])


_UNDO_COMMANDS = {"undo that", "delete that", "scratch that"}
_COMMANDS = {
    "new paragraph": "\n\n",
    "new line": "\n",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "full stop": ".",
    "semicolon": ";",
    "comma": ",",
    "period": ".",
    "colon": ":",
    "open parenthesis": "(",
    "close parenthesis": ")",
}
_COMMAND_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(command) for command in sorted(_COMMANDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def is_undo_command(text: str) -> bool:
    return text.strip().casefold().strip(".!? ") in _UNDO_COMMANDS


def format_dictation(text: str) -> str:
    """Apply spoken punctuation and produce text ready to insert into another app."""
    clean = re.sub(r"\s+", " ", text.strip())
    if not clean:
        return ""
    exact_command = clean.casefold().strip(".!? ")
    if exact_command in {"new line", "new paragraph"}:
        return _COMMANDS[exact_command]

    formatted = _COMMAND_PATTERN.sub(lambda match: _COMMANDS[match.group(1).casefold()], clean)
    formatted = re.sub(r" *\n+ *", lambda match: match.group(0).strip(" "), formatted)
    formatted = re.sub(r"\s+([,.!?;:])", r"\1", formatted)
    formatted = re.sub(r"\(\s+", "(", formatted)
    formatted = re.sub(r"\s+\)", ")", formatted)
    formatted = re.sub(r"[ \t]{2,}", " ", formatted).strip(" ")
    return formatted if formatted.endswith(("\n", "\n\n")) else formatted + " "


class WhisperTranscriber:
    """Lazy, offline faster-whisper transcriber using CPU-friendly int8 inference."""

    def __init__(self, model_name: str, model_dir: Path, predictor: WordPredictor):
        self.model_name = model_name
        self.model_dir = Path(model_dir)
        self.predictor = predictor
        self._model = None
        self._lock = threading.Lock()

    def _cached_model_path(self) -> str | None:
        """Resolve faster-whisper's minimal cache without any network metadata request."""
        repository = self.model_name if "/" in self.model_name else f"Systran/faster-whisper-{self.model_name}"
        snapshots = self.model_dir / f"models--{repository.replace('/', '--')}" / "snapshots"
        if not snapshots.is_dir():
            return None
        required = {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}
        for snapshot in sorted(snapshots.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
            if snapshot.is_dir() and all((snapshot / filename).is_file() for filename in required):
                return str(snapshot)
        return None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            self.model_dir.mkdir(parents=True, exist_ok=True)
            model_source = self._cached_model_path() or self.model_name
            LOGGER.info("Loading offline speech model %s", model_source)
            self._model = WhisperModel(
                model_source,
                device="cpu",
                compute_type="int8",
                download_root=str(self.model_dir),
            )

    def transcribe(self, audio: object) -> str:
        """Transcribe a SpeechRecognition AudioData object without cloud services."""
        import numpy as np

        self.load()
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)  # type: ignore[attr-defined]
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if not samples.size:
            return ""
        prompt = self.predictor.recognition_prompt()
        with self._lock:
            segments, _ = self._model.transcribe(
                samples,
                language="en",
                beam_size=5,
                temperature=0.0,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=prompt or None,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
