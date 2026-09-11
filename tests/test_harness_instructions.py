from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from skillforge import harness, model
from skillforge.build import frontmatter

from project_support import REPO_ROOT


class HarnessInstructionTests(unittest.TestCase):
    def test_all_host_copies_match_the_canonical_skill(self) -> None:
        self.assertEqual(harness.check(REPO_ROOT), [])

    def test_claude_imports_the_shared_repository_instructions(self) -> None:
        self.assertEqual(
            (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip(),
            "@AGENTS.md",
        )
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for command in (
            "python3 -m skillforge sync-harness --check",
            "python3 -m skillforge build --all --vertical all",
            "python3 -m skillforge validate",
            "python3 -m skillforge eval",
            "python3 -m skillforge mutate-test",
            "python3 -m unittest discover -s tests -v",
        ):
            self.assertIn(command, agents)
        self.assertIn(
            "skill://.kiro/skills/skillforge-authoring/SKILL.md",
            agents,
        )

    def test_marketplace_distribution_directory_is_not_gitignored(self) -> None:
        rules = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertNotIn("dist/", rules)
        self.assertNotIn("/dist/", rules)

    def test_authoring_skill_is_discoverable_and_its_references_exist(self) -> None:
        directory = REPO_ROOT / harness.CANONICAL
        text = (directory / "SKILL.md").read_text(encoding="utf-8")
        meta, _ = frontmatter(text)

        self.assertEqual(meta["name"], "skillforge-authoring")
        description = meta["description"].lower()
        for trigger in ("persona", "vertical", "agent", "constraint", "skill.md"):
            self.assertIn(trigger, description)

        links = re.findall(r"\((references/[^)]+)\)", text)
        self.assertGreaterEqual(len(links), 4)
        for relative in links:
            self.assertTrue((directory / relative).is_file(), relative)

    def test_sync_refuses_to_replace_an_unmarked_host_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(REPO_ROOT / "harness", root / "harness")
            destination = root / harness.HOST_DESTINATIONS[0]
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("user-owned\n", encoding="utf-8")

            with self.assertRaises(model.ModelError):
                harness.sync(root)

            self.assertEqual(
                (destination / "SKILL.md").read_text(encoding="utf-8"),
                "user-owned\n",
            )

    def test_sync_repairs_marked_generated_copies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(REPO_ROOT / "harness", root / "harness")
            harness.sync(root)
            changed = root / harness.HOST_DESTINATIONS[1] / "SKILL.md"
            changed.write_text("drift\n", encoding="utf-8")

            self.assertTrue(harness.check(root))
            harness.sync(root)
            self.assertEqual(harness.check(root), [])


if __name__ == "__main__":
    unittest.main()
