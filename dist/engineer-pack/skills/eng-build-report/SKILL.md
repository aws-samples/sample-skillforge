---
name: eng-build-report
description: Turn figures into a written report with a stated method and stated limitations. Use when the user asks for a report, summary, write-up, or something to send onward.
metadata:
  category: reporting
  constraints: data-handling
  quick_trigger: write me a report
  quick_display_name: Build a report
  quick_icon: chart
---

> Generated file — do not edit.
> Persona: engineer (Software engineer)
> Pack:    engineer-pack v0.2.0
> Source:  skill `build-report` @ 3d7e0fd
> Edit the source skill, not this copy — this one is overwritten on every build.

# Build a report

## Boundaries that apply to this skill

**Use the least-sensitive environment that can reproduce the issue.** Start with synthetic fixtures
or approved non-production data. Do not copy customer records, production database rows, or
unredacted logs into source control, tickets, prompts, or local test data.


## Structure

1. **What was asked** — one sentence, in the requester's words.
2. **What the figures say** — the numbers, each traceable to how it was produced.
3. **What they do not say** — the limitations. This section is the one that makes the report
   trustworthy, and the one most often dropped.
4. **What to do next** — only if the figures support it.

## Getting the figures

Use reproducible evidence: commands, tests, logs, or queries that another engineer can run. Separate
what you observed from what you inferred, and keep the exact inputs needed to reproduce the result.

## Never

Do not round a figure to make a point, and do not present a projection as a measurement.
