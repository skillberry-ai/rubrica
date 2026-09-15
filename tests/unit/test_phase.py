"""phase.py in isolation: the block reader and the kind resolver.

Every predicate here is measured in both directions, which is this repo's rule
for a guard. The negative controls are the second half of each test rather than
a separate module, because a resolver that returns everything and one that
returns nothing both pass a one-directional check.
"""

from __future__ import annotations

from rubrica import phase


def test_read_returns_none_for_every_shape_that_is_not_a_phase_block():
    """A run that declared no phase, and the malformed shapes an unvalidated
    artifact reaches this function with. `read` is called by six consumers before
    layer 1 has necessarily run over the document, so a non-dict document and a
    non-dict `phase` must both answer None rather than raising -- an exception
    escaping here would surface a missing optional field as exit 1 with empty
    stdout."""
    assert phase.read({}) is None
    assert phase.read(None) is None
    assert phase.read(7) is None
    assert phase.read("phase") is None
    assert phase.read([{"phase": {"number": 1}}]) is None
    assert phase.read({"phase": None}) is None
    assert phase.read({"phase": 1}) is None
    assert phase.read({"phase": ["trace"]}) is None


def test_read_returns_the_block_when_one_is_declared():
    block = {"number": 1, "deferred_kinds": ["trace"]}
    assert phase.read({"phase": block}) == block


def test_deferred_kinds_is_empty_without_a_block_and_ignores_non_strings():
    """The empty answer is what makes every consumer's no-phase path the
    behaviour the project had before phasing existed: an empty set defers
    nothing, so `deferred_candidate_ids` returns nothing and every writer's
    output is byte-identical to today's."""
    assert phase.deferred_kinds(None) == frozenset()
    assert phase.deferred_kinds({"number": 1}) == frozenset()
    assert phase.deferred_kinds({"number": 1, "deferred_kinds": []}) == frozenset()
    assert phase.deferred_kinds({"number": 1, "deferred_kinds": "trace"}) == frozenset()
    assert phase.deferred_kinds({"number": 1, "deferred_kinds": ["trace", 7, None]}) == frozenset(
        {"trace"}
    )


def test_deferred_candidate_ids_selects_by_kind_and_only_admissible_candidates():
    """Three populations in one catalogue, and the third is the one worth a test
    of its own. A container carrying a deferred kind is `admissible: false` -- its
    elements are the candidates -- so deferring it would hand phase 3 an input to
    admit that was never admissible in the first place. It is left for a member to
    decline instead, which is what happens today."""
    candidates = [
        {"candidate_id": "t1", "kind": "trace"},
        {"candidate_id": "t2", "kind": "trace", "admissible": True},
        {"candidate_id": "src", "kind": "source_code"},
        {"candidate_id": "bundle", "kind": "trace", "admissible": False},
    ]
    block = {"number": 1, "deferred_kinds": ["trace"]}
    assert phase.deferred_candidate_ids(candidates, block) == frozenset({"t1", "t2"})
    # The negative control: no block defers nothing, which is the pre-phasing
    # behaviour every writer falls back to.
    assert phase.deferred_candidate_ids(candidates, None) == frozenset()
    # And a kind no candidate carries selects nothing rather than raising.
    assert (
        phase.deferred_candidate_ids(candidates, {"number": 1, "deferred_kinds": ["design_doc"]})
        == frozenset()
    )


def test_deferred_candidate_ids_tolerates_a_candidates_list_that_is_not_one():
    """`slices.write_slices` guards the catalogue's shape before it calls this,
    but `brief` and `summary` read the same catalogue on the exit-0 report path
    where nothing has. A non-list, and a list of non-dicts, must answer empty."""
    block = {"number": 1, "deferred_kinds": ["trace"]}
    assert phase.deferred_candidate_ids(None, block) == frozenset()
    assert phase.deferred_candidate_ids("trace", block) == frozenset()
    assert phase.deferred_candidate_ids([None, 7, {"kind": "trace"}], block) == frozenset()
