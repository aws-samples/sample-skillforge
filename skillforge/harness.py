"""Synchronize the canonical repository authoring skill into each supported harness."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import model

CANONICAL = Path("harness") / "skills" / "skillforge-authoring"
HOST_DESTINATIONS = (
    Path(".agents") / "skills" / "skillforge-authoring",
    Path(".claude") / "skills" / "skillforge-authoring",
    Path(".kiro") / "skills" / "skillforge-authoring",
)
MARKER = ".skillforge-generated"


def _tree(directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(directory): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != MARKER
    }


def check(root: Path) -> list[str]:
    """Return synchronization problems without changing the repository."""
    source = root / CANONICAL
    if not (source / "SKILL.md").is_file():
        return [f"{CANONICAL}/SKILL.md is missing"]

    expected = _tree(source)
    problems: list[str] = []
    for relative in HOST_DESTINATIONS:
        destination = root / relative
        if not destination.is_dir():
            problems.append(f"{relative}/ is missing; run `python3 -m skillforge sync-harness`")
            continue
        if not (destination / MARKER).is_file():
            problems.append(f"{relative}/ is not marked as a generated Skillforge copy")
            continue
        actual = _tree(destination)
        missing = sorted(str(path) for path in set(expected) - set(actual))
        extra = sorted(str(path) for path in set(actual) - set(expected))
        changed = sorted(str(path) for path in set(expected) & set(actual)
                         if expected[path] != actual[path])
        if missing:
            problems.append(f"{relative}/ is missing {missing}")
        if extra:
            problems.append(f"{relative}/ has unexpected files {extra}")
        if changed:
            problems.append(f"{relative}/ differs from the canonical skill in {changed}")
    return problems


def sync(root: Path) -> list[Path]:
    """Replace only marked host copies with the canonical authoring skill."""
    source = root / CANONICAL
    if not (source / "SKILL.md").is_file():
        raise model.ModelError(f"{source / 'SKILL.md'} not found")

    destinations = [root / relative for relative in HOST_DESTINATIONS]
    for destination in destinations:
        if destination.is_symlink():
            raise model.ModelError(
                f"refusing to replace symlink {destination}; remove it or choose a regular "
                f"generated directory")
        if destination.exists() and not (destination / MARKER).is_file():
            raise model.ModelError(
                f"refusing to replace unmarked directory {destination}. Move it aside or add the "
                f"Skillforge-generated marker intentionally.")

    for destination in destinations:
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        (destination / MARKER).write_text(
            f"Generated from {CANONICAL.as_posix()}; do not edit this copy.\n",
            encoding="utf-8")
    return destinations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true",
                    help="check that all host copies match without changing files")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.check:
        problems = check(root)
        if problems:
            print("✗ harness authoring skill is out of sync:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print("✓ harness authoring skill copies match the canonical source")
        return 0

    try:
        destinations = sync(root)
    except model.ModelError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print(f"synced {CANONICAL.as_posix()} to:")
    for destination in destinations:
        print(f"  {destination.relative_to(root)}")
    return 0
