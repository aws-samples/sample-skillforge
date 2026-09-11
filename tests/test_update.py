from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skillforge import install, model, state
from skillforge import update as updater

from project_support import REPO_ROOT, build_all, copy_project


class UpdateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = copy_project(self.root)
        built, _, build_error = build_all(self.project)
        self.assertEqual(built, 0, build_error)
        self.skills_dir = self.root / "kiro" / "skills"
        self.agents_dir = self.root / "kiro" / "agents"
        self.mcp_config = self.root / "kiro" / "settings" / "mcp.json"
        self.codex_home = self.root / "codex"
        self.environment = patch.dict(os.environ, {
            "KIRO_SKILLS_DIR": str(self.skills_dir),
            "KIRO_AGENTS_DIR": str(self.agents_dir),
            "KIRO_MCP_CONFIG": str(self.mcp_config),
            "CODEX_HOME": str(self.codex_home),
        })
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def install(self, *extra: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = install.main([
                "--root", str(self.project),
                "--persona", "engineer",
                "--vertical", "software-engineering",
                *extra,
            ])
        return result, stdout.getvalue(), stderr.getvalue()

    def update(self, *extra: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = updater.main(["--root", str(self.project), *extra])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_install_records_non_secret_selection_as_json(self) -> None:
        result, output, error = self.install(
            "--copy",
            "--host", "all",
            "--marketplace", "company-skills",
        )

        self.assertEqual(result, 0, error)
        receipt_file = self.project / ".skillforge" / "install.json"
        data = json.loads(receipt_file.read_text(encoding="utf-8"))
        self.assertEqual(data, {
            "schema_version": 2,
            "persona": "engineer",
            "verticals": ["software-engineering"],
            "host": "all",
            "install_mode": "copy",
            "out": "dist",
            "marketplace": "company-skills",
            "installed_version": "0.2.0",
            "kiro": {
                "skills_dir": str(self.skills_dir.resolve()),
                "agents_dir": str(self.agents_dir.resolve()),
                "mcp_config": str(self.mcp_config.resolve()),
            },
            "codex": {
                "agents_dir": str((self.codex_home / "agents").resolve()),
                "config": str((self.codex_home / "config.toml").resolve()),
            },
        })
        self.assertIn(str(state.receipt_path(self.project)), output)
        self.assertNotIn("token", receipt_file.read_text(encoding="utf-8").lower())
        self.assertNotIn("secret", receipt_file.read_text(encoding="utf-8").lower())

    def test_update_rebuilds_and_replays_copy_mode_selection(self) -> None:
        installed, _, install_error = self.install("--copy")
        self.assertEqual(installed, 0, install_error)
        copied = self.skills_dir / "eng-review-code-change" / "SKILL.md"
        self.assertNotIn("UPDATE-RECEIPT-CHECK", copied.read_text(encoding="utf-8"))

        source = self.project / "skills" / "review-code-change" / "SKILL.md"
        source.write_text(
            source.read_text(encoding="utf-8") + "\nUPDATE-RECEIPT-CHECK\n",
            encoding="utf-8",
        )

        result, output, error = self.update("--no-native")

        self.assertEqual(result, 0, error)
        self.assertIn("UPDATE-RECEIPT-CHECK", copied.read_text(encoding="utf-8"))
        self.assertIn("Kiro updated", output)
        receipt = state.load(self.project / ".skillforge" / "install.json")
        self.assertEqual(receipt.install_mode, "copy")
        self.assertEqual(receipt.persona, "engineer")

    def test_check_prints_selection_without_rebuilding(self) -> None:
        installed, _, install_error = self.install("--copy")
        self.assertEqual(installed, 0, install_error)
        built_skill = (
            self.project / "dist" / "engineer-pack" / "skills"
            / "eng-build-report" / "SKILL.md"
        )
        before = built_skill.read_bytes()

        result, output, error = self.update("--check")

        self.assertEqual(result, 0, error)
        self.assertIn("Persona:     engineer", output)
        self.assertIn("software-engineering", output)
        self.assertEqual(built_skill.read_bytes(), before)

    def test_host_all_prints_exact_native_refresh_commands(self) -> None:
        installed, _, install_error = self.install(
            "--copy", "--host", "all", "--marketplace", "company-skills")
        self.assertEqual(installed, 0, install_error)

        result, output, error = self.update("--no-native")

        self.assertEqual(result, 0, error)
        for command in (
            "claude plugin marketplace update company-skills",
            "claude plugin update engineer-pack@company-skills",
            "claude plugin update vertical-software-engineering-engineer@company-skills",
            "codex plugin marketplace upgrade company-skills",
            "codex plugin add engineer-pack@company-skills",
            "codex plugin add vertical-software-engineering-engineer@company-skills",
        ):
            self.assertIn(command, output)

    def test_native_refresh_uses_installed_claude_scope_and_idempotent_codex_add(
            self) -> None:
        receipt = state.InstallReceipt(
            persona="engineer",
            verticals=("software-engineering",),
            host="all",
            install_mode="copy",
            out="dist",
            marketplace="company-skills",
            installed_version="0.2.0",
            kiro_skills_dir=str(self.skills_dir.resolve()),
            kiro_agents_dir=str(self.agents_dir.resolve()),
            kiro_mcp_config=str(self.mcp_config.resolve()),
            codex_agents_dir=str((self.codex_home / "agents").resolve()),
            codex_config=str((self.codex_home / "config.toml").resolve()),
        )
        packs = [
            self.project / "dist" / "engineer-pack",
            self.project / "dist" / "vertical-software-engineering-engineer",
        ]

        claude = r"C:\Tools\claude.cmd"
        with patch.object(updater.shutil, "which", return_value=claude), \
                patch.object(updater, "_run_json", side_effect=[
                    [{"name": "company-skills"}],
                    [{"id": "engineer-pack@company-skills", "scope": "local"}],
                ]), patch.object(updater, "_run") as run:
            message = updater._update_claude(self.project, receipt, packs)

        self.assertEqual(message, "Claude Code refreshed 2 plugin(s)")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn([
            claude, "plugin", "update", "engineer-pack@company-skills",
            "--scope", "local", "--json",
        ], commands)
        self.assertIn([
            claude, "plugin", "install",
            "vertical-software-engineering-engineer@company-skills",
            "--scope", "user", "--json",
        ], commands)

        codex = r"C:\Tools\codex.cmd"
        with patch.object(updater.shutil, "which", return_value=codex), \
                patch.object(updater, "_run_json", return_value={
                    "marketplaces": [{
                        "name": "company-skills",
                        "marketplaceSource": {"sourceType": "git"},
                    }],
                }), patch.object(updater, "_run") as run:
            message = updater._update_codex(self.project, receipt, packs)

        self.assertEqual(message, "Codex refreshed 2 plugin(s)")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn([
            codex, "plugin", "marketplace", "upgrade",
            "company-skills", "--json",
        ], commands)
        self.assertIn([
            codex, "plugin", "add", "engineer-pack@company-skills", "--json",
        ], commands)

        with patch.object(updater.shutil, "which", return_value=codex), \
                patch.object(updater, "_run_json", return_value={
                    "marketplaces": [{
                        "name": "company-skills",
                        "marketplaceSource": {"sourceType": "local"},
                    }],
                }), patch.object(updater, "_run") as run:
            message = updater._update_codex(self.project, receipt, packs)

        self.assertEqual(message, "Codex refreshed 2 plugin(s)")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertNotIn([
            codex, "plugin", "marketplace", "upgrade",
            "company-skills", "--json",
        ], commands)
        self.assertIn([
            codex, "plugin", "add", "engineer-pack@company-skills", "--json",
        ], commands)

    def test_invalid_receipt_stops_before_removing_current_skills(self) -> None:
        installed, _, install_error = self.install("--copy")
        self.assertEqual(installed, 0, install_error)
        receipt_file = self.project / ".skillforge" / "install.json"
        receipt_file.write_text("{not-json", encoding="utf-8")
        existing = self.skills_dir / "eng-start-here" / "SKILL.md"

        result, _, error = self.update()

        self.assertEqual(result, 1)
        self.assertIn("not valid readable JSON", error)
        self.assertTrue(existing.is_file())

    def test_uninstall_uses_recorded_paths_and_removes_receipt(self) -> None:
        installed, _, install_error = self.install("--copy")
        self.assertEqual(installed, 0, install_error)
        receipt_file = self.project / ".skillforge" / "install.json"

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {
            "KIRO_SKILLS_DIR": "",
            "KIRO_MCP_CONFIG": "",
        }), redirect_stdout(stdout), redirect_stderr(stderr):
            result = install.main(["--root", str(self.project), "--uninstall"])

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertFalse(receipt_file.exists())
        self.assertFalse((self.skills_dir / "eng-start-here").exists())

    def test_receipt_schema_accepts_windows_absolute_paths(self) -> None:
        receipt = state.InstallReceipt.from_dict({
            "schema_version": 2,
            "persona": "engineer",
            "verticals": ["software-engineering"],
            "host": "all",
            "install_mode": "copy",
            "out": "dist",
            "marketplace": "skillforge",
            "installed_version": "0.2.0",
            "kiro": {
                "skills_dir": r"C:\Users\Example\.kiro\skills",
                "agents_dir": r"C:\Users\Example\.kiro\agents",
                "mcp_config": r"C:\Users\Example\.kiro\settings\mcp.json",
            },
            "codex": {
                "agents_dir": r"C:\Users\Example\.codex\agents",
                "config": r"C:\Users\Example\.codex\config.toml",
            },
        }, Path("install.json"))

        self.assertEqual(receipt.install_mode, "copy")
        self.assertTrue(receipt.kiro_skills_dir.startswith("C:"))

    def test_version_one_receipt_migrates_agent_paths(self) -> None:
        receipt = state.InstallReceipt.from_dict({
            "schema_version": 1,
            "persona": "engineer",
            "verticals": ["software-engineering"],
            "host": "all",
            "install_mode": "copy",
            "out": "dist",
            "marketplace": "skillforge",
            "installed_version": "0.1.0",
            "kiro": {
                "skills_dir": str(self.skills_dir.resolve()),
                "mcp_config": str(self.mcp_config.resolve()),
            },
        }, Path("install.json"))

        self.assertEqual(receipt.schema_version, 2)
        self.assertEqual(receipt.kiro_agents_dir, str(self.agents_dir.resolve()))
        self.assertEqual(
            Path(receipt.codex_agents_dir).resolve(),
            (self.codex_home / "agents").resolve(),
        )

    def test_windows_defaults_to_copy_mode_without_a_flag(self) -> None:
        self.assertFalse(install.should_symlink(False, False, "nt"))
        self.assertTrue(install.should_symlink(False, False, "posix"))
        self.assertTrue(install.should_symlink(False, True, "nt"))
        self.assertFalse(install.should_symlink(True, False, "posix"))

    def test_update_scripts_cover_posix_and_windows(self) -> None:
        shell = (REPO_ROOT / "scripts" / "update.sh").read_text(encoding="utf-8")
        powershell = (REPO_ROOT / "scripts" / "update.ps1").read_text(encoding="utf-8")

        for text in (shell, powershell):
            self.assertIn("pull --ff-only", text)
            self.assertIn("-m skillforge update", text)
        self.assertIn("python3", shell)
        self.assertIn('cd "$repo_root"', shell)
        self.assertIn("Get-Command py", powershell)
        self.assertIn("Get-Command python3", powershell)
        self.assertIn("Set-Location $RepoRoot", powershell)

    def test_receipt_directory_is_gitignored(self) -> None:
        rules = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn(".skillforge/", rules)

    def test_ci_runs_the_contracts_on_windows_macos_and_linux(self) -> None:
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "test.yml"
        ).read_text(encoding="utf-8")

        for runner in ("windows-latest", "macos-latest", "ubuntu-latest"):
            self.assertIn(runner, workflow)
        self.assertIn("python -m skillforge eval", workflow)
        self.assertIn("python -m skillforge mutate-test", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("Parse PowerShell updater", workflow)


if __name__ == "__main__":
    unittest.main()
