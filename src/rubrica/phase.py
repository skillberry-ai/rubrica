"""The run's phase declaration, and the one place a deferred candidate is resolved.

Phasing exists so a benchmark-ready world model is reachable in hours rather than
a day: the corpus's most expensive input kind is deferred to a later phase instead
of dropped. The measurement is in
`docs/superpowers/specs/2026-09-14-phased-trace-deferral-design.md` -- on the run
that motivated it, `trace` inputs were 78% of the corpus by bytes and 12% cited,
and were the majority source for exactly the two world-model outputs the benchmark
never reads. Of the 113 capabilities carrying a tool binding -- the drivable ones
the coverage denominator counts -- zero depended on a trace.

One module because the block is written by four stages (`triage-slices`,
`triage-seal`, `intake`, `reconcile-seal`) and read by six more, and a second
spelling of "is this candidate deferred" would let two of them disagree about what
the run can ever know. Nothing downstream of `intake` reads the corpus again, so
that disagreement is unrecoverable rather than merely wrong.

Every function here answers rather than raises. Five of the readers are on the
exit-0 report path (`gate-brief`, `run-summary`, `target-brief`) or run before
layer 1 has necessarily validated the document, and an exception escaping this
module would turn a missing optional field into exit 1 with empty stdout -- the
exit-code contract's second rule, and the whole class `findings.py` exists to
prevent.
"""

from __future__ import annotations

# The three literals the disposition contract adds, one home each. `defer` was
# three separate string constants in the first draft of this work and a partial
# rename is what makes a checker accept a value no writer produces -- the same
# argument `skills.SKILL_PREFIX` carries for the `rb-` prefix.
DEFER = "defer"
DEFER_REASON_CODE = "deferred_to_phase"

# The authority a code-written ruling carries. `triage` would attribute a policy
# flag's mechanical consequence to a prompt's judgment, and `human` would claim a
# person ruled on each of 68 candidates one at a time; the whole point of a
# kind-level instrument is that nobody did.
POLICY_AUTHORITY = "policy"


def read(document: object) -> dict | None:
    """The `phase` block of an artifact that carries one, else None.

    Both container guards are load-bearing and both are reachable: a `document`
    that is not a mapping is every pre-phasing artifact read through
    `refs._load`, which returns whatever the file holds, and a `phase` that is
    not a mapping is a hand-edited run -- which gate 0 explicitly invites.
    """
    if not isinstance(document, dict):
        return None
    block = document.get("phase")
    return block if isinstance(block, dict) else None


def deferred_kinds(block: dict | None) -> frozenset[str]:
    """The kinds this phase defers, as a set of strings.

    Empty for `None`, which is what makes every consumer's no-phase path
    byte-identical to the behaviour this package had before phasing: an empty set
    defers no candidate, so every writer's output is unchanged. Non-string members
    are dropped rather than raised on, for the reason the module docstring gives --
    and dropping them is safe because a kind that is not a string cannot equal a
    candidate's `kind` anyway, so this narrows nothing layer 1 would have kept.
    """
    if not isinstance(block, dict):
        return frozenset()
    raw = block.get("deferred_kinds")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(k for k in raw if isinstance(k, str))


def deferred_candidate_ids(candidates: object, block: dict | None) -> frozenset[str]:
    """Which of `candidates` this phase defers.

    `admissible is False` candidates are excluded deliberately. Such a candidate
    is a container whose *elements* are the candidates, and `refs.check_triage`
    already reports an admit of one; deferring it instead would put a container on
    phase 3's list of inputs to admit, where the same finding would be waiting. A
    member declines it today and still does under a phase, because it stays in the
    shard.

    `admissible` absent means admissible -- the catalogue writes the key only to
    say False -- so the test is `is not False` rather than a truthiness check that
    would also exclude every candidate that omits it.
    """
    kinds = deferred_kinds(block)
    if not kinds or not isinstance(candidates, list):
        return frozenset()
    return frozenset(
        cid
        for c in candidates
        if isinstance(c, dict)
        and isinstance(cid := c.get("candidate_id"), str)
        and c.get("kind") in kinds
        and c.get("admissible") is not False
    )
