"""What the three measurement outputs promise as a group.

They are not stage artifacts: no JSON Schema gates them, because this project's
own code writes them and unit tests gate them instead. So each carries a
`format` tag -- which tool wrote this document, at which revision -- and none
carries a `schema_version`, which would tell a reader to go looking for a schema
file that does not exist.

That was an invariant nothing enforced. Renaming any of the three tags to
"WRONG/9" left the whole suite green, and so did adding a `schema_version` to
review/sample.json or to the stability report. A property held by three
independent writers needs one test that names all three, or each writer only
has to be consistent with itself.
"""

from __future__ import annotations

import pytest

from testgen.artifacts import read_json, write_json
from testgen.recall import compare_run
from testgen.review import sample_run
from testgen.stability import diff_runs
from tests.builders import minimal_gold
from tests.unit.test_refs_states import build_state


def _recall_document(tmp_path):
    """measurement/recall.json, as compare-gold writes it."""
    run = build_state(tmp_path / "run", "emit")
    gold = tmp_path / "gold.json"
    write_json(gold, minimal_gold())
    compare_run(run, gold)
    return read_json(run.recall)


def _review_document(tmp_path):
    """measurement/review/sample.json, as sample-for-review writes it."""
    run = build_state(tmp_path / "run", "emit")
    sample_run(run)
    return read_json(run.review_sample)


def _stability_document(tmp_path):
    """diff-runs' report, which goes to stdout: it spans two runs and owns neither."""
    a = build_state(tmp_path / "a", "emit")
    b = build_state(tmp_path / "b", "emit")
    return diff_runs(a, b)


_WRITERS = {
    "recall": (_recall_document, "testgen-recall/1"),
    "review": (_review_document, "testgen-review/1"),
    "stability": (_stability_document, "testgen-stability/1"),
}


@pytest.mark.parametrize("tool", sorted(_WRITERS))
def test_every_measurement_output_names_its_writer_and_claims_no_schema(tmp_path, tool):
    build, expected_tag = _WRITERS[tool]
    document = build(tmp_path)
    assert document["format"] == expected_tag
    assert "schema_version" not in document, (
        "no JSON Schema gates this document; claiming a schema_version sends a "
        "reader looking for a schema file that does not exist"
    )
