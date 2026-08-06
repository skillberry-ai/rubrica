from pathlib import Path

from testgen.findings import Finding, format_findings


def test_str_includes_layer_path_and_pointer():
    f = Finding(Path("/r/01-world-model.json"), "schema", "/capabilities/0", "missing 'operation'")
    assert str(f) == "[schema] /r/01-world-model.json#/capabilities/0: missing 'operation'"


def test_str_omits_the_pointer_for_root_findings():
    f = Finding(Path("/r/a.json"), "refs", "", "unknown capability_id")
    assert str(f) == "[refs] /r/a.json: unknown capability_id"


def test_format_findings_is_sorted_for_stable_output():
    items = [
        Finding(Path("/r/b.json"), "refs", "", "second"),
        Finding(Path("/r/a.json"), "schema", "/x", "first"),
    ]
    assert format_findings(items) == ("[schema] /r/a.json#/x: first\n[refs] /r/b.json: second")


def test_format_findings_of_nothing_is_empty():
    assert format_findings([]) == ""


def test_findings_are_hashable_so_callers_can_dedupe():
    a = Finding(Path("/r/a.json"), "refs", "", "dup")
    b = Finding(Path("/r/a.json"), "refs", "", "dup")
    assert len({a, b}) == 1
