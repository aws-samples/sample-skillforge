from __future__ import annotations

import io
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from skillforge import build, harness, model, validate

REPO_ROOT = Path(__file__).resolve().parents[1]


def copy_project(destination: Path) -> Path:
    root = destination / "project"
    root.mkdir(parents=True)
    for name in ("skills", "agents", "policies", "mcp", "harness", "evals"):
        shutil.copytree(REPO_ROOT / name, root / name)
    for name in ("AGENTS.md", "CLAUDE.md", "skillforge.json"):
        shutil.copy2(REPO_ROOT / name, root / name)
    harness.sync(root)
    return root


def build_all(root: Path) -> tuple[int, str, str]:
    prior = model.ROOT
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = build.main([
                "--root", str(root),
                "--out", "dist",
                "--all",
                "--vertical", "all",
            ])
    finally:
        model.ROOT = prior
    return result, stdout.getvalue(), stderr.getvalue()


def validate_all(root: Path, fast: bool = False) -> tuple[int, str, str]:
    prior = model.ROOT
    stdout = io.StringIO()
    stderr = io.StringIO()
    args = ["--root", str(root), "--out", "dist"]
    if fast:
        args.append("--fast")
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = validate.main(args)
    finally:
        model.ROOT = prior
    return result, stdout.getvalue(), stderr.getvalue()
