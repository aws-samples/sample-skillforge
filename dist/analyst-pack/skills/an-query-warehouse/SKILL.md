---
name: an-query-warehouse
description: Query the analytics warehouse and return figures with their provenance. Use when the user asks for numbers, counts, trends, or "pull the data for X". Names the tables and filters used so any figure can be traced.
compatibility: Drives the `warehouse-mcp` server, which is opt-in and needs a corporate SSO session. Falls back to writing the SQL for the user to run if it is not connected.
metadata:
  category: data
  constraints: data-handling
---

> Generated file — do not edit.
> Persona: analyst (Data analyst)
> Pack:    analyst-pack v0.2.0
> Source:  skill `query-warehouse` @ 3d7e0fd
> Edit the source skill, not this copy — this one is overwritten on every build.

# Query the warehouse

## Boundaries that apply to this skill

**Work in the warehouse, not in production.** Query the analytics warehouse, never an application
database directly — a long-running analytical query against production is an outage. Run
`SELECT current_database()` and confirm before your first query of a session.


Drives the `warehouse-mcp` server. If it is not connected, write the SQL and say plainly that it was
not run — a query you did not execute must never be reported as a result.

For a local extract or a sample database there is `sqlite-explorer`, which is eager and always
connected. Use it for shaping a query before running the real one; never present a figure from a
local sample as a warehouse figure.

## Steps

1. Restate the question as a measurable one. "Are customers happy" is not measurable; "share of
   orders with a return within 30 days" is.
2. Name the tables and filters before running anything, so the reader can challenge the shape of the
   answer rather than only the number.
3. Run it, then report the figure **with** the query that produced it. A number without its query
   cannot be checked and will be quoted for a year.
4. State what the figure does not cover. Every filter excludes something.
