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

from . import agents as agent_build
from . import evals as eval_runner
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


def check_agents(root: Path, r: Report) -> None:
    """Canonical agents and each host's explicit native grant policy."""
    known_personas = set(model.all_persona_ids(root))
    loaded: dict[str, model.Agent] = {}
    for agent_id in model.all_agent_ids(root):
        try:
            agent = model.load_agent(agent_id, root)
        except model.ModelError as exc:
            r.fail(str(exc))
            continue
        loaded[agent_id] = agent
        for problem in resolve.check(
                agent.instructions, known_personas, f"agents/{agent_id}.json: instructions"):
            r.fail(problem)

    included: set[str] = set()
    for persona_id in model.all_persona_ids(root):
        try:
            persona = model.load_persona(persona_id, root)
        except model.ModelError:
            continue
        included.update(persona.include_agents)
        missing = sorted(set(persona.include_agents) - set(loaded))
        if missing:
            r.fail(f"persona {persona_id!r} includes agent(s) that do not exist or are invalid: "
                   f"{missing}")

        built_names: dict[str, str] = {}
        for agent_id in persona.include_agents:
            name = prefixed(agent_id, persona.prefix)
            if name in built_names:
                r.fail(
                    f"persona {persona_id!r} agents {built_names[name]!r} and {agent_id!r} both "
                    f"generate {name!r}; every host would hide one of them")
            built_names[name] = agent_id

    for agent_id in sorted(set(loaded) - included):
        r.warn(f"agents/{agent_id}.json: no persona includes it, so it reaches nobody")


def check_evals(root: Path, r: Report) -> None:
    """Checked-in trigger and non-trigger cases across every coding harness."""
    for problem in eval_runner.check(root):
        r.fail(problem)


def _source_vertical_skills(root: Path) -> dict[str, str]:
    tagged: dict[str, str] = {}
    for directory in sorted((root / "skills").iterdir()):
        md = directory / "SKILL.md"
        if not md.is_file():
            continue
        meta, _ = frontmatter(md.read_text(encoding="utf-8"))
        vertical = (meta.get("metadata") or {}).get("vertical")
        if vertical:
            tagged[directory.name] = vertical
    return tagged


