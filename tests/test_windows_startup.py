import os
import unittest

from windows_startup import startup_command


@unittest.skipUnless(os.name == "nt", "Windows-only startup tests")
class StartupTests(unittest.TestCase):
    def test_startup_uses_current_interpreter_and_minimized_mode(self):
        command = startup_command()
        self.assertIn("python", command.casefold())
        self.assertIn("voice_typer.py", command)
        self.assertTrue(command.endswith("--minimized"))

    def test_startup_command_quotes_paths(self):
        self.assertTrue(command_starts_with_quote())


def command_starts_with_quote() -> bool:
    return startup_command().startswith('"')


if __name__ == "__main__":
    unittest.main()
