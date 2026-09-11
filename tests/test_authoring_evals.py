from __future__ import annotations

import json
import unittest

from project_support import REPO_ROOT


class AuthoringEvalDefinitionTests(unittest.TestCase):
    def test_eval_matrix_covers_every_harness_and_both_trigger_directions(self) -> None:
        data = json.loads(
            (REPO_ROOT / "evals" / "skillforge-authoring.json").read_text())

        self.assertEqual(data["skill"], "skillforge-authoring")
        self.assertEqual(set(data["harnesses"]), {"codex", "claude", "kiro"})
        cases = data["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(case["should_trigger"] for case in cases))
        self.assertTrue(any(not case["should_trigger"] for case in cases))
        for case in cases:
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(case["expected"]["required_outcomes"])


if __name__ == "__main__":
    unittest.main()
