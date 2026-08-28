"""`gate-brief`: the human surface at all four human gates.

A composer, not a new analysis -- it renders reports
that already exist (`utilisation.claim_utilisation`, coverage, verdicts) plus
`sizing.implied_size`, in the shape each gate's human decision actually needs:

- **Gate 0** is this build's new one, and it is what decides whether gate 0 is
  holdable at all. It leads with the objective verdict -- supported or not --
  because that is the single fact most likely to make a tired reader overturn
  the whole triage record, and a reader who stops after ten lines must have
  seen it. The predicted-vs-observed surface divergence follows immediately,
  because it is the one available measure of how well the corpus map the
  objective pass ruled from actually described the corpus. Admits by priority,
  declines grouped by reason code, and every open deficiency beside the
  projection that would close it come next. The slice table and the summary of
  every group split across more than one slice close the brief: they are the
  mechanics of *how* the fan-out read the corpus rather than *what* it ruled,
  so a reader who only wants the ruling never has to scroll past them, and a
  reader weighing a `near_duplicate` decline has the split that produced the
  residue on the same page.
- **Gate 1** puts the world model's gaps next to the triage record's open
  deficiencies -- a pairing that is deliberately *not* a
  mechanical check (matching gap prose to decline prose is semantic, the same
  hole `check-refs` leaves for a claim's support). Both sides of that pairing are
  listed, each gap and each open deficiency by its id and its prose statement,
  so for that one call this rendering really is the whole instrument. Claim
  utilisation and the implied suite size are reported alongside it, and the
  reconcile sweep comes first: how many subjects cover how many claims, how
  many subjects were swept for contradictions, how many contradictions were
  recorded, and -- only when that count is non-zero -- the tally by
  `resolution`, which names `unresolved` at
  zero whenever that branch renders at all. The sweep is an **aggregate**, and
  saying so matters: it renders counts, never the contradictions themselves, so
  it is a pointer at `01-contradictions/` rather than a substitute for reading
  it. That is still worth leading with, because cross-pass incoherence -- a
  later pass quietly modelling what `rb-reconcile-contradict` recorded
  `unresolved` -- is not something layer 2 can see, and a non-zero `unresolved`
  in the tally is the cheapest signal that there is a part worth opening.
  Read coverage is reported *per pass* beside the per-input utilisation, and the
  two are not the same measure: utilisation is a fact about an input, and issue
  #6 measured a run where averaging it across every citing pass reported 33.6%
  while one pass was citing 110 of 135 claims of its own kind and another 2 of
  38. Each pass's own-kind rate is its own line, and only the rows that dropped
  a claim are printed under it, each beside the note the drop required. A pass
  that wrote no readable accounting gets a line too, saying so: a pass silently
  missing from a block of four is the anomaly a reader is at this gate to notice.
  The capabilities the coverage denominator *excludes* are listed here too, and
  what makes this listing matter is its timing rather than any uniqueness: the
  same exclusion is reported twice more, and both are too late to act on.
  `seal_score` writes one `unreachable` hole per undrivable cell into the round's
  coverage document (rounds.py:1325-1335), which a reader meets at gate 2, and
  `emit` names a single unbound capability per instance at stage 06
  (emit.py:99-107, documented in world-model-0.1.json). Gate 1 precedes propose,
  so a reader who does not act here has the loop spend every round against the
  narrowed denominator before either of those two says a word. Issue 17 narrowed
  `denominator.capability_cells` to the cells a scenario can be driven through,
  and the finding that was to have accompanied it miscategorised its own
  condition -- `check-refs` exit 1 buys one stage re-dispatch, which cannot add a
  binding `rb-reconcile-capabilities` was told not to guess. Both numbers print
  either way, for the sweep's reason. Nothing here classifies *why* a binding is
  absent, because that is semantic; the operation and the citing inputs are
  printed so a reader can group them, and the remedy is named because a reader at
  this gate is the last person who can act on it.
- **Gates 2 and 3** render what already exists: the coverage verdict, and the
  challenge stage's verdict tallies.

`gate_brief` treats a readable run's *content* as something to render, never to
raise on -- every artifact it reads is optional, and its absence renders as a
stated absence rather than an exception, on the same ruling that already governs
`claim_utilisation`: a report is never a gate, so it exits 0. One measured
exception to that promise is open and on the record, and it arrives through this
module's own unguarded `claim_utilisation(run)` call in `_gate_1`: three
hand-edited `01-claims/` shapes raise out of that report, taking
`gate-brief --gate 1` to exit 1 with them. `docs/design/limitations.md` records
which shapes and why the half that was closed did not reach this one. A run
directory that cannot be read at all is a different failure (the harness pointed
at something broken), and is left to raise -- `cli.py`'s shared catch maps that
to exit 2 like every other subcommand's.
"""

from __future__ import annotations

from rubrica.artifacts import read_json
from rubrica.errors import UsageError
from rubrica.intake import admit_sort_key
from rubrica.paths import RunPaths, list_json

# Imported rather than re-spelled, private name and all: `_as_list` is the one
# definition of "a list or nothing" in this build, and its docstring carries the
# measurement (`value or []` lets a truthy non-list reach a bare `for` and raise
# TypeError). A local copy beside `_dicts` and `_mapping` would be a second
# spelling of that guard, and half-a-module's-worth of inconsistent isinstance
# checks is the defect `_dicts` exists to have fixed.
# PASS_OWN_KINDS is public for exactly this import: which reconcile pass is
# accountable for which claim kind is a *judgment*, and a second copy of it here
# would let the gate's reading surface and the checker that recomputes the
# numbers come to disagree about what a per-pass rate means -- the drift
# utilisation.py exists as its own module to refuse.
# `_cells` and `drivable_cells` are imported for the same reason and with the same
# reservation: the denominator's arithmetic has exactly one definition in this
# build -- `reconcile-seal` writes `len(drivable_cells(world))` and
# `check_world_model` recomputes it -- and a second spelling here would let the
# gate's reading surface and the field it is describing come to disagree about what
# a cell is. Both index unguarded (`cap["id"]`, `oc["id"]`), which is why
# `_cell_counts` below wraps them rather than calling them straight.
from rubrica.refs import PASS_OWN_KINDS, _as_list, _cells, drivable_cells
from rubrica.sizing import implied_size
from rubrica.utilisation import claim_utilisation

