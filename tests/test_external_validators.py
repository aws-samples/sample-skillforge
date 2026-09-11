from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from skillforge import harness, install
from skillforge import update as updater

from project_support import build_all, copy_project


class ExternalValidatorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("skills-ref"), "skills-ref is not installed")
    def test_official_agent_skills_validator_accepts_source_and_built_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            skill_dirs = [
                path.parent
                for path in sorted((root / "skills").glob("*/SKILL.md"))
            ]
            skill_dirs.append(root / harness.CANONICAL)
            skill_dirs.extend(root / destination for destination in harness.HOST_DESTINATIONS)
            skill_dirs.extend(
                path.parent
                for path in sorted((root / "dist").glob("*/skills/*/SKILL.md"))
            )
            failures = []
            for directory in skill_dirs:
                completed = subprocess.run(
                    ["skills-ref", "validate", str(directory)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if completed.returncode:
                    failures.append(
                        f"{directory.relative_to(root)}:\n"
                        f"{completed.stdout}{completed.stderr}")
            self.assertEqual(failures, [])

    @unittest.skipUnless(
        os.environ.get("SKILLFORGE_RUN_EXTERNAL_HARNESSES") == "1"
        and shutil.which("claude"),
        "set SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 with the Claude CLI installed",
    )
    def test_claude_cli_validates_every_generated_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            failures = []
            for label, target in (
                ("marketplace", root / ".claude-plugin" / "marketplace.json"),
                ("repository skills", root / ".claude" / "skills"),
            ):
                checked = subprocess.run(
                    ["claude", "plugin", "validate", "--strict", str(target)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if checked.returncode:
                    failures.append(f"{label}:\n{checked.stdout}{checked.stderr}")
            for manifest in sorted((root / "dist").rglob(".claude-plugin/plugin.json")):
                pack = manifest.parent.parent
                completed = subprocess.run(
                    ["claude", "plugin", "validate", "--strict", str(pack)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if completed.returncode:
                    failures.append(
                        f"{pack.name}:\n{completed.stdout}{completed.stderr}")
            self.assertEqual(failures, [])

    @unittest.skipUnless(
        os.environ.get("SKILLFORGE_RUN_EXTERNAL_HARNESSES") == "1"
        and shutil.which("claude"),
        "set SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 with the Claude CLI installed",
    )
    def test_claude_cli_installs_example_personas_and_verticals_from_local_marketplace(
            self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            root = copy_project(temporary_path)
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            selections = (
                ("project-manager", (
                    "project-manager-pack",
                    "vertical-project-delivery-project-manager",
                ), (
                    "pm-build-report",
                    "pm-handle-customer-data",
                    "pm-plan-project-delivery",
                    "pm-report-project-status",
                    "pm-start-here",
                )),
                ("engineer", (
                    "engineer-pack",
                    "vertical-software-engineering-engineer",
                ), (
                    "eng-build-report",
                    "eng-design-technical-change",
                    "eng-handle-customer-data",
                    "eng-query-warehouse",
                    "eng-review-code-change",
                    "eng-start-here",
                )),
            )
            for label, plugins, expected_skills in selections:
                config_dir = temporary_path / f"claude-config-{label}"
                config_dir.mkdir()
                environment = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}

                marketplace = subprocess.run(
                    ["claude", "plugin", "marketplace", "add", str(root),
                     "--scope", "user"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=environment,
                )
                self.assertEqual(
                    marketplace.returncode, 0,
                    marketplace.stdout + marketplace.stderr)

                for plugin in plugins:
                    installed = subprocess.run(
                        ["claude", "plugin", "install", f"{plugin}@project",
                         "--scope", "user", "--json"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        env=environment,
                    )
                    self.assertEqual(
                        installed.returncode, 0,
                        installed.stdout + installed.stderr)

                listed = subprocess.run(
                    ["claude", "plugin", "list", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=environment,
                )
                self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
                installed_ids = {entry["id"] for entry in json.loads(listed.stdout)}
                self.assertEqual(
                    installed_ids,
                    {f"{plugin}@project" for plugin in plugins},
                )

                details = []
                for plugin in plugins:
                    described = subprocess.run(
                        ["claude", "plugin", "details", f"{plugin}@project"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        env=environment,
                    )
                    self.assertEqual(
                        described.returncode, 0,
                        described.stdout + described.stderr)
                    details.append(described.stdout)
                inventory = "\n".join(details)
                for skill in expected_skills:
                    self.assertIn(skill, inventory)

    @unittest.skipUnless(
        os.environ.get("SKILLFORGE_RUN_EXTERNAL_HARNESSES") == "1"
        and shutil.which("codex"),
        "set SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 with the Codex CLI installed",
    )
    def test_codex_cli_installs_example_personas_and_verticals_from_local_marketplace(
            self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            root = copy_project(temporary_path)
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            selections = (
                ("project-manager", (
                    "project-manager-pack",
                    "vertical-project-delivery-project-manager",
                )),
                ("engineer", (
                    "engineer-pack",
                    "vertical-software-engineering-engineer",
                )),
            )
            for label, plugins in selections:
                codex_home = temporary_path / f"codex-home-{label}"
                codex_home.mkdir()
                environment = {**os.environ, "CODEX_HOME": str(codex_home)}

                marketplace = subprocess.run(
                    ["codex", "plugin", "marketplace", "add", str(root), "--json"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=environment,
                )
                self.assertEqual(
                    marketplace.returncode, 0,
                    marketplace.stdout + marketplace.stderr)

                for plugin in plugins:
                    installed = subprocess.run(
                        ["codex", "plugin", "add", f"{plugin}@project", "--json"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        env=environment,
                    )
                    self.assertEqual(
                        installed.returncode, 0,
                        installed.stdout + installed.stderr)

                listed = subprocess.run(
                    ["codex", "plugin", "list"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=environment,
                )
                self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
                for plugin in plugins:
                    self.assertIn(plugin, listed.stdout)

    @unittest.skipUnless(
        os.environ.get("SKILLFORGE_RUN_EXTERNAL_HARNESSES") == "1"
        and shutil.which("codex"),
        "set SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 with the Codex CLI installed",
    )
    def test_codex_app_server_accepts_generated_agent_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            root = copy_project(temporary_path)
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            codex_home = temporary_path / "codex-home"
            installed = install.install_codex_agents(
                [root / "dist" / "engineer-pack"],
                agents_dir=codex_home / "agents",
                config_path=codex_home / "config.toml",
            )
            self.assertEqual(installed["agents_installed"], 1)

            checked = subprocess.run(
                [
                    shutil.which("codex"), "app-server",
                ],
                input="",
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "CODEX_HOME": str(codex_home)},
            )
            self.assertEqual(
                checked.returncode, 0, checked.stdout + checked.stderr)

    @unittest.skipUnless(
        os.environ.get("SKILLFORGE_RUN_EXTERNAL_HARNESSES") == "1"
        and shutil.which("kiro-cli"),
        "set SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 with Kiro CLI installed",
    )
    def test_kiro_cli_validates_generated_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = copy_project(Path(temporary))
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            failures = []
            for path in sorted((root / "dist").glob("*/agents/kiro/*.json")):
                checked = subprocess.run(
                    ["kiro-cli", "agent", "validate", "--path", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=root,
                )
                if checked.returncode:
                    failures.append(
                        f"{path.relative_to(root)}:\n"
                        f"{checked.stdout}{checked.stderr}")
            self.assertEqual(failures, [])

    @unittest.skipUnless(
        os.environ.get("SKILLFORGE_RUN_EXTERNAL_HARNESSES") == "1"
        and shutil.which("claude")
        and shutil.which("codex"),
        "set SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 with Claude and Codex installed",
    )
    def test_recorded_update_installs_and_refreshes_all_harnesses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            root = copy_project(temporary_path)
            result, _, error = build_all(root)
            self.assertEqual(result, 0, error)
            claude_config = temporary_path / "claude-config"
            codex_home = temporary_path / "codex-home"
            kiro_skills = temporary_path / "kiro" / "skills"
            kiro_agents = temporary_path / "kiro" / "agents"
            kiro_mcp = temporary_path / "kiro" / "settings" / "mcp.json"
            claude_config.mkdir()
            codex_home.mkdir()
            environment = {
                "CLAUDE_CONFIG_DIR": str(claude_config),
                "CODEX_HOME": str(codex_home),
                "KIRO_SKILLS_DIR": str(kiro_skills),
                "KIRO_AGENTS_DIR": str(kiro_agents),
                "KIRO_MCP_CONFIG": str(kiro_mcp),
            }

            output = StringIO()
            errors = StringIO()
            with patch.dict(os.environ, environment), \
                    redirect_stdout(output), redirect_stderr(errors):
                installed = install.main([
                    "--root", str(root),
                    "--persona", "project-manager",
                    "--vertical", "project-delivery",
                    "--host", "all",
                    "--copy",
                    "--marketplace", "project",
                ])
                first_update = updater.main(["--root", str(root)])
                second_update = updater.main(["--root", str(root)])

            self.assertEqual(installed, 0)
            self.assertEqual(first_update, 0)
            self.assertEqual(
                second_update, 0, output.getvalue() + errors.getvalue())

            claude = subprocess.run(
                ["claude", "plugin", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, **environment},
            )
            self.assertEqual(claude.returncode, 0, claude.stdout + claude.stderr)
            claude_ids = {entry["id"] for entry in json.loads(claude.stdout)}
            self.assertEqual(claude_ids, {
                "project-manager-pack@project",
                "vertical-project-delivery-project-manager@project",
            })

            codex = subprocess.run(
                ["codex", "plugin", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, **environment},
            )
            self.assertEqual(codex.returncode, 0, codex.stdout + codex.stderr)
            codex_ids = {
                entry["pluginId"]
                for entry in json.loads(codex.stdout)["installed"]
            }
            self.assertEqual(codex_ids, {
                "project-manager-pack@project",
                "vertical-project-delivery-project-manager@project",
            })
            self.assertEqual(len(list(kiro_skills.iterdir())), 5)
            self.assertEqual(
                {path.name for path in kiro_agents.glob("*.json")},
                {"pm-project-manager.json"},
            )


if __name__ == "__main__":
    unittest.main()
