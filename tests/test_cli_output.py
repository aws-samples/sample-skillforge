from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from skillforge import model, validate

from project_support import build_all, copy_project


class StrictCp1252Writer:
    """A redirected Windows-style stream that rejects unencodable output."""

    encoding = "cp1252"

    def __init__(self) -> None:
        self.parts: list[str] = []

    def write(self, text: str) -> int:
        text.encode(self.encoding, errors="strict")
        self.parts.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def value(self) -> str:
        return "".join(self.parts)


class CliOutputTests(unittest.TestCase):
    def test_validate_success_output_is_safe_for_windows_cp1252(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)

            stdout = StrictCp1252Writer()
            stderr = StrictCp1252Writer()
            prior = model.ROOT
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = validate.main([
                        "--root", str(root),
                        "--out", "dist",
                    ])
            finally:
                model.ROOT = prior

            self.assertEqual(result, 0, stderr.value())
            self.assertIn("OK: all gates pass", stdout.value())


if __name__ == "__main__":
    unittest.main()