GATES = (0, 1, 2, 3)

# Gate 0's three staged-triage section headers, named once. Each is the anchor a
# reader -- and a test -- scopes to, so a rewording that only lands in one of
# two places would silently unscope an assertion to the whole document.
DIVERGENCE_HEADER = "Surface divergence (predicted vs observed)"
SLICES_HEADER = "Slices the triage family read"
SPLIT_HEADER = "Groups split across more than one slice"

# Gate 1's excluded-capability section header, named for the three above's reason:
# it is the anchor a reader and a test both scope to. What this section reports is
# reported twice more and both times too late -- `seal_score` writes one
# `unreachable` hole per undrivable cell (rounds.py:1325-1335), read at gate 2, and
# `emit` names one capability per instance at stage 06 (emit.py:99-107) -- so what
# this listing has over both is that gate 1 precedes propose, and a reader here can
# still act. The design's paired `check-refs` finding was removed in 11a6c25 for a
# different reason than timing, and the two must not be conflated: a `1` from
# `check-refs` tells the orchestrator to spend its one repair attempt on a stage,
# and no re-dispatch adds a binding `rb-reconcile-capabilities` was told to leave
# off rather than guess -- so the finding miscategorised its own condition. Its
# running before this gate is what would have made that fatal rather than merely
# wrong: derived from A3 and A4, never observed, since no orchestrated run was
# dispatched against an unbound world model to watch the halt.
EXCLUDED_HEADER = "Capabilities excluded from the denominator (no tool binding)"


def gate_brief(run: RunPaths, gate: int) -> str:
    """Plain text (a human reads this, not a machine), never JSON."""
    if gate not in GATES:
        raise UsageError(f"unknown gate {gate!r}; expected one of {GATES}")
    return {0: _gate_0, 1: _gate_1, 2: _gate_2, 3: _gate_3}[gate](run)


def _quietly(path):
    """The document at `path`, or None. A malformed or absent artifact is some
    other command's finding to report (validate's, check-refs'); duplicating
    that here would double-count the same defect and, worse, would make a
    report crash instead of stating what it could not read."""
    try:
        return read_json(path)
    except Exception:  # deliberate, matching utilisation._quietly's reasoning
        return None


def _dicts(value) -> list[dict]:
    """The dict members of `value`, or `[]` if it is not a list at all.

    `_quietly` above only guards the document; every loop below then indexed
    into that document's *elements* with a bare `.get`, and half of them had an
    `isinstance` guard while their siblings in the same function did not. A
    triage record carrying `"deficiencies": ["oops-a-string"]` -- which is
    precisely the shape a human hand-editing the document gate 0 invites them
    to hand-edit produces -- raised `AttributeError: 'str' object has no
    attribute 'get'` and turned this command into a fabricated `[internal]`
    finding at exit 1.

    That is two promises at once: this module's docstring says `gate_brief`
    never raises on a readable run's *content*, and the exit-code contract's
    ruling for a report (claim-utilisation's, restated at cli.py's gate-brief
    arm) is that it always exits 0 on a readable run, so an orchestrator
    reading its code cannot mistake data for a defect. A report that reports
    "this document is malformed" by crashing is the least useful reading of a
    document, and gate 0 is not holdable without it.

    Silently dropping the malformed element is deliberate and is the *only*
    thing this can do: raising breaks the promise above, and inventing a
    finding is `validate`'s job -- run `rubrica validate --stage triage` and
    the schema names it precisely. Each caller states the count it rendered, so
    a dropped element shows up as a number that disagrees with the file.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, dict)]


def _mapping(value) -> dict:
    """`value` if it is a dict, else `{}`.

    The `x.get("y") or {}` idiom this replaces substitutes only on a *falsy*
    value, so a truthy non-dict -- `"objective_review": "nope"`,
    `"capability_matrix": "x"` -- reached `.get` and raised AttributeError.
    Measured at gates 0, 1 and 2, all three at exit 1.
    """
    return value if isinstance(value, dict) else {}


def _strings(value) -> list[str]:
    """The string members of `value`, or `[]` if it is not a list at all.

    `_dicts`' sibling, for the fields whose elements are ids rather than
    objects -- `candidate_ids`, `other_slices`, a surface's `evidence`. The
    same measured failure applies: a hand-edited `"other_slices": "s02"` is a
    string, iterating it yields characters, and every one of them would be
    counted as a slice holding the group.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, str)]


def _count(value) -> int:
    """`value` if it is an integer, else 0 -- for a field this module *sums*.

    `_dicts`' and `_mapping`'s sibling, and the one whose absence does not fail
    cleanly: a comparison against a string reports, but `sum` over one raises
    `TypeError: unsupported operand type(s) for +: 'int' and 'str'`. Measured in
    refs.check_input_dispositions with `"cited": "2"` in 01-outcomes.json, at
    exit 1 with one fabricated `[internal]` finding that loses every real finding
    in the run; here the loss would be the whole gate-1 brief.

    Counting the malformed value as 0 makes the rendered total disagree with the
    file, which is deliberate and is the softer of the two failures: the
    disagreement is recoverable by reading the artifact, and layer 1 rejects the
    non-integer by name (`inputs-seen-0.1.json` requires an integer) while
    check_input_dispositions reports it against the row it sits on.

    One JSON type slips through as itself rather than as 0: `isinstance(True, int)`
    is True in Python, so `"cited": true` sums as 1. Left alone deliberately --
    narrowing it would put a `bool` special case in a guard whose whole job is to
    not be interesting, and layer 1 rejects the boolean either way.
    """
    return value if isinstance(value, int) else 0


