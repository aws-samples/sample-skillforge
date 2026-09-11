"""Build one pack per persona, and one per (vertical, persona) pair.

    python3 -m skillforge build --all
    python3 -m skillforge build --persona analyst
    python3 -m skillforge build --all --vertical pci-dss

## What a pack contains, and why each host gets a different shape

The four supported hosts do not agree on anything except the skills directory, so one source has to
emit five shapes. This is the whole reason the tool exists.

    skills/<prefix><name>/           every host reads this. Flat, direct children only.
    .claude-plugin/plugin.json       Claude Code plugin manifest
    .mcp.json                        Claude Code: EAGER servers, plugin-level
    mcp-plugins/mcp-<group>/         Claude Code: one companion plugin per opt-in group
    mcp/kiro-mcp.json                Kiro: every entitled server, opt-in ones `disabled: true`
    mcp/<group>.json                 plain shape, for any other tool
    agents/                          per-host tool grants, generated
    quick/<skill>.quick              Amazon Quick: hoisted frontmatter

A `mcpServers` entry in a Claude Code plugin manifest is PLUGIN-LEVEL: everything reachable from it
connects at session start and stays connected regardless of which skill runs. There is no per-skill
lifecycle. That is why `loading` exists and why the eager group must be kept to servers worth
having connected while unused.

## Name prefixing

Every skill is prefixed with the persona's `prefix`, so two packs can be installed side by side
without colliding and a user can see which pack a skill came from. A skill whose source name
already starts with the prefix is NOT double-prefixed — `analyst-report` under prefix `analyst-`
would otherwise build as `analyst-analyst-report`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import agents as agent_build
from . import model, resolve

BANNER = """> Generated file — do not edit.
> Persona: {persona} ({display})
> Pack:    {pack} v{version}
> Source:  skill `{skill}`{commit}
> Edit the source skill, not this copy — this one is overwritten on every build.

"""

CONSTRAINT_TITLE = "## Boundaries that apply to this skill"


def frontmatter(text: str) -> tuple[dict, str]:
    """A deliberately small frontmatter reader: flat keys, plus one level under `metadata`.

    Not a YAML parser. It accepts the subset where a real parser and this reader agree, and a
    validator rejects anything outside it — which is safer than a permissive reader that silently
    disagrees with the host about what a skill is called.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end], text[end + 4:].lstrip("\n")
    data: dict = {}
    section = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indented = line[:1].isspace()
        key, _, value = line.strip().partition(":")
        value = value.strip().strip('"').strip("'")
        if indented and section is not None:
            data.setdefault(section, {})[key.strip()] = value
        elif not value:
            section = key.strip()
            data.setdefault(section, {})
        else:
            section = None
            data[key.strip()] = value
    return data, body


def prefixed(name: str, prefix: str) -> str:
    return name if name.startswith(prefix) else f"{prefix}{name}"


def rewrite_names(text: str, mapping: dict[str, str]) -> str:
    """Rewrite backticked skill references to their prefixed names.

    Longest first: rewriting `report` before `report-review` would corrupt the longer name.
    """
    for src in sorted(mapping, key=len, reverse=True):
        text = re.sub(rf"`{re.escape(src)}`", f"`{mapping[src]}`", text)
    return text


def commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return f" @ {out.stdout.strip()}" if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def build_skill(src: Path, dest: Path, persona: model.Persona, pack_name: str, version: str,
                mapping: dict[str, str], root: Path) -> list[str]:
    """Write one resolved skill into the pack. Returns the constraint ids it bound."""
    dest.mkdir(parents=True, exist_ok=True)
    text = (src / "SKILL.md").read_text(encoding="utf-8")

    # Order matters: resolve blocks BEFORE injecting constraints, because resolution can move or
    # delete the H1 that injection anchors on.
    text = resolve.resolve(text, persona.id)
    meta, body = frontmatter(text)
    head = text[:len(text) - len(body)] if body else text

    bound = [c.strip() for c in
             str((meta.get("metadata") or {}).get("constraints", "")).split(",") if c.strip()]
    sections = [t for t in (model.constraint_text(c, persona.id, root) for c in bound) if t]

    body = resolve.inject(body, sections, CONSTRAINT_TITLE)
    body = rewrite_names(body, mapping)
    head = re.sub(r"^name:.*$", f"name: {dest.name}", head, count=1, flags=re.M)

    banner = BANNER.format(persona=persona.id, display=persona.display_name,
                           pack=pack_name, version=version, skill=src.name,
                           commit=commit())
    (dest / "SKILL.md").write_text(head + banner + body, encoding="utf-8")

    for name in model.BUNDLED_DIRS:
        tree = src / name
        if not tree.is_dir():
            continue
        shutil.copytree(tree, dest / name, dirs_exist_ok=True)
        for path in (dest / name).rglob("*"):
            if not path.is_file():
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue          # an image in assets/ — nothing to resolve
            path.write_text(rewrite_names(resolve.resolve(raw, persona.id), mapping),
                            encoding="utf-8")
    return bound


