---
name: an-start-here
description: Router for this pack — invoke it when you have a task but do not know which skill to run. Use when the user says "where do I start", "which skill", or describes a goal spanning several skills.
metadata:
  category: routing
---

> Generated file — do not edit.
> Persona: analyst (Data analyst)
> Pack:    analyst-pack v0.2.0
> Source:  skill `start-here` @ d4ba273
> Edit the source skill, not this copy — this one is overwritten on every build.

# Start here

Take the goal, pick the skill, and say which one you picked and why. Do not answer from general
knowledge when a skill in this pack owns the question.

## Routing

- Getting figures out of the warehouse → `an-query-warehouse`
- Turning figures into something a person reads → `an-build-report`
- Anything touching customer records → `an-handle-customer-data`. Route here for the RULES even when
  another skill does the work.

## When you cannot tell

Ask exactly one question, then stop. Do not pick a skill on a guess and do not ask three questions
at once — one focused question gets an answer, a list gets abandoned.
