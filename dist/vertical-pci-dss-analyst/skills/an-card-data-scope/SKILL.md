---
name: an-card-data-scope
description: Decide whether a system is in PCI DSS scope before designing anything that touches payment data. Use when the user mentions card numbers, PAN, cardholder data, payment flows, or asks whether PCI applies.
metadata:
  category: compliance
  vertical: pci-dss
  constraints: data-handling
---

> Generated file — do not edit.
> Persona: analyst (Data analyst)
> Pack:    vertical-pci-dss-analyst v0.2.0
> Source:  skill `card-data-scope` @ d4ba273
> Edit the source skill, not this copy — this one is overwritten on every build.

# Is it in PCI DSS scope?

## Boundaries that apply to this skill

**Work in the warehouse, not in production.** Query the analytics warehouse, never an application
database directly — a long-running analytical query against production is an outage. Run
`SELECT current_database()` and confirm before your first query of a session.


Establish scope **before** design, not after. Scope decided late is a rebuild.

## In scope

Any system that stores, processes or transmits cardholder data — and any system that can *reach*
one without a control between them. That second clause is the one people miss: a reporting box on
the same flat network as the payment service is in scope even if no card number is ever written to it.

## The primary account number

The PAN is the field that drives everything. If it is present, unmasked, in storage or in a log,
that system is in scope and so is its backup.

Ask three questions, in order:

1. Does the PAN enter this system at all?
2. If it does, is it stored, or only passed through?
3. What sits between this system and the payment service — a control, or nothing?

## Reducing scope beats satisfying it

Tokenise at the edge, and the systems behind it fall out of scope. That is nearly always cheaper
than bringing another system up to compliance, and it is the answer worth proposing first.
