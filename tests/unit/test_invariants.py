import pytest

from testgen.invariants import InvariantForm, evaluate

JOBS = {
    "jobs": [
        {"job_id": 1, "event_count": 2, "log": "a\nb", "trimmed": 5, "original": 9},
        {"job_id": 2, "event_count": 0, "log": "", "trimmed": 0, "original": 0},
    ],
    "job_events": [
        {"job_id": 1, "counter": 1, "stdout": "a"},
        {"job_id": 1, "counter": 2, "stdout": "b"},
    ],
}


# -- compare ------------------------------------------------------------
def test_compare_field_to_field_holds():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "trimmed",
        "op": "<=",
        "right": {"field": "original"},
    }
    assert evaluate(m, JOBS) == []


def test_compare_field_to_field_reports_the_offending_record():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "original",
        "op": "<",
        "right": {"field": "trimmed"},
    }
    violations = evaluate(m, JOBS)
    assert len(violations) == 2
    assert "jobs[0]" in violations[0]


def test_compare_field_to_literal_holds():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "trimmed",
        "op": ">=",
        "right": {"literal": 0},
    }
    assert evaluate(m, JOBS) == []


def test_compare_reports_a_missing_field_rather_than_passing():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "absent",
        "op": "==",
        "right": {"literal": 1},
    }
    violations = evaluate(m, JOBS)
    assert len(violations) == 2
    assert "no field 'absent'" in violations[0]


def test_compare_reports_incomparable_types_rather_than_raising():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "log",
        "op": "<",
        "right": {"literal": 5},
    }
    violations = evaluate(m, JOBS)
    assert len(violations) == 2
    assert "cannot compare" in violations[0]


# -- count --------------------------------------------------------------
COUNT = {
    "form": "count",
    "collection": "jobs",
    "field": "event_count",
    "of": "job_events",
    "local_key": "job_id",
    "foreign_key": "job_id",
}


def test_count_holds_for_a_consistent_seed():
    assert evaluate(COUNT, JOBS) == []


def test_count_reports_a_declared_value_that_disagrees_with_the_records():
    collections = {
        "jobs": [{"job_id": 1, "event_count": 7}],
        "job_events": [{"job_id": 1, "counter": 1}],
    }
    violations = evaluate(COUNT, collections)
    assert len(violations) == 1
    assert "event_count=7" in violations[0]
    assert "has 1" in violations[0]


def test_count_of_zero_related_records_holds():
    collections = {"jobs": [{"job_id": 9, "event_count": 0}], "job_events": []}
    assert evaluate(COUNT, collections) == []


# -- join ---------------------------------------------------------------
JOIN = {
    "form": "join",
    "collection": "jobs",
    "field": "log",
    "of": "job_events",
    "source_field": "stdout",
    "separator": "\n",
    "order_by": "counter",
    "local_key": "job_id",
    "foreign_key": "job_id",
}


def test_join_holds_when_the_field_is_the_ordered_concatenation():
    assert evaluate(JOIN, JOBS) == []


def test_join_respects_order_by_not_seed_order():
    collections = {
        "jobs": [{"job_id": 1, "log": "a\nb"}],
        "job_events": [
            {"job_id": 1, "counter": 2, "stdout": "b"},
            {"job_id": 1, "counter": 1, "stdout": "a"},
        ],
    }
    assert evaluate(JOIN, collections) == []


def test_join_reports_a_field_that_does_not_match():
    collections = {
        "jobs": [{"job_id": 1, "log": "wrong"}],
        "job_events": [{"job_id": 1, "counter": 1, "stdout": "a"}],
    }
    violations = evaluate(JOIN, collections)
    assert len(violations) == 1
    assert "ordered join" in violations[0]


def test_join_reports_related_records_missing_the_order_by_field():
    collections = {
        "jobs": [{"job_id": 1, "log": "a"}],
        "job_events": [{"job_id": 1, "stdout": "a"}],
    }
    violations = evaluate(JOIN, collections)
    assert len(violations) == 1
    assert "order_by" in violations[0]


# -- unique -------------------------------------------------------------
def test_unique_holds_for_distinct_values():
    m = {"form": "unique", "collection": "jobs", "field": "job_id"}
    assert evaluate(m, JOBS) == []


def test_unique_reports_duplicates():
    m = {"form": "unique", "collection": "jobs", "field": "job_id"}
    collections = {"jobs": [{"job_id": 1}, {"job_id": 1}]}
    violations = evaluate(m, collections)
    assert len(violations) == 1
    assert "duplicate" in violations[0]


def test_unique_within_a_group_permits_repeats_across_groups():
    m = {"form": "unique", "collection": "job_events", "field": "counter", "within": "job_id"}
    collections = {
        "job_events": [
            {"job_id": 1, "counter": 1},
            {"job_id": 2, "counter": 1},
        ]
    }
    assert evaluate(m, collections) == []


def test_unique_within_a_group_still_catches_repeats_inside_one_group():
    m = {"form": "unique", "collection": "job_events", "field": "counter", "within": "job_id"}
    collections = {
        "job_events": [
            {"job_id": 1, "counter": 1},
            {"job_id": 1, "counter": 1},
        ]
    }
    violations = evaluate(m, collections)
    assert len(violations) == 1
    assert "job_id" in violations[0]


def test_increasing_holds_for_an_ascending_sequence():
    m = {
        "form": "unique",
        "collection": "job_events",
        "field": "counter",
        "within": "job_id",
        "increasing": True,
    }
    assert evaluate(m, JOBS) == []


def test_increasing_reports_a_descending_sequence():
    m = {
        "form": "unique",
        "collection": "job_events",
        "field": "counter",
        "within": "job_id",
        "increasing": True,
    }
    collections = {
        "job_events": [
            {"job_id": 1, "counter": 2},
            {"job_id": 1, "counter": 1},
        ]
    }
    violations = evaluate(m, collections)
    assert len(violations) == 1
    assert "increasing" in violations[0]


# -- boundaries ---------------------------------------------------------
def test_an_absent_collection_yields_no_violations():
    """Collection presence is refs.py's job, not this module's.

    Reporting it here as well would double-count the same defect in the
    check-refs output.
    """
    m = {"form": "unique", "collection": "absent", "field": "x"}
    assert evaluate(m, JOBS) == []


def test_an_unimplemented_form_raises():
    with pytest.raises(InvariantForm, match="regex"):
        evaluate({"form": "regex", "collection": "jobs", "field": "log"}, JOBS)


def test_violation_messages_are_deterministic():
    m = {"form": "unique", "collection": "jobs", "field": "job_id"}
    collections = {"jobs": [{"job_id": 1}, {"job_id": 1}, {"job_id": 2}, {"job_id": 2}]}
    assert evaluate(m, collections) == evaluate(m, collections)
