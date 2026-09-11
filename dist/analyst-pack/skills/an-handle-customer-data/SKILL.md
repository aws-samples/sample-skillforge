---
name: an-handle-customer-data
description: The rules for touching customer records, and how to work without touching them. Use when a task involves personal data, when the user asks "can I use this data", or before any extract leaves a system.
metadata:
  category: policy
  constraints: data-handling
---

> Generated file — do not edit.
> Persona: analyst (Data analyst)
> Pack:    analyst-pack v0.2.0
> Source:  skill `handle-customer-data` @ 3d7e0fd
> Edit the source skill, not this copy — this one is overwritten on every build.

# Handling customer data

## Boundaries that apply to this skill

**Work in the warehouse, not in production.** Query the analytics warehouse, never an application
database directly — a long-running analytical query against production is an outage. Run
`SELECT current_database()` and confirm before your first query of a session.


## The line

Personal data stays in the system that holds it. Aggregate it, count it, join it — but an extract
containing identifiable records leaving that system needs a named owner who approved it, recorded
before the extract is made rather than after.

## Working without it

Most questions that seem to need identifiable records do not:

- **Counting** — aggregate in the query, extract only the aggregate.
- **Sampling for a demo** — generate synthetic records that share the shape and the edge cases. A
  synthetic set you designed is usually a *better* demo, because you control the edge cases.
- **Debugging a specific record** — work in the system, quote the field that matters, not the row.

## What to do when asked to cross it

Say no, then offer the aggregate or the synthetic alternative in the same reply. A refusal with no
route forward gets escalated over your head; a refusal with an alternative gets accepted.