def _cell_counts(world: dict) -> tuple[int, int] | None:
    """(drivable, declared) distinct capability x outcome-class cells, or None.

    None means "could not be counted", and the caller says so rather than
    printing a number it does not have. `refs._cells` and `refs.drivable_cells`
    are the two functions in this module's reach that index unguarded, and every
    shape a hand-edit at gate 1 produces reaches them. Measured: `"capabilities":
    "nope"` raises `AttributeError: 'str' object has no attribute 'get'` out of
    both, a capability with no `id` raises `KeyError: 'id'` out of `_cells`, and
    `"outcome_classes": "x"` raises `TypeError: string indices must be integers`
    out of `_cells`. Any one of them would take `gate-brief --gate 1` to exit 1 on
    a readable run with a fabricated `[internal]` finding, which is exactly the
    breach `_dicts` and `_mapping` exist to have closed.

    Guarded here rather than in `refs`: those two are a *checker's* readers, and
    `check_world_model` recomputing the denominator over a malformed document
    should raise into `validate`'s territory rather than quietly count less. It is
    this report that is forbidden to fail, so the guard belongs on this side of
    the call, and `rubrica validate --stage reconcile-seal` is what names the
    defect a None here stands for.
    """
    try:
        return len(drivable_cells(world)), len(_cells(world))
    except Exception:  # deliberate, matching _quietly's reasoning
        return None


def _claim_sources(run: RunPaths) -> dict[str, str]:
    """claim id -> the input id that asserted it, for every readable claims file.

    Its own walk rather than `utilisation.claim_utilisation`, which aggregates to
    cited/total per artifact and never exposes the per-claim mapping this needs.
    `_quietly` per file rather than per directory, so one malformed member costs
    its own claims and not every capability's input list -- the promise this
    module's docstring makes, that a report states what it could not read instead
    of crashing.
    """
    sources: dict[str, str] = {}
    for path in list_json(run.claims_dir):
        payload = _mapping(_quietly(path))
        artifact_id = payload.get("artifact_id")
        if not isinstance(artifact_id, str):
            # The filename is what a reader opens next, and `RunPaths.claims`
            # derives it from the artifact id -- so it is the same string on every
            # document this pipeline wrote, and a usable fallback on one it did not.
            artifact_id = path.stem
        for claim in _dicts(payload.get("claims")):
            claim_id = claim.get("id")
            if isinstance(claim_id, str):
                sources[claim_id] = artifact_id
    return sources


def _excluded_lines(run: RunPaths, world: dict) -> list[str]:
    """The `EXCLUDED_HEADER` section: what the denominator does not count.

    Why a human has to read this rather than a checker: absence of `binding.tool`
    has three causes on the one run it was measured against -- a dependency
    declaration that is not target behaviour at all, a real surface on another
    interface, and real agent-level behaviour that `binding`'s tool shape cannot
    express -- and telling them apart is semantic, which layer 2 is forbidden to
    mechanise. So this prints each capability's cells, its `operation` and the
    inputs whose claims it rests on, and lets the reader group them. Counted off
    this rendering on run-20260827-070444: 10 of the 19 excluded capabilities cite
    `pyproject-toml`, 4 of them citing nothing else, and those 4 are dependency
    declarations (`cap-ollama-backend`, `cap-openai-backend`, `cap-keycloak`,
    `cap-langchain-community`). That grouping is the actual cause of the magnitude,
    and it is visible here without this report having asserted it.
    """
    lines = [EXCLUDED_HEADER]
    capabilities = _dicts(world.get("capabilities"))
    # `_mapping(cap.get("binding"))` rather than `cap.get("binding", {})`, for the
    # reason drivable_cells records: an explicit `binding: null` is what a
    # hand-edit at this gate produces, and the second spelling returns None and
    # raises AttributeError on the chained `.get`.
    unbound = [cap for cap in capabilities if not _mapping(cap.get("binding")).get("tool")]
    drivable = len(capabilities) - len(unbound)

    if not capabilities:
        # Never "all 0 capabilities are drivable", which is what the branch below
        # renders on an empty list: it is a claim about a surface that does not
        # exist. The two states behind that empty list are separated on `is_file`,
        # the same line the read-coverage block draws for a pass's partial, because
        # a reader acts differently on each -- a run that stopped short of the seal
        # is not the same thing as a sealed world model declaring nothing, and
        # `capabilities: []` is schema-valid (world-model-0.1.json sets no minItems).
        state = (
            "the world model declares no readable capability"
            if run.world_model.is_file()
            else "no world model yet"
        )
        lines.append(f"  ({state}; nothing to report)")
        return lines

    if not unbound:
        # Stated rather than omitted, for the reconcile sweep's reason: rendering
        # "every capability is drivable" as silence hides a strong claim.
        lines.append(f"  all {len(capabilities)} capabilities are drivable")
    elif drivable:
        lines.append(
            f"  {drivable} of {len(capabilities)} capabilities are drivable; "
            f"{len(unbound)} are excluded below"
        )
    else:
        # The loudest thing this brief says, and the volume is the point: gate 1
        # precedes propose, so a reader here is the last person who can act before
        # the loop spends its rounds -- and on the one shape that halts, `goals: []`
        # with nothing bound, gate 1 is also the only place anyone can tell a world
        # model with no drivable surface from a run that converged, because the loop
        # stops before a coverage document exists. Scoped to that shape on purpose:
        # with goals present the loop runs, seal_score writes its `unreachable` holes
        # with the "declares no binding.tool" justification, and
        # summary_html._hole_reason sets those apart from the open ones -- so a gate-2
        # reader can tell the two apart as well, only later and after the spend.
        # A number in a table is not enough to make anyone look either way.
        #
        # Phrased off the binding count rather than off the cell count, which the
        # line below may not have: `_cell_counts` returns None on a malformed
        # document, and "the denominator is 0 cells" would then be a number this
        # report does not have. "No capability is bound" is computable either way,
        # and it is the premise the rest of the sentence needs.
        #
        # The "no closable holes" clause is conditional, and measured. With nothing
        # bound and `goals: []`, `propose-batches` prints "no closable holes: there
        # is no propose round to dispatch" and exits 0 -- the loop's normal terminal
        # state reached from an entirely undrivable world model. But goal holes are
        # closable independently of any binding: on the same world model with the
        # toy's two goals restored, `propose-batches` wrote `02-batches/round-1.json`
        # and the loop continued, proposing against goals with no capability surface
        # underneath. Both readings are bad and only the second is survivable, so the
        # rendering must not assert the halt as a certainty.
        #
        # Each line stays under 100 characters: a banner that wraps stops being a
        # banner. Measured at 215 on the first draft, where the closing `***` landed
        # mid-paragraph at 80 and 120 columns and everything after the first visual
        # line read as prose -- which costs exactly the loudness these lines exist
        # for. How the warning splits across them is editorial; the fence is not.
        lines.append(
            f"  *** NOTHING IS DRIVABLE: 0 of {len(capabilities)} capabilities declare "
            "binding.tool. ***"
        )
        lines.append(
            "  *** No cell is drivable, so no scenario can exercise a capability against "
            "the target. ***"
        )
        lines.append(
            '  *** If nothing else is closable either, propose-batches exits 0 with "no '
            'closable holes". ***'
        )
        lines.append(
            "  *** That is NOT a converged run: the suite it leads to has no capability "
            "coverage. ***"
        )

    counts = _cell_counts(world)
    if counts is None:
        lines.append(
            "  (the capability x outcome-class cells could not be counted; run "
            "`rubrica validate --stage reconcile-seal`)"
        )
    else:
        drivable_count, declared = counts
        lines.append(
            f"  {drivable_count} of {declared} capability x outcome-class cells count "
            "toward the denominator"
        )

    if not unbound:
        return lines

    source = _claim_sources(run)
    for cap in unbound:
        raw_id = cap.get("id")
        # Rendered as an absence rather than as `None`: a row reading "None" reads
        # as an id, and layer 1 is what names a capability with no id.
        cap_id = raw_id if isinstance(raw_id, str) else "(no id)"
        # Distinct ids, matching what the denominator counts -- a repeated
        # outcome-class id is one cell there, so counting the array's length here
        # would print a number no other surface agrees with.
        cells = len(
            {oc["id"] for oc in _dicts(cap.get("outcome_classes")) if isinstance(oc.get("id"), str)}
        )
        inputs = sorted(
            {
                source[claim_id]
                for claim_id in _as_list(cap.get("claims"))
                if isinstance(claim_id, str) and claim_id in source
            }
        )
        operation = cap.get("operation")
        lines.append(
            f"  {cap_id}  {cells} {'cell' if cells == 1 else 'cells'}  [{', '.join(inputs) or '?'}]"
        )
        lines.append(f"    {operation if isinstance(operation, str) else '(no operation)'}")

    # The action, named where the only person who can still take it is reading.
    # emit.py's late report is the other place that names it, and it names the same
    # two fields; this one has to add what does *not* work, because the natural
    # reading of any finding in this pipeline is "re-dispatch the stage".
    lines.append(
        "  Acting on this means editing 01-world-model.json: add binding.tool and "
        "binding.fixed_args to the capability, or accept the reduced surface and record "
        "that as a decision (rubrica decide)."
    )
    lines.append(
        "  Re-dispatching a reconcile pass will not add a binding -- "
        "rb-reconcile-capabilities is told to leave it off rather than guess a tool name."
    )
    return lines