def check_cross_host_collisions(root: Path, r: Report) -> None:
    """Names that flatten together in Claude, Codex, Kiro, and Quick."""
    tagged = _source_vertical_skills(root)
    verticals: dict[str, model.Vertical] = {}
    for vertical_id in model.all_vertical_ids(root):
        try:
            verticals[vertical_id] = model.load_vertical(vertical_id, root)
        except model.ModelError:
            continue

    for persona_id in model.all_persona_ids(root):
        try:
            persona = model.load_persona(persona_id, root)
        except model.ModelError:
            continue
        sources: list[tuple[str, str]] = [
            (skill, persona.pack_name)
            for skill in persona.include_skills
            if skill not in tagged
        ]
        for vertical_id, vertical in verticals.items():
            if persona_id not in vertical.personas:
                continue
            sources.extend(
                (skill, f"vertical-{vertical_id}-{persona_id}")
                for skill, owner in tagged.items()
                if owner == vertical_id
            )

        seen: dict[str, tuple[str, str]] = {}
        for source, component in sources:
            generated = prefixed(source, persona.prefix)
            if generated in seen:
                prior_source, prior_component = seen[generated]
                r.fail(
                    f"persona {persona_id!r}: {prior_component}/{prior_source} and "
                    f"{component}/{source} both generate skill {generated!r}. Base and all "
                    f"compatible verticals install into one flat namespace on every host.")
            seen[generated] = (source, component)

    # Repository-local authoring skills are separate per host, but duplicate declarations inside
    # any one host's direct-child skill directory shadow each other.
    for host, relative in zip(("codex", "claude", "kiro"), harness.HOST_DESTINATIONS):
        directory = root / relative.parent
        seen: dict[str, Path] = {}
        for md in sorted(directory.glob("*/SKILL.md")) if directory.is_dir() else []:
            metadata, _ = frontmatter(md.read_text(encoding="utf-8"))
            name = metadata.get("name")
            if not name:
                continue
            if name in seen:
                r.fail(
                    f"{host}: {seen[name].relative_to(root)} and {md.relative_to(root)} both "
                    f"declare skill {name!r}; the host can load only one")
            seen[name] = md


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

        if not pack.name.startswith("vertical-"):
            _check_built_agents(root, pack, persona, r)
        # Vertical packs ship no agents and no MCP by design.
        if pack.name.startswith("vertical-"):
            for stray in (".mcp.json", "mcp", "agents"):
                if (pack / stray).exists():
                    r.fail(f"{pack.name} ships {stray}, which a vertical must not: agents are a "
                           f"persona-level axis and its servers are already entitled through the "
                           f"base pack it installs beside.")

    # The same persona's base pack and every compatible vertical can be installed together. Check
    # the actual emitted names too, so a stale checked-in distribution cannot evade the source
    # collision gate.
    for persona_id, persona in personas.items():
        selected = [out / persona.pack_name]
        for vertical_id in model.all_vertical_ids(root):
            try:
                vertical = model.load_vertical(vertical_id, root)
            except model.ModelError:
                continue
            if persona_id in vertical.personas:
                selected.append(out / f"vertical-{vertical_id}-{persona_id}")
        seen: dict[str, str] = {}
        for selected_pack in selected:
            skills = selected_pack / "skills"
            if not skills.is_dir():
                continue
            for skill in sorted(path for path in skills.iterdir() if path.is_dir()):
                if skill.name in seen:
                    r.fail(
                        f"built install set for persona {persona_id!r}: {seen[skill.name]} and "
                        f"{selected_pack.name} both ship skill {skill.name!r}")
                seen[skill.name] = selected_pack.name

    _check_marketplaces(root, r)
    return True


