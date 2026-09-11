---
name: handle-customer-data
description: The rules for touching customer records, and how to work without touching them. Use when a task involves personal data, when the user asks "can I use this data", or before any extract leaves a system.
metadata:
  category: policy
  constraints: data-handling
---

# Handling customer data

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

<!-- profile:analyst -->
Say no, then offer the aggregate or the synthetic alternative in the same reply. A refusal with no
route forward gets escalated over your head; a refusal with an alternative gets accepted.
<!-- /profile -->
<!-- profile:auditor -->
Record the request and the refusal in the engagement file, then continue with the evidence you have.
An auditor asked to accept unapproved data has a finding, not a problem.
<!-- /profile -->
