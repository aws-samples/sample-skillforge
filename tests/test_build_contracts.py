from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skillforge import build, model, validate

from project_support import build_all, copy_project


def snapshot(root: Path) -> dict[str, bytes]:
    targets = [
        root / "dist",
        root / ".claude-plugin" / "marketplace.json",
        root / ".agents" / "plugins" / "marketplace.json",
    ]
    files: dict[str, bytes] = {}
    for target in targets:
        if target.is_file():
            files[str(target.relative_to(root))] = target.read_bytes()
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    files[str(path.relative_to(root))] = path.read_bytes()
    return files


class BuildContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = copy_project(Path(self.temporary.name))
        result, _, error = build_all(self.root)
        self.assertEqual(result, 0, error)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def tagged_skills(self) -> dict[str, str]:
        tagged: dict[str, str] = {}
        for directory in (self.root / "skills").iterdir():
            if not (directory / "SKILL.md").is_file():
                continue
            meta, _ = build.frontmatter(
                (directory / "SKILL.md").read_text(encoding="utf-8"))
            vertical = (meta.get("metadata") or {}).get("vertical")
            if vertical:
                tagged[directory.name] = vertical
        return tagged

    def test_every_pack_has_the_exact_expected_skill_inventory(self) -> None:
        tagged = self.tagged_skills()
        for persona_id in model.all_persona_ids(self.root):
            persona = model.load_persona(persona_id, self.root)
            expected_base = {
                build.prefixed(name, persona.prefix)
                for name in persona.include_skills
                if name not in tagged
            }
            actual_base = {
                path.name for path in
                (self.root / "dist" / persona.pack_name / "skills").iterdir()
                if path.is_dir()
            }
            self.assertEqual(actual_base, expected_base)

            for vertical_id in model.all_vertical_ids(self.root):
                vertical = model.load_vertical(vertical_id, self.root)
                pack = self.root / "dist" / f"vertical-{vertical_id}-{persona_id}"
                if persona_id not in vertical.personas:
                    self.assertFalse(pack.exists())
                    continue
                expected_vertical = {
                    build.prefixed(name, persona.prefix)
                    for name, owner in tagged.items()
                    if owner == vertical_id
                }
                actual_vertical = {
                    path.name for path in (pack / "skills").iterdir() if path.is_dir()
                }
                self.assertEqual(actual_vertical, expected_vertical)

    def test_every_built_skill_is_resolved_and_matches_its_directory(self) -> None:
        for skill_file in sorted((self.root / "dist").glob("*/skills/*/SKILL.md")):
            text = skill_file.read_text(encoding="utf-8")
            meta, _ = build.frontmatter(text)
            self.assertEqual(meta.get("name"), skill_file.parent.name, skill_file)
            self.assertNotIn("<!-- profile:", text, skill_file)
            self.assertNotIn("<!-- /profile -->", text, skill_file)

        analyst = (self.root / "dist" / "analyst-pack" / "skills"
                   / "an-build-report" / "SKILL.md").read_text()
        auditor = (self.root / "dist" / "auditor-pack" / "skills"
                   / "au-build-report" / "SKILL.md").read_text()
        engineer = (self.root / "dist" / "engineer-pack" / "skills"
                    / "eng-build-report" / "SKILL.md").read_text()
        project_manager = (self.root / "dist" / "project-manager-pack" / "skills"
                           / "pm-build-report" / "SKILL.md").read_text()
        self.assertIn("Work in the warehouse, not in production", analyst)
        self.assertIn("Pull them yourself with `an-query-warehouse`", analyst)
        self.assertIn("read access to evidence, not to data", auditor)
        self.assertIn("Request an extract through the engagement contact", auditor)
        self.assertIn("least-sensitive environment", engineer)
        self.assertIn("Use reproducible evidence", engineer)
        self.assertIn("Coordinate access; do not assume it", project_manager)
        self.assertIn("Collect each status or figure", project_manager)

        engineering_vertical = (
            self.root / "dist" / "vertical-software-engineering-engineer" / "skills"
            / "eng-review-code-change" / "SKILL.md"
        ).read_text()
        delivery_vertical = (
            self.root / "dist" / "vertical-project-delivery-project-manager" / "skills"
            / "pm-report-project-status" / "SKILL.md"
        ).read_text()
        self.assertIn("`eng-design-technical-change`", engineering_vertical)
        self.assertIn(
            "> Pack:    vertical-software-engineering-engineer v0.2.0",
            engineering_vertical,
        )
        self.assertIn("`pm-plan-project-delivery`", delivery_vertical)
        self.assertIn("`pm-build-report`", delivery_vertical)
        self.assertIn(
            "> Pack:    vertical-project-delivery-project-manager v0.2.0",
            delivery_vertical,
        )

    def test_claude_and_codex_marketplaces_are_complete_and_agree(self) -> None:
        claude = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        codex = json.loads(
            (self.root / ".agents" / "plugins" / "marketplace.json").read_text())
        claude_names = [entry["name"] for entry in claude["plugins"]]
        codex_names = [entry["name"] for entry in codex["plugins"]]

        self.assertTrue(claude["description"])
        self.assertEqual(len(claude_names), len(set(claude_names)))
        self.assertEqual(claude_names, codex_names)
        for entry in claude["plugins"]:
            source = (self.root / entry["source"]).resolve()
            self.assertTrue(source.is_dir(), entry)
            manifest = json.loads(
                (source / ".claude-plugin" / "plugin.json").read_text())
            self.assertEqual(manifest["name"], entry["name"])
            self.assertEqual(manifest["author"]["name"], "Skillforge contributors")
            if "mcpServers" in manifest:
                pointer = source / manifest["mcpServers"]
                self.assertTrue(pointer.is_file(), pointer)

        for entry in codex["plugins"]:
            source = (self.root / entry["source"]["path"]).resolve()
            self.assertTrue(source.is_dir(), entry)

    def test_kiro_mcp_contract_marks_opt_in_servers_disabled(self) -> None:
        for pack_name in ("analyst-pack", "engineer-pack"):
            config = json.loads(
                (self.root / "dist" / pack_name / "mcp" / "kiro-mcp.json").read_text())
            servers = config["mcpServers"]
            self.assertFalse(servers["sqlite-explorer"].get("disabled", False))
            self.assertEqual(
                servers["sqlite-explorer"]["args"][:3],
                ["--with", "mcp<2", "mcp-server-sqlite"],
            )
            self.assertTrue(servers["warehouse-mcp"]["disabled"])
        for pack_name in ("auditor-pack", "project-manager-pack"):
            self.assertFalse(
                (self.root / "dist" / pack_name / "mcp" / "kiro-mcp.json").exists())

        for pack in (self.root / "dist").glob("vertical-*"):
            for forbidden in (".mcp.json", "mcp", "agents"):
                self.assertFalse((pack / forbidden).exists(), f"{pack.name}/{forbidden}")

    def test_built_pack_validation_scans_bundled_files_and_prefixes(self) -> None:
        skill = self.root / "dist" / "analyst-pack" / "skills" / "an-start-here"
        references = skill / "references"
        references.mkdir()
        (references / "broken.md").write_text(
            "<!-- profile:analyst -->\n`query-warehouse`\n<!-- /profile -->\n",
            encoding="utf-8",
        )
        unprefixed = self.root / "dist" / "analyst-pack" / "skills" / "unexpected"
        unprefixed.mkdir()
        (unprefixed / "SKILL.md").write_text(
            "---\nname: unexpected\ndescription: Broken generated skill.\n---\n",
            encoding="utf-8",
        )
        report = validate.Report()

        validate.check_packs(self.root, self.root / "dist", report)

        self.assertTrue(any("ships a raw conditional marker" in error
                            for error in report.errors), report.errors)
        self.assertTrue(any("unresolved skill reference `query-warehouse`" in error
                            for error in report.errors), report.errors)
        self.assertTrue(any("does not start with persona prefix" in error
                            for error in report.errors), report.errors)

    def test_shared_mcp_groups_get_unique_companion_plugin_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            path = root / "policies" / "personas" / "auditor.json"
            persona = json.loads(path.read_text(encoding="utf-8"))
            persona["include_skills"].append("query-warehouse")
            path.write_text(json.dumps(persona, indent=2) + "\n", encoding="utf-8")

            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            marketplace = json.loads(
                (root / ".claude-plugin" / "marketplace.json").read_text())
            names = [entry["name"] for entry in marketplace["plugins"]]
            companions = [name for name in names if name.startswith("mcp-warehouse-")]
            self.assertEqual(set(companions), {
                "mcp-warehouse-analyst-pack",
                "mcp-warehouse-auditor-pack",
                "mcp-warehouse-engineer-pack",
            })
            self.assertEqual(len(names), len(set(names)))

    def test_build_is_reproducible(self) -> None:
        first = snapshot(self.root)
        result, _, error = build_all(self.root)
        self.assertEqual(result, 0, error)
        self.assertEqual(snapshot(self.root), first)


if __name__ == "__main__":
    unittest.main()
