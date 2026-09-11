from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skillforge import model, resolve, validate

from project_support import build_all, copy_project, validate_all


def add_persona_file(root: Path, persona_id: str = "reviewer") -> None:
    (root / "policies" / "personas" / f"{persona_id}.json").write_text(json.dumps({
        "display_name": "Data reviewer",
        "pack_name": "reviewer-pack",
        "prefix": "rv-",
        "description": "Skills for reviewers working from approved evidence.",
        "router": "start-here",
        "include_skills": ["start-here", "build-report", "handle-customer-data"],
    }, indent=2) + "\n", encoding="utf-8")


def add_profile_branches(root: Path, persona_id: str) -> None:
    for skill in sorted((root / "skills").iterdir()):
        targets = [skill / "SKILL.md"]
        for bundled in model.BUNDLED_DIRS:
            directory = skill / bundled
            if directory.is_dir():
                targets.extend(path for path in directory.rglob("*") if path.is_file())
        for path in targets:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            groups = resolve.groups(text)
            if not groups:
                continue
            lines = text.splitlines(keepends=True)
            for group in reversed(groups):
                insertion = group[-1][2] + 1
                lines[insertion:insertion] = [
                    f"<!-- profile:{persona_id} -->\n",
                    "Work from approved evidence and record its provenance.\n",
                    "<!-- /profile -->\n",
                ]
            path.write_text("".join(lines), encoding="utf-8")


class AuthoringWorkflowTests(unittest.TestCase):
    def test_add_persona_builds_base_and_vertical_packs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            add_persona_file(root)
            add_profile_branches(root, "reviewer")

            constraint = root / "policies" / "constraints" / "data-handling" / "reviewer.md"
            constraint.write_text(
                "**Use approved evidence only.** Record who produced each extract and when.\n",
                encoding="utf-8",
            )
            vertical_path = root / "policies" / "verticals" / "pci-dss.json"
            vertical = json.loads(vertical_path.read_text(encoding="utf-8"))
            vertical["personas"].append("reviewer")
            vertical_path.write_text(json.dumps(vertical, indent=2) + "\n", encoding="utf-8")

            built, _, build_error = build_all(root)
            self.assertEqual(built, 0, build_error)
            checked, output, validation_error = validate_all(root)
            self.assertEqual(checked, 0, output + validation_error)

            base = root / "dist" / "reviewer-pack"
            vertical_pack = root / "dist" / "vertical-pci-dss-reviewer"
            self.assertTrue((base / "skills" / "rv-build-report" / "SKILL.md").is_file())
            self.assertTrue(
                (vertical_pack / "skills" / "rv-card-data-scope" / "SKILL.md").is_file())
            report = (
                base / "skills" / "rv-build-report" / "SKILL.md"
            ).read_text(encoding="utf-8")
            self.assertIn("Use approved evidence only", report)
            self.assertIn("Work from approved evidence", report)
            self.assertNotIn("<!-- profile:", report)

    def test_new_persona_without_profile_branches_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            add_persona_file(root)
            report = validate.Report()

            validate.check_blocks(root, report)

            self.assertTrue(report.errors)
            self.assertTrue(any("does not name ['reviewer']" in error
                                for error in report.errors), report.errors)

    def test_add_vertical_builds_only_additive_packs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            (root / "policies" / "verticals" / "hipaa.json").write_text(json.dumps({
                "id": "hipaa",
                "display_name": "HIPAA",
                "description": "Healthcare-specific rules and workflows.",
                "personas": ["analyst", "auditor"],
            }, indent=2) + "\n", encoding="utf-8")
            skill = root / "skills" / "phi-data-scope"
            skill.mkdir()
            (skill / "SKILL.md").write_text("""---
name: phi-data-scope
description: Decide whether a workflow handles protected health information. Use when the user mentions PHI, patient records, or HIPAA scope.
metadata:
  category: compliance
  vertical: hipaa
  constraints: data-handling
---

# Determine PHI scope

Identify where protected health information enters, leaves, and is retained.
Use `handle-customer-data` for the rules governing any records involved.
""", encoding="utf-8")

            built, _, build_error = build_all(root)
            self.assertEqual(built, 0, build_error)
            checked, output, validation_error = validate_all(root)
            self.assertEqual(checked, 0, output + validation_error)

            for persona, prefix in (("analyst", "an-"), ("auditor", "au-")):
                generated = root / "dist" / f"vertical-hipaa-{persona}" / "skills" \
                    / f"{prefix}phi-data-scope" / "SKILL.md"
                self.assertTrue(generated.is_file())
                self.assertIn(
                    f"`{prefix}handle-customer-data`",
                    generated.read_text(encoding="utf-8"),
                )
            self.assertFalse(
                (root / "dist" / "analyst-pack" / "skills" / "an-phi-data-scope").exists())
            self.assertFalse(
                (root / "dist" / "auditor-pack" / "skills" / "au-phi-data-scope").exists())

    def test_vertical_skill_in_a_persona_is_rejected_as_a_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            path = root / "policies" / "personas" / "analyst.json"
            persona = json.loads(path.read_text(encoding="utf-8"))
            persona["include_skills"].append("card-data-scope")
            path.write_text(json.dumps(persona, indent=2) + "\n", encoding="utf-8")
            report = validate.Report()

            validate.check_personas(root, report)

            self.assertTrue(any("which a vertical already claims" in error
                                for error in report.errors), report.errors)

    def test_vertical_mcp_dependency_requires_each_personas_base_entitlement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            skill = root / "skills" / "card-data-scope" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nUse `warehouse-mcp` to inspect the affected records.\n",
                encoding="utf-8",
            )
            report = validate.Report()

            validate.check_mcp(root, report)

            self.assertTrue(any(
                "vertical 'pci-dss' for persona 'auditor'" in error
                and "warehouse" in error
                for error in report.errors
            ), report.errors)

    def test_malformed_persona_and_vertical_are_reported_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            (root / "policies" / "personas" / "broken.json").write_text(json.dumps({
                "display_name": "Broken",
                "pack_name": "broken-pack",
                "prefix": "br-",
                "include_skills": ["start-here"],
            }), encoding="utf-8")
            (root / "policies" / "verticals" / "broken.json").write_text(
                "{not-json", encoding="utf-8")
            report = validate.Report()

            validate.check_personas(root, report)

            self.assertTrue(any("is missing ['description']" in error
                                for error in report.errors), report.errors)
            self.assertTrue(any("is not valid JSON" in error
                                for error in report.errors), report.errors)


if __name__ == "__main__":
    unittest.main()
