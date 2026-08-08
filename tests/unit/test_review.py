"""sample-for-review: a stratified packet, drawn where the blind spot hides.

The sampling rule is the design. Drawing from the cases the adversary flagged
would find only what the adversary already found; drawing from high-confidence
accepts is what can find a correlated labeler/adversary blind spot, which is the
one failure mode design spec section 10 says the pipeline cannot fix itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from testgen.artifacts import ArtifactError, read_json, write_json
from testgen.errors import UsageError
from testgen.paths import RunPaths
from testgen.review import (
    DEFAULT_SAMPLE_SIZE,
    RUBRIC,
    candidates,
    confidence_band,
    packet,
    sample_run,
    stratified,
)
from tests.builders import minimal_scenarios, minimal_verdict
from tests.unit.test_refs_states import build_state

SID = "scn-001"


def _entry(sid, band="high", hop_depth=2):
    return {"scenario_id": sid, "band": band, "hop_depth": hop_depth}


# -- confidence_band ---------------------------------------------------------


def test_an_unqualified_accept_is_high_confidence():
    assert confidence_band(minimal_verdict()) == "high"


def test_an_accept_the_adversary_qualified_is_low_confidence():
    for key in ("uniquely_determined", "derivable_without_guessing"):
        assert (
            confidence_band(
                minimal_verdict(
                    **{
                        key: False,
                        "alternative_answers": [
                            {"answer": "other", "world_consistent_reason": "also consistent"}
                        ],
                    }
                )
            )
            == "low"
        )


def test_a_non_accept_verdict_is_low_confidence():
    assert confidence_band(minimal_verdict(verdict="re-seed")) == "low"


# -- candidates --------------------------------------------------------------


def test_only_emitted_scenarios_are_reviewable(tmp_path):
    """A reviewer can only act on a task that shipped."""
    run = build_state(tmp_path, "emit")
    assert [entry["scenario_id"] for entry in candidates(run)] == [SID]
    assert candidates(run)[0]["band"] == "high"
    assert candidates(run)[0]["hop_depth"] == 2


def test_a_scenario_with_no_verdict_is_low_confidence_not_excluded(tmp_path):
    """Excluding it would hide exactly the package that most needs a human."""
    run = build_state(tmp_path, "emit")
    run.verdict(SID).unlink()
    assert candidates(run)[0]["band"] == "low"


# -- stratified --------------------------------------------------------------


def test_high_confidence_entries_come_first():
    """The sha256 tie-break is chosen to oppose the band preference.

    sha256("d") sorts before sha256("c"), so a digest-only sort (no band
    preference at all) would pick "d". The expected ["c"] can only come from
    the band term actually running -- do not "tidy" these ids back to a/b,
    whose digests happen to agree with the band order and would let a
    deleted band preference pass unnoticed.
    """
    entries = [_entry("d", band="low"), _entry("c", band="high")]
    assert [e["scenario_id"] for e in stratified(entries, 1)] == ["c"]


def test_the_sample_spreads_across_hop_depths_before_going_deep():
    """Stratified, not just top-ranked.

    Three samples all at hop depth 1 would tell a reviewer nothing about whether
    the deep scenarios are fair.

    The depth-1 ids are chosen so a flat `sorted(entries, key=_order_key)[:2]`
    (no round-robin at all) draws both of its first two picks from depth 1 --
    "a2", "p2", and "p3" sort ahead of "b1" by sha256 digest. The expected
    spread across [1, 3] can only come from the round-robin actually running;
    do not rename these ids casually.
    """
    entries = [
        _entry("a2", hop_depth=1),
        _entry("p2", hop_depth=1),
        _entry("p3", hop_depth=1),
        _entry("b1", hop_depth=3),
    ]
    sampled = stratified(entries, 2)
    assert sorted(e["hop_depth"] for e in sampled) == [1, 3]


def test_the_sample_is_deterministic():
    """No random, no builtin hash (salted per process), no timestamp.

    A sample that moved between runs would make the review trend line meaningless
    -- a change in the scores could not be told from a change in the sample.
    """
    entries = [_entry(f"scn-{i:03d}", hop_depth=(i % 3) + 1) for i in range(20)]
    first = [e["scenario_id"] for e in stratified(entries, 5)]
    assert first == [e["scenario_id"] for e in stratified(list(reversed(entries)), 5)]


def test_the_sample_is_stable_across_process_hash_salts():
    """sha256, not the salted builtin hash().

    The forward-vs-reversed assertion above pins input-order independence --
    a different property. It cannot see a swap to builtin hash(), because both
    of its calls run inside this one test, sharing this one process's hash
    salt, so they stay consistent with each other regardless of which key
    function did the sorting. Seeing the salt requires two separate processes:
    run the same computation under two different PYTHONHASHSEED values and
    require the same answer from both, which sha256 (seed-independent) gives
    and hash() (salted per process) would not.
    """
    script = (
        "from testgen.review import stratified\n"
        "entries = [\n"
        "    {'scenario_id': f'scn-{i:03d}', 'band': 'high', 'hop_depth': (i % 3) + 1}\n"
        "    for i in range(20)\n"
        "]\n"
        "print(','.join(e['scenario_id'] for e in stratified(entries, 5)))\n"
    )
    outputs = []
    for seed in ("0", "1"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(result.stdout.strip())
    assert outputs[0] != "", "the subprocess produced no output"
    assert outputs[0] == outputs[1]


def test_asking_for_more_than_exists_returns_everything():
    entries = [_entry("a"), _entry("b")]
    assert len(stratified(entries, 10)) == 2


def test_asking_for_none_returns_nothing():
    assert stratified([_entry("a")], 0) == []


def test_a_low_band_entry_is_included_once_the_high_band_runs_out():
    """The preference is a preference, not an exclusion.

    A suite where the adversary qualified everything would otherwise produce an
    empty packet -- the run most in need of review producing the least of it.
    """
    entries = [_entry("a", band="high"), _entry("b", band="low")]
    assert len(stratified(entries, 2)) == 2


# -- packet ------------------------------------------------------------------


def test_the_packet_carries_the_five_things_the_spec_names(tmp_path):
    run = build_state(tmp_path, "emit")
    text = packet(run, candidates(run))
    assert "A job failed on prod0" in text, "instruction"
    assert "sha256" in text.lower(), "seed digest"
    assert "90420" in text, "expected"
    assert "answered independently from the seed" in text, "adversary notes"
    for item in RUBRIC:
        assert item.replace("_", " ") in text.replace("_", " ")


def test_the_packet_carries_the_seed_digest_and_not_the_seed(tmp_path):
    """Section 7 says digest.

    A reviewer needs to confirm which world the label was authored against; the
    whole simulated backend pasted inline buries the four questions they are there
    to answer.
    """
    from testgen.artifacts import sha256_of

    run = build_state(tmp_path, "emit")
    text = packet(run, candidates(run))
    assert sha256_of(run.seed(SID))[:16] in text
    assert '"controller": "prod0"' not in text


def test_the_packet_states_why_the_sample_is_drawn_where_it_is(tmp_path):
    """Without the reason, a reader will 'fix' the sampling to be uniform."""
    run = build_state(tmp_path, "emit")
    text = packet(run, candidates(run))
    assert "blind spot" in text
    assert "high-confidence" in text


def test_the_packet_marks_each_sampled_band(tmp_path):
    run = build_state(tmp_path, "emit")
    assert "high" in packet(run, candidates(run))


def test_a_rationale_is_included_when_the_instantiate_stage_wrote_one(tmp_path):
    run = build_state(tmp_path, "emit")
    run.rationale(SID).write_text("Chose 90420 because it is the only prod0 failure.", "utf-8")
    assert "only prod0 failure" in packet(run, candidates(run))


# -- sample_run --------------------------------------------------------------


def test_sample_run_writes_the_packet_and_the_machine_readable_record(tmp_path):
    run = build_state(tmp_path, "emit")
    sampled, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert findings == []
    assert run.review_packet.is_file()
    record = read_json(run.review_sample)
    assert record["run_id"] == read_json(run.manifest)["run_id"]
    assert [s["scenario_id"] for s in record["sampled"]] == [SID]
    assert record["rubric"] == list(RUBRIC)
    assert "created" not in json.dumps(record), "no timestamp: the record must be diffable"


def test_sample_run_reports_a_suite_with_nothing_to_review(tmp_path):
    run = build_state(tmp_path, "challenge")  # emit has not run
    sampled, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert sampled == []
    assert len(findings) == 1
    assert "no emitted packages" in findings[0].message


def test_sample_run_reports_when_no_high_confidence_accept_exists(tmp_path):
    """The signal, not a failure.

    A suite in which the adversary qualified every accept is a suite whose review
    cannot look where the blind spot hides -- which is worth saying out loud.
    """
    run = build_state(tmp_path, "emit")
    write_json(run.verdict(SID), minimal_verdict(verdict="reject", notes="ambiguous"))
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)
    _, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert any("high-confidence" in f.message for f in findings)


def test_an_unreadable_scenario_list_names_the_artifact_and_writes_nothing(tmp_path):
    """A default hop depth of 0 collapses the stratification this tool exists for.

    `_load(run.scenarios) or {"scenarios": []}` gave every candidate hop_depth 0,
    so a three-task packet came out drawn from one stratum, at exit 0, with no
    finding -- indistinguishable from a suite that really is flat.
    """
    run = build_state(tmp_path, "emit")
    run.scenarios.write_text("{not json", encoding="utf-8")

    sampled, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert sampled == []
    assert len(findings) == 1
    assert findings[0].artifact == run.scenarios
    assert "02-scenarios.json" in str(findings[0])
    assert not run.review_packet.exists()
    assert not run.review_sample.exists()


def test_a_non_positive_size_is_a_usage_error_before_anything_is_written(tmp_path):
    """An empty packet at exit 0 cannot be told from a review that found nothing."""
    run = build_state(tmp_path, "emit")
    with pytest.raises(UsageError):
        sample_run(run, 0)
    with pytest.raises(UsageError):
        sample_run(run, -1)
    assert not run.review_packet.exists()
    assert not run.review_sample.exists()


def test_a_directory_that_is_not_a_run_is_refused_before_the_packet_is_written(tmp_path):
    """manifest.json is read first, the way smoke_run reads it.

    It used to be read last, after the packet and the record were already on disk,
    so a directory that is not a run got a measurement/review/ tree written into
    it before the ArtifactError was raised.
    """
    run = build_state(tmp_path / "real", "emit")
    stray = RunPaths(tmp_path / "not-a-run")
    stray.root.mkdir(parents=True)
    # The suite directory is copied in so the refusal cannot be attributed to
    # there being nothing to review.
    shutil.copytree(run.suite_dir, stray.suite_dir)

    with pytest.raises(ArtifactError):
        sample_run(stray, DEFAULT_SAMPLE_SIZE)
    assert not stray.measurement_dir.exists()


def test_sample_run_is_idempotent(tmp_path):
    run = build_state(tmp_path, "emit")
    sample_run(run, DEFAULT_SAMPLE_SIZE)
    first = run.review_packet.read_text()
    sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert run.review_packet.read_text() == first
