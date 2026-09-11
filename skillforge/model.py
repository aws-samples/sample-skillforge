"""The authoring model: personas, constraints, verticals, MCP groups.

Four concepts, and the distinction between two of them is the one thing worth getting straight
before reading anything else:

    PERSONAS SWAP. VERTICALS ADD.

A persona is an audience with its own rules. Two personas can hold mutually exclusive instructions
for the SAME skill, so only one persona may be installed at a time. A vertical is optional domain
content — regulated industry, a compliance regime, a product line — that installs *beside* a base
pack. Any number may be installed together.

Everything else follows from that. A skill claimed by a vertical must NOT also appear in a
persona's `include_skills`: verticals install into one flat namespace next to the base pack, so one
would silently overwrite the other and the loser is invisible.

## Entitlement is derived, not declared

A persona is entitled to exactly the MCP groups whose servers its own skills and agents NAME. There
is no `mcp` key in a persona file and `load_persona` raises if one appears.

That is a deliberate constraint, not an omission. A hand-kept list is a second answer to "which
servers does this pack ship", and the two drift — in the toolkit this was extracted from, a stale
list handed one persona an authenticated CRM connection no skill of its own used.

The residual risk runs the other way and is documented rather than gated: **a prose mention
entitles**. Matching cannot tell "use this server" from "we deliberately do not use this server",
so naming a server in a skill that does not call it hands that persona the group.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path.cwd()

#: Slugs become path segments (policies/constraints/<id>/, dist/<pack_name>/), so they are
#: shape-checked before use. Without this a crafted id reads outside the policies tree.
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: A group's `loading`. "eager" servers start with the session; "opt-in" ones ship disabled and
#: start only when the user asks. No default and no third state: guessing would silently make a
#: server eager, which is the failure this axis exists to prevent.
LOADING = ("eager", "opt-in")

#: A group's `access`, kept separate from `loading` because they answer different questions.
#: "open" needs nothing beyond the launcher. "restricted" needs something the toolkit cannot
#: provide — a VPN, a licence, a corporate SSO session, a secret. A restricted group must be
#: opt-in: a server that cannot start without a credential must never be switched on implicitly.
ACCESS = ("open", "restricted")


class ModelError(Exception):
    """A problem in the authoring model. Always names the file to edit."""


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ModelError(f"{path} not found")
    except ValueError as exc:
        raise ModelError(f"{path} is not valid JSON: {exc}")


@dataclass(frozen=True)
class Persona:
    """One audience. Its pack is built from `include_skills` + `include_agents`."""

    id: str
    display_name: str
    pack_name: str
    description: str
    prefix: str
    include_skills: tuple[str, ...]
    include_agents: tuple[str, ...] = ()
    router: str | None = None

    @property
    def mcp(self) -> tuple[str, ...]:
        """Derived at build time by `derive_mcp_groups`; never stored on the persona."""
        raise AttributeError(
            "persona.mcp does not exist by design — entitlement is DERIVED from the servers this "
            "persona's own skills and agents name. Call derive_mcp_groups(persona, ...).")


@dataclass(frozen=True)
class Vertical:
    """Optional domain content, installed beside a base pack rather than instead of one."""

    id: str
    display_name: str
    description: str
    personas: tuple[str, ...]


@dataclass(frozen=True)
class McpGroup:
    id: str
    access: str
    loading: str
    servers: dict = field(default_factory=dict)
    install: dict = field(default_factory=dict)
    note: str = ""


def personas_dir(root: Path = None) -> Path:
    return (root or ROOT) / "policies" / "personas"


def load_persona(persona_id: str, root: Path = None) -> Persona:
    if not SLUG.match(str(persona_id)):
        raise ModelError(f"persona id {persona_id!r} is not kebab-case")
    data = _load(personas_dir(root) / f"{persona_id}.json")

    # An `mcp` key means someone tried to hand-declare entitlement. Raising is the point: a
    # silently-ignored key would leave the author believing they had configured something.
    if "mcp" in data:
        raise ModelError(
            f"policies/personas/{persona_id}.json declares `mcp`. Entitlement is DERIVED from the "
            f"servers this persona's own skills and agents name — delete the key. If a server "
            f"should reach this pack, a skill in it must name the server.")

    missing = [k for k in ("display_name", "pack_name", "description", "prefix", "include_skills")
               if k not in data]
    if missing:
        raise ModelError(f"policies/personas/{persona_id}.json is missing {missing}")
    for key in ("pack_name", "prefix"):
        value = str(data[key]).rstrip("-")
        if not SLUG.match(value):
            raise ModelError(
                f"policies/personas/{persona_id}.json: {key}={data[key]!r} must be kebab-case — "
                f"it becomes a directory name and a skill-name prefix")
    return Persona(
        id=persona_id,
        display_name=data["display_name"],
        pack_name=data["pack_name"],
        description=data["description"],
        prefix=data["prefix"],
        include_skills=tuple(data["include_skills"]),
        include_agents=tuple(data.get("include_agents") or ()),
        router=data.get("router"),
    )


def all_persona_ids(root: Path = None) -> list[str]:
    return sorted(p.stem for p in personas_dir(root).glob("*.json"))


def load_vertical(vertical_id: str, root: Path = None) -> Vertical:
    if not SLUG.match(str(vertical_id)):
        raise ModelError(f"vertical id {vertical_id!r} is not kebab-case")
    data = _load((root or ROOT) / "policies" / "verticals" / f"{vertical_id}.json")
    personas = tuple(data.get("personas") or ())
    if not personas:
        raise ModelError(
            f"policies/verticals/{vertical_id}.json declares no `personas`. A vertical with no "
            f"base pack to install beside cannot reach anyone.")
    return Vertical(vertical_id, data.get("display_name", vertical_id),
                    data.get("description", ""), personas)


def all_vertical_ids(root: Path = None) -> list[str]:
    d = (root or ROOT) / "policies" / "verticals"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def constraint_text(constraint_id: str, persona_id: str, root: Path = None) -> str | None:
    """This constraint's text for this persona, or None if it has none for them.

    The id is shape-checked HERE, where the path is built, and not only in a validator — a
    validator is a different process and cannot stop `constraint_text('../../secret', …)` from
    splicing a file into a published pack.
    """
    if not SLUG.match(str(constraint_id)):
        raise ModelError(f"constraint id {constraint_id!r} is not kebab-case")
    directory = (root or ROOT) / "policies" / "constraints" / constraint_id
    if not directory.is_dir():
        raise ModelError(f"unknown constraint {constraint_id!r}: {directory} not found")
    path = directory / f"{persona_id}.md"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def load_mcp_groups(root: Path = None) -> dict[str, McpGroup]:
    """Every group under mcp/. Both axes are required with no defaults."""
    groups: dict[str, McpGroup] = {}
    directory = (root or ROOT) / "mcp"
    if not directory.is_dir():
        return groups
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        data = _load(path)
        gid = path.stem
        for key, allowed in (("access", ACCESS), ("loading", LOADING)):
            if data.get(key) not in allowed:
                raise ModelError(
                    f"mcp/{gid}.json: {key}={data.get(key)!r} must be one of {allowed}. There is "
                    f"no default — an unset value would be a guess about whether a server starts "
                    f"or what it needs to start.")
        if data["access"] == "restricted" and data["loading"] != "opt-in":
            raise ModelError(
                f"mcp/{gid}.json is access=restricted and loading={data['loading']!r}. A server "
                f"that needs a credential, VPN or licence must be opt-in — starting it implicitly "
                f"either fails at session start or connects something the user did not ask for.")
        servers = data.get("mcpServers") or {}
        for name in servers:
            if name in seen:
                raise ModelError(
                    f"server {name!r} is declared in both mcp/{seen[name]}.json and "
                    f"mcp/{gid}.json. One server, one group — two groups means two answers to "
                    f"whether it starts.")
            seen[name] = gid
        groups[gid] = McpGroup(gid, data["access"], data["loading"], servers,
                               data.get("install") or {}, data.get("note", ""))
    return groups


#: Directories copied into a pack alongside SKILL.md. MCP derivation and the build must agree
#: about what a skill ships, so this is defined once: a server named only in a `references/` file
#: must entitle the persona whose pack that file reaches.
BUNDLED_DIRS = ("references", "assets", "scripts")


def skill_text(skill_dir: Path) -> str:
    """Everything a skill ships, concatenated — SKILL.md plus the bundled trees.

    Undecodable files (images in assets/) are skipped rather than failing the build.
    """
    parts: list[str] = []
    md = skill_dir / "SKILL.md"
    if md.is_file():
        parts.append(md.read_text(encoding="utf-8", errors="replace"))
    for name in BUNDLED_DIRS:
        for path in sorted((skill_dir / name).rglob("*")) if (skill_dir / name).is_dir() else []:
            if path.is_file():
                try:
                    parts.append(path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, OSError):
                    continue
    return "\n".join(parts)


def derive_mcp_groups(persona: Persona, groups: dict[str, McpGroup],
                      root: Path = None, resolve=None) -> tuple[str, ...]:
    """The groups this persona is entitled to, from what its own content names.

    `resolve` is the persona-conditional resolver. It matters: a server named only inside a
    `<!-- profile:other -->` block must NOT entitle this persona, because that text never reaches
    this pack. Passing None skips resolution and over-entitles, which is why the build always
    passes it.

    Matching is on word boundaries and on the `mcp__<server>__` tool form, so `ash` does not match
    inside `dashboard`.
    """
    base = root or ROOT
    corpus: list[str] = []
    for skill in persona.include_skills:
        d = base / "skills" / skill
        if d.is_dir():
            corpus.append(skill_text(d))
    for agent in persona.include_agents:
        for path in (base / "agents").rglob(f"{agent}.md"):
            corpus.append(path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(resolve(c, persona.id) if resolve else c for c in corpus)

    entitled = []
    for gid, group in groups.items():
        for server in group.servers:
            if re.search(rf"\b{re.escape(server)}\b", text) or f"mcp__{server}__" in text:
                entitled.append(gid)
                break
    return tuple(sorted(entitled))
