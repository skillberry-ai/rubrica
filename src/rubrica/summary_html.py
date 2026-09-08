"""The markup half of `run-summary`. `summary.py` reads and computes; this renders.

Hand-built markup over a templating dependency, the choice
`scripts/render-pipeline-diagram.py` already made in this repo: the project has
three runtime dependencies, each argued for in pyproject.toml, and a report is a
poor reason to make Jinja the fourth.

Everything user-controlled goes through `summary.esc`. That is not stylistic:
`discriminating_fact` and a verdict's `notes` are rendered into `title`
attributes and both carry double quotes in real runs, so an unescaped value ends
the attribute and spills prose into the tag. Dict keys and numbers go through it
too -- a hand-edited artifact can put markup in a key, and a rule that has an
exception is a rule nobody can check by reading.

The page is self-contained -- inline CSS, inline JS, no external asset and no
network -- so it still reads when the run directory is archived or opened
offline. Links to sibling artifacts are relative, which is what lets the page
travel with the run while remaining openable on its own.

`decisions.md` is the one artifact this module reads, and every other section
calls the builder in `summary.py` that owns its document and renders whatever
comes back, `Absent` included. That is what keeps the two halves separable: a
section that disagrees with the `gate-brief` a reader runs beside it is a defect
in one builder rather than in two spellings of the same read.

The exception is deliberate rather than an oversight, and `_decisions` states it
again where it happens: `decisions.md` is prose all the way down, so a builder
over it would return `str | Absent` having computed nothing -- a pass-through
whose only work is the escaping this module does anyway. There is nothing for the
reading half to own, so the cut would buy a symmetry and no separability.
`test_summary_html_reads_exactly_one_artifact_and_names_it` is what keeps this
sentence true: a second read there fails the suite rather than quietly making the
docstring wrong.
"""

from __future__ import annotations

from rubrica import summary
from rubrica.paths import RunPaths
from rubrica.summary import Malformed, Marker, esc

_CSS = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 1200px;
       padding: 2rem; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.1rem; margin-top: 2.5rem;
     border-bottom: 1px solid currentColor; padding-bottom: .25rem; }
