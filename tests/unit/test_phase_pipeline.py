"""The phase block's carry chain, from the operator flag to the world model.

One module for the whole chain rather than one per stage, because what is being
tested is that four writers and six readers agree about a single fact, and a
per-stage module cannot see a disagreement between two stages.

The toy catalogue is a mixed slice by construction -- `trace-json` sits in `s01`
alongside a `mcp_tool_schema` and a `design_doc` at the default cap -- so
`--defer-kind trace` over it exercises subtraction without a synthetic fixture. A
*fully* deferred slice needs more than one slice to exist, so
`_multi_slice_catalogue` below builds one, and it is this module's own rather than
an addition to tests/toy.py: the golden toy is the model answer a skill imitates,
and a fixture that deferred one of its three inputs would teach a skill that the
golden world has two.
"""

from __future__ import annotations

import json

from rubrica import cli, refs, slices, validate
from rubrica.artifacts import write_json
from rubrica.paths import RunPaths
from tests.toy import build_toy_run

# The cap every multi-slice fixture below packs against. It must clear the toy
# corpus's largest single row -- api.json at 2381 bytes -- because a cap under
# that is refused by oversized_rows before planning starts, and it must be small
# enough that _pack_adjacent cannot roll the kind-split units back into one
# slice. 2500 is the number test_refs_slices.py and test_slices.py already use
# for the second half of that reason, measured: at this cap each of the toy
# fixture's three candidates lands in a slice of its own.
_MULTI_SLICE_CAP = 2500


def phase_run(tmp_path, *, number=1, kinds=("trace",)):
    """A toy run sliced under a phase, stopping at triage-slices.

    Re-slices rather than building a second corpus: `write_slices` is idempotent
    and safe to re-run by design (a human adopting a projection at gate 0 changes
    the catalogue), so calling it again with a phase is exactly what an operator
    reversing a gate-0 decision does.
    """
    run = build_toy_run(tmp_path, upto="triage-slices")
    slices.write_slices(run, phase_block={"number": number, "deferred_kinds": list(kinds)})
    return run


def _plan(run: RunPaths) -> dict:
    return json.loads(run.slices.read_text())


def test_the_plan_records_the_phase_and_the_deferred_candidates(tmp_path):
    run = phase_run(tmp_path)
    plan = _plan(run)
    assert plan["phase"] == {"number": 1, "deferred_kinds": ["trace"]}
    entry = plan["slices"][0]
    assert entry["deferred_candidate_ids"] == ["trace-json"]
    # The partition stays total: the deferred candidate is still in the slice it
    # belongs to, so check_slices' "every catalogue candidate lands in exactly one
    # slice" clause is untouched and phase 3 reads the same boundaries.
    assert set(entry["candidate_ids"]) == {"api-json", "notes-md", "trace-json"}


def test_a_run_with_no_phase_declares_neither_field(tmp_path):
    """The negative control, and the compatibility guarantee: absent means the
    package behaves exactly as it did before phasing. Both keys absent rather than
    null or empty, so a reader cannot tell this plan from one written before the
    field existed."""
    run = build_toy_run(tmp_path, upto="triage-slices")
    plan = _plan(run)
    assert "phase" not in plan
    assert "deferred_candidate_ids" not in plan["slices"][0]


def test_the_shard_omits_the_deferred_candidate_and_bytes_follows_it(tmp_path):
    """Subtraction is what makes rb-triage-rule need no edit: a member never sees a
    deferred candidate, so no prompt is asked to apply the policy and the mixed
    slice is cheaper to dispatch as well as correct.

    `bytes` tracks the shard rather than the slice because check_slices recomputes
    it from the shard's own candidates -- it is the dispatch's read cost, which is
    what the cap is a cap on."""
    run = phase_run(tmp_path)
    shard = json.loads(run.slice_shard("s01").read_text())
    assert [c["candidate_id"] for c in shard["candidates"]] == ["api-json", "notes-md"]
    entry = _plan(run)["slices"][0]
    assert entry["bytes"] == sum(slices.row_bytes(c) for c in shard["candidates"])
    # The positive control: the trace row really does have weight, so the equality
    # above is subtraction and not two numbers that happen to match.
    catalogue = json.loads(run.catalogue.read_text())
    trace = next(c for c in catalogue["candidates"] if c["candidate_id"] == "trace-json")
    assert slices.row_bytes(trace) > 0


def test_check_slices_is_clean_over_a_phase_plan(tmp_path):
    """check_slices reads the plan, and two of its clauses had to learn the
    deferred subset: the shard/id comparison and the shard-presence one. The
    mixed-slice case is here; the fully-deferred one is below, because only that
    shape reaches the presence clause's exemption."""
    run = phase_run(tmp_path)
    assert refs.check_slices(run) == []


def _multi_slice_catalogue(run: RunPaths, *, trace_count: int, filler_bytes: int = 400) -> None:
    """Overwrite the run's catalogue with one whose traces cannot share a slice.

    `plan_slices` splits an over-cap directory leaf by kind before it splits by
    bytes, so a catalogue whose trace rows exceed the cap on their own is what
    produces slices holding nothing but traces -- the shape three of the eleven
    slices had on the corpus this design was measured against.

    `filler_bytes` is the knob that decides which cap the fixture is shaped for,
    and it has to be a knob rather than a constant because the two callers reach
    different caps: a test calling `write_slices` directly picks
    `_MULTI_SLICE_CAP`, while a test going through `main` gets
    DEFAULT_SLICE_BYTES, which the CLI has no flag to change. Both need the trace
    rows to outweigh the cap on their own; only the weight differs.
    """
    catalogue = json.loads(run.catalogue.read_text())
    kept = [c for c in catalogue["candidates"] if c["kind"] != "trace"]
    # Built from the real trace candidate so every field the packer reads is
    # present and only the weight differs; `digest` is an open object in
    # catalogue-0.1.json, so the filler keeps the row schema-valid.
    template = next(c for c in catalogue["candidates"] if c["kind"] == "trace")
    traces = []
    for i in range(trace_count):
        row = dict(template)
        row["candidate_id"] = f"trace-{i:02d}"
        row["digest"] = {**template.get("digest", {}), "filler": "x" * filler_bytes}
        traces.append(row)
    catalogue["candidates"] = kept + traces
    write_json(run.catalogue, catalogue)