def write_mcp(pack: Path, entitled: tuple[str, ...], groups: dict[str, model.McpGroup],
              pack_name: str, version: str, author: dict) -> dict:
    """Emit every MCP shape the four hosts need. Returns the manifest fragment."""
    eager = {n: s for g in entitled if groups[g].loading == "eager"
             for n, s in groups[g].servers.items()}
    opt_in = {g: groups[g] for g in entitled if groups[g].loading == "opt-in"}

    fragment: dict = {}
    if eager:
        (pack / ".mcp.json").write_text(
            json.dumps({"mcpServers": eager}, indent=2) + "\n", encoding="utf-8")
        fragment["mcpServers"] = "./.mcp.json"

    if entitled:
        (pack / "mcp").mkdir(exist_ok=True)
        # Kiro: one file, every entitled server, opt-in ones marked disabled. Kiro's flag is per
        # server — the finest control of the four hosts.
        kiro = {n: dict(s) for n, s in eager.items()}
        for group in opt_in.values():
            for n, s in group.servers.items():
                kiro[n] = {**s, "disabled": True}
        (pack / "mcp" / "kiro-mcp.json").write_text(
            json.dumps({"mcpServers": kiro}, indent=2) + "\n", encoding="utf-8")

        for gid, group in opt_in.items():
            (pack / "mcp" / f"{gid}.json").write_text(
                json.dumps({"mcpServers": group.servers}, indent=2) + "\n", encoding="utf-8")
            # Claude Code has no per-server toggle, so an opt-in group becomes its own companion
            # plugin the user enables. Include the pack name because two personas may derive the
            # same group, and marketplace plugin names must remain unique.
            companion_name = f"mcp-{gid}-{pack_name}"
            companion = pack / "mcp-plugins" / companion_name
            (companion / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            (companion / ".claude-plugin" / "plugin.json").write_text(json.dumps({
                "name": companion_name,
                "version": version,
                "description": (group.note or f"Opt-in MCP servers: {', '.join(group.servers)}.")
                               + (" Needs credentials, a VPN or a licence this pack cannot supply."
                                  if group.access == "restricted" else ""),
                "author": author,
                "mcpServers": "./.mcp.json",
            }, indent=2) + "\n", encoding="utf-8")
            (companion / ".mcp.json").write_text(
                json.dumps({"mcpServers": group.servers}, indent=2) + "\n", encoding="utf-8")

        installs = {n: c for g in entitled for n, c in groups[g].install.items()}
        if installs:
            (pack / "mcp" / "install.json").write_text(
                json.dumps({"install": installs}, indent=2) + "\n", encoding="utf-8")
    return fragment


def build_pack(persona: model.Persona, out: Path, version: str, root: Path,
               author: dict, vertical: model.Vertical | None = None) -> dict:
    """Build one pack. Returns a summary dict."""
    groups = model.load_mcp_groups(root)

    # Which skills: the persona's own (base pack), or the vertical's (vertical pack). Disjoint by
    # construction — a vertical-tagged skill is claimed by the vertical and must not appear in a
    # persona's include_skills.
    tagged: dict[str, str] = {}
    for d in sorted((root / "skills").iterdir()):
        if not (d / "SKILL.md").is_file():
            continue
        meta, _ = frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        vid = (meta.get("metadata") or {}).get("vertical")
        if vid:
            tagged[d.name] = vid

    available = {d.name for d in (root / "skills").iterdir() if d.is_dir()}
    missing = sorted(set(persona.include_skills) - available)
    if missing:
        raise model.ModelError(
            f"persona {persona.id!r} includes skill(s) that do not exist: {missing}. A "
            f"declared-but-absent skill would ship a pack quietly missing it.")
    base_wanted = [s for s in persona.include_skills if s not in tagged]
    available_agents = set(model.all_agent_ids(root))
    missing_agents = sorted(set(persona.include_agents) - available_agents)
    if missing_agents:
        raise model.ModelError(
            f"persona {persona.id!r} includes agent(s) that do not exist: {missing_agents}. "
            f"Create agents/<id>.json or remove the include_agents entry.")

    if vertical:
        wanted = [s for s, v in tagged.items() if v == vertical.id]
        pack_name = f"vertical-{vertical.id}-{persona.id}"
        reference_names = list(dict.fromkeys(base_wanted + wanted))
    else:
        wanted = base_wanted
        pack_name = persona.pack_name
        reference_names = wanted

    pack = out / pack_name
    if pack.exists():
        shutil.rmtree(pack)
    pack.mkdir(parents=True)

    mapping = {s: prefixed(s, persona.prefix) for s in reference_names}
    constraints: set[str] = set()
    for name in wanted:
        constraints.update(build_skill(root / "skills" / name,
                                       pack / "skills" / mapping[name],
                                       persona, pack_name, version, mapping, root))

    # A vertical ships NO agents and no MCP: include_agents is a persona-level axis, and a
    # vertical's servers would already be entitled through the base pack it installs beside.
    entitled: tuple[str, ...] = ()
    fragment: dict = {}
    built_agents: list[dict] = []
    if vertical is None:
        compatible_verticals = {
            vid
            for vid in model.all_vertical_ids(root)
            if persona.id in model.load_vertical(vid, root).personas
        }
        agent_reference_names = list(dict.fromkeys(
            base_wanted
            + [name for name, vid in tagged.items() if vid in compatible_verticals]
        ))
        agent_mapping = {
            name: prefixed(name, persona.prefix)
            for name in agent_reference_names
        }
        built_agents = agent_build.write_pack_agents(
            pack, persona, version, agent_mapping, root)
        entitled = model.derive_mcp_groups(persona, groups, root, resolve.resolve)
        fragment = write_mcp(pack, entitled, groups, pack_name, version, author)

    manifest = {
        "$schema": "https://anthropic.com/claude-code/plugin.schema.json",
        "name": pack_name,
        "version": version,
        "description": (vertical.description if vertical else persona.description),
        "author": author,
        **fragment,
    }
    (pack / ".claude-plugin").mkdir(exist_ok=True)
    (pack / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {"pack": pack_name, "skills": sorted(mapping[name] for name in wanted),
            "agents": sorted(entry["name"] for entry in built_agents),
            "mcp": list(entitled), "constraints": sorted(constraints)}


def write_marketplaces(root: Path, out: Path, packs: list[str], version: str,
                       author: dict, description: str) -> None:
    """The two marketplace files, GENERATED.

    Both Claude Code and Codex install a marketplace straight from a git repo — that is the whole
    distribution story: push the repo, and two of the four hosts can install from it with one
    command. Kiro has no marketplace and needs `skillforge install`.

    Generated rather than hand-kept, because a marketplace entry pointing at a pack the build no
    longer emits fails at INSTALL time, not here — and the two files would drift from each other.

    They point at `dist/`, never at the repo root: a skill carrying conditional blocks resolves
    only at build time, so installing the source tree delivers every persona's mutually exclusive
    instructions in one file.
    """
    entries = [{"name": p, "source": f"./{out.name}/{p}",
                "description": json.loads((out / p / ".claude-plugin" / "plugin.json")
                                          .read_text())["description"]}
               for p in packs]
    # Companion plugins for opt-in MCP groups, one per group, disabled by default.
    for pack in packs:
        for companion in sorted((out / pack / "mcp-plugins").glob("mcp-*")) \
                if (out / pack / "mcp-plugins").is_dir() else []:
            entries.append({
                "name": companion.name,
                "source": f"./{out.name}/{pack}/mcp-plugins/{companion.name}",
                "description": json.loads(
                    (companion / ".claude-plugin" / "plugin.json").read_text())["description"],
                "defaultEnabled": False,
            })

    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": root.name, "version": version,
        "description": description,
        "owner": author,
        "plugins": entries,
    }, indent=2) + "\n", encoding="utf-8")

    (root / ".agents" / "plugins").mkdir(parents=True, exist_ok=True)
    (root / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({
        "name": root.name, "version": version,
        "interface": {"displayName": root.name},
        "plugins": [{"name": e["name"],
                     "source": {"source": "local", "path": e["source"]},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"}}
                    for e in entries],
    }, indent=2) + "\n", encoding="utf-8")


def write_quick(pack: Path, version: str) -> list[str]:
    """Amazon Quick variants, for skills that declare `metadata.quick_trigger`.

    Quick wants `display_name`, `icon`, `trigger` and `tools` as TOP-LEVEL frontmatter keys, which
    the Agent Skills validator rejects outright. So the canonical SKILL.md keeps them nested under
    `metadata.quick_*` (legal — metadata is an arbitrary string map) and they are HOISTED here. One
    methodology, two packagings, neither validator failing.

    A skill carrying conditional blocks is REFUSED, not resolved. A Quick package has no persona
    concept: no flag, no field recording which persona it was built for, and no sibling artefact.
    Choosing here would ship one persona's boundaries to whoever imports the folder.
    """
    built = []
    for skill in sorted((pack / "skills").iterdir()) if (pack / "skills").is_dir() else []:
        md = skill / "SKILL.md"
        if not md.is_file():
            continue
        text = md.read_text(encoding="utf-8")
        meta, body = frontmatter(text)
        quick = {k[len("quick_"):]: v for k, v in (meta.get("metadata") or {}).items()
                 if k.startswith("quick_")}
        if "trigger" not in quick:
            continue
        # Built packs are already resolved, so a marker here means resolution failed upstream.
        if "<!-- profile:" in text:
            print(f"    · quick: refusing {skill.name} — it carries conditional blocks and Quick "
                  f"has no persona to resolve against")
            continue
        head = {"name": skill.name, "description": meta.get("description", ""),
                "display_name": quick.get("display_name", skill.name),
                "trigger": quick["trigger"]}
        if "icon" in quick:
            head["icon"] = quick["icon"]
        lines = "\n".join(f'{k}: "{v}"' if " " in str(v) else f"{k}: {v}"
                           for k, v in head.items())
        (pack / "quick").mkdir(exist_ok=True)
        (pack / "quick" / f"{skill.name}.quick").write_text(
            f"---\n{lines}\n---\n\n{body}", encoding="utf-8")
        built.append(skill.name)
    return built


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--persona", action="append", help="persona id (repeatable)")
    ap.add_argument("--all", action="store_true", help="every persona")
    ap.add_argument("--vertical", help="a vertical id, or 'all'")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    model.ROOT = root
    out = root / args.out
    config = json.loads((root / "skillforge.json").read_text()) \
        if (root / "skillforge.json").is_file() else {}
    version = config.get("version", "0.0.0")
    author = config.get("author") or {"name": "Skillforge contributors"}
    description = config.get("description") or "Generated Skillforge packs."

    ids = model.all_persona_ids(root) if args.all else (args.persona or [])
    if not ids:
        print("give --persona <id> or --all", file=sys.stderr)
        return 1

    verticals = (model.all_vertical_ids(root) if args.vertical == "all"
                 else [args.vertical] if args.vertical else [])
    built_packs: list[str] = []
    try:
        for pid in ids:
            persona = model.load_persona(pid, root)
            r = build_pack(persona, out, version, root, author)
            quick = write_quick(out / r["pack"], version)
            built_packs.append(r["pack"])
            print(f"  {r['pack']:34} {len(r['skills']):3} skill(s)  "
                  f"agents={r['agents'] or '-'}  "
                  f"mcp={r['mcp'] or '-'}  constraints={r['constraints'] or '-'}"
                  + (f"  quick={len(quick)}" if quick else ""))
            for vid in verticals:
                v = model.load_vertical(vid, root)
                if pid not in v.personas:
                    print(f"    · {vid}: not declared for {pid}, skipped")
                    continue
                rv = build_pack(persona, out, version, root, author, vertical=v)
                built_packs.append(rv["pack"])
                print(f"    {rv['pack']:32} {len(rv['skills']):3} skill(s)")
        write_marketplaces(root, out, built_packs, version, author, description)
        print(f"\n  marketplaces: .claude-plugin/marketplace.json and "
              f".agents/plugins/marketplace.json ({len(built_packs)} pack(s) + companions)")
    except model.ModelError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1
    return 0
