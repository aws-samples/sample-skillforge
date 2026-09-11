"""Install a built pack into a host.

    python3 -m skillforge install --persona analyst
    python3 -m skillforge install --persona analyst --vertical pci-dss
    python3 -m skillforge install --persona analyst --host kiro
    python3 -m skillforge install --uninstall

Each successful install records its non-secret selection in `.skillforge/install.json`, so
`python3 -m skillforge update` can rebuild and reconcile the same persona, verticals and paths after
the repository is pulled.

Claude Code and Codex both install a marketplace straight from a git repo, so for those this prints
the two commands rather than reimplementing them — a tool that shells out to another tool's
marketplace is a tool that breaks when that marketplace changes.

Kiro has no marketplace, so it is installed here properly.

## Three rules, all learned expensively

**PERSONAS SWAP.** Installing one removes the other. Two practitioner packs at once means the
catalogue contradicts itself: the same skill name resolves to instructions written under different
rules, and which one loads is the host's choice, not yours.

**VERTICALS ADD.** Any number of vertical packs may be selected alongside the persona pack. They
are installed as one reconciled set, so switching persona removes the old persona's vertical
variants too.

**Never delete a server the user configured.** Entries this tool created are marked, and only marked
entries are removed. An entry that existed before is *adopted* — marked separately, and restored to
its original enabled state when it leaves the selected pack set or on uninstall. Conflating the two
destroys a user's config, and the print saying "your own were left alone" is worthless if it is not
true.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

from . import model, state

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


def _selected_packs(packs: Path | Iterable[Path]) -> list[Path]:
    selected = [packs] if isinstance(packs, Path) else list(packs)
    if not selected:
        raise model.ModelError("no packs selected for installation")

    seen: set[str] = set()
    for pack in selected:
        if pack.name in seen:
            raise model.ModelError(f"pack {pack.name!r} was selected more than once")
        seen.add(pack.name)
        if not (pack / "skills").is_dir():
            raise model.ModelError(
                f"{pack} has no skills/. Build the persona and its verticals before installing.")
    return selected


def _desired_mcp(packs: list[Path]) -> dict[str, dict]:
    """Merge the MCP servers shipped by the selected packs, refusing conflicting definitions."""
    desired: dict[str, dict] = {}
    owners: dict[str, str] = {}
    for pack in packs:
        src = pack / "mcp" / "kiro-mcp.json"
        if not src.is_file():
            continue
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise model.ModelError(f"{src} is not valid JSON: {exc}")
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            raise model.ModelError(f"{src} must contain an `mcpServers` object")
        for name, spec in servers.items():
            if not isinstance(spec, dict):
                raise model.ModelError(f"{src}: server {name!r} must be an object")
            if name in desired and desired[name] != spec:
                raise model.ModelError(
                    f"server {name!r} differs between packs {owners[name]!r} and {pack.name!r}")
            desired[name] = spec
            owners[name] = pack.name
    return desired


def _load_kiro_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise model.ModelError(
            f"{path} cannot be read as JSON: {exc}. It was left unchanged.")
    if not isinstance(config, dict):
        raise model.ModelError(f"{path} must contain a JSON object. It was left unchanged.")
    if "mcpServers" in config and not isinstance(config["mcpServers"], dict):
        raise model.ModelError(
            f"{path}: `mcpServers` must be an object. The file was left unchanged.")
    return config


def _restore_adopted(spec: dict) -> None:
    prior = spec.pop(PRIOR, False)
    spec.pop(ADOPTED, None)
    if prior:
        spec["disabled"] = True
    else:
        spec.pop("disabled", None)


def _validate_mcp_selection(config: dict, desired: dict[str, dict], path: Path) -> None:
    servers = config.get("mcpServers") or {}
    for name in desired:
        existing = servers.get(name)
        if existing is not None and not isinstance(existing, dict):
            raise model.ModelError(
                f"{path}: server {name!r} is not an object. It was left unchanged.")


def _reconcile_mcp(desired: dict[str, dict], config: dict | None = None,
                   path: Path | None = None) -> dict:
    """Make Skillforge-owned MCP state match `desired`, preserving user-owned entries."""
    path = path or kiro_mcp_config()
    config = _load_kiro_config(path) if config is None else config
    _validate_mcp_selection(config, desired, path)
    servers = config.get("mcpServers")
    added = adopted = deleted = restored = 0
    changed = False

    if servers is None:
        if not desired:
            return {
                "mcp_added": 0,
                "mcp_adopted": 0,
                "mcp_deleted": 0,
                "mcp_restored": 0,
            }
        servers = {}
        config["mcpServers"] = servers

    # First remove entitlements from the previous persona/vertical selection. Entries created by
    # Skillforge are deleted; user entries that were merely adopted are restored exactly.
    for name, existing in list(servers.items()):
        if name in desired or not isinstance(existing, dict):
            continue
        if existing.get(CREATED):
            del servers[name]
            deleted += 1
            changed = True
        elif existing.get(ADOPTED):
            _restore_adopted(existing)
            restored += 1
            changed = True

    for name, spec in desired.items():
        existing = servers.get(name)
        if existing is None:
            servers[name] = {**spec, CREATED: True}
            added += 1
            changed = True
        elif isinstance(existing, dict) and existing.get(CREATED):
            replacement = {**spec, CREATED: True}
            if existing != replacement:
                servers[name] = replacement
                changed = True
        elif isinstance(existing, dict) and existing.get(ADOPTED):
            continue
        elif isinstance(existing, dict):
            # Preserve every field in a user's existing server. The markers only record that it
            # overlaps this install and what enabled state must be restored when it no longer does.
            servers[name] = {
                **existing,
                ADOPTED: True,
                PRIOR: bool(existing.get("disabled", False)),
            }
            adopted += 1
            changed = True

    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {
        "mcp_added": added,
        "mcp_adopted": adopted,
        "mcp_deleted": deleted,
        "mcp_restored": restored,
    }


def install_kiro(packs: Path | Iterable[Path], symlink: bool | None = None,
                 skills_dir: Path | None = None,
                 mcp_config: Path | None = None) -> dict:
    """Install one persona pack plus zero or more vertical packs as a reconciled set."""
    if symlink is None:
        symlink = os.name != "nt"
    selected = _selected_packs(packs)
    desired_mcp = _desired_mcp(selected)
    skills_dir = skills_dir or kiro_skills_dir()
    mcp_config = mcp_config or kiro_mcp_config()
    config = _load_kiro_config(mcp_config)
    _validate_mcp_selection(config, desired_mcp, mcp_config)

    # Detect a broken build before removing the currently installed set.
    targets: dict[str, Path] = {}
    for pack in selected:
        for skill in sorted((pack / "skills").iterdir()):
            if not (skill / "SKILL.md").is_file():
                continue
            if skill.name in targets:
                raise model.ModelError(
                    f"skill {skill.name!r} appears in both {targets[skill.name].parent.parent.name!r} "
                    f"and {pack.name!r}; installing either would hide the other")
            targets[skill.name] = skill

    skills_dir.mkdir(parents=True, exist_ok=True)
    removed = remove_ours(skills_dir)

    # Marks each pack as ours so uninstall can tell our symlinks from the user's.
    for pack in selected:
        (pack / ".skillforge-pack").write_text(pack.name + "\n", encoding="utf-8")

    linked = skipped = 0
    for name, skill in sorted(targets.items()):
        target = skills_dir / name
        if target.exists() or target.is_symlink():
            skipped += 1
            continue              # a directory or symlink the user owns; never overwrite it
        if symlink:
            target.symlink_to(skill.resolve())
        else:
            shutil.copytree(skill, target)
            (target / ".skillforge").write_text(
                skill.parent.parent.name + "\n", encoding="utf-8")
        linked += 1

    mcp = _reconcile_mcp(desired_mcp, config, mcp_config)
    return {
        "packs": [p.name for p in selected],
        "linked": linked,
        "skipped": skipped,
        "removed": removed,
        **mcp,
    }


def uninstall_kiro(skills_dir: Path | None = None,
                   mcp_config: Path | None = None) -> dict:
    removed = remove_ours(skills_dir or kiro_skills_dir())
    mcp = _reconcile_mcp({}, path=mcp_config or kiro_mcp_config())
    return {"removed": removed, **mcp}


def resolve_vertical_ids(persona: model.Persona, requested: Iterable[str],
                         root: Path) -> list[str]:
    values = list(requested)
    if "all" in values:
        if len(values) != 1:
            raise model.ModelError("use `--vertical all` by itself")
        return [
            vid
            for vid in model.all_vertical_ids(root)
            if persona.id in model.load_vertical(vid, root).personas
        ]

    vertical_ids = list(dict.fromkeys(values))
    for vid in vertical_ids:
        vertical = model.load_vertical(vid, root)
        if persona.id not in vertical.personas:
            raise model.ModelError(
                f"vertical {vid!r} is not declared for persona {persona.id!r}")
    return vertical_ids


def selected_pack_paths(root: Path, out: str | Path, persona: model.Persona,
                        vertical_ids: Iterable[str],
                        require_built: bool = True) -> list[Path]:
    output = Path(out)
    if not output.is_absolute():
        output = root / output
    packs = [output / persona.pack_name]
    packs.extend(output / f"vertical-{vid}-{persona.id}" for vid in vertical_ids)
    if require_built:
        missing = [str(pack) for pack in packs if not (pack / "skills").is_dir()]
        if missing:
            raise model.ModelError(
                f"built pack(s) missing skills/: {missing}. Run `python3 -m skillforge build "
                f"--all --vertical all` first.")
    return packs


def should_symlink(force_copy: bool, force_symlink: bool,
                   platform_name: str | None = None) -> bool:
    platform_name = os.name if platform_name is None else platform_name
    return force_symlink or (not force_copy and platform_name != "nt")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--persona", help="persona id whose pack to install")
    ap.add_argument("--vertical", action="append",
                    help="vertical id to install alongside the persona; repeatable, or 'all'")
    ap.add_argument("--host", choices=("kiro", "all"), default="kiro")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--copy", action="store_true",
                      help="copy skills instead of symlinking them")
    mode.add_argument("--symlink", action="store_true",
                      help="force symlinks (Windows normally defaults to copies)")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--state",
                    help="installation receipt path; defaults to .skillforge/install.json")
    ap.add_argument("--marketplace",
                    help="Claude Code / Codex marketplace name; defaults to the repository name")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    model.ROOT = root
    state_file = state.receipt_path(root, args.state)

    if args.uninstall:
        try:
            receipt = state.load(state_file) if state_file.is_file() else None
            skills_dir = Path(receipt.kiro_skills_dir) if receipt else kiro_skills_dir()
            mcp_config = Path(receipt.kiro_mcp_config) if receipt else kiro_mcp_config()
            r = uninstall_kiro(skills_dir, mcp_config)
        except model.ModelError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        removed_receipt = state.remove(state_file)
        print(f"Kiro: removed {r['removed']} skill(s), {r['mcp_deleted']} server(s) this tool "
              f"created")
        if r["mcp_restored"]:
            print(f"      restored {r['mcp_restored']} of your own server(s) it had adopted, with "
                  f"their original enabled state")
        if removed_receipt:
            print(f"      removed installation receipt {state_file}")
        print("Claude Code / Codex: `claude plugin uninstall <pack>` / "
              "`codex plugin remove <pack>@<marketplace>`")
        return 0

    if not args.persona:
        print("give --persona <id> (or --uninstall)", file=sys.stderr)
        return 1
    try:
        use_symlink = should_symlink(args.copy, args.symlink)
        persona = model.load_persona(args.persona, root)
        vertical_ids = resolve_vertical_ids(persona, args.vertical or (), root)
        packs = selected_pack_paths(root, args.out, persona, vertical_ids)
        skills_dir = kiro_skills_dir().resolve()
        mcp_config = kiro_mcp_config().resolve()
        r = install_kiro(
            packs,
            symlink=use_symlink,
            skills_dir=skills_dir,
            mcp_config=mcp_config,
        )
        marketplace = args.marketplace or root.name
        receipt = state.InstallReceipt(
            persona=persona.id,
            verticals=tuple(vertical_ids),
            host=args.host,
            install_mode="symlink" if use_symlink else "copy",
            out=args.out,
            marketplace=marketplace,
            installed_version=state.project_version(root),
            kiro_skills_dir=str(skills_dir),
            kiro_mcp_config=str(mcp_config),
        )
        state.write(state_file, receipt)
    except model.ModelError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    print(f"Kiro: {r['linked']} skill(s) {'linked' if use_symlink else 'copied'} into "
          f"{skills_dir} from {', '.join(r['packs'])}")
    if r["skipped"]:
        print(f"      skipped {r['skipped']} user-owned path(s) with colliding skill names")
    if r["removed"]:
        print(f"      removed {r['removed']} skill(s) from the previous selection — personas swap, "
              f"while the selected verticals install alongside the new persona")
    if r["mcp_added"] or r["mcp_adopted"]:
        print(f"      mcp: added {r['mcp_added']}, adopted {r['mcp_adopted']} of your own "
              f"(restored on uninstall, not deleted)")
    if r["mcp_deleted"] or r["mcp_restored"]:
        print(f"      mcp: removed {r['mcp_deleted']} stale Skillforge server(s), restored "
              f"{r['mcp_restored']} of your own")
    print("      opt-in servers arrive DISABLED — enable the ones you want in Kiro's MCP panel")
    print("      restart kiro-cli and the Kiro IDE to pick it up")
    print(f"      recorded selection in {state_file}")

    print(f"\nClaude Code and Codex install from the repo itself — push it, then:")
    print("  claude plugin marketplace add <owner>/<repo>")
    for pack in packs:
        print(f"  claude plugin install {pack.name}@{marketplace}")
    print("  codex  plugin marketplace add <owner>/<repo>")
    for pack in packs:
        print(f"  codex plugin add {pack.name}@{marketplace}")

    quick = [(pack, len(list((pack / "quick").glob("*.quick"))))
             for pack in packs if (pack / "quick").is_dir()]
    if quick:
        print(f"\nAmazon Quick: {sum(n for _, n in quick)} variant(s) across "
              f"{', '.join(str(pack / 'quick') for pack, _ in quick)}. Import the folders by hand, "
              f"then QUIT AND RELAUNCH Quick — it reads skills only at launch, so until you do the "
              f"skills are installed and dead.")
    return 0
