from pathlib import Path

from rubrica.findings import Finding, format_findings


def test_a_finding_is_unwaived_by_default():
    """Additive: every existing construction passes four fields and must keep
    behaving exactly as it did."""
    f = Finding(Path("a.json"), "refs", "/", "boom")
    assert f.waived is False
    assert str(f) == "[refs] a.json#/: boom"


def test_a_waived_finding_says_so_on_its_line():
    """Prefixed rather than suffixed so a line-oriented reader can filter on it
    without parsing the message."""
    f = Finding(Path("a.json"), "refs", "/", "boom", waived=True)
    assert str(f) == "[waived] [refs] a.json#/: boom"


def test_format_findings_still_sorts_stably_with_a_mix():
    a = Finding(Path("a.json"), "refs", "/", "aaa", waived=True)
    b = Finding(Path("b.json"), "refs", "/", "bbb")
    assert format_findings([b, a]).splitlines() == [
        "[waived] [refs] a.json#/: aaa",
        "[refs] b.json#/: bbb",
    ]
