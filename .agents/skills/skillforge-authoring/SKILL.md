---
name: skillforge-authoring
description: Add or modify Skillforge personas, verticals, canonical agents, policy constraints, and agent skills. Use when asked to add, create, or change a persona or audience pack, a vertical or domain/compliance add-on, an agent or per-host tool grant, a profile branch, a constraint, or a source SKILL.md in a Skillforge repository. Do not use only to install an already-built pack.
metadata:
  category: development
---

# Author Skillforge content

Work in the canonical source trees. Do not hand-edit generated packs, marketplaces, or host copies
of this authoring skill.

## Route the change

- For a persona or audience pack, read [references/add-persona.md](references/add-persona.md).
- For a vertical, domain pack, or compliance add-on, read
  [references/add-vertical.md](references/add-vertical.md).
- For a canonical agent or per-host tool grant, read
  [references/add-agent.md](references/add-agent.md).
- For a new or changed canonical skill, constraint, profile block, or MCP mention, read
  [references/skill-quality.md](references/skill-quality.md).
- When changing build, install, validation, marketplace, or host-specific output behavior, also
  read [references/harness-contracts.md](references/harness-contracts.md).

Read only the references needed by the current request.

## Shared invariants

- Personas swap; verticals add.
- Every conditional group names every persona, including explicit empty branches.
- Prefer a constraint for different boundaries and a profile block for genuinely different work.
- A vertical-tagged skill is excluded from every persona's `include_skills`.
- Persona frontmatter is shared and cannot make promises that only one resolved branch fulfils.
- MCP entitlement is derived; do not declare it on a persona.
- Every canonical agent declares explicit grants for Claude Code, Codex, Kiro, and Amazon Quick.

## Finish

If this canonical authoring skill changed, run:

```bash
python3 -m skillforge sync-harness
```

Then build and verify the complete matrix:

```bash
python3 -m skillforge build --all --vertical all
python3 -m skillforge validate
python3 -m skillforge eval
python3 -m skillforge mutate-test
python3 -m unittest discover -s tests -v
```

Inspect the resulting diff. Source changes should be intentional; generated changes should follow
from the build or harness sync.
