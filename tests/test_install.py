from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skillforge import install, model

from project_support import build_all, copy_project


class KiroInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.skills_dir = self.root / "kiro" / "skills"
        self.mcp_config = self.root / "kiro" / "settings" / "mcp.json"
        self.environment = patch.dict(os.environ, {
            "KIRO_SKILLS_DIR": str(self.skills_dir),
            "KIRO_MCP_CONFIG": str(self.mcp_config),
        })
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def make_pack(self, name: str, skills: list[str],
                  servers: dict[str, dict] | None = None) -> Path:
        pack = self.root / "dist" / name
        for skill in skills:
            directory = pack / "skills" / skill
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "SKILL.md").write_text(
                f"---\nname: {skill}\ndescription: Test skill.\n---\n", encoding="utf-8")
        if servers is not None:
            mcp = pack / "mcp"
            mcp.mkdir(parents=True, exist_ok=True)
            (mcp / "kiro-mcp.json").write_text(
                json.dumps({"mcpServers": servers}), encoding="utf-8")
        return pack

    def read_mcp(self) -> dict:
        return json.loads(self.mcp_config.read_text(encoding="utf-8"))["mcpServers"]

    def test_installs_persona_and_vertical_then_swaps_them_together(self) -> None:
        analyst = self.make_pack("analyst-pack", ["an-start-here"], {
            "sqlite-explorer": {"command": "uvx", "args": ["sqlite"]},
            "warehouse-mcp": {"command": "warehouse-mcp", "disabled": True},
        })
        pci = self.make_pack(
            "vertical-pci-dss-analyst", ["an-card-data-scope"])

        result = install.install_kiro([analyst, pci], symlink=False)

        self.assertEqual(result["packs"], ["analyst-pack", "vertical-pci-dss-analyst"])
        self.assertEqual(result["linked"], 2)
        self.assertTrue((self.skills_dir / "an-start-here").is_dir())
        self.assertTrue((self.skills_dir / "an-card-data-scope").is_dir())
        self.assertEqual(result["mcp_added"], 2)

        auditor = self.make_pack("auditor-pack", ["au-start-here"])
        swapped = install.install_kiro(auditor, symlink=False)

        self.assertEqual(swapped["removed"], 2)
        self.assertEqual(swapped["mcp_deleted"], 2)
        self.assertFalse((self.skills_dir / "an-start-here").exists())
        self.assertFalse((self.skills_dir / "an-card-data-scope").exists())
        self.assertTrue((self.skills_dir / "au-start-here").is_dir())
        self.assertEqual(self.read_mcp(), {})

    def test_restores_an_adopted_user_server_when_persona_changes(self) -> None:
        self.mcp_config.parent.mkdir(parents=True)
        self.mcp_config.write_text(json.dumps({"mcpServers": {
            "warehouse-mcp": {
                "command": "my-warehouse",
                "disabled": True,
                "note": "user-owned",
            },
            "unrelated": {"command": "leave-me-alone"},
        }}), encoding="utf-8")
        analyst = self.make_pack("analyst-pack", ["an-query-warehouse"], {
            "warehouse-mcp": {"command": "warehouse-mcp", "disabled": True},
        })

        installed = install.install_kiro(analyst, symlink=False)

        self.assertEqual(installed["mcp_adopted"], 1)
        adopted = self.read_mcp()["warehouse-mcp"]
        self.assertEqual(adopted["command"], "my-warehouse")
        self.assertEqual(adopted["note"], "user-owned")
        self.assertTrue(adopted[install.ADOPTED])
        self.assertTrue(adopted[install.PRIOR])

        auditor = self.make_pack("auditor-pack", ["au-start-here"])
        swapped = install.install_kiro(auditor, symlink=False)

        self.assertEqual(swapped["mcp_restored"], 1)
        restored = self.read_mcp()
        self.assertEqual(restored["warehouse-mcp"], {
            "command": "my-warehouse",
            "disabled": True,
            "note": "user-owned",
        })
        self.assertEqual(restored["unrelated"], {"command": "leave-me-alone"})

    @unittest.skipIf(os.name == "nt", "creating symlinks may require Windows Developer Mode")
    def test_does_not_replace_a_user_owned_skill_symlink(self) -> None:
        user_skill = self.root / "user-skills" / "an-start-here"
        user_skill.mkdir(parents=True)
        self.skills_dir.mkdir(parents=True)
        collision = self.skills_dir / "an-start-here"
        collision.symlink_to(user_skill)
        analyst = self.make_pack("analyst-pack", ["an-start-here"])

        result = install.install_kiro(analyst, symlink=False)

        self.assertEqual(result["linked"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(collision.resolve(), user_skill.resolve())

    def test_invalid_mcp_config_is_left_unchanged_before_skills_are_replaced(self) -> None:
        self.mcp_config.parent.mkdir(parents=True)
        self.mcp_config.write_text("{not-json", encoding="utf-8")
        analyst = self.make_pack("analyst-pack", ["an-start-here"])

        with self.assertRaises(model.ModelError):
            install.install_kiro(analyst)

        self.assertEqual(self.mcp_config.read_text(encoding="utf-8"), "{not-json")
        self.assertFalse((self.skills_dir / "an-start-here").exists())

    def test_cli_accepts_a_vertical_alongside_the_persona(self) -> None:
        project = self.root / "project"
        personas = project / "policies" / "personas"
        verticals = project / "policies" / "verticals"
        personas.mkdir(parents=True)
        verticals.mkdir(parents=True)
        (personas / "analyst.json").write_text(json.dumps({
            "display_name": "Analyst",
            "pack_name": "analyst-pack",
            "prefix": "an-",
            "description": "Analyst skills.",
            "include_skills": ["start-here"],
        }), encoding="utf-8")
        (verticals / "pci-dss.json").write_text(json.dumps({
            "id": "pci-dss",
            "display_name": "PCI DSS",
            "description": "Card-data rules.",
            "personas": ["analyst"],
        }), encoding="utf-8")

        base = project / "dist" / "analyst-pack" / "skills" / "an-start-here"
        vertical = project / "dist" / "vertical-pci-dss-analyst" / "skills" \
            / "an-card-data-scope"
        for directory in (base, vertical):
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text(
                f"---\nname: {directory.name}\ndescription: Test skill.\n---\n",
                encoding="utf-8")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = install.main([
                "--root", str(project),
                "--persona", "analyst",
                "--vertical", "pci-dss",
                "--host", "kiro",
            ])

        self.assertEqual(result, 0, stderr.getvalue())
        expected_symlink = install.should_symlink(False, False)
        self.assertEqual(
            (self.skills_dir / "an-start-here").is_symlink(),
            expected_symlink,
        )
        self.assertEqual(
            (self.skills_dir / "an-card-data-scope").is_symlink(),
            expected_symlink,
        )
        self.assertTrue((self.skills_dir / "an-start-here").exists())
        self.assertTrue((self.skills_dir / "an-card-data-scope").exists())
        self.assertIn("analyst-pack, vertical-pci-dss-analyst", stdout.getvalue())

    def test_checked_in_example_persona_vertical_pairs_install_and_swap(self) -> None:
        project = copy_project(self.root)
        built, _, build_error = build_all(project)
        self.assertEqual(built, 0, build_error)

        project_manager = [
            project / "dist" / "project-manager-pack",
            project / "dist" / "vertical-project-delivery-project-manager",
        ]
        installed = install.install_kiro(project_manager, symlink=False)

        self.assertEqual(installed["linked"], 5)
        self.assertEqual({
            path.name for path in self.skills_dir.iterdir()
        }, {
            "pm-build-report",
            "pm-handle-customer-data",
            "pm-plan-project-delivery",
            "pm-report-project-status",
            "pm-start-here",
        })
        self.assertFalse(self.mcp_config.exists())

        engineer = [
            project / "dist" / "engineer-pack",
            project / "dist" / "vertical-software-engineering-engineer",
        ]
        swapped = install.install_kiro(engineer, symlink=False)

        self.assertEqual(swapped["removed"], 5)
        self.assertEqual(swapped["linked"], 6)
        self.assertEqual(swapped["mcp_added"], 2)
        self.assertEqual({
            path.name for path in self.skills_dir.iterdir()
        }, {
            "eng-build-report",
            "eng-design-technical-change",
            "eng-handle-customer-data",
            "eng-query-warehouse",
            "eng-review-code-change",
            "eng-start-here",
        })
        servers = self.read_mcp()
        self.assertFalse(servers["sqlite-explorer"].get("disabled", False))
        self.assertTrue(servers["warehouse-mcp"]["disabled"])


if __name__ == "__main__":
    unittest.main()
