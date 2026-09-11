# Skillforge

Write agent skills once. Ship them to **Claude Code, Codex, Kiro and Amazon Quick** — with your own
personas, your own policy rules, and optional domain add-ons.

```bash
python3 -m skillforge build --all --vertical all   # generate the packs
python3 -m skillforge validate                     # every gate
python3 -m skillforge install --persona analyst --vertical pci-dss
                                                   # Kiro; prints Claude Code / Codex commands
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

Maintain that by hand across several audiences and the artefacts multiply quickly. They drift, and
the failures are silent: a server that connects and exposes nothing, a skill that ships one
audience's rules to another, or a description the host truncated so the skill never fires.

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
  mcp-plugins/mcp-warehouse-analyst-pack/
                                      Claude Code: uniquely named opt-in companion
  mcp/kiro-mcp.json                   Kiro: all servers, opt-in ones `disabled: true`
  mcp/warehouse.json                  plain shape, any other tool
  quick/*.quick                       Amazon Quick: hoisted frontmatter
.claude-plugin/marketplace.json       generated
.agents/plugins/marketplace.json      generated — Codex reads this
```

Both marketplaces are **generated**. Hand-kept, they drift from each other and from what the build
emits — and a stale entry fails at *install* time, not build time.

`dist/` is generated but intentionally checked in: Claude Code and Codex install from the pushed
repository, where no build command runs before the marketplace resolves those paths.

## Distributing it

Push the repo. Two of the four hosts install from it directly:

```bash
claude plugin marketplace add <owner>/<repo>   && claude plugin install analyst-pack
codex  plugin marketplace add <owner>/<repo>   && codex  plugin add analyst-pack@<repo>
python3 -m skillforge install --persona analyst --vertical pci-dss   # Kiro
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

Three rules the installer keeps, because breaking them destroys someone's setup:

**Personas swap.** Installing one removes the other, including vertical variants built for the old
persona.

**Verticals add.** Select any number alongside the persona by repeating `--vertical`:

```bash
python3 -m skillforge install --persona analyst \
  --vertical pci-dss \
  --vertical another-domain
```

Use `--vertical all` to install every built vertical that declares the selected persona.

**Your own MCP servers are never deleted.** Entries this tool created are marked and only those are
removed. One that existed already is *adopted* — marked separately and restored to its original
enabled state when the persona changes or on uninstall. A tool that prints "your own were left
alone" and isn't telling the truth is worse than one that says nothing.

On macOS and Linux, Kiro skills are symlinked by default. On Windows they are copied by default, so
Developer Mode or administrator symlink privileges are not required. Use `--copy` or `--symlink` to
override the platform default. The mode actually used is recorded for later updates.

## Updating an installation

Every successful install writes a non-secret receipt to `.skillforge/install.json`. The directory is
gitignored, so the selection survives a pull without being committed. It records the persona,
verticals, install mode, output directory, marketplace name, version, and the resolved Kiro skills
and MCP paths. Use `--state <path>` on both `install` and `update` to keep it elsewhere.

Inspect the recorded selection without changing anything:

```bash
python3 -m skillforge update --check
```

Pull, rebuild, validate, and reconcile the same installation:

```bash
# macOS / Linux
./scripts/update.sh
```

```powershell
# Windows PowerShell
.\scripts\update.ps1
```

Both scripts use `git pull --ff-only`, so local changes or a diverged branch stop the update rather
than creating an automatic merge. The Python command can also be run directly after a manual pull:

```bash
python3 -m skillforge update
```

Kiro is reapplied automatically, including copy-mode Windows installations and MCP reconciliation.
When the receipt was created with the explicit `--host all` option, the updater also refreshes or
installs the recorded Claude Code and Codex plugins through their native CLIs. Pass `--no-native` to
print those commands without running them. Published plugin changes should also bump
`skillforge.json`'s version so native plugin caches recognize the release.

## Getting started

```bash
git clone <this repo> && cd skillforge
python3 -m skillforge sync-harness --check
python3 -m skillforge build --all --vertical all
python3 -m skillforge validate
python3 -m unittest discover -s tests -v
```

The checked-in examples now include four personas (`analyst`, `auditor`, `project-manager`, and
`engineer`), one constraint family, three verticals, nine skills, and two MCP groups. The project
manager pairs with `project-delivery`; the engineer pairs with `software-engineering`:

```bash
python3 -m skillforge install --persona project-manager --vertical project-delivery
python3 -m skillforge install --persona engineer --vertical software-engineering
```

They are examples to adapt or delete once you have your own content.

## Authoring with Codex, Claude Code or Kiro

The repository keeps one short instruction source in `AGENTS.md`. Claude Code imports it through
`CLAUDE.md`; Codex and Kiro read it directly.

Persona and vertical procedures live in the canonical
`harness/skills/skillforge-authoring/` skill. Generated copies are checked in under:

```
.agents/skills/skillforge-authoring/   Codex
.claude/skills/skillforge-authoring/   Claude Code
.kiro/skills/skillforge-authoring/     Kiro
```

Kiro's default agent discovers the workspace skill automatically. If a project uses a custom Kiro
agent, add `skill://.kiro/skills/skillforge-authoring/SKILL.md` to that agent's `resources` list.

Edit only the canonical copy, then synchronize and verify:

```bash
python3 -m skillforge sync-harness
python3 -m skillforge sync-harness --check
```

The skill routes persona, vertical, canonical-skill, and host-contract work to focused references so
ordinary sessions carry only the short routing instructions.

## Test layers

`python3 -m unittest discover -s tests -v` covers:

- adding a persona successfully and rejecting one missing conditional branches;
- adding a vertical successfully and rejecting base/vertical collisions;
- exact base and vertical skill inventories;
- resolved names, constraints and conditional blocks;
- Claude Code and Codex marketplace agreement;
- Kiro MCP and install/swap safety;
- JSON receipt replay, copy-mode updates, and Windows/Unix update entry points;
- reproducible builds and synchronized harness instructions.

The official `skills-ref` validator runs automatically when installed. Claude Code's strict plugin
validator plus isolated local-marketplace installs in Claude Code and Codex are opt-in external
gates:

```bash
SKILLFORGE_RUN_EXTERNAL_HARNESSES=1 \
  python3 -m unittest discover -s tests -p 'test_external_validators.py' -v
```

Host-neutral should-trigger and should-not-trigger cases live in
`evals/skillforge-authoring.json` for replay in clean Codex, Claude Code and Kiro workspaces.

## Status

**v0.1.0, early.** Working: the model, the build, all four host shapes, both marketplaces, Quick
variants, the Kiro installer with persona + vertical reconciliation and MCP adopt/restore, shared
repository authoring instructions for Codex/Claude Code/Kiro, recorded cross-platform updates,
contract tests, and the validator.

Not built yet: agent generation with per-host tool grants, an automated runner for the checked-in
eval cases, cross-host duplicate-skill detection, and a full mutation harness that proves every gate
fails when it should. Those matter — the per-host grant divergence in the table above is where most
of the silent failures live — but skills, personas, verticals and constraints work on all four hosts
today.
