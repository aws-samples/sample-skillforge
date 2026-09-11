---
name: build-report
description: Turn figures into a written report with a stated method and stated limitations. Use when the user asks for a report, summary, write-up, or something to send onward.
metadata:
  category: reporting
  constraints: data-handling
  quick_trigger: write me a report
  quick_display_name: Build a report
  quick_icon: chart
---

# Build a report

## Structure

1. **What was asked** — one sentence, in the requester's words.
2. **What the figures say** — the numbers, each traceable to how it was produced.
3. **What they do not say** — the limitations. This section is the one that makes the report
   trustworthy, and the one most often dropped.
4. **What to do next** — only if the figures support it.

## Getting the figures

<!-- profile:analyst -->
Pull them yourself with `query-warehouse`, and keep the queries in an appendix so a reader can
re-run them.
<!-- /profile -->
<!-- profile:auditor -->
Request an extract through the engagement contact and record its provenance — who produced it, from
which system, on what date. You do not query systems directly, so an extract with no recorded
provenance cannot support a finding.
<!-- /profile -->

## Never

Do not round a figure to make a point, and do not present a projection as a measurement.