def _disposition_parts(run: RunPaths) -> tuple[list[dict], list[str]]:
    """Every readable `00-dispositions/<slice>.json`, and the slice ids whose
    part is present but could not be read.

    The parts are the only place the surfaces the fan-out *observed* exist:
    `triage-seal` copies `objective_review` from `00-objective.json` and the
    deficiencies from `00-audit.json`, and carries neither
    `predicted_surface_count` nor any part's `observed_surfaces` into the
    sealed record. So section 4.1's divergence can only be rendered by reading
    back what the members wrote, which is why gate 0's brief reads a staged
    artifact at all.

    The *directory* listing is deliberately not guarded: `list_json` raises
    `UsageError` on an unreadable directory and `cli.py` maps that to exit 2,
    which is this module's docstring's own line between "a readable run's
    content" (always exit 0, absence stated) and "a run directory that cannot
    be read at all". `claim_utilisation` over `01-claims/` and `_gate_3` over
    `05-verdicts/` are the two existing reports doing exactly this, and a third
    spelling of the same decision is how one of them would eventually get it
    wrong. An individual unreadable part *file* is the tolerated case, and it
    is the one a real run produces.
    """
    unreadable: list[str] = []
    parts: list[dict] = []
    for path in list_json(run.dispositions_dir):
        document = _quietly(path)
        if isinstance(document, dict):
            parts.append(document)
        else:
            unreadable.append(path.stem)
    return parts, unreadable


