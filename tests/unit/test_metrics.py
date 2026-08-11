"""jaccard, and the 0/0 ruling it exists to hold in one place."""

from __future__ import annotations

from rubrica.metrics import jaccard


def test_identical_sets_score_one():
    assert jaccard(frozenset("ab"), frozenset("ab")) == 1.0


def test_disjoint_sets_score_zero():
    assert jaccard(frozenset("ab"), frozenset("cd")) == 0.0


def test_partial_overlap_is_the_intersection_over_the_union():
    assert jaccard(frozenset("abc"), frozenset("bcd")) == 0.5


def test_two_empty_sets_score_one():
    """The ruling, and the trap.

    0/0 has no arithmetic answer. Returning 0.0 would report two runs that both
    produced nothing as maximally *different*, which is false. 1.0 is correct --
    the sets are identical -- and it is why every caller is required to report the
    set sizes alongside the number: a 1.0 over two empty sets is true and useless,
    and only the sizes make that visible.
    """
    assert jaccard(frozenset(), frozenset()) == 1.0


def test_one_empty_set_scores_zero():
    assert jaccard(frozenset("a"), frozenset()) == 0.0
    assert jaccard(frozenset(), frozenset("a")) == 0.0


def test_the_result_is_rounded_so_two_runs_produce_byte_identical_output():
    assert jaccard(frozenset(range(3)), frozenset(range(7))) == 0.428571
