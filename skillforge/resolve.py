"""Persona-conditional blocks, and policy-constraint injection.

Two mechanisms, and choosing between them is the first decision when a skill needs to differ by
persona:

    A CONSTRAINT prepends a boundaries section after the H1. Use it when the WORK is the same and
    the RULES differ — and one edit updates every skill that binds it.

    A BLOCK changes an instruction in place. Use it when the WORK differs. Injection alone would
    produce a file that forbids an action and then explains how to perform it, with "the boundary
    is above it" as the only defence.

Reach for a constraint first.

## Block rules, and why each exists

    <!-- profile:analyst -->
    Pull the figures from the warehouse directly.
    <!-- /profile -->
    <!-- profile:auditor -->
    <!-- /profile -->

Adjacent blocks form one group, and EVERY group must name EVERY persona. A persona that should
receive nothing gets an explicit empty block, never an absent one — an absent block reads exactly
like a forgotten one, and the persona it was forgotten for silently receives nothing.

HTML comments, so the unbuilt source still renders as a document.

Markers inside a fenced code block are documentation and are ignored, which is why the example
above is safe to sit in this docstring. To vary a fenced template, wrap the whole fence in each
branch.

Stripping runs BEFORE constraint injection, because stripping can move or delete the H1 that
injection anchors on.
"""

from __future__ import annotations

import re

OPEN = re.compile(r"<!--\s*profile:([a-z0-9-]+)\s*-->")
CLOSE = re.compile(r"<!--\s*/profile\s*-->")
FENCE = re.compile(r"^\s*(```|~~~)")


class BlockError(Exception):
    """A malformed or incomplete conditional group. Names the file and the fix."""


def _outside_fences(text: str):
    """Yield (index, line, in_fence) so markers inside fenced blocks can be ignored."""
    in_fence = False
    for i, line in enumerate(text.splitlines(keepends=True)):
        if FENCE.match(line):
            in_fence = not in_fence
            yield i, line, True
            continue
        yield i, line, in_fence


def groups(text: str) -> list[list[tuple[str, int, int]]]:
    """Conditional groups as [[(persona, start_line, end_line), …], …].

    Raises on an unopened, unclosed or nested marker — each of which produces a pack that either
    carries a raw marker or silently drops text.
    """
    spans: list[tuple[str, int, int]] = []
    current: tuple[str, int] | None = None
    for i, line, in_fence in _outside_fences(text):
        if in_fence:
            continue
        opened = OPEN.search(line)
        closed = CLOSE.search(line)
        if opened:
            if current:
                raise BlockError(
                    f"line {i + 1}: `profile:{opened.group(1)}` opens inside "
                    f"`profile:{current[0]}`. Nested blocks are refused — the resolved output "
                    f"depends on evaluation order, which is not something a reader can see.")
            current = (opened.group(1), i)
        elif closed:
            if not current:
                raise BlockError(f"line {i + 1}: `<!-- /profile -->` with nothing open")
            spans.append((current[0], current[1], i))
            current = None
    if current:
        raise BlockError(
            f"`profile:{current[0]}` opened at line {current[1] + 1} and never closed. Everything "
            f"after it would be delivered to one persona and no other.")

    # Adjacent spans are one group: a group is what must name every persona.
    out: list[list[tuple[str, int, int]]] = []
    for span in spans:
        if out and span[1] <= out[-1][-1][2] + 1:
            out[-1].append(span)
        else:
            out.append([span])
    return out


def check(text: str, known: set[str], label: str = "file") -> list[str]:
    """Problems with this file's conditional groups. Empty list means it is well formed."""
    problems: list[str] = []
    try:
        found = groups(text)
    except BlockError as exc:
        return [f"{label}: {exc}"]
    for n, group in enumerate(found, 1):
        named = [p for p, _, _ in group]
        unknown = sorted(set(named) - known)
        if unknown:
            problems.append(
                f"{label}: group {n} names unknown persona(s) {unknown}. Known: {sorted(known)}")
        absent = sorted(known - set(named))
        if absent:
            problems.append(
                f"{label}: group {n} does not name {absent}. Every group must name every persona "
                f"— give one that should receive nothing an EXPLICIT empty block, because an "
                f"absent block is indistinguishable from a forgotten one.")
        duplicated = sorted({p for p in named if named.count(p) > 1})
        if duplicated:
            problems.append(f"{label}: group {n} names {duplicated} more than once")
    return problems


def resolve(text: str, persona_id: str) -> str:
    """Keep this persona's branches, drop the others, remove every marker.

    Run on every file that ships — SKILL.md and the bundled trees alike. A file that ships
    unresolved delivers both personas' mutually exclusive instructions in one document.
    """
    try:
        found = groups(text)
    except BlockError:
        # A malformed file is the validator's problem to report, with a line number and a fix.
        # Failing the build here would report it as a crash instead.
        return text
    lines = text.splitlines(keepends=True)
    drop: set[int] = set()
    for group in found:
        for persona, start, end in group:
            drop.add(start)
            drop.add(end)
            if persona != persona_id:
                drop.update(range(start + 1, end))
    return "".join(line for i, line in enumerate(lines) if i not in drop)


def inject(body: str, sections: list[str], title: str) -> str:
    """Prepend a section after the H1, or at the top if there is none.

    After the H1 rather than before, because a document whose first line is a boundary notice
    rather than its own title reads as though the notice is the subject.
    """
    if not sections:
        return body
    block = f"{title}\n\n" + "\n\n".join(s.strip() for s in sections) + "\n"
    lines = body.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            rest = lines[i + 1:]
            gap = "" if rest and rest[0].strip() == "" else "\n"
            return "".join(lines[:i + 1]) + gap + "\n" + block + "\n" + "".join(rest)
    return block + "\n" + body