h3 { font-size: .95rem; margin: 1.4rem 0 .3rem; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid #8884; }
th { cursor: pointer; user-select: none; white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.absent { opacity: .65; font-style: italic; }
/* An artifact that is there and unreadable is a defect in the run, not a stage
   that has not happened yet -- so it carries the flag rule's weight rather than
   absence's grey, and says so in words either way. */
.malformed { border-left: 3px solid #c60; padding-left: .5rem; font-style: italic; }
.note { opacity: .7; font-size: 12px; }
.flag { border-left: 3px solid #c60; padding: .4rem .75rem; margin: .4rem 0; }
.flag .thr { opacity: .7; font-size: 12px; }
.spine { display: flex; flex-wrap: wrap; gap: .3rem; list-style: none; padding: 0; }
.spine li { padding: .15rem .5rem; border: 1px solid #8886; border-radius: 3px;
            font-size: 12px; }
.spine li.yes { font-weight: 600; } .spine li.no { opacity: .45; }
.cell.yes { background: #2a72; } .cell.no { background: #c602; }
.matrix td.cell { white-space: nowrap; font-size: 12px; }
/* The goal grid's four states. `yes` and `no` reuse the cell matrix's tints --
   same question, same answer -- and the two extra ones are what a goal-by-depth
   cell can be that a capability cell cannot: reached at a depth the goal never
   asked for, and a depth that is simply not this goal's business. Each also
   carries a mark and a title, per the `.hole-reason` rule below: colour alone
   never carries a distinction on this page. */
.gcell.yes { background: #2a72; } .gcell.no { background: #c602; }
.gcell.off { background: #85f3; } .gcell.na { opacity: .35; }
.matrix td.gcell, .matrix th.gcell { white-space: nowrap; font-size: 12px;
    text-align: center; font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
/* An unreachable hole is a closed question; every other reason is an open one a
   human at gate 2 may still act on. Weight and a rule carry it, never colour
   alone -- each row also says which in words. */
.hole-reason.open { font-weight: 600; border-left: 3px solid #c60; }
.hole-reason.closed { opacity: .6; }
.hole-reason .qkind { font-size: 11px; opacity: .7; font-weight: 400; }
.clip { opacity: .6; }
details summary { cursor: pointer; }
pre { white-space: pre-wrap; font-size: 12px; }
"""

# Sorting and filtering only. No fetch, no external library: the page must work
# from a file:// URL with no network.
_JS = """
document.querySelectorAll('table.sortable').forEach(function (table) {
  table.querySelectorAll('th').forEach(function (th, i) {
    th.addEventListener('click', function () {
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      var asc = !(th.dataset.asc === 'true');
      th.dataset.asc = asc;
      rows.sort(function (a, b) {
        var x = a.cells[i].textContent.trim();
        var y = b.cells[i].textContent.trim();
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) { return asc ? nx - ny : ny - nx; }
        return asc ? x.localeCompare(y) : y.localeCompare(x);
      });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
});
var filter = document.getElementById('scn-filter');
if (filter) {
  filter.addEventListener('input', function () {
    var q = filter.value.toLowerCase();
    document.querySelectorAll('#scn-table tbody tr').forEach(function (tr) {
      tr.style.display = tr.textContent.toLowerCase().indexOf(q) === -1 ? 'none' : '';
    });
  });
}
"""

# A field the document does not carry, rendered rather than left blank.
# `summary.esc(None)` is the empty string by design -- right for prose, wrong for
# a table cell: measured in Task 2, a manifest with no `limits` rendered
# `max_rounds` as an empty `<td>`, and a blank cell reads as a ceiling of nothing
# rather than as a limit the manifest never recorded.
_NOT_RECORDED = '<span class="absent">not recorded</span>'


def _val(value) -> str:
    """One scalar cell: the escaped value, or an explicit absence marker.

    The empty string takes the marker too, not only `None`. Nearly every scalar
    `summary.py` reads goes through `str(payload.get(key, ""))`, so a field the
    artifact never carried and a field carrying `""` arrive here
    indistinguishable -- and both are absences a reader must be able to see. `0`
    and `False` are values and render as themselves: `0 == ""` is False, which is
    why this is an equality test against `""` rather than a truthiness test.

    **A JSON boolean renders `yes`/`no`, not `True`/`False`.** Measured on
    `run-20260825-094033`: 35 cells read `True` and one read `False`, in Python's
    spelling on a page that is otherwise about a run rather than about the program
    reading it -- and the scenario table's `instance` column, one column away from
    two of them, already rendered `yes`. Settled here because this is the single
    scalar-cell policy; settling it per call site is how the page came to spell one
    boolean two ways.

    `is True` / `is False` rather than `== True`: `1 == True`, and a count of one
    is not a yes.
    """
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None or value == "":
        return _NOT_RECORDED
    return esc(value)


# The width at which a prose cell is clipped. One constant for the two columns
# that clip -- a disposition's `reason` and a gap's `why_it_matters` -- because a
# reader comparing the two tables should not have to notice they cut at different
# places.
_CLIP_AT = 120


def _clipped(text: str) -> str:
    """Prose for a cell, with a visible mark when anything was cut.

    The full text is on the cell's `title` either way, but nothing on the page
    says to hover: a sentence clipped at `_CLIP_AT` characters reads as a complete
    one, and the reader who most needs the rest is exactly the one with no way to
    tell there is any. The ellipsis is a character rather than a CSS affordance
    for the reason the labels in `_hole_reason` are words: it survives the page
    being printed, dumped to text, or read with the stylesheet stripped.
    """
    if len(text) <= _CLIP_AT:
        return _val(text)
    return esc(text[:_CLIP_AT].rstrip()) + '<span class="clip">&hellip;</span>'


def _table(headers: tuple[str, ...], rows: list[str], *, css_id: str = "", num: tuple = ()) -> str:
    """A sortable table with its headings escaped here, so no caller can forget.

    `num` names the right-aligned columns by their heading rather than by index:
    the index of a column moves whenever one is inserted before it, and a
    misaligned column is the kind of defect nobody notices in a review.
    """
    head = "".join(
        f'<th class="num">{esc(h)}</th>' if h in num else f"<th>{esc(h)}</th>" for h in headers
    )
    ident = f' id="{esc(css_id)}"' if css_id else ""
    return (
        f'<table class="sortable"{ident}><thead><tr>{head}</tr></thead>'
        f"<tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
    )


def _pct(value) -> str:
    """A coverage percentage: a float to three places, anything else verbatim.

    Display formatting, which is not the coercion Task 5's pass-through ruling is
    against: `"pct": "half"` still renders `half`, because a non-numeric pct is a
    score-stage defect for `validate` to name and a `0.0` in its place would hide
    it. What this drops is float noise -- measured on `run-20260825-094033`,
    19-of-148 cells rendered as `0.12837837837837837`, seventeen digits in a cell
    nobody reads past the second.

    Three places rather than one, and that is measured too: the field is a
    *fraction* in every coverage document on disk (0.55 on `run-20260823-112746`,
    1.0 on the toy world), so `:.1f` would render 11-of-20 cells as `0.6` -- a
    rounding a reader can catch out against the covered and total columns beside
    it. At three places 0.128 and 0.550 both survive, and nothing on this page
    turns on the fourth.
    """
    if isinstance(value, float):
        return esc(f"{value:.3f}")
    return _val(value)


def _hole_reason(reason: str) -> str:
    """A hole's reason, with `unreachable` set apart from every other one.

    Spec 3.4's requirement and its reasoning: an `unreachable` hole is a *closed*
    question -- the cell has no natural instance, so no projection and no later
    round will fill it -- while every other reason names an open one that a human
    at gate 2 may still act on. Rendered flat, the two read alike, and a reader
    counting open holes counts the closed ones with them.

    Distinguished by a word as well as a class. The class is what carries it in a
    browser; the word is what survives the page being printed, piped through a
    text dump, or read with the stylesheet stripped -- and a distinction that
    exists only in a colour is one a colour-blind reader does not have.

    A hole whose `reason` is missing counts as open: it is the reading that puts
    the cell in front of a human rather than filing it away, and an unrecorded
    reason is a score-stage defect for `validate` to name.
    """
    closed = reason == "unreachable"
    kind = "closed" if closed else "open"
    label = "closed question" if closed else "open question"
    return (
        f'<td class="hole-reason {kind}">{_val(reason)} '
        f'<span class="qkind">({esc(label)})</span></td>'
    )


def _kv_table(pairs) -> str:
    """A two-column key/value table over an arbitrary mapping.

    Used for `target`, `denominator` and the smoke report, which `summary.py`
    deliberately carries as whole dicts rather than unpacking into fields: the
    page prints them key by key, so a schema revision adds a row here instead of
    silently dropping one. Not sortable -- a two-row table nobody sorts, and the
    `<th>` cursor would advertise an interaction that does nothing.
    """
    rows = "".join(f"<tr><td>{esc(k)}</td><td>{_val(v)}</td></tr>" for k, v in pairs)
    return f"<table><tbody>{rows}</tbody></table>"


def _marker(body: Marker) -> str:
    """A marker as one sentence: what was looked for, and why there is no body.

    Two sentences, not one, because the two markers are two facts and the spine
    above asserts one of them. `Absent` is a stage that has not run: the spine
    shows it unproduced and the reader is done. `Malformed` is an artifact the
    spine *counts* -- it exists, so the stage wrote something -- that this section
    could not read, which is a defect `validate --stage X` will name. Spelling
    both "Not present" is what let one page say `score` had produced an artifact
    and that `03-coverage/` was not there.

    `why` is printed in parentheses rather than mapped onto a fixed line per
    section, because a builder can return the same marker for more than one
    reason: `utilisation` distinguishes "the seal has not run" from
    "01-claims/ or 01-world-model.json unreadable".
    """
    tail = f" ({esc(body.why)})" if body.why else ""
    if isinstance(body, Malformed):
        return f'<p class="malformed">Present but unreadable: {esc(body.what)}{tail}</p>'
    return f'<p class="absent">Not present: {esc(body.what)}{tail}</p>'


def _section(heading: str, body) -> str:
    """One section, with its heading always present.

    A marker renders as a stated absence naming what was looked for, never as a
    skipped section: on a run that stopped at extract, "no 01-world-model.json" is
    the most informative thing the world model section can say, and a section that
    disappears is indistinguishable from one this renderer forgot.
    """
    inner = _marker(body) if isinstance(body, Marker) else body
    return f"<h2>{esc(heading)}</h2>\n{inner}\n"


def _spine(run: RunPaths) -> str:
    """Every stage, marked produced or absent, and the tally under it.

    Leads the page because "how far did this get" is the first thing a reader of a
    partial run needs, and 10 of the 11 runs measured at design time were partial.
    """
    rows = summary.stage_spine(run)
    items = "".join(
        f'<li class="{"yes" if row.produced else "no"}">{esc(row.name)}</li>' for row in rows
    )
    produced = sum(1 for row in rows if row.produced)
    return (
        f'<ul class="spine">{items}</ul>'
        f"<p>{esc(produced)} of {esc(len(rows))} stages produced an artifact.</p>"
        # The reconciliation, stated where the claim is made: this row tests that
        # the evidence *exists*, and a section below tests that it can be read. A
        # stage bolded here whose section says "Present but unreadable" is those
        # two tests disagreeing about one artifact on purpose, and a reader who is
        # not told that reads it as a rendering bug.
        '<p class="note">Produced means the stage\'s artifact exists. Whether it '
        "can be read is each section's own answer below, which is why a bolded "
        "stage can sit above a section reporting an unreadable artifact.</p>"
    )


def _header(run: RunPaths):
    got = summary.header(run)
    if isinstance(got, Marker):
        return got
    fields = (
        ("run_id", got.run_id),
        ("created_utc", got.created_utc),
        ("schema_version", got.schema_version),
        ("max_rounds", got.max_rounds),
        ("max_scenarios", got.max_scenarios),
        ("max_scenario_part_bytes", got.max_scenario_part_bytes),
    )
    parts = [_kv_table(fields)]
    if got.stages:
        rows = [
            "<tr>"
            f"<td>{_val(record.stage)}</td>"
            f"<td>{_val(record.model)}</td>"
            f"<td>{_val(record.effort)}</td>"
            f'<td class="mono">{_val(record.skill_sha256)}</td>'
            "</tr>"
            for record in got.stages
        ]
        parts.append("<h3>Stage records</h3>")
        parts.append(_table(("stage", "model", "effort", "skill sha256"), rows))
        parts.append(
            '<p class="note">Which model at which effort ran against which skill hash '
            "-- the only thing on this page that says whether two runs are comparable.</p>"
        )
    else:
        parts.append(
            '<p class="absent">manifest.stages records no dispatched stage. '
            "The stages that run as code never have an entry; a dispatched one that "
            "does not is the stage-record-incomplete flag.</p>"
        )
    return "\n".join(parts)


def _flags(run: RunPaths) -> str:
    """Each flag with the rule that fired it.

    The threshold is rendered beside the headline and not dropped, because a flag
    whose rule is not on the page is a black box a reader cannot argue with --
    Task 7 measured that a renderer omitting it would pass every test that module
    has, which is why `test_render_states_every_flag_with_its_threshold` asserts
    every flag's threshold text over a run engineered to fire all of them. No
    numeral here on purpose: the table grows, and the count that used to be written
    down in three places went stale the moment issue #37 added a flag.
    """
    fired = summary.flags(run)
    if not fired:
        return '<p class="absent">No flags fired.</p>'
    return "\n".join(
        f'<div class="flag"><b>{esc(flag.headline)}</b> '
        f'<span class="thr">{esc(flag.threshold)}</span><br>{esc(flag.detail)}</div>'
        for flag in fired
    )


def _inputs(run: RunPaths):
    got = summary.inputs(run)
    if isinstance(got, Marker):
        return got
    kinds = ", ".join(f"{esc(kind)}: {esc(count)}" for kind, count in sorted(got.kinds.items()))
    parts = [
        f"<p>{esc(len(got.rows))} input(s), {esc(got.total_bytes)} bytes total"
        + (f" &middot; {kinds}</p>" if kinds else "</p>")
    ]
    if not got.rows:
        parts.append('<p class="absent">manifest.json lists no input.</p>')
        return "\n".join(parts)
    rows = []
    for row in got.rows:
        # Linked only when there is a filename to link: `00-inputs/` with nothing
        # after it points at the directory, which is not this row's artifact.
        stored = (
            f'<a href="00-inputs/{esc(row.stored_as)}">{esc(row.stored_as)}</a>'
            if row.stored_as
            else _NOT_RECORDED
        )
        rows.append(
            "<tr>"
            f'<td class="mono">{_val(row.artifact_id)}</td>'
            f"<td>{_val(row.kind)}</td>"
            f'<td class="num">{esc(row.bytes_)}</td>'
            # The full digest on the title, the first twelve in the cell: 64 mono
            # characters per row is most of the table's width, and the digest is
            # something a reader compares rather than reads.
            f'<td class="mono" title="{esc(row.sha256)}">{_val(row.sha256[:12])}</td>'
            f'<td class="mono" title="{esc(row.source_path)}">{stored}</td>'
            "</tr>"
        )
    parts.append(
        _table(
            ("artifact_id", "kind", "bytes", "sha256", "stored as"),
            rows,
            num=("bytes",),
        )
    )
    parts.append(
        '<p class="note">In the manifest\'s own order, which on a run that came '
        "through triage is the priority order intake materialised.</p>"
    )
    return "\n".join(parts)


def _objective(run: RunPaths):
    got = summary.objective(run)
    if isinstance(got, Marker):
        return got
    parts = [
        f"<p><b>Declared objective:</b> {_val(got.declared)}</p>",
        # `_val`, never a boolean test: `supported` is typed `object` because it
        # comes straight off a document that may have been hand-edited, and the
        # gate-0 verdict turns on it -- rendering a malformed one as False would
        # invent a verdict the pass never gave.
        f"<p><b>Supported:</b> {_val(got.supported)}"
        f" &middot; <b>predicted surfaces:</b> {_val(got.predicted_count)}"
        f" &middot; <b>observed surfaces:</b> {esc(len(got.surfaces))}</p>",
        '<p class="note">The predicted count against the observed one is the '
        "surface-divergence surface a human reads at gate 0.</p>",
    ]
    if not got.surfaces:
        parts.append('<p class="absent">The objective pass recorded no surface.</p>')
        return "\n".join(parts)
    rows = [
        "<tr>"
        f"<td>{_val(surface.name)}</td>"
        f'<td class="num">{esc(surface.candidates)}</td>'
        f'<td class="num">{esc(surface.bytes_)}</td>'
        f'<td class="mono" title="{esc(", ".join(surface.evidence))}">'
        f"{esc(len(surface.evidence))}</td>"
        "</tr>"
        for surface in got.surfaces
    ]
    parts.append(
        _table(
            ("surface", "candidates", "bytes", "evidence"),
            rows,
            num=("candidates", "bytes", "evidence"),
        )
    )
    return "\n".join(parts)


def _disposition_rows(members: list[dict]) -> list[str]:
    """One row per disposition, reading the raw record rather than a dataclass.

    `summary.dispositions` carries the members through unmodified, so the field
    names here are triage-0.1.json's own. `reason` is prose and goes on a title
    attribute for `_scenarios`' reason: it is a paragraph in every real run, and a
    column of paragraphs makes one row taller than the rest of the page.
    """
    return [
        "<tr>"
        f'<td class="num">{_val(member.get("priority"))}</td>'
        f'<td class="mono">{_val(member.get("candidate_id"))}</td>'
        f"<td>{_val(member.get('authority'))}</td>"
        f'<td title="{esc(member.get("reason"))}">'
        f"{_clipped(str(member.get('reason', '')))}</td>"
        "</tr>"
        for member in members
    ]


def _dispositions(run: RunPaths):
    got = summary.dispositions(run)
    if isinstance(got, Marker):
        return got
    parts = [f"<p>{esc(got.admit_count)} admitted, {esc(got.decline_count)} declined.</p>"]
    if got.admits:
        parts.append("<h3>Admitted, in priority order</h3>")
        parts.append(
            _table(
                ("priority", "candidate_id", "authority", "reason"),
                _disposition_rows(got.admits),
                num=("priority",),
            )
        )
    else:
        parts.append('<p class="absent">00-triage.json records no admitted candidate.</p>')
    if not got.declines_by_reason:
        parts.append('<p class="absent">No candidate was declined.</p>')
    for code, members in got.declines_by_reason.items():
        # Collapsed by default: a declined candidate is gone as completely as if
        # the corpus never held it, so the group counts must be visible at a
        # glance while the rows behind them are a click away.
        parts.append(
            f"<details><summary>Declined &mdash; {esc(code)} ({esc(len(members))})</summary>"
            + _table(
                ("priority", "candidate_id", "authority", "reason"),
                _disposition_rows(members),
                num=("priority",),
            )
            + "</details>"
        )
    return "\n".join(parts)


def _deficiencies(run: RunPaths) -> str:
    """Every deficiency, with the projection that would close it and whether one did.

    `closed_by` is rendered as a status rather than dropped: it is the only thing
    separating a deficiency a human answered from one nothing has, and `brief.py`
    draws the same line at gate 0 (`closed by X` against `OPEN`). The wording
    follows it, so the page and the brief a reader runs beside it agree.
    """
    found = summary.deficiencies(run)
    if not found:
        return (
            '<p class="absent">No deficiency was recorded. A run with neither '
            "00-triage.json nor 00-audit.json and a run whose audit recorded none "
            "read the same here; the pipeline progress above says which.</p>"
        )
    rows = [
        "<tr>"
        f'<td class="mono">{_val(item.id_)}</td>'
        f"<td>{f'closed by {esc(item.closed_by)}' if item.closed_by else '<b>OPEN</b>'}</td>"
        f"<td>{_val(item.statement)}</td>"
        + (
            f"<td>{esc(item.projection)}</td>"
            if item.projection
            # A deficiency nothing would close is the one gate 0 has to rule on
            # unaided, so the absence is stated rather than left blank.
            else '<td><span class="absent">nothing would close it</span></td>'
        )
        + "</tr>"
        for item in found
    ]
    return _table(("deficiency_id", "status", "statement", "projection"), rows)


def _world_model(run: RunPaths):
    got = summary.world_model(run)
    if isinstance(got, Marker):
        return got
    # `_NOT_RECORDED` rather than the number for a None count, which is the state
    # the document carries no such key at all. `esc(None)` is the empty string, so
    # this cell would otherwise render blank -- and a blank next to a row of numbers
    # reads as zero, which is the one reading that must not happen here: the sealed
    # model omits `services` when no pass wrote a grouping and carries `[]` when a
    # pass looked and found no tools, and those are different facts about the target.
    counts = "".join(
        f"<tr><td>{esc(kind)}</td>"
        f'<td class="num">{_NOT_RECORDED if count is None else esc(count)}</td></tr>'
        for kind, count in got.counts.items()
    )
    return "\n".join(
        [
            f"<table><tbody>{counts}</tbody></table>",
            "<h3>Target</h3>",
            _kv_table(sorted(got.target.items())),
            "<h3>Denominator</h3>",
            _kv_table(sorted(got.denominator.items())),
            '<p class="note">The contradictions count above is the sealed one. The '
            "Contradictions section below tallies the fan-out parts instead: they are "
            "two facts, and a divergence between them is a finding about the run.</p>",
        ]
    )


def _utilisation(run: RunPaths):
    got = summary.utilisation(run)
    if isinstance(got, Marker):
        return got
    # `pct is None` means "no claim to cite", which is a different fact from 0%:
    # 0% says every claim was dropped, which is a judgment about the reconcile
    # passes.
    overall = (
        f"{esc(f'{got.pct:.1f}')}%"
        if got.pct is not None
        else '<span class="absent">no claim to cite</span>'
    )
    parts = [f"<p><b>{overall}</b> &mdash; {esc(got.cited)} of {esc(got.total)} claims cited.</p>"]
    if got.uncited:
        parts.append(
            f"<p>{esc(len(got.uncited))} input(s) contributed no cited claim: "
            f'<span class="mono">{esc(", ".join(got.uncited))}</span></p>'
        )
    else:
        parts.append("<p>Every input with claims contributed at least one cited claim.</p>")
    rows = [
        "<tr>"
        f'<td class="mono">{_val(row.get("artifact_id"))}</td>'
        f'<td class="num">{_val(row.get("cited"))}</td>'
        f'<td class="num">{_val(row.get("total"))}</td>'
        f'<td class="num">{_val(row.get("percent"))}</td>'
        "</tr>"
        for row in got.per_artifact
    ]
    parts.append(
        _table(
            ("artifact_id", "cited", "total", "percent"),
            rows,
            num=("cited", "total", "percent"),
        )
    )
    return "\n".join(parts)


def _gaps(run: RunPaths) -> str:
    found = summary.gaps(run)
    if not found:
        return (
            '<p class="absent">The world model records no gap. A run with no world '
            "model reads the same here; the World model section above says which.</p>"
        )
    rows = [
        "<tr>"
        f'<td class="mono">{_val(gap.id_)}</td>'
        f"<td>{_val(gap.subject)}</td>"
        f"<td>{_val(', '.join(gap.blocks))}</td>"
        f"<td>{_val(gap.unknown)}</td>"
        f'<td title="{esc(gap.why)}">{_clipped(gap.why)}</td>'
        "</tr>"
        for gap in found
    ]
    return _table(("gap", "subject", "blocks", "unknown", "why it matters"), rows)


def _contradictions(run: RunPaths):
    got = summary.contradictions(run)
    if isinstance(got, Marker):
        return got
    rows = "".join(
        f'<tr><td>{esc(key)}</td><td class="num">{esc(count)}</td></tr>'
        for key, count in got.by_resolution.items()
    )
    return "\n".join(
        [
            f"<p>{esc(got.total)} contradiction(s) recorded across "
            f"{esc(got.parts_swept)} subject part(s).</p>",
            f"<table><tbody>{rows}</tbody></table>",
            '<p class="note">A tally, not a substitute for opening the parts: a '
            "non-zero unresolved is the cheapest signal that one is worth reading.</p>",
        ]
    )


def _matrix(cells) -> str:
    """The capability matrix: one row per capability, that capability's own cells in it.

    **Not a capability-by-outcome-class grid, and that is a measured decision.**
    An outcome class belongs to one capability in every run on disk, so the full
    cross product is almost entirely empty: `run-20260825-094033` has 148 cells
    over 37 capabilities and 148 distinct outcome classes, which is a 5,476-cell
    grid that is 97% padding -- 328KB of page, most of it dots. The row-per-
    capability shape is linear in the cells that exist and puts each outcome class
    id beside its own colour, which is what a reader scanning for an open cell
    needs anyway.

    First-seen order, both down the rows and along each one, rather than sorted:
    that is `latest.json`'s own order, and re-sorting would make the page disagree
    with the document a reader opens beside it. It is deterministic either way,
    which is what `test_render_is_byte_identical_across_two_calls` locks.
    """
    caps: list[str] = []
    by_cap: dict[str, list] = {}
    for cell in cells:
        if cell.capability_id not in caps:
            caps.append(cell.capability_id)
        by_cap.setdefault(cell.capability_id, []).append(cell)
    rows = []
    for cap in caps:
        tds = []
        for cell in by_cap[cap]:
            ids = ", ".join(cell.scenario_ids)
            tds.append(
                f'<td class="cell {"yes" if cell.covered else "no"}" '
                f'title="{esc(ids) if ids else "no scenario covers this cell"}">'
                f"{esc(cell.outcome_class_id)} ({esc(len(cell.scenario_ids))})</td>"
            )
        rows.append(f'<tr><td class="mono">{esc(cap)}</td>' + "".join(tds) + "</tr>")
    return (
        '<div class="scroll"><table class="matrix">'
        "<tbody>\n" + "\n".join(rows) + "\n</tbody></table></div>"
    )


# The four states a goal-by-hop-depth cell can be in, each as (class, mark, title).
# A table rather than a chain of conditionals in the loop, because the property the
# tests lock is that all four are *distinguishable* -- and two of them differ from
# their neighbour only in the title, which is exactly the pair a hand-written
# conditional collapses. `{d}` is the depth.
_GOAL_STATES: dict[tuple[bool, bool], tuple[str, str, str]] = {
    (True, True): ("yes", "\u2713", "covered at hop depth {d}"),
    (True, False): ("no", "\u2717", "expected at hop depth {d}, no scenario reached it"),
    # Not an open slot and not a covered one. Measured on `run-20260825-094033`:
    # `goal-slack-draft` has `present: [1]` against `expected: [2, 3]`, is `covered:
    # false`, and carries no hole saying why -- so this cell is the only place on
    # the page that fact appears at all.
    (False, True): (
        "off",
        "\u26a0",
        "a scenario reached hop depth {d}, which this goal does not expect",
    ),
    (False, False): ("na", "\u00b7", "not expected at hop depth {d}"),
}


def _goal_matrix(goals) -> str:
    """The goal matrix: one row per goal, one column per hop depth, four states.

    **A real grid, where the capability matrix deliberately is not one.** `_matrix`
    above refuses the cross product because an outcome class belongs to one
    capability, so 37x148 would be 97% padding. Here the columns are hop depths,
    which `coverage-0.1.json` bounds to 1..5 -- so the grid is at most five columns
    wide however large the world model is, and it is dense: on
    `run-20260825-094033`, 22 goals over three depths, 66 cells with nothing
    padded.

    Drawn because the grid shape is what makes one particular failure legible.
    `docs/design/limitations.md` records, at "The loop's stopping rule is blind to
    goal-coverage progress", that after round 2 each of nine uncovered goals was
    missing exactly one hop depth and always the deepest. Fourteen of the 22 goals
    on that run have a scenario and are still uncovered. As a row of two comma
    lists that is a diff a reader does by eye; as a column of open cells under
    `hop 3` it is the first thing they see.

    Columns are the union of every depth in *either* list, ascending. The union
    rather than the expected depths alone is what gives the `off` state a column at
    all, and ascending because hop depth is a magnitude -- `hop 3` left of `hop 1`
    reads as a rendering bug. Rows keep `latest.json`'s own order, the same ruling
    `_matrix` records.
    """
    depths = sorted({d for goal in goals for d in (*goal.expected, *goal.present)})
    head = "".join(f'<th class="gcell">hop {esc(d)}</th>' for d in depths)
    rows = []
    for goal in goals:
        ids = ", ".join(goal.scenario_ids)
        # The scenarios belong to the row, never to a cell: `goal_matrix` records
        # them per goal and says nothing about which one reached which depth, so a
        # cell title claiming that would be the page asserting what the document
        # does not.
        first = (
            f'<td class="mono" title="{esc(ids) if ids else "no scenario covers this goal"}">'
            f"{esc(goal.goal_id)}</td>"
        )
        expected, present = set(goal.expected), set(goal.present)
        tds = []
        for depth in depths:
            css, mark, title = _GOAL_STATES[(depth in expected, depth in present)]
            # The depth is printed in the cell as well as in the column heading:
            # the grid scrolls sideways at five columns on a narrow window, and a
            # bare tick with the heading off-screen names nothing.
            label = f"{esc(depth)}&nbsp;{mark}" if css != "na" else mark
            tds.append(f'<td class="gcell {css}" title="{esc(title.format(d=depth))}">{label}</td>')
        rows.append(f"<tr>{first}" + "".join(tds) + "</tr>")
    return (
        '<div class="scroll"><table class="matrix"><thead><tr><th>goal</th>'
        f"{head}</tr></thead><tbody>\n" + "\n".join(rows) + "\n</tbody></table></div>"
    )


def _coverage(run: RunPaths):
    got = summary.coverage(run)
    if isinstance(got, Marker):
        return got
    rows = [
        "<tr>"
        f"<td>{_val(row.round_)}</td>"
        f"<td>{_val(row.verdict)}</td>"
        f'<td class="num">{esc(row.cells_covered)}</td>'
        f'<td class="num">{esc(row.cells_total)}</td>'
        f'<td class="num">{_pct(row.pct)}</td>'
        f'<td class="num">{esc(row.goals_covered)}</td>'
        f'<td class="num">{esc(row.goals_total)}</td>'
        f'<td class="num">{_val(row.new_cells)}</td>'
        f'<td class="num">{_val(row.rounds_without_progress)}</td>'
        f'<td class="num">{esc(row.holes)}</td>'
        "</tr>"
        for row in got.rounds
    ]
    parts = [
        f"<p>Coverage ended <b>{_val(got.terminal_verdict)}</b>, per 03-coverage/latest.json.</p>",
        _table(
            (
                "round",
                "verdict",
                "cells covered",
                "cells total",
                "pct",
                "goals covered",
                "goals total",
                "new cells",
                "rounds without progress",
                "holes that round",
            ),
            rows,
            num=(
                "cells covered",
                "cells total",
                "pct",
                "goals covered",
                "goals total",
                "new cells",
                "rounds without progress",
                "holes that round",
            ),
        ),
        # The two hole counts come from different documents by design and can
        # differ without either being wrong -- `holes that round` is each round
        # document's own array, the list below is `latest.json`'s. Said here so a
        # reader cannot take the difference for an arithmetic error.
        '<p class="note">"holes that round" counts each round document\'s own '
        "holes[]; the list further down is latest.json's, so the two can differ "
        "without either being wrong.</p>",
    ]
    if got.implied is not None:
        parts.append(
            f"<p>The world model implies {esc(got.implied.get('implied'))} scenario(s) "
            f"against a ceiling {esc(got.implied.get('ceiling'))} "
            f"(basis {esc(got.implied.get('basis'))}, sizing denominator "
            f"{esc(got.implied.get('denominator'))}"
            + (", <b>ceiling binding</b>" if got.implied.get("ceiling_binding") else "")
            + ").</p>"
        )
        # The word carries two numbers on this page and neither said which sense it
        # meant: `sizing.implied_size` divides capability cells plus expected
        # hop-depth slots, less any blocked cells, by one run's measured acceptance
        # rate, while the World model section prints the sealed `denominator`
        # object, which counts cells and goals. Measured on run-20260825-094033:
        # 127 here against 148 cells and 22 goals there.
        parts.append(
            '<p class="note">The sizing denominator is capability cells plus '
            "expected hop-depth slots, less blocked cells &mdash; not the world "
            'model\'s own <span class="mono">denominator</span> record above, '
            "which counts cells and goals.</p>"
        )
    else:
        # One line for three facts -- no world model yet, a world model
        # `implied_size` could not read, and the guarded exception -- because
        # separating them would put a sizing diagnostic's failure modes on a page
        # that composes rather than analyses.
        parts.append(
            '<p class="absent">Implied suite size not computed: no world model, or '
            "an artifact it needs could not be read.</p>"
        )
    parts.append(f"<h3>Capability matrix ({esc(len(got.cells))} cells)</h3>")
    if got.cells:
        parts.append(_matrix(got.cells))
        parts.append(
            '<p class="note">One row per capability, holding that capability\'s own '
            "cells; the count in each is how many scenarios cover it, and the title "
            "names them.</p>"
        )
    else:
        parts.append('<p class="absent">latest.json carries no capability cell.</p>')
    parts.append(f"<h3>Goal matrix ({esc(len(got.goals))} goals)</h3>")
    if got.goals:
        parts.append(_goal_matrix(got.goals))
        parts.append(
            '<p class="note">One row per goal, one column per hop depth: '
            "<b>&#10003;</b> covered, <b>&#10007;</b> expected and unreached, "
            "<b>&#9888;</b> reached at a depth the goal does not expect, "
            "<b>&middot;</b> not expected. A goal counts as covered only when every "
            "expected depth is reached, so a row of one tick and one cross is an "
            "uncovered goal that already has a scenario. The first cell names the "
            "scenarios covering the goal &mdash; the document records those per goal, "
            "not per depth.</p>"
        )
    else:
        parts.append('<p class="absent">latest.json carries no goal row.</p>')
    parts.append(f"<h3>Open holes at the last round ({esc(len(got.holes))})</h3>")
    # Said at the heading rather than left to the column: a reader comparing this
    # count against the matrix's is comparing two different denominators, and the
    # caveat above this table is about a different discrepancy entirely (per-round
    # holes against latest.json's).
    parts.append(
        '<p class="note">A hole names a capability cell or a goal, so this count '
        "and the cell count above are over different sets and need not agree.</p>"
    )
    if got.holes:
        hole_rows = [
            "<tr>"
            f'<td class="mono">{_val(hole.ref)}</td>'
            + _hole_reason(hole.reason)
            + f"<td>{_val(hole.justification)}</td>"
            "</tr>"
            for hole in got.holes
        ]
        # `ref`, not `cell`: a hole's `ref` is a cell ref *or* a goal ref --
        # measured on `run-20260825-094033`, 22 of 151 holes were `goal:goal-...`
        # -- and heading the column `cell` beside a `Capability matrix (148 cells)`
        # made `151 holes` read as an arithmetic error. The count is right; the
        # header was wrong.
        parts.append(_table(("ref (cell or goal)", "reason", "justification"), hole_rows))
    else:
        parts.append("<p>latest.json records no open hole.</p>")
    return "\n".join(parts)


def _scenarios(run: RunPaths):
    got = summary.scenarios(run)
    if isinstance(got, Marker):
        return got
    if not got:
        return '<p class="absent">02-scenarios.json records no scenario.</p>'
    rows = []
    for row in got:
        # Linked when a verdict was read for this id, plain text otherwise. The
        # proxy is the verdict *value*, which is the only evidence of the join the
        # row carries -- a scenario judged with no `verdict` field is a challenge
        # defect for `validate` to name, and it renders unlinked here.
        ident = (
            f'<a href="05-verdicts/{esc(row.id_)}.json">{esc(row.id_)}</a>'
            if row.verdict
            else _val(row.id_)
        )
        # `(overstated)` / `(understated)` beside the count rather than a column of
        # its own: the comparison is already a flag, and this is where a reader who
        # followed the flag looks.
        #
        # Both directions since issue #37, and the understated branch is first
        # because the two are mutually exclusive per row and the order of an
        # if/elif is the only place a reader can see which one was considered the
        # more consequential: an overstated hop_depth wastes a tool call, an
        # understated one ships a scenario tagged shallower than it is, and coverage
        # is credited per hop depth. `<b>` on that one alone, for the same reason --
        # the flag table already ranks them, and a row a reader lands on from the
        # flag should not read as its sibling's equal.
        calls = _val(row.min_tool_calls)
        if row.difficulty_understated:
            calls = (
                f'<span title="minimum_tool_calls_found &gt; hop_depth">'
                f"{esc(row.min_tool_calls)} <b>(understated)</b></span>"
            )
        elif row.difficulty_overstated:
            calls = (
                f'<span title="minimum_tool_calls_found &lt; hop_depth">'
                f"{esc(row.min_tool_calls)} (overstated)</span>"
            )
        # Spec 3.5 asks for three hrefs per row -- `04-instances/<id>/`,
        # `05-verdicts/<id>.json` and `06-suite/<id>/` -- because the drill-in path
        # is what replaces inlining a seed or a golden answer in the cell. The
        # href is safe without a second check for the same reason the id above is
        # linked only when a verdict was read: `has_instance` is False and
        # `suite_files` is empty for every id `is_safe_segment` rejected, so an
        # id like `../../etc` never reaches an href here.
        instance = (
            f'<a href="04-instances/{esc(row.id_)}/">yes</a>' if row.has_instance else _NOT_RECORDED
        )
        package = (
            f'<a href="06-suite/{esc(row.id_)}/">{esc(", ".join(row.suite_files))}</a>'
            if row.suite_files
            # Three states read the same here -- no package, an unreadable
            # 06-suite/, an unsafe id -- and the honest reading for an inventory is
            # that none of them put a task on disk.
            else '<span class="absent">no package</span>'
        )
        rows.append(
            "<tr>"
            f'<td class="mono">{ident}</td>'
            f"<td>{_val(row.round_)}</td>"
            f'<td title="{esc(row.discriminating_fact)}">{_val(row.title)}</td>'
            f'<td class="mono">{_val(row.goal_id)}</td>'
            f'<td class="mono">{_val(row.actor_id)}</td>'
            f"<td>{_val(row.hop_depth)}</td>"
            f'<td class="mono">{_val(", ".join(row.cells))}</td>'
            f"<td>{_val(row.status)}</td>"
            f'<td title="{esc(row.notes)}">{_val(row.verdict)}</td>'
            f"<td>{_val(row.uniquely_determined)}</td>"
            f"<td>{_val(row.derivable)}</td>"
            f'<td class="num">{calls}</td>'
            f"<td>{instance}</td>"
            f'<td class="mono">{package}</td>'
            "</tr>"
        )
    return "\n".join(
        [
            f"<p>{esc(len(got))} scenario(s) proposed.</p>",
            '<input id="scn-filter" placeholder="filter scenarios">',
            # Wrapped rather than left to squeeze: fourteen columns overflow 1200px
            # on a real run, and the page body must never scroll horizontally.
            '<div class="scroll">'
            + _table(
                (
                    "id",
                    "round",
                    "title",
                    "goal",
                    "actor",
                    "hop depth",
                    "cells",
                    "status",
                    "verdict",
                    "uniquely determined",
                    "derivable",
                    "min tool calls",
                    "instance",
                    "package",
                ),
                rows,
                css_id="scn-table",
                num=("min tool calls",),
            )
            + "</div>",
            '<p class="note">The discriminating fact is on the title cell and the '
            "verdict notes are on the verdict cell: both are paragraphs, and a column "
            "of paragraphs makes one row taller than the rest of the page. Each row "
            "links to what it has on disk: the id to its verdict, the instance cell "
            "to 04-instances/, the package cell to 06-suite/.</p>",
        ]
    )


def _challenge(run: RunPaths):
    got = summary.challenge(run)
    if isinstance(got, Marker):
        return got
    tallies = "".join(
        f'<tr><td>{esc(key)}</td><td class="num">{esc(count)}</td></tr>'
        for key, count in got.tallies.items()
    )
    parts = [
        f"<p>{esc(got.judged)} scenario(s) judged, {esc(got.packages)} package(s) "
        "in 06-suite/.</p>",
        f"<table><tbody>{tallies}</tbody></table>",
        '<p class="note">The two counts diverge for real reasons -- a re-seeded '
        "scenario is judged and never emitted, one whose record disappeared between "
        "the stages is emitted and pruned -- so they are read from separate "
        "directories rather than one from the other.</p>",
    ]
    if got.incomplete_packages:
        parts.append(
            f"<p><b>{esc(len(got.incomplete_packages))} package(s) missing a file:</b> "
            f'<span class="mono">{esc(", ".join(got.incomplete_packages))}</span> '
            "&mdash; emit began these and did not finish them.</p>"
        )
    if got.smoke is not None:
        parts.append("<h3>Smoke report</h3>")
        parts.append(_kv_table(sorted(got.smoke.items(), key=lambda pair: str(pair[0]))))
    else:
        parts.append('<p class="absent">No smoke report (07-report.json).</p>')
    return "\n".join(parts)


def _decisions(run: RunPaths):
    """`decisions.md` verbatim inside a `<pre>`, or a stated absence.

    Read here rather than in `summary.py` because there is nothing to compute: it
    is the one artifact in the run that is prose all the way down, and a dataclass
    holding one string would be a section builder that only escapes.

    `run.decisions` rather than a path joined here, which is `paths.py`'s rule for
    every artifact path in this repo -- a rename there cannot leave a stale
    spelling behind.

    **`UnicodeDecodeError` is caught here, and it is not an `OSError`.** It is a
    `ValueError`, so before this line it escaped `_decisions`, `render`,
    `run_summary` and every handler in `cli.py` but the catch-all, and made a
    *report* exit 1 -- with an `[internal]` finding advising `rubrica validate
    --stage <stage>`, which cannot name `decisions.md` at all, since it is prose
    with no schema. Reproduced end to end with a `decisions.md` holding
    `b"Some prose with a latin-1 byte: \\xe9tape\\n"`. `artifacts.read_json` ruled
    on the identical shape for every artifact that *does* have a schema -- bytes
    that are not UTF-8 are malformed content, reported against the path that holds
    them rather than raised past the handler that knows one -- and this is the same
    ruling for the one artifact this module reads itself. It is `Malformed` rather
    than `errors="replace"` for the reason `Malformed` exists: a page that silently
    substituted U+FFFD would render prose nobody wrote and say nothing about it,
    while a run whose `decisions.md` is not text is a fact a reader at a gate needs.

    An `OSError` splits the same way: `decisions.md` is unwritten on most runs, and
    one that is there and unopenable -- a mode-000 file, a directory in its place
    -- is a different fact from one nothing has written yet.
    """
    try:
        text = run.decisions.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return Malformed("decisions.md", f"not UTF-8 text: {exc}")
    except OSError:
        return summary._absent_or_malformed(
            run.decisions, "decisions.md", "the file could not be read"
        )
    return f"<pre>{esc(text)}</pre>"


def render(run: RunPaths) -> str:
    """The whole page, as one string."""
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{esc(run.root.name)} — rubrica run summary</title>",
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{esc(run.root.name)}</h1>",
        # Stated once, at the top, because it is a property of the whole page and
        # of one flag: every link below is relative to the run directory, which is
        # correct for the default destination and dead for every `-o` outside it --
        # and `-o` is exactly the flag an operator reaches for on a read-only run.
        '<p class="note">Artifact links are relative to the run directory, so they '
        "resolve only while this page sits inside it: written elsewhere with "
        '<span class="mono">-o</span>, the page still reads and its links do not '
        "resolve.</p>",
        _section("Pipeline progress", _spine(run)),
        _section("Run header", _header(run)),
        _section("Flags", _flags(run)),
        _section("Inputs", _inputs(run)),
        _section("Objective", _objective(run)),
        _section("Dispositions", _dispositions(run)),
        _section("Deficiencies", _deficiencies(run)),
        _section("World model", _world_model(run)),
        _section("Claim utilisation", _utilisation(run)),
        _section("Gaps", _gaps(run)),
        _section("Contradictions", _contradictions(run)),
        _section("Coverage", _coverage(run)),
        _section("Scenarios", _scenarios(run)),
        _section("Challenge and emitted suite", _challenge(run)),
        _section("Decisions", _decisions(run)),
        f"<script>{_JS}</script>",
        "</body></html>",
    ]
    return "\n".join(parts)
