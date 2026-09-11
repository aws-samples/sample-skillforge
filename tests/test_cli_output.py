from __future__ import annotations

import ast
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from skillforge import model, validate

from project_support import REPO_ROOT, build_all, copy_project


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
    def test_all_path_text_io_declares_an_encoding(self) -> None:
        missing: list[str] = []
        for directory in ("skillforge", "tests"):
            for path in sorted((REPO_ROOT / directory).glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not isinstance(
                            node.func, ast.Attribute):
                        continue
                    if node.func.attr not in {"read_text", "write_text"}:
                        continue
                    if not any(keyword.arg == "encoding" for keyword in node.keywords):
                        missing.append(
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno} "
                            f"{node.func.attr}()")
        self.assertEqual(
            missing,
            [],
            "Path text I/O must declare an encoding for Windows compatibility",
        )

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
