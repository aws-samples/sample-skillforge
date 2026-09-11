"""Install a built pack into a host.

    python3 -m skillforge install --persona analyst
    python3 -m skillforge install --persona analyst --host kiro
    python3 -m skillforge install --uninstall

Claude Code and Codex both install a marketplace straight from a git repo, so for those this prints
the two commands rather than reimplementing them — a tool that shells out to another tool's
marketplace is a tool that breaks when that marketplace changes.

Kiro has no marketplace, so it is installed here properly.

## Two rules, both learned expensively

**PERSONAS SWAP.** Installing one removes the other. Two practitioner packs at once means the
catalogue contradicts itself: the same skill name resolves to instructions written under different
rules, and which one loads is the host's choice, not yours.

**Never delete a server the user configured.** Entries this tool created are marked, and only marked
entries are removed. An entry that existed before is *adopted* — marked separately, and restored to
its original enabled state on uninstall. Conflating the two destroys a user's config, and the print
saying "your own were left alone" is worthless if it is not true.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import model

#: Marks an entry this tool CREATED. Only these may be deleted.
CREATED = "x-created-by-skillforge"
#: Marks an entry that already existed and was adopted. These are restored, never deleted.
ADOPTED = "x-adopted-by-skillforge"
#: The adopted entry's original `disabled` state, so restore is exact rather than a guess.
PRIOR = "x-prior-disabled-skillforge"


def kiro_skills_dir() -> Path:
    return Path(os.environ.get("KIRO_SKILLS_DIR") or Path.home() / ".kiro" / "skills")


def kiro_mcp_config() -> Path:
    return Path(os.environ.get("KIRO_MCP_CONFIG")
                or Path.home() / ".kiro" / "settings" / "mcp.json")


def kiro_agents_dir() -> Path:
    return Path(os.environ.get("KIRO_AGENTS_DIR") or Path.home() / ".kiro" / "agents")


def remove_ours(directory: Path) -> int:
    """Remove only the symlinks/copies this tool created. Returns how many."""
    if not directory.is_dir():
        return 0
    removed = 0
    for entry in sorted(directory.iterdir()):
        # A symlink points at dist/<pack>/skills/<skill>, and the marker sits at dist/<pack>/ —
        # two levels UP. Checking the link target itself found nothing, so the persona swap
        # silently did not happen and both packs stayed installed, which is the one state that is
        # always wrong. Walk the parents instead of assuming a depth.
        if entry.is_symlink():
            target = entry.resolve()
            if any((parent / ".skillforge-pack").is_file() for parent in target.parents):
                entry.unlink()
                removed += 1
        elif (entry / ".skillforge").is_file():
            shutil.rmtree(entry)
            removed += 1
    return removed


def install_kiro(pack: Path, symlink: bool = True) -> dict:
    """Skills, MCP config and the agent's launch block. Returns a summary."""
    skills_dir = kiro_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    removed = remove_ours(skills_dir)

    # Marks the pack as ours so uninstall can tell our symlinks from the user's.
    (pack / ".skillforge-pack").write_text(pack.name + "\n", encoding="utf-8")

    linked = 0
    for skill in sorted((pack / "skills").iterdir()):
        if not (skill / "SKILL.md").is_file():
            continue
        target = skills_dir / skill.name
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                target.unlink()
            else:
                continue          # a real directory the user owns; never overwrite it
        if symlink:
            target.symlink_to(skill.resolve())
        else:
            shutil.copytree(skill, target)
            (target / ".skillforge").write_text(pack.name + "\n", encoding="utf-8")
        linked += 1

    # MCP: merge, never replace. Kiro's per-server `disabled` flag is the finest control of the
    # four hosts, which is why opt-in servers can ship switched off rather than omitted.
    added = adopted = 0
    src = pack / "mcp" / "kiro-mcp.json"
    if src.is_file():
        config_path = kiro_mcp_config()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {}
        servers = config.setdefault("mcpServers", {})
        for name, spec in json.loads(src.read_text(encoding="utf-8"))["mcpServers"].items():
            existing = servers.get(name)
            if existing is None:
                servers[name] = {**spec, CREATED: True}
                added += 1
            elif existing.get(CREATED):
                servers[name] = {**spec, CREATED: True}
            elif not existing.get(ADOPTED):
                servers[name] = {**existing, ADOPTED: True,
                                 PRIOR: bool(existing.get("disabled", False))}
                adopted += 1
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    return {"linked": linked, "removed": removed, "mcp_added": added, "mcp_adopted": adopted}


