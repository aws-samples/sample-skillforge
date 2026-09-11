"""Prove every validation gate rejects a representative defect."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import build, harness, model, validate


@dataclass(frozen=True)
class Mutation:
    id: str
    gate: str
    expected: str
    apply: Callable[[Path], None]
    needs_build: bool = False


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _break_harness(root: Path) -> None:
    (root / "CLAUDE.md").write_text("No shared import.\n", encoding="utf-8")


def _break_skill_name(root: Path) -> None:
    path = root / "skills" / "start-here" / "SKILL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("name: start-here", "name: wrong-name", 1),
        encoding="utf-8",
    )


def _break_profile_group(root: Path) -> None:
    path = root / "skills" / "start-here" / "SKILL.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n<!-- profile:analyst -->\nOnly one persona is named.\n<!-- /profile -->\n",
        encoding="utf-8",
    )


def _break_persona(root: Path) -> None:
    path = root / "policies" / "personas" / "auditor.json"
    data = _json(path)
    data["pack_name"] = "analyst-pack"
    _write_json(path, data)


def _break_agent_grant(root: Path) -> None:
    path = root / "agents" / "software-engineer.json"
    data = _json(path)
    data["grants"]["claude"]["tools"].append("mcp__server__*")
    _write_json(path, data)


def _break_mcp(root: Path) -> None:
    path = root / "mcp" / "warehouse.json"
    data = _json(path)
    data["loading"] = "eager"
    _write_json(path, data)


def _break_evals(root: Path) -> None:
    path = root / "evals" / "skillforge-authoring.json"
    data = _json(path)
    data["harnesses"].remove("kiro")
    _write_json(path, data)


def _add_flattened_collision(root: Path) -> None:
    directory = root / "skills" / "an-start-here"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\n"
        "name: an-start-here\n"
        "description: Deliberately colliding mutation fixture.\n"
        "---\n\n"
        "# Collision\n",
        encoding="utf-8",
    )
    path = root / "policies" / "personas" / "analyst.json"
    data = _json(path)
    data["include_skills"].append("an-start-here")
    _write_json(path, data)


def _break_built_pack(root: Path) -> None:
    path = root / "dist" / "analyst-pack" / "skills" / "an-start-here" / "SKILL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "name: an-start-here", "name: stale-generated-name", 1),
        encoding="utf-8",
    )


MUTATIONS = (
    Mutation("claude-drops-shared-import", "harness-instructions",
             "must import @AGENTS.md", _break_harness),
    Mutation("skill-name-disagrees-with-folder", "skills",
             "must match the folder name", _break_skill_name),
    Mutation("profile-group-omits-personas", "conditional-blocks",
             "does not name", _break_profile_group),
    Mutation("personas-share-pack-name", "personas",
             "share pack_name", _break_persona),
    Mutation("claude-agent-uses-wildcard", "agents",
             "wildcard", _break_agent_grant),
    Mutation("restricted-mcp-becomes-eager", "mcp",
             "must be opt-in", _break_mcp),
    Mutation("eval-matrix-drops-host", "eval-cases",
             "must cover all supported coding harnesses", _break_evals),
    Mutation("prefixed-source-collides-after-flattening", "cross-host-collisions",
             "both generate skill", _add_flattened_collision),
    Mutation("built-skill-frontmatter-drifts", "built-packs",
             "built name=", _break_built_pack, needs_build=True),
)


def _copy_project(source: Path, destination: Path) -> Path:
    root = destination / "project"
    root.mkdir()
    for name in ("skills", "agents", "policies", "mcp", "harness", "evals"):
        shutil.copytree(source / name, root / name)
    for name in ("AGENTS.md", "CLAUDE.md", "skillforge.json"):
        shutil.copy2(source / name, root / name)
    harness.sync(root)
    return root


def run_mutation(source: Path, mutation: Mutation) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="skillforge-mutation-") as temporary:
        root = _copy_project(source, Path(temporary))
        prior_root = model.ROOT
        model.ROOT = root
        try:
            if mutation.needs_build:
                result = build.main([
                    "--root", str(root),
                    "--out", "dist",
                    "--all",
                    "--vertical", "all",
                ])
                if result:
                    return False, "baseline build failed"

            baseline = validate.Report()
            ran = validate.run_gate(
                mutation.gate, root, root / "dist", baseline)
            if not ran:
                return False, "baseline gate was skipped"
            if baseline.errors:
                return False, f"baseline gate already failed: {baseline.errors}"

            mutation.apply(root)
            mutated = validate.Report()
            ran = validate.run_gate(
                mutation.gate, root, root / "dist", mutated)
            if not ran:
                return False, "mutated gate was skipped"
            if not mutated.errors:
                return False, "mutation survived the gate"
            if not any(mutation.expected in error for error in mutated.errors):
                return False, (
                    f"gate failed for the wrong reason; expected {mutation.expected!r}, "
                    f"got {mutated.errors}"
                )
            return True, mutated.errors[0]
        except Exception as exc:  # the harness reports crashes as failures, never as a pass
            return False, f"{type(exc).__name__}: {exc}"
        finally:
            model.ROOT = prior_root


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--gate", action="append", choices=validate.gate_names())
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    selected = set(args.gate or validate.gate_names())

    failures = 0
    for mutation in MUTATIONS:
        if mutation.gate not in selected:
            continue
        passed, detail = run_mutation(root, mutation)
        print(f"  {'ok  ' if passed else 'FAIL'}  {mutation.gate:24} {mutation.id}")
        if not passed:
            failures += 1
            print(f"        {detail}", file=sys.stderr)
    if failures:
        print(f"\nERROR: {failures} mutation(s) escaped or failed incorrectly", file=sys.stderr)
        return 1
    print("\nOK: every validation gate rejected its mutation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
