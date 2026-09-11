---
name: review-code-change
description: Review a code change for correctness, regressions, security, operability, and missing tests, with findings tied to concrete evidence. Use when the user asks for a code review, diff review, pull-request review, or pre-merge assessment.
metadata:
  category: engineering
  vertical: software-engineering
---

# Review a code change

Find defects that change outcomes. Do not turn style preferences into blockers.

## Review order

1. Read the intended behavior and acceptance criteria from `design-technical-change` or the change
   description.
2. Trace changed inputs through state changes, external calls, and returned outputs.
3. Check error paths, authorization boundaries, concurrency, retries, and backward compatibility.
4. Inspect tests for the risky behavior, not just the lines that changed.
5. Run the narrowest relevant checks when possible and distinguish executed evidence from static
   inspection.

## Findings

For each finding, state the affected behavior, where it occurs, why it matters, and the smallest
credible fix. Lead with findings in severity order. If there are none, say so and identify any
tests or environments you could not verify.