def _divergence_lines(run: RunPaths) -> list[str]:
    """Section 4.1's predicted-vs-observed surface divergence.

    The observed total is computed the way `rb-triage-audit`'s Method computes
    it -- every predicted surface with at least one admitted candidate anywhere
    in the parts, plus every distinct `observed_surfaces` entry any part
    reported. Deliberately not a simpler count: a human reading a shortfall
    here and then reading the audit's deficiencies must see the same
    arithmetic, and two definitions of "observed" in one gate's reading surface
    would make the brief and the record it summarises disagree about a number
    that is supposed to be the same number.
    """
    lines = [DIVERGENCE_HEADER]
    objective = _mapping(_quietly(run.objective))
    parts, unreadable_parts = _disposition_parts(run)

    admitted: set[str] = set()
    for part in parts:
        for entry in _dicts(part.get("dispositions")):
            candidate_id = entry.get("candidate_id")
            if entry.get("disposition") == "admit" and isinstance(candidate_id, str):
                admitted.add(candidate_id)

    # A surface's name is what a human reads it by, so an unnamed one renders
    # as "?" rather than being dropped: dropping it would silently lower the
    # predicted total the reader is asked to compare against.
    predicted_names: list[str] = []
    confirmed: list[str] = []
    unconfirmed: list[str] = []
    for surface in _dicts(_mapping(objective.get("objective_review")).get("surfaces")):
        name = surface.get("name")
        name = name if isinstance(name, str) else "?"
        predicted_names.append(name)
        evidence = _strings(surface.get("evidence"))
        (confirmed if any(cid in admitted for cid in evidence) else unconfirmed).append(name)

    # Names already predicted are not counted twice. `observed_surfaces` is
    # specified as what a member saw that the prediction did *not* name, but a
    # member that restates a predicted surface is schema-legal, and counting it
    # would manufacture a surplus out of agreement.
    seen = set(predicted_names)
    surplus: list[str] = []
    for part in parts:
        for surface in _dicts(part.get("observed_surfaces")):
            name = surface.get("name")
            name = name if isinstance(name, str) else "?"
            if name not in seen:
                seen.add(name)
                surplus.append(name)

    predicted_count = objective.get("predicted_surface_count")
    # The document's own number, not len(predicted_names): they are supposed to
    # agree, `refs.check_objective` is what says so, and rendering the recorded
    # value is what lets a human see them disagree.
    shown = predicted_count if isinstance(predicted_count, int) else "?"
    observed = len(confirmed) + len(surplus)
    lines.append(f"  predicted by the objective pass from the corpus map: {shown}")
    lines.append(
        f"  observed by the fan-out across {len(parts)} disposition "
        f"part{'s' if len(parts) != 1 else ''}: {observed}"
    )
    lines.append(
        f"  predicted, but confirmed by no admitted candidate in any part ({len(unconfirmed)}): "
        + (", ".join(unconfirmed) if unconfirmed else "(none)")
    )
    lines.append(
        f"  observed in a slice and never predicted ({len(surplus)}): "
        + (", ".join(surplus) if surplus else "(none)")
    )
    lines.append(
        "  A shortfall is a loss -- a surface the map expected that nothing any slice ruled "
        "on confirmed -- and `rb-triage-audit` records it as a deficiency. A surplus is not: "
        "`predicted_surface_count` was a prediction against exactly this comparison, never a "
        "target the fan-out was meant to hit, so a surplus reads as how well the map described "
        "the corpus."
    )
    if not run.objective.is_file():
        lines.append(
            "  (00-objective.json is absent -- `triage-objective` has not run for this run, "
            "so there is no prediction to compare against)"
        )
    elif not objective:
        lines.append(
            "  (00-objective.json is present but could not be read -- "
            "`rubrica validate --stage triage-objective` names the defect)"
        )
    if not parts and not unreadable_parts:
        lines.append(
            "  (no disposition parts on disk -- `triage-rule` has not run, or the parts have "
            "been cleared away since; the observed total above is over nothing)"
        )
    if unreadable_parts:
        lines.append(
            "  (could not read the disposition part for: "
            + ", ".join(unreadable_parts)
            + " -- their surfaces and admits are missing from the totals above)"
        )
    return lines


def _slice_lines(run: RunPaths) -> list[str]:
    """The slice table and the split-group summary, from `00-slices.json`.

    One reader for both because they are one document, and reading it twice
    would let the two sections disagree about it.
    """
    document = _mapping(_quietly(run.slices))
    entries = _dicts(document.get("slices"))

    cap = document.get("cap_bytes")
    cap_note = f", cap {cap} bytes each" if isinstance(cap, int) else ""
    table = [f"{SLICES_HEADER} ({len(entries)}{cap_note})"]
    for entry in entries:
        slice_id = entry.get("id")
        slice_id = slice_id if isinstance(slice_id, str) else "?"
        candidate_count = len(_strings(entry.get("candidate_ids")))
        table.append(
            f"  {slice_id}: {candidate_count} candidate"
            f"{'s' if candidate_count != 1 else ''}, {entry.get('bytes', '?')} bytes"
            f" -- {entry.get('label', '')}"
        )
    if not run.slices.is_file():
        table.append(
            "  (00-slices.json is absent -- `triage-slices` has not run for this run, or the "
            "slice plan has been cleared away since)"
        )
    elif not entries:
        table.append(
            "  (00-slices.json is present but could not be read, or lists no slices -- "
            "`rubrica validate --stage triage-slices` names the defect)"
        )

    # Every group with a member outside the slice being read, and every slice
    # that holds part of it. Accumulated across the whole plan rather than
    # reported per slice: "held by 4 slices" is the fact a human acts on, and
    # a per-slice rendering would state it four times, once from each side.
    holders: dict[str, set[str]] = {}
    totals: dict[str, object] = {}
    for entry in entries:
        slice_id = entry.get("id")
        for provenance in _dicts(entry.get("provenance")):
            others = _strings(provenance.get("other_slices"))
            if not others:
                continue
            group = provenance.get("group")
            # str() on the key for the reason gate 0's reason_code key is
            # coerced: this is grouped on and then sorted, and a non-string one
            # both risks being unhashable and makes the sort compare str to int.
            group = str(group) if group else "?"
            held = holders.setdefault(group, set())
            if isinstance(slice_id, str):
                held.add(slice_id)
            held.update(others)
            totals.setdefault(group, provenance.get("in_group_total"))

    split = [f"{SPLIT_HEADER} ({len(holders)})"]
    if holders:
        for group in sorted(holders):
            slice_ids = sorted(holders[group])
            split.append(
                f"  {group}: {totals.get(group, '?')} candidates across {len(slice_ids)} "
                f"slices ({', '.join(slice_ids)})"
            )
        split.append(
            "  No member of a split group saw the whole group, so a near-duplicate spanning "
            "the split could be admitted twice or declined against a sibling that is not "
            "there. Gate 0 is the only place that residue can be acted on -- nothing "
            "downstream of `intake` reads the corpus again."
        )
    elif entries:
        split.append("  (none -- every group the slicer found fits inside one slice)")
    else:
        # Not "(none)": with no readable slice plan this section knows nothing
        # about how the groups were partitioned, and "every group fits inside
        # one slice" would be an announcement of absence made because the input
        # could not be read -- the exact shape `paths.list_dir` exists to stop
        # `check-refs` and `validate` doing, stated as a fact to the one human
        # who can act on a split.
        split.append(
            "  (unknown -- see the note above for why 00-slices.json was not read; without "
            "a slice plan, whether any group was split across slices is not established "
            "either way)"
        )
    return table + [""] + split


