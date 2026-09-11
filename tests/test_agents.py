from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skillforge import model, validate
from skillforge.build import frontmatter

from project_support import build_all, copy_project, validate_all


class AgentGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = copy_project(Path(self.temporary.name))
        result, _, error = build_all(self.root)
        self.assertEqual(result, 0, error)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_persona_agents_generate_all_four_native_grant_shapes(self) -> None:
        cases = (
            ("project-manager-pack", "pm-project-manager", "project-manager"),
            ("engineer-pack", "eng-software-engineer", "software-engineer"),
        )
        for pack_name, built_name, source_name in cases:
            pack = self.root / "dist" / pack_name
            manifest = json.loads(
                (pack / "agents" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["persona"], pack_name.removesuffix("-pack"))
            self.assertEqual([entry["name"] for entry in manifest["agents"]], [built_name])
            source = model.load_agent(source_name, self.root)
            self.assertEqual(manifest["agents"][0]["grants"], source.grants)

            claude = pack / "agents" / f"{built_name}.md"
            codex = pack / "agents" / "codex" / f"{built_name}.toml"
            kiro = pack / "agents" / "kiro" / f"{built_name}.json"
            quick = pack / "agents" / "quick" / f"{built_name}.json"
            for path in (claude, codex, kiro, quick):
                self.assertTrue(path.is_file(), path)

            metadata, claude_body = frontmatter(claude.read_text(encoding="utf-8"))
            self.assertEqual(metadata["name"], built_name)
            self.assertEqual(
                metadata["tools"],
                ", ".join(source.grants["claude"]["tools"]),
            )
            codex_text = codex.read_text(encoding="utf-8")
            self.assertIn(
                f'sandbox_mode = "{source.grants["codex"]["sandbox_mode"]}"',
                codex_text,
            )
            kiro_data = json.loads(kiro.read_text(encoding="utf-8"))
            self.assertEqual(kiro_data["tools"], source.grants["kiro"]["tools"])
            self.assertEqual(
                kiro_data["allowedTools"],
                source.grants["kiro"]["allowed_tools"],
            )
            quick_data = json.loads(quick.read_text(encoding="utf-8"))
            self.assertEqual(quick_data["tools"], source.grants["quick"]["tools"])
            self.assertNotIn("<!-- profile:", claude_body)

        engineer = (
            self.root / "dist" / "engineer-pack" / "agents"
            / "eng-software-engineer.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`eng-design-technical-change`", engineer)
        self.assertIn("`eng-review-code-change`", engineer)
        project_manager = (
            self.root / "dist" / "project-manager-pack" / "agents"
            / "pm-project-manager.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`pm-plan-project-delivery`", project_manager)
        self.assertIn("`pm-report-project-status`", project_manager)

    def test_agent_grants_require_every_host_and_exact_claude_names(self) -> None:
        path = self.root / "agents" / "software-engineer.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["grants"]["quick"]
        data["grants"]["claude"]["tools"].append("mcp__server__*")
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        report = validate.Report()

        validate.check_agents(self.root, report)

        self.assertTrue(any("missing ['quick']" in error for error in report.errors),
                        report.errors)

    def test_flattened_name_collision_is_rejected_before_build(self) -> None:
        directory = self.root / "skills" / "eng-start-here"
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            "---\nname: eng-start-here\ndescription: Collision fixture.\n---\n",
            encoding="utf-8",
        )
        path = self.root / "policies" / "personas" / "engineer.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["include_skills"].append("eng-start-here")
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        report = validate.Report()

        validate.check_cross_host_collisions(self.root, report)

        self.assertTrue(any("both generate skill 'eng-start-here'" in error
                            for error in report.errors), report.errors)

    def test_full_validation_accepts_generated_agents(self) -> None:
        result, output, error = validate_all(self.root)
        self.assertEqual(result, 0, output + error)

    def test_built_agent_prompt_drift_is_rejected(self) -> None:
        path = (
            self.root / "dist" / "engineer-pack" / "agents" / "kiro"
            / "eng-software-engineer.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        data["prompt"] = "Stale generated prompt."
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        report = validate.Report()

        validate.check_packs(self.root, self.root / "dist", report)

        self.assertTrue(any("generated kiro agent" in error and "drifted" in error
                            for error in report.errors), report.errors)


if __name__ == "__main__":
    unittest.main()
