"""Every gate, one command.

    python3 -m skillforge validate
    python3 -m skillforge validate --fast     # source only, no build needed

Two rules this file follows, both learned from a toolkit where breaking them cost real time:

**Run every gate even when one fails.** A runner that stops at the first failure means someone fixes
one thing, re-runs, and finds another — four times. One run should tell you everything.

**Report SKIPPED, never "ok", for a gate that could not run.** A gate whose input was not built
checked nothing. Printing a tick for it is worse than printing nothing, because it is believed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import harness, model, resolve
from .build import frontmatter, prefixed

#: Frontmatter this repo's reader and a real YAML parser agree on. Anything else is rejected rather
#: than guessed at: a skill whose `name` the host reads differently from the build is a skill that
#: installs under a name nothing references.
SPEC_KEYS = {"name", "description", "compatibility", "license", "allowed-tools", "metadata"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_harness_instructions(root: Path, r: Report) -> None:
    """Repository instructions and generated local authoring-skill adapters."""
    agents = root / "AGENTS.md"
    claude = root / "CLAUDE.md"
    if not agents.is_file():
        r.fail("AGENTS.md is missing — Codex and Kiro would not receive repository instructions")
    if not claude.is_file():
        r.fail("CLAUDE.md is missing — Claude Code would not receive repository instructions")
    elif "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
        r.fail("CLAUDE.md must import @AGENTS.md so all harnesses share one instruction source")

    for problem in harness.check(root):
        r.fail(problem)

    canonical = root / harness.CANONICAL / "SKILL.md"
    if canonical.is_file():
        meta, _ = frontmatter(canonical.read_text(encoding="utf-8"))
        if meta.get("name") != "skillforge-authoring":
            r.fail(f"{harness.CANONICAL}/SKILL.md must declare name=skillforge-authoring")
        description = meta.get("description", "")
        for term in ("persona", "vertical"):
            if term not in description.lower():
                r.fail(f"{harness.CANONICAL}/SKILL.md description must mention {term!r} so the "
                       f"authoring workflow can be discovered")


def check_skills(root: Path, r: Report) -> None:
    """The Agent Skills standard, plus the conventions that make a pack buildable."""
    for d in sorted((root / "skills").iterdir()):
        if not d.is_dir():
            continue
        md = d / "SKILL.md"
        if not md.is_file():
            r.fail(f"skills/{d.name}/ has no SKILL.md")
            continue
        text = md.read_text(encoding="utf-8")
        meta, body = frontmatter(text)

        if not meta.get("name"):
            r.fail(f"skills/{d.name}: no `name` in frontmatter")
        elif meta["name"] != d.name:
            r.fail(f"skills/{d.name}: name={meta['name']!r} must match the folder name. The "
                   f"standard requires it and hosts scan for direct children, so a mismatch is a "
                   f"skill the host cannot find.")
        elif not NAME_RE.match(meta["name"]):
            r.fail(f"skills/{d.name}: name must be lowercase kebab-case")

        desc = meta.get("description", "")
        if not desc:
            r.fail(f"skills/{d.name}: no `description`. It is the field that drives activation — "
                   f"a skill without one never fires.")
        elif len(desc) > 1024:
            r.fail(f"skills/{d.name}: description is {len(desc)} chars, max 1024")

        stray = sorted(set(meta) - SPEC_KEYS)
        if stray:
            r.fail(f"skills/{d.name}: unexpected top-level frontmatter {stray}. The spec allows "
                   f"only {sorted(SPEC_KEYS)} — put anything else under `metadata`. (Amazon Quick "
                   f"wants top-level `trigger`/`icon`; those live in metadata.quick_* and are "
                   f"hoisted at build time.)")

        if len(body.splitlines()) > 500:
            r.warn(f"skills/{d.name}: {len(body.splitlines())} lines exceeds the ~500 guidance — "
                   f"move reference material into references/ so the steps stay readable")


def check_blocks(root: Path, r: Report) -> None:
    """Conditional groups, across SKILL.md and every file the build copies."""
    known = set(model.all_persona_ids(root))
    for d in sorted((root / "skills").iterdir()):
        if not d.is_dir():
            continue
        targets = [d / "SKILL.md"]
        for name in model.BUNDLED_DIRS:
            if (d / name).is_dir():
                targets += [p for p in sorted((d / name).rglob("*")) if p.is_file()]
        total = 0
        for path in targets:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            label = str(path.relative_to(root))
            for problem in resolve.check(text, known, label):
                r.fail(problem)
            try:
                total += len(resolve.groups(text))
            except resolve.BlockError:
                pass
        # A cap, because at four groups the source stops being reviewable as one document and the
        # honest fix is two skills.
        if total > 3:
            r.fail(f"skills/{d.name}: {total} conditional groups across the skill. At more than 3 "
                   f"the source cannot be read as one document — split the skill instead.")


def check_personas(root: Path, r: Report) -> None:
    ids = model.all_persona_ids(root)
    if not ids:
        r.fail("no personas under policies/personas/")
        return
    packs: dict[str, str] = {}
    personas: dict[str, model.Persona] = {}
    available = {d.name for d in (root / "skills").iterdir() if d.is_dir()}
    claimed: dict[str, str] = {}
    for d in sorted((root / "skills").iterdir()):
        if not (d / "SKILL.md").is_file():
            continue
        meta, _ = frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        vid = (meta.get("metadata") or {}).get("vertical")
        if vid:
            claimed[d.name] = vid

    for pid in ids:
        try:
            p = model.load_persona(pid, root)
        except model.ModelError as exc:
            r.fail(str(exc))
            continue
        personas[pid] = p
        if p.pack_name in packs:
            r.fail(f"personas {packs[p.pack_name]!r} and {pid!r} share pack_name "
                   f"{p.pack_name!r} — one build would overwrite the other")
        packs[p.pack_name] = pid

        missing = sorted(set(p.include_skills) - available)
        if missing:
            r.fail(f"persona {pid!r} includes skill(s) that do not exist: {missing}")
        collision = sorted(set(p.include_skills) & set(claimed))
        if collision:
            r.fail(f"persona {pid!r} includes {collision}, which a vertical already claims. That "
                   f"is a collision, not double coverage: verticals install beside the base pack "
                   f"in one flat namespace, so one silently overwrites the other. Remove it from "
                   f"policies/personas/{pid}.json.")
        if p.router and p.router not in p.include_skills:
            r.fail(f"persona {pid!r} names router {p.router!r} but does not include it")

    vertical_ids = model.all_vertical_ids(root)
    verticals: dict[str, model.Vertical] = {}
    for vid in vertical_ids:
        try:
            verticals[vid] = model.load_vertical(vid, root)
        except model.ModelError as exc:
            r.fail(str(exc))

    for skill, vid in claimed.items():
        if vid not in vertical_ids:
            r.fail(f"skills/{skill}: metadata.vertical={vid!r} names no vertical under "
                   f"policies/verticals/")
    for vid, v in verticals.items():
        if not [s for s, got in claimed.items() if got == vid]:
            r.fail(f"vertical {vid!r} claims no skills — nothing would be built for it")
        unknown = sorted(set(v.personas) - set(ids))
        if unknown:
            r.fail(f"vertical {vid!r} declares unknown persona(s) {unknown}")

    orphans = sorted(available - {s for persona in personas.values()
                                  for s in persona.include_skills}
                     - set(claimed))
    for skill in orphans:
        r.warn(f"skills/{skill}: no persona includes it and no vertical claims it, so it reaches "
               f"nobody. If you just tagged it as a vertical skill, check the tag parsed — the fix "
               f"is the tag, not adding it to a persona.")


def check_mcp(root: Path, r: Report) -> None:
    """The loading model, and that every declared server is actually used by someone."""
    try:
        groups = model.load_mcp_groups(root)
    except model.ModelError as exc:
        r.fail(str(exc))
        return
    if not groups:
        return

    derived: set[str] = set()
    personas: dict[str, model.Persona] = {}
    base_entitlements: dict[str, set[str]] = {}
    for pid in model.all_persona_ids(root):
        try:
            p = model.load_persona(pid, root)
        except model.ModelError:
            continue
        personas[pid] = p
        entitled = set(model.derive_mcp_groups(p, groups, root, resolve.resolve))
        base_entitlements[pid] = entitled
        derived.update(entitled)

    vertical_skills: dict[str, list[Path]] = {}
    for directory in sorted((root / "skills").iterdir()):
        md = directory / "SKILL.md"
        if not md.is_file():
            continue
        meta, _ = frontmatter(md.read_text(encoding="utf-8"))
        vertical = (meta.get("metadata") or {}).get("vertical")
        if vertical:
            vertical_skills.setdefault(vertical, []).append(directory)

    for vid in model.all_vertical_ids(root):
        try:
            vertical = model.load_vertical(vid, root)
        except model.ModelError:
            continue
        for pid in vertical.personas:
            if pid not in personas:
                continue
            text = "\n".join(
                resolve.resolve(model.skill_text(directory), pid)
                for directory in vertical_skills.get(vid, [])
            )
            required = set(model.mcp_groups_named(text, groups))
            missing = sorted(required - base_entitlements.get(pid, set()))
            if missing:
                r.fail(
                    f"vertical {vid!r} for persona {pid!r} names MCP group(s) {missing}, but "
                    f"{personas[pid].pack_name!r} does not entitle them. Vertical packs ship no "
                    f"MCP configuration, so name those servers in a base skill that genuinely "
                    f"uses them or remove the vertical dependency.")

    for gid, group in groups.items():
        if gid not in derived:
            r.fail(f"mcp/{gid}.json: no persona derives this group, so it reaches nobody. An "
                   f"unused server cannot help anyone and is exposure for nothing — either a "
                   f"skill must name one of its servers, or the group should go.")
        for name, spec in group.servers.items():
            if not (spec.get("command") or spec.get("url")):
                r.fail(f"mcp/{gid}.json: server {name!r} has neither `command` nor `url`, so "
                       f"nothing can start it")
            cmd = spec.get("command")
            if cmd and cmd not in ("uvx", "npx", "pipx", "python3", "node", "docker") \
                    and name not in group.install:
                r.warn(f"mcp/{gid}.json: {name!r} runs a bare binary ({cmd!r}) with no `install` "
                       f"recipe. Enabling the group then yields an entry that cannot spawn until "
                       f"the binary exists, which reads as a broken server.")


def check_packs(root: Path, out: Path, r: Report) -> bool:
    """The BUILT packs — what actually installs. Returns False if there is nothing to check."""
    packs = [d for d in sorted(out.glob("*")) if (d / "skills").is_dir()] if out.is_dir() else []
    if not packs:
        return False

    source_names = {
        directory.name
        for directory in (root / "skills").iterdir()
        if (directory / "SKILL.md").is_file()
    }
    personas: dict[str, model.Persona] = {}
    pack_personas: dict[str, model.Persona] = {}
    for pid in model.all_persona_ids(root):
        try:
            persona = model.load_persona(pid, root)
        except model.ModelError:
            continue
        personas[pid] = persona
        pack_personas[persona.pack_name] = persona
    for vid in model.all_vertical_ids(root):
        try:
            vertical = model.load_vertical(vid, root)
        except model.ModelError:
            continue
        for pid in vertical.personas:
            if pid in personas:
                pack_personas[f"vertical-{vid}-{pid}"] = personas[pid]

    for pack in packs:
        persona = pack_personas.get(pack.name)
        if persona is None:
            r.fail(f"{pack.name}: built pack matches no declared persona or vertical")
            continue
        base = out / persona.pack_name / "skills"
        allowed_references = {
            directory.name for directory in base.iterdir() if directory.is_dir()
        } if base.is_dir() else set()
        allowed_references.update(
            directory.name for directory in (pack / "skills").iterdir() if directory.is_dir())
        known_prefixed = {prefixed(name, persona.prefix) for name in source_names}

        for skill in sorted((pack / "skills").iterdir()):
            md = skill / "SKILL.md"
            if not md.is_file():
                r.fail(f"{pack.name}/{skill.name}: no SKILL.md")
                continue
            text = md.read_text(encoding="utf-8")
            meta, _ = frontmatter(text)
            if meta.get("name") != skill.name:
                r.fail(f"{pack.name}/{skill.name}: built name={meta.get('name')!r} does not match "
                       f"its directory. Hosts scan direct children and the standard requires the "
                       f"two to agree.")
            if not skill.name.startswith(persona.prefix):
                r.fail(f"{pack.name}/{skill.name}: does not start with persona prefix "
                       f"{persona.prefix!r}")

            targets = [md]
            for bundled in model.BUNDLED_DIRS:
                directory = skill / bundled
                if directory.is_dir():
                    targets.extend(path for path in sorted(directory.rglob("*")) if path.is_file())
            for path in targets:
                try:
                    shipped = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                label = f"{pack.name}/{path.relative_to(pack)}"
                try:
                    unresolved_groups = resolve.groups(shipped)
                except resolve.BlockError as exc:
                    r.fail(f"{label}: ships malformed conditional markers: {exc}")
                    unresolved_groups = []
                if unresolved_groups:
                    r.fail(f"{label}: ships a raw conditional marker, so it delivers another "
                           f"persona's instructions too")
                without_banner = "\n".join(
                    line for line in shipped.splitlines()
                    if not line.startswith("> Source:"))
                for source_name in source_names:
                    if f"`{source_name}`" in without_banner:
                        r.fail(f"{label}: contains unresolved skill reference `{source_name}`")
                for reference in known_prefixed:
                    if f"`{reference}`" in without_banner \
                            and reference not in allowed_references:
                        r.fail(f"{label}: references `{reference}`, which is not available from "
                               f"the base pack plus {pack.name}")
        # Vertical packs ship no agents and no MCP by design.
        if pack.name.startswith("vertical-"):
            for stray in (".mcp.json", "mcp", "agents"):
                if (pack / stray).exists():
                    r.fail(f"{pack.name} ships {stray}, which a vertical must not: agents are a "
                           f"persona-level axis and its servers are already entitled through the "
                           f"base pack it installs beside.")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fast", action="store_true", help="source only; skip the built packs")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    model.ROOT = root
    r = Report()

    gates = [("harness-instructions", check_harness_instructions),
             ("skills", check_skills), ("conditional-blocks", check_blocks),
             ("personas", check_personas), ("mcp", check_mcp)]
    for name, fn in gates:
        before = len(r.errors)
        fn(root, r)
        print(f"  {'ok  ' if len(r.errors) == before else 'FAIL'}  {name}")

    if args.fast:
        print("  SKIP  built-packs (--fast; a skipped gate checked nothing)")
    else:
        before = len(r.errors)
        ran = check_packs(root, root / args.out, r)
        print(f"  {'ok  ' if ran and len(r.errors) == before else 'FAIL' if ran else 'SKIP'}  "
              f"built-packs" + ("" if ran else "  (nothing built — run `skillforge build --all`)"))

    print()
    for w in r.warnings:
        print(f"  warning: {w}")
    if r.errors:
        print(f"\n✗ {len(r.errors)} problem(s):", file=sys.stderr)
        for e in r.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"✓ all gates pass"
          + (f" ({len(r.warnings)} warning(s), advisory)" if r.warnings else ""))
    return 0