def _read_json(path: Path, r: Report) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        r.fail(f"{path}: invalid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        r.fail(f"{path}: must contain a JSON object")
        return None
    return value


def _check_built_agents(root: Path, pack: Path, persona: model.Persona, r: Report) -> None:
    expected = {
        prefixed(agent_id, persona.prefix): agent_id
        for agent_id in persona.include_agents
    }
    directory = pack / "agents"
    if not expected:
        if directory.exists():
            r.fail(f"{pack.name} ships agents/ but persona {persona.id!r} includes none")
        return

    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        r.fail(f"{pack.name}: agents/manifest.json is missing")
        return
    manifest = _read_json(manifest_path, r)
    if manifest is None:
        return
    if manifest.get("schema_version") != agent_build.MANIFEST_VERSION:
        r.fail(f"{pack.name}: agents/manifest.json has unsupported schema_version")
    if manifest.get("persona") != persona.id:
        r.fail(f"{pack.name}: agents/manifest.json persona must be {persona.id!r}")
    entries = manifest.get("agents")
    if not isinstance(entries, list):
        r.fail(f"{pack.name}: agents/manifest.json agents must be a list")
        return
    names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
    if len(names) != len(set(names)):
        r.fail(f"{pack.name}: agents/manifest.json contains duplicate agent names")
    if set(names) != set(expected):
        r.fail(
            f"{pack.name}: built agents {sorted(str(name) for name in names)} do not match "
            f"persona include_agents {sorted(expected)}")

    declared_files: dict[str, set[str]] = {
        "claude": set(), "codex": set(), "kiro": set(), "quick": set(),
    }
    tagged = _source_vertical_skills(root)
    compatible_verticals: set[str] = set()
    for vertical_id in model.all_vertical_ids(root):
        try:
            vertical = model.load_vertical(vertical_id, root)
        except model.ModelError:
            continue
        if persona.id in vertical.personas:
            compatible_verticals.add(vertical_id)
    reference_names = list(dict.fromkeys(
        [
            skill for skill in persona.include_skills
            if skill not in tagged
        ]
        + [
            skill for skill, vertical_id in tagged.items()
            if vertical_id in compatible_verticals
        ]
    ))
    mapping = {
        source: prefixed(source, persona.prefix)
        for source in reference_names
    }
    for entry in entries:
        if not isinstance(entry, dict):
            r.fail(f"{pack.name}: agents/manifest.json entries must be objects")
            continue
        name = entry.get("name")
        source = entry.get("source")
        if expected.get(name) != source:
            r.fail(f"{pack.name}: agent {name!r} has source {source!r}, expected "
                   f"{expected.get(name)!r}")
            continue
        try:
            canonical = model.load_agent(source, root)
        except model.ModelError as exc:
            r.fail(str(exc))
            continue
        if entry.get("grants") != canonical.grants:
            r.fail(f"{pack.name}: agent {name!r} grant manifest drifted from agents/{source}.json")
        instructions = agent_build.resolved_instructions(canonical, persona, mapping)

        files = entry.get("files")
        if not isinstance(files, dict) or set(files) != set(model.AGENT_HOSTS):
            r.fail(f"{pack.name}: agent {name!r} must list one file for every host")
            continue
        resolved: dict[str, Path] = {}
        for host, relative in files.items():
            if not isinstance(relative, str):
                r.fail(f"{pack.name}: agent {name!r} file for {host} must be a string")
                continue
            path = (pack / relative).resolve()
            try:
                path.relative_to(pack.resolve())
            except ValueError:
                r.fail(f"{pack.name}: agent {name!r} file for {host} escapes the pack")
                continue
            if not path.is_file():
                r.fail(f"{pack.name}: agent {name!r} file for {host} is missing: {relative}")
                continue
            declared_files[host].add(relative)
            resolved[host] = path
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "<!-- profile:" in text or "<!-- /profile -->" in text:
                r.fail(f"{pack.name}: agent {name!r} for {host} ships a raw profile marker")

        expected_text = {
            "claude": agent_build.render_claude(canonical, name, instructions),
            "codex": agent_build.render_codex(canonical, instructions),
            "kiro": json.dumps(
                agent_build.render_kiro(canonical, instructions), indent=2) + "\n",
            "quick": json.dumps(
                agent_build.render_quick(canonical, instructions), indent=2) + "\n",
        }
        for host, path in resolved.items():
            try:
                actual = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                r.fail(f"{pack.name}: cannot read {host} agent {name!r}: {exc}")
                continue
            if actual != expected_text[host]:
                r.fail(
                    f"{pack.name}: generated {host} agent {name!r} drifted from "
                    f"agents/{source}.json")

        claude = resolved.get("claude")
        if claude:
            metadata, _ = frontmatter(claude.read_text(encoding="utf-8"))
            expected_tools = ", ".join(canonical.grants["claude"]["tools"]) or "[]"
            if metadata.get("name") != name:
                r.fail(f"{pack.name}: Claude agent {name!r} declares name "
                       f"{metadata.get('name')!r}")
            if metadata.get("tools") != expected_tools:
                r.fail(f"{pack.name}: Claude agent {name!r} tool allowlist drifted")

        codex = resolved.get("codex")
        if codex:
            text = codex.read_text(encoding="utf-8")
            grant = canonical.grants["codex"]
            for key in ("sandbox_mode", "web_search"):
                expected_line = f"{key} = {json.dumps(grant[key])}"
                if expected_line not in text:
                    r.fail(f"{pack.name}: Codex agent {name!r} is missing {expected_line}")

        kiro = resolved.get("kiro")
        if kiro:
            data = _read_json(kiro, r)
            grant = canonical.grants["kiro"]
            if data is not None and (
                    data.get("tools") != grant["tools"]
                    or data.get("allowedTools") != grant["allowed_tools"]):
                r.fail(f"{pack.name}: Kiro agent {name!r} tool grants drifted")

        quick = resolved.get("quick")
        if quick:
            data = _read_json(quick, r)
            if data is not None and data.get("tools") != canonical.grants["quick"]["tools"]:
                r.fail(f"{pack.name}: Quick agent {name!r} tool grants drifted")

    actual_files = {
        "claude": {
            path.relative_to(pack).as_posix()
            for path in directory.glob("*.md")
        },
        "codex": {
            path.relative_to(pack).as_posix()
            for path in (directory / "codex").glob("*.toml")
        } if (directory / "codex").is_dir() else set(),
        "kiro": {
            path.relative_to(pack).as_posix()
            for path in (directory / "kiro").glob("*.json")
        } if (directory / "kiro").is_dir() else set(),
        "quick": {
            path.relative_to(pack).as_posix()
            for path in (directory / "quick").glob("*.json")
        } if (directory / "quick").is_dir() else set(),
    }
    for host in model.AGENT_HOSTS:
        extras = sorted(actual_files[host] - declared_files[host])
        if extras:
            r.fail(f"{pack.name}: undeclared {host} agent file(s) {extras}")


def _check_marketplaces(root: Path, r: Report) -> None:
    claude_path = root / ".claude-plugin" / "marketplace.json"
    codex_path = root / ".agents" / "plugins" / "marketplace.json"
    missing = [
        str(path.relative_to(root))
        for path in (claude_path, codex_path)
        if not path.is_file()
    ]
    if missing:
        r.fail(f"built distribution is missing marketplace file(s) {missing}")
        return
    claude = _read_json(claude_path, r)
    codex = _read_json(codex_path, r)
    if claude is None or codex is None:
        return
    claude_entries = claude.get("plugins")
    codex_entries = codex.get("plugins")
    if not isinstance(claude_entries, list) or not isinstance(codex_entries, list):
        r.fail("marketplace plugin inventories must be lists")
        return
    claude_names = [
        entry.get("name") for entry in claude_entries if isinstance(entry, dict)
    ]
    codex_names = [
        entry.get("name") for entry in codex_entries if isinstance(entry, dict)
    ]
    if len(claude_names) != len(set(claude_names)):
        r.fail("Claude marketplace contains duplicate plugin names")
    if len(codex_names) != len(set(codex_names)):
        r.fail("Codex marketplace contains duplicate plugin names")
    if claude_names != codex_names:
        r.fail("Claude and Codex marketplaces advertise different plugin inventories")


SOURCE_GATES = (
    ("harness-instructions", check_harness_instructions),
    ("skills", check_skills),
    ("conditional-blocks", check_blocks),
    ("personas", check_personas),
    ("agents", check_agents),
    ("mcp", check_mcp),
    ("eval-cases", check_evals),
    ("cross-host-collisions", check_cross_host_collisions),
)
BUILT_GATE = "built-packs"


def gate_names() -> tuple[str, ...]:
    return tuple(name for name, _ in SOURCE_GATES) + (BUILT_GATE,)


def run_gate(name: str, root: Path, out: Path, report: Report) -> bool:
    """Run one named gate. The bool says whether the gate had input to inspect."""
    if name == BUILT_GATE:
        return check_packs(root, out, report)
    for gate_name, function in SOURCE_GATES:
        if name == gate_name:
            function(root, report)
            return True
    raise KeyError(name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fast", action="store_true", help="source only; skip the built packs")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    model.ROOT = root
    r = Report()

    for name, fn in SOURCE_GATES:
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
        print(f"\nERROR: {len(r.errors)} problem(s):", file=sys.stderr)
        for e in r.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: all gates pass"
          + (f" ({len(r.warnings)} warning(s), advisory)" if r.warnings else ""))
    return 0