def uninstall_kiro() -> dict:
    removed = remove_ours(kiro_skills_dir())
    deleted = restored = 0
    path = kiro_mcp_config()
    if path.is_file():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            config = {}
        servers = config.get("mcpServers") or {}
        for name in [n for n, s in servers.items() if isinstance(s, dict) and s.get(CREATED)]:
            del servers[name]
            deleted += 1
        for name, spec in servers.items():
            if isinstance(spec, dict) and spec.get(ADOPTED):
                prior = spec.pop(PRIOR, False)
                spec.pop(ADOPTED, None)
                if prior:
                    spec["disabled"] = True
                else:
                    spec.pop("disabled", None)
                restored += 1
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {"removed": removed, "mcp_deleted": deleted, "mcp_restored": restored}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--persona", help="persona id whose pack to install")
    ap.add_argument("--host", choices=("kiro", "all"), default="all")
    ap.add_argument("--copy", action="store_true",
                    help="copy instead of symlink (Windows without Developer Mode)")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    model.ROOT = root

    if args.uninstall:
        r = uninstall_kiro()
        print(f"Kiro: removed {r['removed']} skill(s), {r['mcp_deleted']} server(s) this tool "
              f"created")
        if r["mcp_restored"]:
            print(f"      restored {r['mcp_restored']} of your own server(s) it had adopted, with "
                  f"their original enabled state")
        print("Claude Code / Codex: `claude plugin uninstall <pack>` / "
              "`codex plugin remove <pack>@<marketplace>`")
        return 0

    if not args.persona:
        print("give --persona <id> (or --uninstall)", file=sys.stderr)
        return 1
    try:
        persona = model.load_persona(args.persona, root)
    except model.ModelError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    pack = root / args.out / persona.pack_name
    if not (pack / "skills").is_dir():
        print(f"✗ {pack} has no skills/. Run `python3 -m skillforge build --persona "
              f"{args.persona}` first — this installs what was BUILT, which only exists after a "
              f"build.", file=sys.stderr)
        return 1

    r = install_kiro(pack, symlink=not args.copy)
    print(f"Kiro: {r['linked']} skill(s) {'copied' if args.copy else 'linked'} into "
          f"{kiro_skills_dir()}")
    if r["removed"]:
        print(f"      removed {r['removed']} skill(s) from the other persona — personas swap, so "
              f"only one may be installed at a time")
    if r["mcp_added"] or r["mcp_adopted"]:
        print(f"      mcp: added {r['mcp_added']}, adopted {r['mcp_adopted']} of your own "
              f"(restored on uninstall, not deleted)")
    print("      opt-in servers arrive DISABLED — enable the ones you want in Kiro's MCP panel")
    print("      restart kiro-cli and the Kiro IDE to pick it up")

    print(f"\nClaude Code and Codex install from the repo itself — push it, then:")
    print(f"  claude plugin marketplace add <owner>/<repo>  &&  "
          f"claude plugin install {persona.pack_name}")
    print(f"  codex  plugin marketplace add <owner>/<repo>  &&  "
          f"codex plugin add {persona.pack_name}@<repo>")
    if (pack / "quick").is_dir():
        n = len(list((pack / "quick").glob("*.quick")))
        print(f"\nAmazon Quick: {n} variant(s) in {pack / 'quick'}. Import the folder by hand, "
              f"then QUIT AND RELAUNCH Quick — it reads skills only at launch, so until you do the "
              f"skill is installed and dead.")
    return 0
