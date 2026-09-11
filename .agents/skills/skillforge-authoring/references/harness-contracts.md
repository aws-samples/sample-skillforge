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
- A declared manifest name matches the pack directory.
- Every relative MCP pointer resolves.
- Each opt-in MCP group has a companion plugin and is disabled by default in the marketplace.

## Codex

- `.agents/plugins/marketplace.json` lists every generated pack and companion exactly once.
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

## External checks

Run standards and host CLI validators when installed. If a validator or authenticated harness is
unavailable, report the gate as skipped. Static contracts run on every change; model-backed harness
evaluations belong in an isolated workspace and should be opt-in.
