"""Rebuild and reapply the installation recorded by `skillforge install`.

Run this after updating the repository:

    git pull --ff-only
    python3 -m skillforge update

Or use `scripts/update.sh`, which performs both commands.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from . import build, install, model, state, validate


def _native_commands(receipt: state.InstallReceipt, packs: list[Path]) -> list[str]:
    if receipt.host != "all":
        return []
    names = [pack.name for pack in packs]
    commands = [
        f"claude plugin marketplace update {receipt.marketplace}",
        *(f"claude plugin update {name}@{receipt.marketplace}" for name in names),
        f"codex plugin marketplace upgrade {receipt.marketplace}",
        *(f"codex plugin add {name}@{receipt.marketplace}" for name in names),
    ]
    return commands


def _run(command: list[str], root: Path) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise model.ModelError(f"could not run {' '.join(command)}: {exc}")
    if completed.returncode:
        detail = (completed.stdout + completed.stderr).strip()
        raise model.ModelError(
            f"{' '.join(command)} failed"
            + (f": {detail}" if detail else ""))
    return completed.stdout


def _run_json(command: list[str], root: Path) -> object:
    output = _run(command, root)
    try:
        return json.loads(output)
    except ValueError as exc:
        raise model.ModelError(
            f"{' '.join(command)} returned invalid JSON: {exc}")


def _update_claude(root: Path, receipt: state.InstallReceipt,
                   packs: list[Path]) -> str:
    claude = shutil.which("claude")
    if not claude:
        return "Claude Code skipped: `claude` is not installed"

    marketplaces = _run_json(
        [claude, "plugin", "marketplace", "list", "--json"], root)
    names = {
        entry.get("name")
        for entry in marketplaces
        if isinstance(entry, dict)
    } if isinstance(marketplaces, list) else set()
    if receipt.marketplace in names:
        _run([claude, "plugin", "marketplace", "update", receipt.marketplace], root)
    else:
        _run([
            claude, "plugin", "marketplace", "add", str(root),
            "--scope", "user",
        ], root)

    listed = _run_json([claude, "plugin", "list", "--json"], root)
    scopes = {
        entry.get("id"): entry.get("scope") or "user"
        for entry in listed
        if isinstance(entry, dict)
    } if isinstance(listed, list) else {}
    for pack in packs:
        plugin_id = f"{pack.name}@{receipt.marketplace}"
        if plugin_id in scopes:
            command = [
                claude, "plugin", "update", plugin_id,
                "--scope", scopes[plugin_id], "--json",
            ]
        else:
            command = [
                claude, "plugin", "install", plugin_id,
                "--scope", "user", "--json",
            ]
        _run(command, root)
    return f"Claude Code refreshed {len(packs)} plugin(s)"


def _update_codex(root: Path, receipt: state.InstallReceipt,
                  packs: list[Path]) -> str:
    codex = shutil.which("codex")
    if not codex:
        return "Codex skipped: `codex` is not installed"

    marketplaces = _run_json(
        [codex, "plugin", "marketplace", "list", "--json"], root)
    entries = marketplaces.get("marketplaces", []) \
        if isinstance(marketplaces, dict) else []
    configured = {
        entry.get("name"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    marketplace = configured.get(receipt.marketplace)
    if marketplace is not None:
        source = marketplace.get("marketplaceSource")
        source_type = source.get("sourceType") \
            if isinstance(source, dict) else None
        if source_type != "local":
            _run([
                codex, "plugin", "marketplace", "upgrade",
                receipt.marketplace, "--json",
            ], root)
    else:
        _run([
            codex, "plugin", "marketplace", "add", str(root), "--json",
        ], root)

    # `plugin add` is idempotent in Codex and refreshes the installed cache from the current
    # marketplace snapshot; there is no separate `plugin update` subcommand.
    for pack in packs:
        _run([
            codex, "plugin", "add",
            f"{pack.name}@{receipt.marketplace}", "--json",
        ], root)
    return f"Codex refreshed {len(packs)} plugin(s)"


def _print_selection(receipt_file: Path, receipt: state.InstallReceipt,
                     packs: list[Path]) -> None:
    print(f"Receipt:     {receipt_file}")
    print(f"Persona:     {receipt.persona}")
    print(f"Verticals:   {', '.join(receipt.verticals) if receipt.verticals else '-'}")
    print(f"Packs:       {', '.join(pack.name for pack in packs)}")
    print(f"Install:     {receipt.install_mode}")
    print(f"Kiro skills: {receipt.kiro_skills_dir}")
    print(f"Kiro MCP:    {receipt.kiro_mcp_config}")
    print(f"Version:     {receipt.installed_version}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--state",
                    help="installation receipt path; defaults to .skillforge/install.json")
    ap.add_argument("--check", action="store_true",
                    help="show the recorded selection without building or installing")
    ap.add_argument("--no-native", action="store_true",
                    help="print Claude Code / Codex refresh commands instead of running them")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    receipt_file = state.receipt_path(root, args.state)
    prior_root = model.ROOT
    model.ROOT = root
    try:
        receipt = state.load(receipt_file)
        persona = model.load_persona(receipt.persona, root)
        vertical_ids = install.resolve_vertical_ids(persona, receipt.verticals, root)
        packs = install.selected_pack_paths(
            root, receipt.out, persona, vertical_ids, require_built=False)

        if args.check:
            _print_selection(receipt_file, receipt, packs)
            return 0

        print("Checking source before rebuilding...")
        if validate.main(["--root", str(root), "--out", receipt.out, "--fast"]):
            print("✗ update stopped before changing the built packs", file=sys.stderr)
            return 1

        print("\nRebuilding every persona and vertical...")
        if build.main([
            "--root", str(root),
            "--out", receipt.out,
            "--all",
            "--vertical", "all",
        ]):
            print("✗ update stopped because the build failed", file=sys.stderr)
            return 1

        print("\nValidating the rebuilt distribution...")
        if validate.main(["--root", str(root), "--out", receipt.out]):
            print("✗ update stopped because the rebuilt packs failed validation",
                  file=sys.stderr)
            return 1

        packs = install.selected_pack_paths(root, receipt.out, persona, vertical_ids)
        result = install.install_kiro(
            packs,
            symlink=receipt.install_mode == "symlink",
            skills_dir=Path(receipt.kiro_skills_dir),
            mcp_config=Path(receipt.kiro_mcp_config),
        )
        updated = replace(receipt, installed_version=state.project_version(root))
        state.write(receipt_file, updated)

        print(
            f"\n✓ Kiro updated: {result['linked']} skill(s) installed from "
            f"{', '.join(result['packs'])}; removed {result['removed']} stale skill(s)")
        print(f"  receipt refreshed: {receipt_file}")

        commands = _native_commands(updated, packs)
        if commands:
            if args.no_native:
                print("\nClaude Code / Codex cache refresh:")
                for command in commands:
                    print(f"  {command}")
            else:
                print(f"  {_update_claude(root, updated, packs)}")
                print(f"  {_update_codex(root, updated, packs)}")
            print("  Restart each harness after its update completes.")
        return 0
    except model.ModelError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    finally:
        model.ROOT = prior_root


if __name__ == "__main__":
    raise SystemExit(main())
