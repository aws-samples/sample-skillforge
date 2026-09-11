from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skillforge import evals

from project_support import REPO_ROOT, copy_project


class AuthoringEvalDefinitionTests(unittest.TestCase):
    def test_eval_matrix_covers_every_harness_and_both_trigger_directions(self) -> None:
        data = json.loads(
            (REPO_ROOT / "evals" / "skillforge-authoring.json").read_text(
                encoding="utf-8"))

        self.assertEqual(data["skill"], "skillforge-authoring")
        self.assertEqual(data["runner"], "skillforge-authoring-v1")
        self.assertEqual(set(data["harnesses"]), {"codex", "claude", "kiro"})
        cases = data["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(case["should_trigger"] for case in cases))
        self.assertTrue(any(not case["should_trigger"] for case in cases))
        for case in cases:
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(case["expected"]["required_outcomes"])

    def test_checked_in_eval_runner_executes_every_case_for_every_harness(self) -> None:
        data, problems = evals.load_suite(
            REPO_ROOT / "evals" / "skillforge-authoring.json")
        self.assertEqual(problems, [])
        results = evals.run_suite(REPO_ROOT, data)

        self.assertEqual(len(results), 9)
        self.assertTrue(all(result.passed for result in results), results)

    def test_eval_runner_detects_a_drifted_host_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            path = root / ".kiro" / "skills" / "skillforge-authoring" / "SKILL.md"
            path.write_text("drift\n", encoding="utf-8")

            problems = evals.check(root)

            self.assertTrue(any("eval kiro/" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