def _gate_0(run: RunPaths) -> str:
    if not run.triage.is_file():
        # A ruling held by the report as well as by
        # the check: a run minted through `intake --input` never had a triage
        # step, and that absence is not a finding.
        #
        # Branched on the catalogue rather than stated unconditionally, because
        # a missing triage record has two causes and this used to name only
        # one. On a run `survey` minted, the catalogue is right there and triage
        # simply has not run yet -- so telling that reader "this run was minted
        # through `intake --input`, which has no catalogue and no triage step at
        # all" was false, and false at precisely the moment they are waiting for
        # triage and asking this command whether it has landed.
        if run.catalogue.is_file():
            return (
                f"GATE 0 -- {run.root}\n\n"
                "No triage record for this run yet (00-triage.json is absent), but "
                "00-catalogue.json is present: this run was minted by `survey` and the "
                "triage family has not run, or has not reached `triage-seal`. Run the "
                "family through to `triage-seal` and read this brief again -- there is "
                "nothing to review at gate 0 until it lands.\n"
            )
        return (
            f"GATE 0 -- {run.root}\n\n"
            "No triage record for this run (00-triage.json is absent), and no "
            "00-catalogue.json either. This run was minted through `intake --input`, "
            "which has no catalogue and no triage step at all -- nothing to review "
            "at gate 0.\n"
        )

    triage = _mapping(_quietly(run.triage))
    catalogue = _mapping(_quietly(run.catalogue))
    candidates = {
        c["candidate_id"]: c
        for c in _dicts(catalogue.get("candidates"))
        # isinstance rather than `"candidate_id" in c`: an unhashable id (a
        # list) raises TypeError building this dict, the same shape
        # adopt_projection's own `used` map was measured raising.
        if isinstance(c.get("candidate_id"), str)
    }

    review = _mapping(triage.get("objective_review"))
    lines = [f"GATE 0 -- {run.root}", "", "Objective verdict"]
    lines.append(f"  declared objective: {review.get('declared_objective', '?')}")
    lines.append(
        "  supported by the surfaces found: " + ("yes" if review.get("supported") else "no")
    )
    if review.get("notes"):
        lines.append(f"  notes: {review['notes']}")
    recommended = _mapping(review.get("recommended_objective"))
    if recommended:
        lines.append(
            f"  recommended objective instead: {recommended.get('objective')} -- "
            f"{recommended.get('reason')}"
        )
    lines.append("")

    # Immediately after the verdict, because it is the only measure of the
    # corpus map that verdict was ruled from -- see section 4.1.
    lines.extend(_divergence_lines(run))
    lines.append("")

    dispositions = _dicts(triage.get("dispositions"))
    # intake.admit_sort_key, not a third spelling of the same sort. The lambda
    # this replaces (`d.get("priority", 10**9)`) shared the measured TypeError
    # of the two it is now unified with -- a string `priority` alongside an
    # integer one raised out of `sorted`, at exit 1 from a command whose whole
    # ruling is that it exits 0. Using the *pipeline's* order here has a second
    # benefit beyond not raising: the admits a human reads at gate 0 are listed
    # in the order intake will actually materialise them.
    admits = sorted(
        (d for d in dispositions if d.get("disposition") == "admit"),
        key=admit_sort_key,
    )
    lines.append(f"Admits, by priority ({len(admits)})")
    if admits:
        for d in admits:
            priority = d.get("priority")
            marker = f"[{priority}]" if priority is not None else "-"
            lines.append(f"  {marker} {d.get('candidate_id', '?')}: {d.get('reason', '')}")
    else:
        lines.append("  (none)")
    lines.append("")

    declines_by_code: dict[str, list[dict]] = {}
    for d in dispositions:
        if d.get("disposition") == "decline":
            code = d.get("reason_code")
            # str() on the key, not the bare value: `reason_code` is grouped on
            # and then sorted, and a non-string one both risks being unhashable
            # and makes `sorted(declines_by_code)` compare str to int.
            declines_by_code.setdefault(str(code) if code else "?", []).append(d)
    total_declines = sum(len(v) for v in declines_by_code.values())
    lines.append(f"Declines, by reason code ({total_declines})")
    if declines_by_code:
        for code in sorted(declines_by_code):
            entries = declines_by_code[code]
            lines.append(f"  {code} ({len(entries)}):")
            for d in entries:
                bytes_note = ""
                # `candidates.get(...)` raises TypeError on an unhashable
                # candidate_id, so the lookup is gated on the key being the
                # string the schema requires; a non-string one simply renders
                # without its byte count.
                cid = d.get("candidate_id")
                candidate = candidates.get(cid) if isinstance(cid, str) else None
                if candidate is not None:
                    bytes_note = f", {candidate.get('bytes', '?')} bytes"
                lines.append(
                    f"    - {d.get('candidate_id', '?')}{bytes_note}: {d.get('reason', '')}"
                )
    else:
        lines.append("  (none)")
    lines.append("")

    deficiencies = _dicts(triage.get("deficiencies"))
    projections_by_closes: dict[str, list[dict]] = {}
    for projection in _dicts(triage.get("projections")):
        raw_closes = projection.get("closes")
        # Strings only, from a real list. A non-string `closes` entry can be
        # unhashable (`setdefault` raises TypeError on a list), and one that is
        # not a string cannot match a `deficiency_id` that is, so nothing
        # renderable is lost by skipping it.
        for closes in raw_closes if isinstance(raw_closes, list) else []:
            if isinstance(closes, str):
                projections_by_closes.setdefault(closes, []).append(projection)

    lines.append(f"Open deficiencies and their projections ({len(deficiencies)})")
    if deficiencies:
        for deficiency in deficiencies:
            deficiency_id = deficiency.get("deficiency_id", "?")
            closed_by = deficiency.get("closed_by")
            status = f"closed by {closed_by}" if closed_by else "OPEN"
            lines.append(f"  {deficiency_id} [{status}]: {deficiency.get('statement', '')}")
            for projection in projections_by_closes.get(deficiency_id, []):
                projection_id = projection.get("projection_id", "?")
                confidence = _mapping(projection.get("method")).get("confidence", "?")
                satisfied_by = projection.get("satisfied_by")
                satisfied_note = f", satisfied by {satisfied_by}" if satisfied_by else ""
                wanted = _mapping(projection.get("wanted")).get("statement", "")
                lines.append(
                    f"      -> {projection_id} (confidence: {confidence}{satisfied_note}): {wanted}"
                )
    else:
        lines.append("  (none)")
    lines.append("")

    # Last: how the fan-out read the corpus, rather than what it ruled.
    lines.extend(_slice_lines(run))

    return "\n".join(lines) + "\n"