def _fully_deferred_ids(plan: dict) -> list[str]:
    return [
        entry["id"]
        for entry in plan["slices"]
        if set(entry.get("deferred_candidate_ids", ())) == set(entry["candidate_ids"])
    ]


def test_a_fully_deferred_slice_gets_no_shard_and_no_part_is_expected(tmp_path):
    """Three of eleven dispatches became empty on the measured corpus, and that is
    the whole of the gate-0 saving. Two clauses had to learn it: check_slices'
    "slice has no shard on disk" and check_disposition_parts' "slice has no
    disposition part on disk"."""
    run = build_toy_run(tmp_path, upto="triage-slices")
    _multi_slice_catalogue(run, trace_count=6)
    slices.write_slices(
        run, cap=_MULTI_SLICE_CAP, phase_block={"number": 1, "deferred_kinds": ["trace"]}
    )
    plan = _plan(run)
    fully_deferred = _fully_deferred_ids(plan)
    assert fully_deferred, "the fixture must produce at least one all-trace slice"
    for sid in fully_deferred:
        assert not run.slice_shard(sid).is_file()
    # Neither checker objects: the shard is absent by declaration and so is the
    # part that a shard would have been dispatched to produce.
    assert refs.check_slices(run) == []
    run.dispositions_dir.mkdir(parents=True, exist_ok=True)
    missing = [f.message for f in refs.check_disposition_parts(run)]
    for sid in fully_deferred:
        assert not any(f"slice {sid} has no disposition part" in m for m in missing)
    # The positive control, and it is the half that makes the loop above a guard:
    # a slice that is NOT fully deferred still owes both a shard and a part.
    partial = [s["id"] for s in plan["slices"] if s["id"] not in fully_deferred]
    assert partial
    for sid in partial:
        assert run.slice_shard(sid).is_file()
    assert any(f"slice {sid} has no disposition part" in m for sid in partial for m in missing)


def test_the_cli_declares_the_phase_and_prints_a_dash_for_a_fully_deferred_slice(tmp_path, capsys):
    """The operator reads this stdout to confirm the saving, so a slice with no
    shard has to appear with no size rather than vanish: eight lines where three
    carry a dash says what happened, and five lines does not.

    It also pins the exit code. The handler stats each slice's shard to print its
    size, and the bare `.stat()` this replaced raised FileNotFoundError on a slice
    the stage had correctly declined to write -- which cli.py's catch-all turns
    into an exit-1 `[internal]` finding blaming a stage that did exactly as it was
    told, the wrong-artifact failure the exit-code contract's third rule forbids.

    Sized for DEFAULT_SLICE_BYTES because that is the only cap `main` can reach --
    triage-slices takes no cap flag -- and at 40 rows of ~2 KB the trace kind
    outweighs it twice over, so the split leaves two all-trace slices beside the
    one holding both non-trace candidates.
    """
    run = build_toy_run(tmp_path, upto="triage-slices")
    _multi_slice_catalogue(run, trace_count=40, filler_bytes=1600)
    assert (
        cli.main(["triage-slices", "--run", str(run.root), "--phase", "1", "--defer-kind", "trace"])
        == 0
    )
    out, err = capsys.readouterr()
    assert err == ""
    plan = _plan(run)
    assert plan["phase"] == {"number": 1, "deferred_kinds": ["trace"]}
    fully_deferred = _fully_deferred_ids(plan)
    assert fully_deferred, "the fixture must produce at least one all-trace slice"
    # Every slice the plan names still has a line, and the deferred ones carry a
    # dash where a byte count would be.
    lines = [line for line in out.splitlines() if line]
    assert len(lines) == len(plan["slices"])
    for sid in fully_deferred:
        assert any(line.startswith(f"{sid}  -  ") for line in lines)
    # The positive control: the undeferred slice still reports a real size, so the
    # dash is the absent shard and not the format string losing its number.
    for entry in plan["slices"]:
        if entry["id"] not in fully_deferred:
            size = run.slice_shard(entry["id"]).stat().st_size
            assert any(line.startswith(f"{entry['id']}  {size}  ") for line in lines)


def test_layer_one_accepts_a_phase_plan_and_holds_deferred_kinds_to_the_catalogue_enum(tmp_path):
    """The schema half of the declaration, which no other test in this module
    reaches: every assertion above reads the plan as JSON, so a `phase` block that
    `additionalProperties: false` would have rejected still satisfies them.

    The second half is the point of $ref'ing catalogue-0.1.json#/$defs/kind rather
    than restating the enum: `traces` is the plural a hand-typed list would have
    accepted, and a run that deferred it would pay full price while reporting a
    phase. argparse refuses it at the CLI, and layer 1 refuses it here, so the
    guard survives a caller that reaches write_slices directly."""
    run = build_toy_run(tmp_path, upto="triage-slices")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    assert validate.validate_stage(run, "triage-slices") == []
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["traces"]})
    messages = [f.message for f in validate.validate_stage(run, "triage-slices")]
    assert any("'traces' is not one of" in m for m in messages)
