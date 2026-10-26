"""Tkinter desktop interface, audio lifecycle, and system tray for Voice Typer."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import keyboard
import pystray
import speech_recognition as sr
from PIL import Image

from ai_cleanup import AICleanupError, OllamaCleanup
from app_settings import SettingsStore
from voice_typer_core import WhisperTranscriber, WordPredictor, format_dictation, is_undo_command
from win32_typer import WindowsTyper
from windows_startup import is_startup_enabled, set_startup_enabled

APP_NAME = "Voice Typer"
HOTKEY_LISTEN = "ctrl+alt+shift+l"
HOTKEY_QUIT = "ctrl+alt+shift+q"
HOTKEY_UNDO = "ctrl+alt+shift+z"
HOTKEY_SUGGESTIONS = ("ctrl+alt+shift+1", "ctrl+alt+shift+2", "ctrl+alt+shift+3")
LOGGER = logging.getLogger(__name__)
ASSETS = Path(__file__).resolve().parent / "assets"


class VoiceTyperApp:
    def __init__(self, root: tk.Tk, data_dir: Path, model_name: str, start_minimized: bool = False):
        self.root = root
        self.data_dir = data_dir
        self.settings = SettingsStore(data_dir / "settings.json")
        self.predictor = WordPredictor(data_dir / "my_words.txt")
        self.predictor.load()
        self.transcriber = WhisperTranscriber(model_name, data_dir / "models", self.predictor)
        self.typer = WindowsTyper()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.listening = threading.Event()
        self.ready = threading.Event()
        self.microphone_restart = threading.Event()
        self.state_lock = threading.Lock()
        self.suggestions: list[str] = []
        self.last_insertion = ""
        self.microphones = self._input_devices()
        available_indexes = {index for index, _ in self.microphones}
        saved_microphone = self.settings.get("microphone_index")
        self.microphone_index = saved_microphone if saved_microphone in available_indexes else None
        self.pause_value = float(self.settings.get("pause_seconds"))
        self.pause_seconds = tk.DoubleVar(value=self.pause_value)
        self.microphone_choice = tk.StringVar()
        self.startup_choice = tk.BooleanVar(value=is_startup_enabled())
        self.ai_active = bool(self.settings.get("ai_enabled"))
        self.ai_choice = tk.BooleanVar(value=self.ai_active)
        self.ai_model_choice = tk.StringVar(value=str(self.settings.get("ai_model")))
        self.ai_cleanup = OllamaCleanup(self.ai_model_choice.get())
        self.tray: pystray.Icon | None = None
        self.tray_notice_shown = False
        self.listener_thread = threading.Thread(target=self._listen_loop, name="voice-listener", daemon=True)

        self._build_window()
        self._setup_tray()
        self._register_hotkeys()
        self.listener_thread.start()
        self.root.after(100, self._process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        if self.ai_active:
            self.root.after(200, self._check_ai_availability)
        if start_minimized:
            self.root.after(300, self.hide_window)

    @staticmethod
    def _input_devices() -> list[tuple[int, str]]:
        """Return only capture devices, using the same indexes as SpeechRecognition."""
        audio = sr.Microphone.get_pyaudio().PyAudio()
        try:
            devices = []
            for index in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(index)
                if int(info.get("maxInputChannels", 0)) > 0:
                    devices.append((index, str(info.get("name", f"Microphone {index}"))))
            return devices
        finally:
            audio.terminate()

    def _build_window(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry("650x900")
        self.root.minsize(560, 760)
        self.root.configure(background="#f4f6fa")
        try:
            self.root.iconbitmap(str(ASSETS / "voice_typer.ico"))
        except tk.TclError:
            pass

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), background="#f4f6fa")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), background="#f4f6fa", foreground="#536174")
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"), background="#f4f6fa")
        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), padding=10)
        style.configure("TButton", font=("Segoe UI", 10), padding=7)
        style.configure("TScale", background="#f4f6fa")

        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)
        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 16))
        try:
            self.header_icon = tk.PhotoImage(file=str(ASSETS / "voice_typer.png")).subsample(6, 6)
            icon_label = tk.Label(header, image=self.header_icon, bg="#f4f6fa")
            icon_label.pack(side="left", padx=(0, 12))
        except tk.TclError:
            self.header_icon = None
        title_group = ttk.Frame(header)
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(title_group, text="Voice Typer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_group, text="Private, offline dictation for Windows", style="Sub.TLabel").pack(anchor="w")

        status_frame = ttk.Frame(container)
        status_frame.pack(fill="x", pady=(0, 12))
        self.status_dot = tk.Label(status_frame, text="●", fg="#d97706", bg="#f4f6fa", font=("Segoe UI", 18))
        self.status_dot.pack(side="left")
        self.status_label = ttk.Label(status_frame, text="Preparing…", style="Status.TLabel", wraplength=530)
        self.status_label.pack(side="left", padx=8)

        self.listen_button = ttk.Button(
            container,
            text="Start dictating",
            style="Accent.TButton",
            command=lambda: self.toggle_listening(from_gui=True),
            state="disabled",
        )
        self.listen_button.pack(fill="x", pady=(0, 8))
        ttk.Label(
            container,
            text=f"Global hotkey: {HOTKEY_LISTEN.replace('+', ' + ').title()}",
            style="Sub.TLabel",
        ).pack(pady=(0, 14))

        audio_settings = ttk.LabelFrame(container, text="Audio & startup", padding=12)
        audio_settings.pack(fill="x", pady=(0, 12))
        ttk.Label(audio_settings, text="Microphone").pack(anchor="w")
        names = ["Windows default microphone"] + [name for _, name in self.microphones]
        self.microphone_combo = ttk.Combobox(
            audio_settings,
            values=names,
            textvariable=self.microphone_choice,
            state="disabled",
            height=8,
        )
        self.microphone_combo.pack(fill="x", pady=(5, 8))
        self.microphone_combo.bind("<<ComboboxSelected>>", self._microphone_changed)
        if self.microphone_index is not None:
            selected = next((i + 1 for i, (index, _) in enumerate(self.microphones) if index == self.microphone_index), None)
            if selected is not None:
                self.microphone_combo.current(selected)
        elif self.microphones:
            self.microphone_combo.current(0)
        else:
            self.microphone_combo.set("No input microphone detected")
        ttk.Checkbutton(
            audio_settings,
            text="Start Voice Typer when I sign in to Windows",
            variable=self.startup_choice,
            command=self._startup_changed,
        ).pack(anchor="w")

        ai_settings = ttk.LabelFrame(container, text="Optional local AI cleanup", padding=12)
        ai_settings.pack(fill="x", pady=(0, 12))
        ttk.Checkbutton(
            ai_settings,
            text="Clean grammar, filler words, and false starts with Ollama",
            variable=self.ai_choice,
            command=self._ai_changed,
        ).pack(anchor="w")
        model_row = ttk.Frame(ai_settings)
        model_row.pack(fill="x", pady=(8, 0))
        ttk.Label(model_row, text="Model").pack(side="left")
        ai_model_combo = ttk.Combobox(
            model_row,
            textvariable=self.ai_model_choice,
            values=("qwen2.5:1.5b-instruct", "llama3.2:3b", "qwen3:1.7b"),
        )
        ai_model_combo.pack(side="left", fill="x", expand=True, padx=(10, 0))
        ai_model_combo.bind("<<ComboboxSelected>>", self._ai_model_changed)
        ai_model_combo.bind("<FocusOut>", self._ai_model_changed)

        patience = ttk.LabelFrame(container, text="Listening patience", padding=12)
        patience.pack(fill="x", pady=(0, 14))
        self.pause_label = ttk.Label(patience, text=f"End a phrase after {self.pause_value:.1f} seconds of silence")
        self.pause_label.pack(anchor="w")
        ttk.Scale(patience, from_=0.6, to=4.0, variable=self.pause_seconds, command=self._pause_changed).pack(
            fill="x", pady=(7, 0)
        )

        ttk.Label(container, text="Next-word suggestions", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.suggestion_buttons: list[ttk.Button] = []
        suggestion_frame = ttk.Frame(container)
        suggestion_frame.pack(fill="x", pady=(7, 8))
        for index in range(3):
            button = ttk.Button(
                suggestion_frame,
                text=f"{index + 1}. —",
                command=lambda i=index: self._accept_from_gui(i),
            )
            button.pack(side="left", fill="x", expand=True, padx=(0 if index == 0 else 4, 0))
            self.suggestion_buttons.append(button)
        ttk.Label(
            container,
            text="Ctrl+Alt+Shift+1 / 2 / 3 accepts a suggestion. Ctrl+Alt+Shift+Z undoes.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        history_header = ttk.Frame(container)
        history_header.pack(fill="x")
        ttk.Label(history_header, text="Recent dictation", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(history_header, text="Clear", command=self._clear_history).pack(side="right")
        history_frame = ttk.Frame(container)
        history_frame.pack(fill="both", expand=True, pady=(7, 10))
        self.history = tk.Text(
            history_frame,
            height=5,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 10),
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history.yview)
        self.history.configure(yscrollcommand=scrollbar.set)
        self.history.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        footer = ttk.Frame(container)
        footer.pack(fill="x")
        ttk.Button(footer, text="Edit vocabulary", command=self._edit_vocabulary).pack(side="left")
        ttk.Button(footer, text="Reload vocabulary", command=self._reload_vocabulary).pack(side="left", padx=6)
        ttk.Button(footer, text="Hide to tray", command=self.hide_window).pack(side="right")

    def _setup_tray(self) -> None:
        images = {}
        for name in ("voice_typer", "voice_typer_listening"):
            with Image.open(ASSETS / f"{name}.png") as image:
                images[name] = image.copy()
        self.tray_images = images
        menu = pystray.Menu(
            pystray.MenuItem("Open Voice Typer", lambda icon, item: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem(
                "Start / pause dictation", lambda icon, item: self.root.after(0, self.toggle_listening)
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.root.after(0, self.shutdown)),
        )
        self.tray = pystray.Icon("VoiceTyper", images["voice_typer"], "Voice Typer — Ready", menu)
        threading.Thread(target=self.tray.run, name="voice-tray", daemon=True).start()

    def _register_hotkeys(self) -> None:
        try:
            keyboard.add_hotkey(HOTKEY_LISTEN, lambda: self.root.after(0, self.toggle_listening))
            keyboard.add_hotkey(HOTKEY_QUIT, lambda: self.root.after(0, self.shutdown))
            keyboard.add_hotkey(HOTKEY_UNDO, lambda: self.root.after(0, self.undo_last))
            for index, hotkey in enumerate(HOTKEY_SUGGESTIONS):
                keyboard.add_hotkey(hotkey, lambda i=index: self.root.after(0, self.accept_suggestion, i))
        except Exception as error:
            LOGGER.exception("Could not register hotkeys")
            self.events.put(("fatal", f"Could not register global hotkeys: {error}"))

    def _pause_changed(self, _value: object = None) -> None:
        self.pause_value = float(self.pause_seconds.get())
        self.pause_label.configure(text=f"End a phrase after {self.pause_value:.1f} seconds of silence")
        self.settings.set("pause_seconds", self.pause_value)

    def _microphone_changed(self, _event: object = None) -> None:
        selected = self.microphone_combo.current()
        if selected < 0:
            return
        self.listening.clear()
        self.ready.clear()
        self.microphone_index = None if selected == 0 else self.microphones[selected - 1][0]
        self.settings.set("microphone_index", self.microphone_index)
        self.listen_button.configure(state="disabled", text="Start dictating")
        self._set_status("Switching microphone…", "#d97706")
        self.microphone_restart.set()

    def _ai_model_changed(self, _event: object = None) -> None:
        model = self.ai_model_choice.get().strip()
        try:
            self.settings.set("ai_model", model)
        except ValueError:
            self.ai_model_choice.set(str(self.settings.get("ai_model")))
            return
        self.ai_cleanup.model = model
        if self.ai_active:
            self._check_ai_availability()

    def _ai_changed(self) -> None:
        self.ai_active = bool(self.ai_choice.get())
        self.settings.set("ai_enabled", self.ai_active)
        if self.ai_active:
            self._set_status("Checking local AI…", "#d97706")
            self._check_ai_availability()
        else:
            self._set_status("AI cleanup off — standard offline dictation remains active", "#2563eb")

    def _check_ai_availability(self) -> None:
        def check() -> None:
            try:
                self.ai_cleanup.check_available()
                self.events.put(("ai_ready", f"Local AI ready: {self.ai_cleanup.model}"))
            except AICleanupError as error:
                self.events.put(("ai_error", str(error)))

        threading.Thread(target=check, name="ai-check", daemon=True).start()

    def _startup_changed(self) -> None:
        try:
            set_startup_enabled(bool(self.startup_choice.get()))
        except OSError as error:
            LOGGER.exception("Could not update startup registration")
            self.startup_choice.set(is_startup_enabled())
            messagebox.showerror(APP_NAME, f"Could not update Windows startup: {error}")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self) -> None:
        self.root.withdraw()
        if self.tray and not self.tray_notice_shown:
            self.tray_notice_shown = True
            try:
                self.tray.notify("Voice Typer is still running. Use the tray icon to open or exit it.", APP_NAME)
            except Exception:
                LOGGER.exception("Could not show tray notification")

    def toggle_listening(self, from_gui: bool = False) -> None:
        if not self.ready.is_set() or self.stop_event.is_set():
            return
        if self.listening.is_set():
            self.listening.clear()
            self._set_status("Paused", "#64748b")
            self.listen_button.configure(text="Resume dictating")
        else:
            self.listening.set()
            self._set_status("Listening — speak naturally", "#16a34a")
            self.listen_button.configure(text="Pause dictating")
            if from_gui:
                self.root.after(250, self.hide_window)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text)
        self.status_dot.configure(fg=color)
        if self.tray:
            self.tray.title = f"{APP_NAME} — {text}"[:63]
            self.tray.icon = self.tray_images["voice_typer_listening" if self.listening.is_set() else "voice_typer"]

    def _restore_working_status(self) -> None:
        if self.stop_event.is_set():
            return
        if self.listening.is_set():
            self._set_status("Listening — speak naturally", "#16a34a")
        elif self.ready.is_set():
            self._set_status("Ready — click your target app, then start", "#2563eb")

    def _listen_loop(self) -> None:
        try:
            self.events.put(("status", ("Loading offline speech model…", "#d97706")))
            self.transcriber.load()
            while not self.stop_event.is_set():
                self.microphone_restart.clear()
                self.events.put(("status", ("Preparing microphone…", "#d97706")))
                recognizer = sr.Recognizer()
                recognizer.dynamic_energy_threshold = True
                microphone = sr.Microphone(device_index=self.microphone_index)
                with microphone as source:
                    recognizer.adjust_for_ambient_noise(source, duration=1.0)
                    self.ready.set()
                    self.events.put(("ready", None))
                    while not self.stop_event.is_set() and not self.microphone_restart.is_set():
                        if not self.listening.is_set():
                            self.stop_event.wait(0.1)
                            continue
                        recognizer.pause_threshold = self.pause_value
                        recognizer.non_speaking_duration = min(0.4, recognizer.pause_threshold / 2)
                        try:
                            audio = recognizer.listen(source, timeout=1.0, phrase_time_limit=None)
                        except sr.WaitTimeoutError:
                            continue
                        if not self.listening.is_set() or self.stop_event.is_set() or self.microphone_restart.is_set():
                            continue
                        self.events.put(("status", ("Transcribing offline…", "#2563eb")))
                        try:
                            text = self.transcriber.transcribe(audio)
                        except Exception as error:
                            LOGGER.exception("Transcription failed")
                            self.events.put(("status", (f"Transcription error: {error}", "#dc2626")))
                            continue
                        ai_warning = None
                        if text and self.ai_active:
                            self.events.put(("status", ("Cleaning dictation with local AI…", "#7c3aed")))
                            try:
                                text = self.ai_cleanup.enhance(text)
                            except Exception as error:
                                LOGGER.warning("AI cleanup failed; using original dictation: %s", error)
                                ai_warning = "AI unavailable — original dictation preserved"
                        if self.listening.is_set():
                            self.events.put(("status", ("Listening — speak naturally", "#16a34a")))
                        if ai_warning:
                            self.events.put(("ai_warning", ai_warning))
                        if text:
                            self.events.put(("dictation", text))
        except Exception as error:
            LOGGER.exception("Listener stopped")
            self.events.put(("fatal", self._friendly_listener_error(error)))

    @staticmethod
    def _friendly_listener_error(error: Exception) -> str:
        if isinstance(error, OSError):
            return (
                "Microphone unavailable. Connect a microphone and allow desktop apps in "
                "Windows Settings → Privacy & security → Microphone."
            )
        return f"Voice Typer could not start: {error}"

    def _process_events(self) -> None:
        if self.stop_event.is_set():
            return
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "status":
                    text, color = payload  # type: ignore[misc]
                    self._set_status(text, color)
                elif event == "ready":
                    self.ready.set()
                    self._set_status("Ready — click your target app, then start", "#2563eb")
                    self.listen_button.configure(state="normal")
                    self.microphone_combo.configure(state="readonly" if self.microphones else "disabled")
                    self._refresh_suggestions()
                elif event == "ai_ready":
                    self._set_status(str(payload), "#7c3aed")
                elif event == "ai_error":
                    self.ai_active = False
                    self.ai_choice.set(False)
                    self.settings.set("ai_enabled", False)
                    self._set_status(str(payload), "#dc2626")
                elif event == "ai_warning":
                    self._set_status(str(payload), "#d97706")
                    self.root.after(3000, self._restore_working_status)
                elif event == "dictation":
                    self._handle_dictation(str(payload))
                elif event == "fatal":
                    self.listening.clear()
                    self._set_status(str(payload), "#dc2626")
                    self.listen_button.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _handle_dictation(self, text: str) -> None:
        if is_undo_command(text):
            self.undo_last()
            self._add_history("↶ Undid the last insertion")
            return
        formatted = format_dictation(text)
        if not formatted:
            return
        try:
            self.typer.type_text(formatted)
            self.predictor.remember(text)
            self.predictor.record_typed(formatted)
            with self.state_lock:
                self.last_insertion = formatted
            self._add_history(text)
            self._refresh_suggestions()
        except Exception as error:
            LOGGER.exception("Could not type dictation")
            self._set_status(f"Could not type: {error}", "#dc2626")

    def _add_history(self, text: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("1.0", text.strip() + "\n\n")
        self.history.configure(state="disabled")

    def _clear_history(self) -> None:
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")

    def _edit_vocabulary(self) -> None:
        os.startfile(self.predictor.words_file)  # type: ignore[attr-defined]

    def _reload_vocabulary(self) -> None:
        predictor = WordPredictor(self.data_dir / "my_words.txt")
        predictor.load()
        self.predictor = predictor
        self.transcriber.predictor = predictor
        self._refresh_suggestions()
        self._set_status("Vocabulary reloaded", "#2563eb")

    def _refresh_suggestions(self) -> None:
        with self.state_lock:
            self.suggestions = self.predictor.predict(3)
            current = list(self.suggestions)
        for index, button in enumerate(self.suggestion_buttons):
            word = current[index] if index < len(current) else "—"
            button.configure(text=f"{index + 1}. {word}")

    def _accept_from_gui(self, index: int) -> None:
        self.hide_window()
        self.root.after(350, lambda: self.accept_suggestion(index))

    def accept_suggestion(self, index: int) -> None:
        with self.state_lock:
            if index >= len(self.suggestions):
                return
            word = self.suggestions[index]
        inserted = word + " "
        try:
            self.typer.type_text(inserted)
            self.predictor.record_typed(inserted)
            with self.state_lock:
                self.last_insertion = inserted
            self._refresh_suggestions()
        except Exception as error:
            LOGGER.exception("Could not type suggestion")
            self._set_status(f"Could not type suggestion: {error}", "#dc2626")

    def undo_last(self) -> None:
        with self.state_lock:
            count = len(self.last_insertion)
            self.last_insertion = ""
        if count:
            try:
                self.typer.backspace(count)
            except Exception as error:
                LOGGER.exception("Could not undo")
                self._set_status(f"Could not undo: {error}", "#dc2626")

    def shutdown(self) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.listening.clear()
        try:
            keyboard.unhook_all()
        except Exception:
            LOGGER.exception("Could not remove hotkeys")
        if self.tray:
            self.tray.stop()
        self.root.destroy()
