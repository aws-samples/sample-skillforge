# Canonical skill quality

## Frontmatter

- The directory name and frontmatter `name` are identical lowercase kebab-case.
- `description` says what the skill does and when it should activate. It must remain true for every
  persona because frontmatter is shared.
- Keep host-specific fields under `metadata`; canonical top-level frontmatter follows the Agent
  Skills standard.
- Put Quick fields under `metadata.quick_*`; the build hoists them into separate artifacts.

## Persona differences

Use a constraint when the task is the same but policy or access differs. Use a conditional block
when the steps themselves differ.

Every adjacent profile group names every persona exactly once. Use an explicit empty branch rather
than omitting one. Keep the total number of groups small enough that the source remains readable;
split the skill when the workflow has become multiple skills in disguise.

## References and names

Keep procedural instructions in `SKILL.md` and substantial supporting detail in `references/`.
Ensure every linked file exists and every bundled text file resolves profile blocks correctly.

Reference other skills in backticks so the build can rewrite their names with the persona prefix.
After building, verify every rewritten skill reference names a skill that can be installed beside
the referring skill.

## MCP mentions

Naming an MCP server anywhere in resolved base-persona content grants its entire group to that
persona. Mention a server only when the skill actually needs it. A server named only by a vertical
skill is not currently entitled because vertical packs ship no MCP configuration. Restricted
servers are opt-in and must include an installation recipe when they use a bare executable.

## Verification

Run the complete build before validation so the built-pack and host-contract gates check real
artifacts rather than skipping them.
