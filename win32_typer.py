"""Unicode-safe Windows text injection using SendInput."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

ULONG_PTR = wintypes.WPARAM
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08
VK_RETURN = 0x0D


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD))


class INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = (("type", wintypes.DWORD), ("union", INPUTUNION))


class WindowsTyper:
    """Type text without changing the clipboard or losing non-ASCII characters."""

    def __init__(self, delay: float = 0.002):
        self.delay = delay
        self._send_input = ctypes.WinDLL("user32", use_last_error=True).SendInput
        self._send_input.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._send_input.restype = wintypes.UINT

    def _send(self, inputs: list[INPUT]) -> None:
        if not inputs:
            return
        array = (INPUT * len(inputs))(*inputs)
        sent = self._send_input(len(inputs), array, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            error = ctypes.get_last_error()
            raise OSError(error, f"Windows accepted {sent} of {len(inputs)} keystrokes")

    @staticmethod
    def _key(vk: int, key_up: bool = False) -> INPUT:
        return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if key_up else 0, 0, 0))

    @staticmethod
    def _unicode(unit: int, key_up: bool = False) -> INPUT:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
        return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, unit, flags, 0, 0))

    def type_text(self, text: str) -> None:
        for character in text:
            if character == "\r":
                continue
            if character == "\n":
                self._send([self._key(VK_RETURN), self._key(VK_RETURN, True)])
            else:
                encoded = character.encode("utf-16-le")
                units = [int.from_bytes(encoded[index:index + 2], "little") for index in range(0, len(encoded), 2)]
                events: list[INPUT] = []
                for unit in units:
                    events.extend((self._unicode(unit), self._unicode(unit, True)))
                self._send(events)
            if self.delay:
                time.sleep(self.delay)

    def backspace(self, count: int) -> None:
        for _ in range(max(0, count)):
            self._send([self._key(VK_BACK), self._key(VK_BACK, True)])
            if self.delay:
                time.sleep(self.delay)
