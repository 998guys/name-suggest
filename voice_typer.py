"""Voice Typer command-line entry point."""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import speech_recognition as sr

from voice_typer_core import WhisperTranscriber, WordPredictor, data_directory

APP_NAME = "Voice Typer"


def _single_instance_mutex() -> object | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, r"Local\VoiceTyperSingleInstance")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        messagebox.showinfo(APP_NAME, "Voice Typer is already running. Check the system tray.")
        return None
    return handle


def _download_model(data_dir: Path, model_name: str) -> None:
    predictor = WordPredictor(data_dir / "my_words.txt")
    predictor.load()
    WhisperTranscriber(model_name, data_dir / "models", predictor).load()
    print(f"Offline model '{model_name}' is ready.")


def _diagnose(data_dir: Path, model_name: str) -> int:
    print(f"Data folder: {data_dir}")
    print(f"Python: {sys.version.split()[0]}")
    try:
        microphones = sr.Microphone.list_microphone_names()
        print(f"Audio devices: {len(microphones)} detected")
        for name in microphones[:5]:
            print(f"  - {name}")
    except Exception as error:
        print(f"Microphone check failed: {error}")
        return 1
    try:
        _download_model(data_dir, model_name)
    except Exception as error:
        print(f"Speech model check failed: {error}")
        return 1
    print("Diagnosis passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Private offline voice typing for Windows")
    parser.add_argument("--model", default=os.environ.get("VOICE_TYPER_MODEL", "base.en"))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--download-model", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--minimized", action="store_true", help="Start in the system tray")
    args = parser.parse_args()

    if os.name != "nt":
        parser.error("Voice Typer currently supports Windows only.")
    data_dir = (args.data_dir or data_directory()).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=data_dir / "voice_typer.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    if args.download_model:
        _download_model(data_dir, args.model)
        return 0
    if args.diagnose:
        return _diagnose(data_dir, args.model)

    mutex = _single_instance_mutex()
    if os.name == "nt" and mutex is None:
        return 0
    from voice_typer_app import VoiceTyperApp

    root = tk.Tk()
    VoiceTyperApp(root, data_dir, args.model, start_minimized=args.minimized)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
