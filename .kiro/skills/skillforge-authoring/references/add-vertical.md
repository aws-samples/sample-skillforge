# Add a vertical

## Declare the vertical

Create `policies/verticals/<id>.json`; the file stem is the canonical id:

```json
{
  "id": "hipaa",
  "display_name": "HIPAA",
  "description": "Healthcare-specific rules and workflows.",
  "personas": ["analyst", "auditor"]
}
```

List only personas for which the vertical is meaningful and reviewed.

## Add its skills

Create ordinary canonical skills under `skills/<name>/SKILL.md` and tag each one:

```yaml
metadata:
  category: compliance
  vertical: hipaa
  constraints: data-handling
```

Never add a vertical-tagged skill to a persona's `include_skills`. Base and vertical packs install
into one flat skill namespace, so including it in both would make one copy hide the other.

Conditional groups inside a vertical skill must still name every known persona, not only the
personas listed by that vertical. The source remains globally reviewable even when only a subset is
built.

## Current host boundaries

Vertical packs intentionally ship no agents or MCP configuration. Do not introduce an MCP
dependency that is named only by a vertical skill; the current build derives MCP entitlement from
base-persona content.

Vertical packs also do not currently emit Amazon Quick variants. Do not promise a Quick artifact
without implementing and testing that build path.

## Acceptance checks

- One vertical pack is built for every declared persona.
- No vertical skill appears in a base pack.
- The persona prefix is applied to every vertical skill.
- The vertical pack contains no `.mcp.json`, `mcp/`, or `agents/`.
- Every profile block is resolved and every applicable constraint is injected.