def _gate_1(run: RunPaths) -> str:
    lines = [f"GATE 1 -- {run.root}", ""]

    # The reconcile sweep, read before anything derived from it. Cross-pass
    # incoherence -- a later pass modelling what rb-reconcile-contradict recorded
    # `unresolved` -- has no mechanical check and must not be given a fake one:
    # whether a claim *supports* an element is semantic, which is the hole layer 2
    # is forbidden to paper over. What follows is an aggregate: counts and a
    # resolution tally, not the contradictions themselves. It goes first because a
    # non-zero `unresolved` is what should send a reader into 01-contradictions/
    # before reading the world model built on top of it -- this report points at
    # the parts, it does not reproduce them.
    cover = _mapping(_quietly(run.subjects))
    subjects = _dicts(cover.get("subjects"))
    covered = {
        cid
        for subject in subjects
        # isinstance rather than a truthiness check, and for the same reason gate
        # 0's candidate map above carries one: this builds a *set*, so an
        # unhashable member -- `"claims": [["c-1"]]`, `[{"id": "c-1"}]`, both
        # readable JSON and both what a hand-edit at this gate produces -- raises
        # `TypeError: unhashable type` out of the comprehension. Measured at exit
        # 1 with a fabricated `[internal]` finding, which is the third instance in
        # this module of the shape adopt_projection's `used` map was measured
        # raising. `_as_list` guards the container; only this guards the members,
        # and a truthy element can still be a dict.
        for cid in _as_list(subject.get("claims"))
        if isinstance(cid, str)
    }
    lines.append("Reconcile sweep")
    if subjects:
        lines.append(f"  {len(subjects)} subjects over {len(covered)} claims")
    else:
        lines.append("  (no subject cover yet; nothing to report)")

    swept, found = 0, []
    for path in list_json(run.contradictions_dir):
        part = _mapping(_quietly(path))
        swept += 1
        found.extend(_dicts(part.get("contradictions")))
    # Both numbers, always. "12 subjects swept, 0 contradictions" is a strong
    # claim about the corpus and has to be legible as one -- a brief that printed
    # only a non-empty list would render a sweep that found nothing anywhere as
    # silence, which is the reading this stage most needs a human to question.
    lines.append(f"  {swept} subjects swept, {len(found)} contradictions recorded")
    if found:
        tally: dict[str, int] = {}
        for contradiction in found:
            resolution = contradiction.get("resolution")
            key = resolution if isinstance(resolution, str) else "(no resolution)"
            tally[key] = tally.get(key, 0) + 1
        # unresolved first, and shown as a zero whenever this branch renders at
        # all: it is the value under the most pressure to be dropped by a pass
        # that wants to look decisive, so a sweep that recorded contradictions and
        # resolved every one should be visibly odd rather than merely unremarked.
        # Scoped to the branch on purpose -- a run with *no* contradictions at all
        # never reaches here, and its reading is the "0 contradictions recorded"
        # line above, which is the stronger claim of the two anyway.
        ordered = ["unresolved", *sorted(k for k in tally if k != "unresolved")]
        lines.append("  " + ", ".join(f"{key}: {tally.get(key, 0)}" for key in ordered))
    lines.append("")

    # Read once, here, and used again by the gaps section at the foot of this
    # brief: two `_quietly(run.world_model)` calls could disagree if the file
    # changed mid-render, and a brief whose two halves describe different
    # documents is worse than either half alone.
    world = _mapping(_quietly(run.world_model))

    # What the denominator does NOT count. Placed above the numbers derived from
    # it -- utilisation, and the implied size that reads
    # `denominator.capability_cells` -- because a reader who has not seen the
    # exclusion cannot read the size line correctly.
    lines.extend(_excluded_lines(run, world))
    lines.append("")

    lines.append("Claim utilisation, per input")
    utilisation = claim_utilisation(run)
    if utilisation["artifacts"]:
        for entry in utilisation["artifacts"]:
            lines.append(
                f"  {entry['artifact_id']}: {entry['cited']}/{entry['total']} claims cited "
                f"({entry['percent']}%)"
            )
    else:
        lines.append("  (no world model yet; nothing to report)")
    lines.append("")

    # Per pass, not per input, and that distinction is the whole point: the block
    # above is an aggregate across every citing pass, which is what hid issue #6.
    # Measured on run-20260823-112746, utilisation read 33.6% while the pass that
    # had read every claims file was citing 110 of 135 claims of its own kind and
    # the pass that had read three of twenty-three was citing 2 of 38 -- and
    # trajectories-json-9 reported 13 claims cited, every one of them a capability
    # claim, while the goals pass never opened the file. A per-artifact number
    # cannot say which pass did the citing, so one diligent pass masks another's
    # skipped file.
    lines.append("Read coverage, per pass")
    rendered = False
    for attribute, own_kinds in PASS_OWN_KINDS:
        path = getattr(run, attribute)
        rows = _dicts(_mapping(_quietly(path)).get("inputs_seen"))
        if not rows:
            # Named rather than skipped. A bare `continue` dropped the pass out
            # of the block entirely, and the "nothing to report" line below only
            # fires when *all four* are absent -- so three passes rendering and
            # one omitted read as a complete brief, with the omission being the
            # anomaly a reader is here to notice. `is_file` separates the two
            # cases a reader would act on differently: a partial that has not
            # been written yet is a run that stopped, and one that is there
            # carrying no readable rows is a defect
            # `rubrica validate --stage X` will name.
            state = (
                "present, but unreadable or carrying no inputs_seen rows"
                if path.is_file()
                else "not written yet"
            )
            lines.append(f"  {path.name}: no accounting ({state})")
            continue
        rendered = True
        cited = sum(_count(row.get("cited")) for row in rows)
        total = sum(_count(row.get("own_kind_total")) for row in rows)
        # The artifact's filename, not the stage name: it is what a reader opens
        # next, and it is derived from the same attribute rather than needing a
        # second mapping from pass to partial.
        lines.append(f"  {path.name}: {cited}/{total} claims of {', '.join(own_kinds)} cited")
        # Only the rows that dropped something, and always with the note the
        # schema required for the drop. The accounting is total over
        # manifest.inputs, so most rows on a real run read 0/0/0 -- printing them
        # would bury the one line a human is at this gate to rule on.
        for row in rows:
            # Truthiness rather than `_count` here, and the asymmetry is
            # deliberate: a row that states a drop in any shape is a row worth
            # printing, and the values printed below are raw, so a malformed
            # `dropped` shows up as itself. `_count` guards the sums because
            # addition raises; nothing raises on deciding whether to print a line.
            if row.get("dropped"):
                note = row.get("note")
                # Raw, unlike the summed columns above: a reader who came here
                # because the pass total looked wrong needs to see what the row
                # actually says, and a malformed count rendered as 0 would read as
                # the artifact's own claim rather than this report's substitution.
                lines.append(
                    f"    {row.get('artifact_id')}: {row.get('cited')}/"
                    f"{row.get('own_kind_total')} cited, {row.get('dropped')} dropped"
                    f" -- {note if isinstance(note, str) else '(no note)'}"
                )
    if not rendered:
        lines.append("  (no reconcile partials with an accounting yet; nothing to report)")
    lines.append("")

    lines.append("Implied suite size")
    size = implied_size(run)
    if size is None:
        # None means either "no world model yet" or "one exists but could not
        # be read" (sizing.implied_size's own guard) -- this report cannot
        # tell those apart without re-reading what implied_size already
        # decided not to raise on, so it says both rather than picking one
        # and being wrong half the time.
        lines.append("  (implied size unavailable -- no world model yet, or it could not be read)")
    else:
        binding_note = (
            " -- ABOVE the ceiling; this target may want splitting across runs"
            if size["ceiling_binding"]
            else ""
        )
        # blocked_note makes the arithmetic on this line actually add up when
        # coverage has narrowed the denominator: capability_cells + hop_slots
        # alone is the *pre-deduction* total, and printing "= denominator"
        # right after it without showing the subtraction reads as broken math
        # to the human this line exists for.
        blocked_note = f" - {size['blocked_cells']} blocked" if size["blocked_cells"] else ""
        lines.append(
            f"  {size['capability_cells']} capability cells + {size['hop_slots']} hop-depth "
            f"slots{blocked_note} ({size['basis']}) = {size['denominator']} -> "
            f"implied {size['implied']}, ceiling {size['ceiling']}{binding_note}"
        )
    lines.append("")

    gaps = _dicts(world.get("gaps"))
    lines.append(f"World-model gaps ({len(gaps)})")
    if gaps:
        for gap in gaps:
            lines.append(f"  {gap.get('id', '?')}: {gap.get('unknown', '')}")
    else:
        lines.append("  (none)")
    lines.append("")

    triage = _quietly(run.triage)
    lines.append(
        "Triage's open deficiencies -- read against the gaps above. This pairing is "
        "semantic, so it is a human's call and this rendering is the "
        "whole instrument for making it, not a check"
    )
    if triage is None:
        lines.append("  (no triage record for this run)")
    else:
        open_deficiencies = [
            d for d in _dicts(_mapping(triage).get("deficiencies")) if not d.get("closed_by")
        ]
        if open_deficiencies:
            for deficiency in open_deficiencies:
                lines.append(
                    f"  {deficiency.get('deficiency_id', '?')}: {deficiency.get('statement', '')}"
                )
        else:
            lines.append("  (none open)")

    return "\n".join(lines) + "\n"


