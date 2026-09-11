---
name: pm-report-project-status
description: Produce a concise, evidence-based project status update with progress, decisions, risks, dependencies, and next actions. Use when the user asks for a weekly status, steering update, RAG report, executive update, or delivery summary.
metadata:
  category: delivery
  vertical: project-delivery
---

> Generated file — do not edit.
> Persona: project-manager (Project manager)
> Pack:    vertical-project-delivery-project-manager v0.1.0
> Source:  skill `report-project-status` @ ee70cb5
> Edit the source skill, not this copy — this one is overwritten on every build.

# Report project status

Report movement and decisions, not activity volume.

## Steps

1. Reuse the outcomes and milestones from `pm-plan-project-delivery`.
2. For each status claim, record the owner, evidence, and date last confirmed.
3. Explain changes since the previous update: completed outcomes, changed dates, new risks, and
   decisions made.
4. Escalate only items that need a named decision or action, with the latest useful decision date.
5. End with the next milestone and what evidence will show it is complete.

Use `pm-build-report` for the final narrative. Never convert “work started” or “most tasks complete”
into a green status without acceptance evidence.
