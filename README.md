# Skillforge

Write agent skills once. Ship them to **Claude Code, Codex, Kiro and Amazon Quick** — with your own
personas, your own policy rules, and optional domain add-ons.

```bash
python3 -m skillforge build --all --vertical all   # generate the packs
python3 -m skillforge validate                     # every gate
python3 -m skillforge install --persona analyst    # Kiro; prints the Claude Code / Codex commands
```

## Why this exists

Writing a skill is easy. Shipping it is not, and the reason is that the hosts agree on almost
nothing:

| | Claude Code | Codex | Kiro | Amazon Quick |
|---|---|---|---|---|
| Skills | `skills/<name>/SKILL.md` | same | same | **top-level `trigger`, `icon`** — which the spec forbids |
| Install | `marketplace add` from git | `marketplace add` from git | no marketplace | manual import |
| MCP servers | plugin-level `.mcp.json` | `mcpServers` | agent's own block **and** global config | n/a |
| Tool grants | explicit prefixed names; **wildcards match nothing** | none — no allowlist exists | `@server/*` wildcards, which **do** expand | `tools` |

Maintain that by hand across two audiences and you have eight artefacts to keep in step. They drift,
and the failures are silent: a server that connects and exposes nothing, a skill that ships one
audience's rules to the other, a description the host truncated so the skill never fires.

## The model — four concepts

**Skills** are ordinary `skills/<name>/SKILL.md`, to the [Agent Skills](https://agentskills.io)
standard. Portable by construction.

**Personas swap.** An audience with its own rules. One source, N packs — and because two personas
can hold *mutually exclusive* instructions for the same skill, only one may be installed at a time.
The installer enforces that.

**Verticals add.** Optional domain content — a compliance regime, a regulated industry, a product
line. Tag a skill `metadata.vertical: pci-dss` and it leaves every base pack for
`dist/vertical-pci-dss-<persona>/`, installable *alongside*. Any number can be installed together.

**Constraints** are policy text written once and injected into every skill that binds it. Tag
`metadata.constraints: data-handling` and one edit updates every skill. This is how a compliance
owner owns a rule without touching forty files.

### Personas swap, verticals add

That distinction drives everything else. It is also why a vertical-tagged skill must **not** appear
in a persona's `include_skills`: verticals install beside the base pack in one flat namespace, so one
would silently overwrite the other and the loser is invisible. The validator rejects it.

## Two ways for a skill to differ by persona

**A constraint** prepends a boundaries section. Use it when the *work* is the same and the *rules*
differ.

**A conditional block** changes an instruction in place. Use it when the *work* differs:

```markdown
<!-- profile:analyst -->
Pull the figures yourself with `query-warehouse`.
<!-- /profile -->
<!-- profile:auditor -->
Request an extract through the engagement contact and record its provenance.
<!-- /profile -->
```

Reach for a constraint first. Injection alone would produce a file that forbids an action and then
explains how to perform it.

**Every group must name every persona.** One that should receive nothing gets an *explicit empty
block* — an absent block is indistinguishable from a forgotten one, and the persona it was forgotten
for silently receives nothing. Markers inside fenced code are documentation and ignored, which is why
the example above is safe to sit in this README.

**Frontmatter cannot vary by persona.** It is copied verbatim into every pack. So `description` must
be true for *all* of them — and it is the field that drives activation, so a description promising
what only one branch delivers makes the skill fire on a request the reader's own copy then declines.
No gate can catch that; it is a review question.

## MCP: entitlement is derived, not declared

A persona gets a server group only if its own skills or agents **name** the server. There is no `mcp`
key in a persona file, and the loader **raises** if one appears.

```
mcp/warehouse.json     access: restricted   loading: opt-in
```

Two axes, no defaults:

- **`access`** — `open`, or `restricted` for anything needing a credential, VPN or licence this tool
  cannot supply. Restricted **must** be opt-in.
- **`loading`** — `eager` starts with the session; `opt-in` ships switched off.

`loading` exists because a `mcpServers` entry in a Claude Code plugin manifest is **plugin-level**:
everything reachable from it connects at session start and stays connected regardless of which skill
runs. There is no per-skill lifecycle. Put a CRM server in the eager group and every user gets an
authenticated CRM connection while doing something unrelated.

**The one risk worth knowing: a prose mention entitles.** Matching cannot tell "use this server" from
"we deliberately do not use this server."

## What the build emits

```
dist/analyst-pack/
  skills/an-*/                        every host
  .claude-plugin/plugin.json          Claude Code manifest
  .mcp.json                           Claude Code: eager servers
  mcp-plugins/mcp-warehouse/          Claude Code: opt-in group as a companion plugin
  mcp/kiro-mcp.json                   Kiro: all servers, opt-in ones `disabled: true`
  mcp/warehouse.json                  plain shape, any other tool
  quick/*.quick                       Amazon Quick: hoisted frontmatter
.claude-plugin/marketplace.json       generated
.agents/plugins/marketplace.json      generated — Codex reads this
```

Both marketplaces are **generated**. Hand-kept, they drift from each other and from what the build
emits — and a stale entry fails at *install* time, not build time.

## Distributing it

Push the repo. Two of the four hosts install from it directly:

```bash
claude plugin marketplace add <owner>/<repo>   && claude plugin install analyst-pack
codex  plugin marketplace add <owner>/<repo>   && codex  plugin add analyst-pack@<repo>
python3 -m skillforge install --persona analyst   # Kiro
```

The marketplaces point at `dist/`, never the repo root — a skill with conditional blocks resolves
only at build time, so installing the source tree delivers every persona's contradictory
instructions in one file.

**Amazon Quick is a manual import**, and there is one fact worth putting on a sticky note: Quick reads
its skills **only at launch**, so between importing and relaunching the skill is installed and dead.

Quick also can't be spec-conformant — it wants `display_name`, `icon` and `trigger` as top-level
frontmatter, which the Agent Skills validator rejects. So they live under `metadata.quick_*` and are
hoisted into a separate `.quick` artefact. A skill carrying conditional blocks is **refused**, not
resolved: Quick has no persona concept, so choosing would ship one persona's boundaries to whoever
imports the folder.

## Installing safely

Two rules the installer keeps, because breaking either destroys someone's setup:

**Personas swap.** Installing one removes the other.

**Your own MCP servers are never deleted.** Entries this tool created are marked and only those are
removed. One that existed already is *adopted* — marked separately and restored to its original
enabled state on uninstall. A tool that prints "your own were left alone" and isn't telling the truth
is worse than one that says nothing.

## Getting started

```bash
git clone <this repo> && cd skillforge
python3 -m skillforge build --all --vertical all
python3 -m skillforge validate
```

Then replace the example content: two personas (`analyst`, `auditor` — deliberately in conflict), one
constraint, one vertical, five skills, two MCP groups. It exists to be deleted once you have your own.

## Status

**v0.1.0, early.** Working: the model, the build, all four host shapes, both marketplaces, Quick
variants, the Kiro installer with adopt/restore, and the validator.

Not built yet: agent generation with per-host tool grants, an eval runner, cross-host duplicate-skill
detection, and a mutation harness that proves each gate fails when it should. Those matter — the
per-host grant divergence in the table above is where most of the silent failures live — but skills,
personas, verticals and constraints work on all four hosts today.
