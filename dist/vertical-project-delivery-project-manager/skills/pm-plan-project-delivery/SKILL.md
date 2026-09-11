---
name: pm-plan-project-delivery
description: Turn an outcome into an executable project plan with milestones, owners, dependencies, risks, and acceptance evidence. Use when the user asks for a project plan, delivery plan, milestone plan, work breakdown, or launch plan.
metadata:
  category: delivery
  vertical: project-delivery
---

> Generated file — do not edit.
> Persona: project-manager (Project manager)
> Pack:    vertical-project-delivery-project-manager v0.2.0
> Source:  skill `plan-project-delivery` @ 3d7e0fd
> Edit the source skill, not this copy — this one is overwritten on every build.

# Plan project delivery

Build the smallest plan that makes ownership, sequence, and proof of completion unambiguous.

## Steps

1. State the outcome and the date or condition that defines success.
2. Split the work into milestones that each produce a reviewable result, not percentages of effort.
3. Give every milestone one accountable owner and name its dependencies.
4. Record the highest-impact risks with an owner, a next action, and a decision date.
5. Define acceptance evidence for every milestone so “done” can be checked rather than asserted.
6. Identify customer-data needs early and use `pm-handle-customer-data` before requesting an extract.

## Output

Use a compact table with milestone, owner, dependency, target, acceptance evidence, and status.
Separate confirmed commitments from proposed dates. When the plan needs to be sent onward, use
`pm-build-report` and preserve the source and date of each status claim.

## Never

Do not hide an unknown behind a precise date. Mark it as an assumption, name who can resolve it, and
set the next decision point.
