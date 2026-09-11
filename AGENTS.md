# Skillforge repository instructions

## Sources of truth

- Product inputs live under `skills/`, `agents/`, `policies/`, `mcp/`, and `skillforge/`.
- Repository authoring guidance lives under `harness/skills/`; its generated host copies are
  checked in so every harness discovers the same workflow.
- Tests, eval cases, and contributor documentation live under `tests/`, `evals/`, and `README.md`.
- Do not hand-edit `dist/`, `.claude-plugin/marketplace.json`,
  `.agents/plugins/marketplace.json`, or the generated authoring-skill copies under
  `.agents/skills/`, `.claude/skills/`, and `.kiro/skills/`.
- Personas swap. Verticals add. A vertical-tagged skill never belongs in a persona's
  `include_skills`.
- MCP entitlement is derived from the server names present in the resolved base-persona content;
  never add an `mcp` key to a persona.

## Persona and vertical work

Load the repository skill named `skillforge-authoring` before adding or changing a persona,
vertical, canonical agent or tool grant, policy constraint, profile block, or canonical `SKILL.md`.

Kiro's default agent discovers the workspace copy automatically. A custom Kiro agent must include
`skill://.kiro/skills/skillforge-authoring/SKILL.md` in its `resources` list.

The non-negotiable authoring rules are:

- A new persona must appear in every conditional group, using an explicit empty branch when it
  should receive no text.
- Use a constraint when the work stays the same but the boundary changes. Use a conditional block
  only when the work itself changes.
- A vertical skill declares `metadata.vertical` and installs beside the base pack. Do not add it to
  any persona's `include_skills`.
- Frontmatter is shared by every persona and must remain true for every resolved variant.
- Canonical agents declare explicit native grants for all four hosts; never infer a missing host.

## Required completion checks

Run these after relevant changes:

1. `python3 -m skillforge sync-harness --check`
2. `python3 -m skillforge build --all --vertical all`
3. `python3 -m skillforge validate`
4. `python3 -m skillforge eval`
5. `python3 -m skillforge mutate-test`
6. `python3 -m unittest discover -s tests -v`

If the canonical authoring skill changed, run `python3 -m skillforge sync-harness` before the checks.
Report a skipped external harness or standards validator as skipped, never as passed.
