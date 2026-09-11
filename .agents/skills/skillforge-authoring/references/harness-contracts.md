# Harness contracts

Use these checks when changing generated output, installation, marketplaces, or validation.

## Shared skill contract

- Every generated skill is a direct child of `skills/`.
- Directory name equals frontmatter `name`.
- No raw profile marker survives.
- The expected persona prefix appears exactly once.
- The exact expected base or vertical inventory is present.

## Claude Code

- Every pack has `.claude-plugin/plugin.json`.
- Persona agents are direct `agents/<name>.md` plugin components with exact tool names.
- A declared manifest name matches the pack directory.
- Every relative MCP pointer resolves.
- Each opt-in MCP group has a companion plugin and is disabled by default in the marketplace.

## Codex

- `.agents/plugins/marketplace.json` lists every generated pack and companion exactly once.
- Persona agents emit TOML under `agents/codex/`; `--host all` reconciles a marked registration
  block in the user's Codex config without replacing unrelated settings.
- Every local source path exists and resolves inside the repository.
- The Codex and Claude marketplaces advertise the same plugin names.

## Kiro

- The default agent discovers `.kiro/skills/` automatically. A custom agent explicitly lists
  `skill://.kiro/skills/skillforge-authoring/SKILL.md` in its `resources`.
- `mcp/kiro-mcp.json` contains every entitled server.
- Opt-in servers have `disabled: true`.
- Installing a persona plus verticals preserves all selected skills.
- Switching persona removes the old persona and its vertical variants.
- User-owned skill paths and MCP entries are never overwritten or deleted.
- Persona agents emit JSON with `tools` and `allowedTools`; installed agent files are reconciled
  with a hash manifest so user modifications are preserved.

## Amazon Quick

- Persona agents emit JSON definitions with an explicit `tools` list for manual import.
- Quick artifacts remain manual and require a relaunch after import.

## Cross-host gates

- `python3 -m skillforge eval` runs every checked-in trigger and non-trigger case against Codex,
  Claude Code, and Kiro discovery adapters.
- `cross-host-collisions` evaluates each persona's base pack plus every compatible vertical as one
  flat install set.
- `python3 -m skillforge mutate-test` gives every validation gate one representative defect and
  fails if any defect survives.

## External checks

Run standards and host CLI validators when installed. If a validator or authenticated harness is
unavailable, report the gate as skipped. Static contracts run on every change; model-backed harness
evaluations belong in an isolated workspace and remain opt-in.
