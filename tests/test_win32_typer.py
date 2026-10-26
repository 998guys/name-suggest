import ctypes
import os
import unittest

from win32_typer import INPUT, WindowsTyper


@unittest.skipUnless(os.name == "nt", "Windows-only typing tests")
class WindowsTypingTests(unittest.TestCase):
    def test_input_structure_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_unicode_uses_utf16_code_units(self):
        typer = WindowsTyper(delay=0)
        sent = []
        typer._send = sent.extend
        typer.type_text("A😀")
        self.assertEqual(len(sent), 6)
        self.assertEqual(sent[0].ki.wScan, ord("A"))
        self.assertEqual(sent[2].ki.wScan, 0xD83D)
        self.assertEqual(sent[4].ki.wScan, 0xDE00)

    def test_newline_uses_return_not_literal_character(self):
        typer = WindowsTyper(delay=0)
        sent = []
        typer._send = sent.extend
        typer.type_text("\n")
        self.assertEqual([event.ki.wVk for event in sent], [0x0D, 0x0D])


if __name__ == "__main__":
    unittest.main()
