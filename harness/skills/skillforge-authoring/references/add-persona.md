# Add a persona

## Create the persona

Use a lowercase kebab-case file name under `policies/personas/`; the file stem is the persona id.
Start from an existing persona and provide:

```json
{
  "display_name": "Data reviewer",
  "pack_name": "reviewer-pack",
  "prefix": "rv-",
  "description": "Skills for reviewers working from approved evidence.",
  "router": "start-here",
  "include_skills": [
    "start-here",
    "build-report",
    "handle-customer-data"
  ],
  "include_agents": ["reviewer"]
}
```

Keep the trailing hyphen in `prefix`. Do not add an `mcp` key; server entitlement is derived from
the resolved content included in the persona.

`include_agents` is optional. Every named id must have a canonical `agents/<id>.json`; read
`add-agent.md` before creating or changing one.

## Make existing content complete for the new persona

Every conditional group in every canonical skill and bundled text file must name the new persona.
Use an explicit empty branch if that persona receives no instruction. An absent branch is treated
as an authoring error.

For each constraint used by the new persona's skills, decide whether it applies:

- If it applies, add `policies/constraints/<constraint>/<persona>.md`.
- If it intentionally does not apply, leave it absent and verify that the resolved skill is still
  safe and internally consistent.

Add the persona id to each vertical it should support. Do not add every vertical automatically;
the vertical's `personas` list is an explicit compatibility statement.

## Acceptance checks

- The base pack is `dist/<pack_name>/`.
- Every included skill is prefixed exactly once.
- Every declared vertical builds `dist/vertical-<vertical>-<persona>/`.
- No resolved file contains a profile marker.
- The persona receives only MCP groups named by its resolved base content.
- Every included agent emits all four host grant shapes and a manifest entry.