def _gate_2(run: RunPaths) -> str:
    lines = [f"GATE 2 -- {run.root}", ""]
    coverage = _quietly(run.coverage_latest)
    if coverage is None:
        lines.append("No coverage report yet (03-coverage/latest.json is absent).")
        return "\n".join(lines) + "\n"

    coverage = _mapping(coverage)
    lines.append(f"Coverage verdict: {coverage.get('verdict', '?')}")
    capability_matrix = _mapping(coverage.get("capability_matrix"))
    goal_matrix = _mapping(coverage.get("goal_matrix"))
    lines.append(
        f"  capability cells: {capability_matrix.get('covered', '?')}/"
        f"{capability_matrix.get('total', '?')}"
    )
    lines.append(f"  goals: {goal_matrix.get('covered', '?')}/{goal_matrix.get('total', '?')}")
    progress = _mapping(coverage.get("progress"))
    lines.append(
        f"  round {coverage.get('round', '?')}: {progress.get('new_cells_this_round', '?')} new "
        f"cells this round, {progress.get('rounds_without_progress', '?')} rounds without progress"
    )
    # len() over the raw value would count a string's characters as holes, so
    # the count is of a real list or nothing.
    raw_holes = coverage.get("holes")
    lines.append(f"  open holes: {len(raw_holes) if isinstance(raw_holes, list) else 0}")

    size = implied_size(run)
    if size is not None:
        binding_note = ", BINDING" if size["ceiling_binding"] else ""
        lines.append(
            f"  implied suite size: {size['implied']} (ceiling {size['ceiling']}{binding_note})"
        )

    return "\n".join(lines) + "\n"


def _gate_3(run: RunPaths) -> str:
    lines = [f"GATE 3 -- {run.root}", ""]
    tallies: dict[str, int] = {}
    for path in list_json(run.verdicts_dir):
        payload = _quietly(path)
        if isinstance(payload, dict):
            # str() on the key: `tallies` is grouped on and then `sorted`, so a
            # non-string verdict would either be unhashable or make the sort
            # compare str to int -- the same reason gate 0's reason_code key is
            # coerced.
            verdict = payload.get("verdict")
            verdict = str(verdict) if verdict else "?"
            tallies[verdict] = tallies.get(verdict, 0) + 1

    total = sum(tallies.values())
    lines.append(f"Verdict tallies ({total} instance{'s' if total != 1 else ''} challenged)")
    if tallies:
        for verdict in sorted(tallies):
            lines.append(f"  {verdict}: {tallies[verdict]}")
    else:
        lines.append("  (none)")

    return "\n".join(lines) + "\n"
