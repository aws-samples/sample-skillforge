---
name: start-here
description: Router for this pack — invoke it when you have a task but do not know which skill to run. Use when the user says "where do I start", "which skill", or describes a goal spanning several skills.
metadata:
  category: routing
---

# Start here

Take the goal, pick the skill, and say which one you picked and why. Do not answer from general
knowledge when a skill in this pack owns the question.

## Routing

<!-- profile:analyst -->
- Getting figures out of the warehouse → `query-warehouse`
<!-- /profile -->
<!-- profile:auditor -->
<!-- /profile -->
<!-- profile:engineer -->
- Getting figures out of the warehouse → `query-warehouse`
<!-- /profile -->
<!-- profile:project-manager -->
<!-- /profile -->
- Turning figures into something a person reads → `build-report`
- Anything touching customer records → `handle-customer-data`. Route here for the RULES even when
  another skill does the work.

## When you cannot tell

Ask exactly one question, then stop. Do not pick a skill on a guess and do not ask three questions
at once — one focused question gets an answer, a list gets abandoned.
