"""Run checked-in, deterministic harness-routing evaluations.

These evaluations do not spend model tokens or mutate a repository. They prove that each coding
harness can discover the canonical authoring skill and that its checked-in trigger examples still
route in both directions. Live CLI integration tests remain opt-in in tests/test_external_validators.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import harness
from .build import frontmatter

SUPPORTED_HARNESSES = ("codex", "claude", "kiro")
HOST_SKILL_PATHS = {
    "codex": harness.HOST_DESTINATIONS[0],
    "claude": harness.HOST_DESTINATIONS[1],
    "kiro": harness.HOST_DESTINATIONS[2],
}

AUTHORING_ACTION = re.compile(
    r"\b(add|author|change|create|edit|implement|make|modify|remove|update)\b",
    re.IGNORECASE,
)
AUTHORING_OBJECT = re.compile(
    r"\b(persona|vertical|constraint|profile (?:block|branch)|canonical skill|"
    r"source skill|skill\.md|audience pack|domain pack|compliance add-on|agent)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvalResult:
    harness: str
    case: str
    expected: bool
    actual: bool
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "harness": self.harness,
            "case": self.case,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "detail": self.detail,
        }


def classify_authoring_prompt(prompt: str) -> bool:
    """The repository skill's deterministic routing contract."""
    return bool(AUTHORING_ACTION.search(prompt) and AUTHORING_OBJECT.search(prompt))


def load_suite(path: Path) -> tuple[dict | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{path} is missing"]
    except (OSError, ValueError) as exc:
        return None, [f"{path} is not valid readable JSON: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{path} must contain a JSON object"]

    problems: list[str] = []
    if data.get("version") != 1:
        problems.append(f"{path}: version must be 1")
    if data.get("runner") != "skillforge-authoring-v1":
        problems.append(f"{path}: runner must be 'skillforge-authoring-v1'")
    if data.get("skill") != "skillforge-authoring":
        problems.append(f"{path}: skill must be 'skillforge-authoring'")

    harnesses = data.get("harnesses")
    if not isinstance(harnesses, list) or any(
            host not in SUPPORTED_HARNESSES for host in harnesses):
        problems.append(
            f"{path}: harnesses must be a list drawn from {SUPPORTED_HARNESSES}")
    elif len(harnesses) != len(set(harnesses)):
        problems.append(f"{path}: harnesses contains duplicates")
    elif set(harnesses) != set(SUPPORTED_HARNESSES):
        problems.append(
            f"{path}: harnesses must cover all supported coding harnesses "
            f"{SUPPORTED_HARNESSES}")

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append(f"{path}: cases must be a non-empty list")
        return data, problems
    ids: list[str] = []
    directions: set[bool] = set()
    for index, case in enumerate(cases):
        label = f"{path}: cases[{index}]"
        if not isinstance(case, dict):
            problems.append(f"{label} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            problems.append(f"{label}.id must be a non-empty string")
        else:
            ids.append(case_id)
        if not isinstance(case.get("should_trigger"), bool):
            problems.append(f"{label}.should_trigger must be a boolean")
        else:
            directions.add(case["should_trigger"])
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            problems.append(f"{label}.prompt must be a non-empty string")
        expected = case.get("expected")
        if not isinstance(expected, dict) or not isinstance(
                expected.get("required_outcomes"), list) or not expected["required_outcomes"]:
            problems.append(f"{label}.expected.required_outcomes must be a non-empty list")
    if len(ids) != len(set(ids)):
        problems.append(f"{path}: case ids must be unique")
    if directions != {False, True}:
        problems.append(f"{path}: cases must cover both trigger and non-trigger outcomes")
    return data, problems


def _tree(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != harness.MARKER
    } if directory.is_dir() else {}


def host_discovery_problems(root: Path, host: str) -> list[str]:
    canonical = root / harness.CANONICAL
    destination = root / HOST_SKILL_PATHS[host]
    problems: list[str] = []
    if _tree(destination) != _tree(canonical):
        problems.append(
            f"{host}: {HOST_SKILL_PATHS[host]}/ does not match {harness.CANONICAL}/")

    agents = root / "AGENTS.md"
    agents_text = agents.read_text(encoding="utf-8") if agents.is_file() else ""
    if "skillforge-authoring" not in agents_text:
        problems.append(f"{host}: AGENTS.md does not route authoring work to skillforge-authoring")
    if host == "claude":
        claude = root / "CLAUDE.md"
        if not claude.is_file() or "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
            problems.append("claude: CLAUDE.md does not import @AGENTS.md")
    if host == "kiro" and "skill://.kiro/skills/skillforge-authoring/SKILL.md" not in agents_text:
        problems.append("kiro: AGENTS.md does not document the custom-agent skill resource")
    return problems


def run_suite(root: Path, data: dict, selected: list[str] | None = None) -> list[EvalResult]:
    canonical = root / harness.CANONICAL / "SKILL.md"
    discovery_description = ""
    if canonical.is_file():
        metadata, _ = frontmatter(canonical.read_text(encoding="utf-8"))
        discovery_description = str(metadata.get("description", "")).lower()
    description_ok = all(
        phrase in discovery_description
        for phrase in ("persona", "vertical", "do not use only to install")
    )

    hosts = selected or data["harnesses"]
    results: list[EvalResult] = []
    for host in hosts:
        discovery = host_discovery_problems(root, host)
        if not description_ok:
            discovery.append(
                "canonical description must cover personas, verticals, and the install-only "
                "non-trigger boundary")
        detail = "; ".join(discovery)
        for case in data["cases"]:
            actual = classify_authoring_prompt(case["prompt"])
            expected = case["should_trigger"]
            results.append(EvalResult(
                harness=host,
                case=case["id"],
                expected=expected,
                actual=actual,
                passed=not discovery and actual == expected,
                detail=detail or (
                    "" if actual == expected
                    else f"routing returned {actual}, expected {expected}"
                ),
            ))
    return results


def check(root: Path, suite_path: Path | None = None) -> list[str]:
    path = suite_path or root / "evals" / "skillforge-authoring.json"
    data, problems = load_suite(path)
    if data is None or problems:
        return problems
    results = run_suite(root, data)
    return [
        f"eval {result.harness}/{result.case}: {result.detail or 'unexpected route'}"
        for result in results
        if not result.passed
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--file", default="evals/skillforge-authoring.json")
    ap.add_argument("--harness", action="append", choices=SUPPORTED_HARNESSES)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    path = Path(args.file)
    if not path.is_absolute():
        path = root / path
    data, problems = load_suite(path)
    if data is None or problems:
        for problem in problems:
            print(f"✗ {problem}", file=sys.stderr)
        return 1

    selected = list(dict.fromkeys(args.harness or data["harnesses"]))
    results = run_suite(root, data, selected)
    if args.as_json:
        print(json.dumps({
            "passed": all(result.passed for result in results),
            "results": [result.to_dict() for result in results],
        }, indent=2))
    else:
        for result in results:
            status = "ok  " if result.passed else "FAIL"
            route = "trigger" if result.actual else "skip"
            print(f"  {status}  {result.harness:6}  {result.case:28} {route}")
            if result.detail and not result.passed:
                print(f"        {result.detail}")
        passed = sum(result.passed for result in results)
        print(f"\n{'✓' if passed == len(results) else '✗'} "
              f"{passed}/{len(results)} harness eval(s) passed")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
