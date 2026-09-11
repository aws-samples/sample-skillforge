# Add a canonical agent

Create `agents/<id>.json` using a lowercase kebab-case id. An agent is persona-level, so add that id
to the owning persona's `include_agents`; never put agents in a vertical.

Start from an existing definition and provide all four grant blocks:

```json
{
  "display_name": "Reviewer",
  "description": "Reviews evidence without changing source files.",
  "instructions": "Use the installed `start-here` and `build-report` skills.",
  "grants": {
    "claude": {
      "tools": ["Read", "Grep", "Glob", "Skill"],
      "model": "inherit"
    },
    "codex": {
      "sandbox_mode": "read-only",
      "web_search": "disabled"
    },
    "kiro": {
      "tools": ["read"],
      "allowed_tools": ["read"]
    },
    "quick": {
      "tools": []
    }
  }
}
```

There are no defaults. A missing host fails the build because silently inheriting a host's broad
tool set is unsafe.

## Host grant rules

- Claude Code grants are exact tool names. Do not use wildcards; they match nothing.
- Codex has no per-tool allowlist. Set its sandbox and web-search policy explicitly.
- Kiro's `allowed_tools` bypass approval and must be a subset of `tools`. MCP wildcards use the
  exact `@server/*` form.
- Quick's `tools` list is emitted into its JSON agent definition.

Reference canonical skill names in backticks. The build rewrites them with the persona prefix,
including compatible vertical skills.

## Generated files

A base persona pack emits:

```text
agents/<prefixed-id>.md                 Claude Code plugin agent
agents/codex/<prefixed-id>.toml         Codex custom-agent config
agents/kiro/<prefixed-id>.json          Kiro custom agent
agents/quick/<prefixed-id>.json         Amazon Quick import definition
agents/manifest.json                    cross-host inventory and grants
```

Kiro agents are reconciled with the selected persona. With `--host all`, Codex agent files and the
managed registration block in `config.toml` are also reconciled. User-owned or user-modified files
are preserved.

## Acceptance checks

- Every host block is present and validates in its native shape.
- The persona's generated agent name is prefixed exactly once.
- Every referenced skill name is rewritten.
- Vertical packs contain no agents.
- `python3 -m skillforge validate` accepts the generated manifest and all four files.
