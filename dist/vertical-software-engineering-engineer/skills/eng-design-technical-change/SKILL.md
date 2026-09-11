---
name: eng-design-technical-change
description: Design a bounded technical change with requirements, interfaces, failure modes, rollout, rollback, and verification. Use when the user asks for an implementation plan, technical design, architecture change, migration design, or engineering approach.
metadata:
  category: engineering
  vertical: software-engineering
---

> Generated file — do not edit.
> Persona: engineer (Software engineer)
> Pack:    vertical-software-engineering-engineer v0.2.0
> Source:  skill `design-technical-change` @ d4ba273
> Edit the source skill, not this copy — this one is overwritten on every build.

# Design a technical change

Prefer the smallest reversible change that satisfies the requirement.

## Steps

1. Restate the required behavior and the observable acceptance criteria.
2. Map the components, interfaces, state, and owners affected by the change.
3. Describe the proposed flow, including validation and authorization boundaries.
4. Enumerate failure modes, partial-success states, and recovery behavior.
5. Plan tests at the narrowest useful level, then add integration coverage at changed boundaries.
6. Define rollout signals, rollback conditions, and any data migration or compatibility window.
7. If diagnosis or testing may touch customer records, follow `eng-handle-customer-data` first.

## Output

Separate facts discovered in the repository from assumptions that still need confirmation. Include
rejected alternatives only when the tradeoff matters to implementation or review.
