#!/usr/bin/env python3
"""Render docs/concepts/pipeline-diagram.html: the pipeline drawn rather than described.

The prose counterpart is docs/concepts/pipeline.md. This page exists because
three properties of the pipeline are hard to hold in a sentence and easy to see
in a drawing: which stages fan out and where their barrier falls, which of the
gates a human holds, and the fact that no arrow ever runs from one stage
directly to the next -- every one of them goes through an artifact on disk.

ROWS below is the whole content model; everything else computes geometry from
it. That is deliberate. The spine is tall enough that hand-placed coordinates
would have to be recomputed for every row below an insertion, which is how a
drawing like this stops being updated and starts being wrong -- so adding a
stage here is a table edit, and the numbers follow.

The output is committed so a reader needs no build step, and
tests/unit/test_docs_accuracy.py re-renders and compares: a hand-edit to the
HTML, or a stage added to paths.STAGES without a row here, fails the suite.
Re-render with `python scripts/render-pipeline-diagram.py`, or verify with
`--check`.

Lines here stay inside ruff's 100 columns even though most of them are markup.
The wrapping was applied at existing spaces only and the rendered page was
pixel-compared before and after, so it costs the drawing nothing.
"""

from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path

# scripts/ -> repository root -> the committed page.
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "docs" / "concepts" / "pipeline-diagram.html"

# ---------------------------------------------------------------- geometry ---
W = 1120
GUT = 56  # left gutter: loop bracket + the two challenge feedback curves
DIR_X = 96  # right edge of the dir-prefix column (text right-aligned here)
BOX_X, BOX_W = 108, 286
ART_X, ART_W = 466, 300
GATE_X = 786
BAND_X0, BAND_X1 = 60, W - 20

BOX_H = 62
FAN_OFF = 7  # per-shadow offset for a fan-out stack
ROW_GAP = 20
BAND_H = 42
BAND_GAP = 16

MONO_W = 0.60  # advance width per em, monospace
SANS_W = 0.53


def mono_w(text: str, size: float) -> float:
    return len(text) * size * MONO_W


# ------------------------------------------------------------------- rows ----
# Every field here is checked against the repo: paths.RunPaths for the
# artifacts, each SKILL.md's contract block for reads/writes/runs-as,
# validate.STAGE_ARTIFACTS for what layer 1 demands, CLAUDE.md's stage table
# for where the gates sit.
ROWS: list[dict] = [
    dict(
        kind="stage",
        dir="—",
        name="survey",
        runs="code · walks a corpus",
        art=["00-catalogue.json"],
        gates=["validate"],
        note="one bounded digest per candidate; mints the run",
    ),
    dict(
        kind="stage",
        dir="—",
        name="triage",
        runs="rb-triage",
        art=["00-triage.json"],
        gates=["validate", "check-refs"],
        note="admit / decline, one disposition per candidate",
    ),
    dict(
        kind="stage",
        dir="—",
        name="triage-slices",
        runs="code · partitions the catalogue into shards",
        art=["00-slices.json", "00-slices/<id>.json"],
        gates=["validate"],
        note="a reading unit, not a decision unit",
    ),
    dict(
        kind="stage",
        dir="—",
        name="triage-objective",
        runs="rb-triage-objective",
        art=["00-objective.json"],
        gates=["validate"],
        note="rules the objective from the corpus map, before any candidate digest is read",
    ),
    dict(
        kind="stage",
        dir="—",
        name="triage-rule",
        runs="rb-triage-rule",
        art=["00-dispositions/<slice_id>.json"],
        gates=["validate"],
        fan="fan-out · one member per slice",
        note="rules on every candidate in one slice -- admit, or decline with a reason",
    ),
    dict(
        kind="stage",
        dir="—",
        name="triage-seal",
        runs="code · assembles the staged parts",
        art=["00-triage.json"],
        gates=["validate"],
        note="sorts last in the triage family; writes what triage above still writes directly",
    ),
    dict(
        kind="band",
        n="0",
        title="Human gate 0 — the triage record",
        sub="Decides what the run can ever know. Nothing below intake reads the corpus again, "
        "so a declined candidate is gone as completely as if it never existed.",
    ),
    dict(
        kind="stage",
        dir="00",
        name="intake",
        runs="code · admits what triage ruled on",
        art=["manifest.json", "00-inputs/<stored_as>"],
        gates=["validate"],
        note="fixes the run's identity: digests, limits, target",
    ),
    dict(
        kind="stage",
        dir="01a",
        name="extract",
        runs="rb-extract",
        art=["01-claims/<artifact_id>.json"],
        gates=["validate"],
        fan="fan-out · one member per admitted input",
        note="",
    ),
    dict(
        kind="stage",
        dir="01b",
        name="reconcile",
        runs="rb-reconcile",
        art=["01-world-model.json"],
        gates=["validate", "check-refs"],
        barrier="barrier · every extract member has finished",
        note="",
    ),
    dict(
        kind="band",
        n="1",
        title="Human gate 1 — the world model",
        sub="gate-brief lays out claim utilisation per input and the implied suite size. "
        "A blocking gap halts one step earlier and arrives at this same human.",
    ),
    dict(
        kind="note",
        text="loop · round = 1 … K,  K = manifest.limits.max_rounds",
    ),
    dict(
        kind="stage",
        dir="02",
        name="propose",
        runs="rb-propose · one dispatch per round",
        art=["02-scenarios.json"],
        gates=["validate"],
        loop="top",
        note="append-only, so it can never be a fan-out",
    ),
    dict(
        kind="stage",
        dir="03",
        name="score",
        runs="rb-score",
        art=[
            "03-coverage/round-N.json · latest.json",
            "02-scenarios.json  (folds, rejects)",
        ],
        gates=["validate", "check-refs"],
        barrier="barrier · closes the round",
        loop="bottom",
        note="runs dedupe-candidates itself, as Method step 1",
    ),
    dict(
        kind="verdicts",
        label="latest.json verdict — score computes it, only the orchestrator acts on it",
        chips=[
            ("continue", "round++"),
            ("converged", "leave the loop"),
            ("halted_no_progress", "leave the loop"),
            ("halted_round_cap", "leave the loop"),
        ],
    ),
    dict(
        kind="band",
        n="2",
        title="Human gate 2 — scenarios and coverage",
        sub="The cost gate. Everything below is paid per scenario, twice over: once to "
        "instantiate it and once to challenge it.",
    ),
    dict(
        kind="stage",
        dir="04",
        name="instantiate",
        runs="rb-instantiate",
        art=[
            "04-instances/<sid>/",
            "seed.json · expected.json · rationale.md",
        ],
        gates=["validate", "check-refs"],
        fan="fan-out · one member per active scenario",
        note="check-refs here is the reachability gate",
    ),
    dict(
        kind="stage",
        dir="05",
        name="challenge",
        runs="rb-challenge",
        art=["05-verdicts/<sid>.json"],
        gates=["validate", "check-refs"],
        fan="fan-out · one member per instance",
        note="check-refs only once every member has finished",
    ),
    dict(
        kind="band",
        n="3",
        title="Human gate 3 — rejects and re-seeds",
        sub="The verdict tally: accept · re-seed · reject. A re-seed buys one more "
        "instantiate dispatch; a reject sends the scenario back to be scored again.",
    ),
    dict(
        kind="stage",
        dir="06",
        name="emit",
        runs="rb-emit · thin wrapper over rubrica emit",
        art=[
            "06-suite/<sid>/",
            "task.toml · instruction.md · seed.json",
            "golden.json · provenance.md",
            "tests/{expected.json,verify.py,test.sh}",
        ],
        gates=["validate", "check-refs"],
        note="the compiler is code: same inputs, same bytes",
    ),
    dict(
        kind="stage",
        dir="07",
        name="smoke",
        runs="code · runs the suite against the roster",
        art=["07-report.json"],
        gates=["validate", "check-refs"],
        note="a reporter and a gate: any verdict but healthy stops",
    ),
]


def is_prompt(row: dict) -> bool:
    return row.get("runs", "").startswith("rb-")


# ---------------------------------------------------------------- layout -----
def lay_out(rows: list[dict]) -> int:
    """Assign a `y` to every row and return the total drawing height."""
    y = 74  # column headers live above this
    for row in rows:
        if row["kind"] == "band":
            row["y"] = y + BAND_GAP
            row["h"] = BAND_H + 20  # the band plus its two-line sub-caption
            y = row["y"] + row["h"] + BAND_GAP
        elif row["kind"] == "note":
            row["y"] = y + 6
            row["h"] = 20
            y = row["y"] + row["h"] + 8
        elif row["kind"] == "verdicts":
            row["y"] = y + 4
            row["h"] = 50
            y = row["y"] + row["h"] + 10
        else:
            box_h = BOX_H + (2 * FAN_OFF + 14 if row.get("fan") else 0)
            art_h = 20 + 15 * len(row["art"])
            gate_h = 46 if row.get("note") else 26
            row["h"] = max(box_h, art_h, gate_h)
            row["y"] = y + (18 if row.get("barrier") else 0)
            y = row["y"] + row["h"] + ROW_GAP
    return y + 6


HEIGHT = lay_out(ROWS)


def by_name(name: str) -> dict:
    return next(r for r in ROWS if r.get("name") == name)


def mid(row: dict) -> float:
    return row["y"] + BOX_H / 2


# ------------------------------------------------------------------- SVG -----
def esc(text: str) -> str:
    return escape(text, quote=True)


def text(x, y, s, cls, anchor="start", size=11):
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" class="{cls}" text-anchor="{anchor}" '
        f'font-size="{size}">{esc(s)}</text>'
    )


def pill(x, y, label, cls="g-pill", size=10.5):
    w = mono_w(label, size) + 18
    out = [
        f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="19" rx="9.5" class="{cls}"/>',
        text(x + w / 2, y + 13.5, label, f"{cls}-t", "middle", size),
    ]
    return "".join(out), w


def hero() -> str:
    p: list[str] = []
    a = p.append

    a(
        f'<svg viewBox="0 0 {W} {HEIGHT}" class="dia hero" role="img" '
        'aria-label="Every stage of a Rubrica run in order, each with what it runs as, '
        "the artifact it writes into the run directory, and the deterministic gates that "
        "follow it. The human gates sit as full-width bands after triage, reconcile, score "
        'and challenge.">'
    )
    a(
        '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0 L10 5 L0 10 z" class="ar"/></marker>'
        '<marker id="ar-s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0 0 L10 5 L0 10 z" class="ar-s"/></marker></defs>'
    )

    # -- column headers
    a(text(DIR_X, 30, "dir", "hd", "end"))
    a(text(BOX_X, 30, "stage · what runs it", "hd"))
    a(text(ART_X, 30, "what it writes into the run directory", "hd"))
    a(text(GATE_X, 30, "gates, in order", "hd"))
    a(f'<line x1="{GUT}" y1="42" x2="{BAND_X1}" y2="42" class="rule-hd"/>')

    for row in ROWS:
        y = row["y"]

        if row["kind"] == "band":
            a(
                f'<rect x="{BAND_X0}" y="{y}" width="{BAND_X1 - BAND_X0}" '
                f'height="{BAND_H}" rx="3" class="band"/>'
            )
            a(f'<rect x="{BAND_X0}" y="{y}" width="5" height="{BAND_H}" class="band-edge"/>')
            a(text(BAND_X0 + 20, y + 26, f"GATE {row['n']}", "band-n", "start", 13))
            a(text(BAND_X0 + 96, y + 26, row["title"], "band-t", "start", 13.5))
            a(text(BAND_X0 + 20, y + BAND_H + 17, row["sub"], "band-s", "start", 12))
            continue

        if row["kind"] == "note":
            a(text(BOX_X, y + 14, row["text"], "loop-note", "start", 11))
            continue

        if row["kind"] == "verdicts":
            a(text(BOX_X, y + 12, row["label"], "vd-lab", "start", 10.5))
            x = BOX_X
            for label, effect in row["chips"]:
                svg, w = pill(x, y + 22, label, "vd-pill", 10.5)
                a(svg)
                a(text(x + w / 2, y + 52, effect, "vd-eff", "middle", 9.5))
                x += w + 12
            continue

        # ---- a stage row
        fan = row.get("fan")
        box_y = y

        if row.get("barrier"):
            a(
                f'<line x1="{BOX_X}" y1="{y - 9}" x2="{BOX_X + BOX_W}" y2="{y - 9}" '
                f'class="barrier"/>'
            )
            a(text(BOX_X + BOX_W + 8, y - 5, row["barrier"], "barrier-t", "start", 9.5))

        a(text(DIR_X, box_y + 26, row["dir"], "dir", "end", 12))

        cls = "box-prompt" if is_prompt(row) else "box-code"
        if fan:
            for i in (2, 1):
                off = i * FAN_OFF
                a(
                    f'<rect x="{BOX_X + off}" y="{box_y + off}" width="{BOX_W}" '
                    f'height="{BOX_H}" rx="2" class="{cls} ghost"/>'
                )
        a(f'<rect x="{BOX_X}" y="{box_y}" width="{BOX_W}" height="{BOX_H}" rx="2" class="{cls}"/>')
        if is_prompt(row):
            a(f'<rect x="{BOX_X}" y="{box_y}" width="4.5" height="{BOX_H}" class="prompt-edge"/>')
        a(text(BOX_X + 16, box_y + 26, row["name"], "st-name", "start", 15))
        a(text(BOX_X + 16, box_y + 45, row["runs"], "st-runs", "start", 10.5))
        if fan:
            a(text(BOX_X, box_y + BOX_H + 2 * FAN_OFF + 13, fan, "fan-t", "start", 9.5))

        # writes-arrow
        ay = box_y + BOX_H / 2
        x0 = BOX_X + BOX_W + (2 * FAN_OFF + 8 if fan else 8)
        a(
            f'<line x1="{x0}" y1="{ay:.0f}" x2="{ART_X - 8}" y2="{ay:.0f}" '
            f'class="edge" marker-end="url(#ar)"/>'
        )
        a(text((x0 + ART_X) / 2, ay - 8, "writes", "edge-t", "middle", 9))

        # artifact chip
        art_h = 12 + 15 * len(row["art"])
        art_y = ay - art_h / 2
        a(
            f'<rect x="{ART_X}" y="{art_y:.0f}" width="{ART_W}" height="{art_h}" rx="2" '
            f'class="artifact"/>'
        )
        for i, line in enumerate(row["art"]):
            a(text(ART_X + 12, art_y + 16 + 15 * i, line, "art-t", "start", 10))

        # gates
        gx = GATE_X
        for g in row["gates"]:
            svg, w = pill(gx, ay - 22, g, "g-pill", 10.5)
            a(svg)
            gx += w + 8
        if row.get("note"):
            a(text(GATE_X, ay + 15, row["note"], "g-note", "start", 10))

    # -- the round loop bracket, in the gutter
    top, bot = by_name("propose"), by_name("score")
    ty, byy = top["y"] + 14, bot["y"] + BOX_H - 14
    a(
        f'<path d="M{BOX_X - 6} {byy:.0f} H30 V{ty:.0f} H{BOX_X - 6}" class="edge loop" '
        f'marker-end="url(#ar)"/>'
    )
    a(
        f'<text x="24" y="{(ty + byy) / 2:.0f}" class="loop-t" text-anchor="middle" '
        f'font-size="9.5" transform="rotate(-90 24 {(ty + byy) / 2:.0f})">continue</text>'
    )

    # -- challenge's two feedback edges, also in the gutter
    ch = by_name("challenge")
    inst = by_name("instantiate")
    sc = by_name("score")
    for x_lane, src_dy, dst_row, dst_dy, label in (
        (44, 18, inst, BOX_H - 16, "re-seed · once"),
        (14, 34, sc, BOX_H - 30, "reject"),
    ):
        y0 = ch["y"] + src_dy
        y1 = dst_row["y"] + dst_dy
        a(
            f'<path d="M{BOX_X - 6} {y0:.0f} H{x_lane} V{y1:.0f} H{BOX_X - 6}" '
            f'class="edge back" marker-end="url(#ar-s)"/>'
        )
        a(
            f'<text x="{x_lane - 6}" y="{(y0 + y1) / 2:.0f}" class="back-t" '
            f'text-anchor="middle" font-size="9" '
            f'transform="rotate(-90 {x_lane - 6} {(y0 + y1) / 2:.0f})">{esc(label)}</text>'
        )

    a("</svg>")
    return "\n".join(p)


# ------------------------------------------------- figure 2: the only channel -
def fig_channel() -> str:
    return """
<svg viewBox="0 0 940 388" class="dia" role="img" aria-label="A dispatched stage receives only
three things — the run directory, its stage name and its skill file path — and every fact it uses
comes from an artifact on disk. There is no edge at all between one stage and the next.">
  <defs><marker id="c-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
    orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class="ar"/></marker>
  <marker id="c-ar-s" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7"
    orient="auto-start-reverse"><path d="M10 0 L0 5 L10 10 z" class="ar"/></marker></defs>

  <text x="16" y="24" class="hd" font-size="11">what a dispatch carries</text>
  <text x="372" y="24" class="hd" font-size="11">two adjacent stages</text>
  <text x="700" y="24" class="hd" font-size="11">the run directory</text>
  <line x1="16" y1="36" x2="924" y2="36" class="rule-hd"/>

  <rect x="16" y="128" width="152" height="96" rx="2" class="box-code"/>
  <text x="92" y="158" class="st-name" text-anchor="middle" font-size="13">rb-orchestrate</text>
  <text x="92" y="178" class="st-runs" text-anchor="middle" font-size="10">not a stage:</text>
<text x="92" y="193" class="st-runs" text-anchor="middle" font-size="10">no stage, no schemas</text>
<text x="92" y="211" class="st-runs" text-anchor="middle" font-size="10">writes decisions.md</text>

  <line x1="172" y1="176" x2="196" y2="176" class="edge" marker-end="url(#c-ar)"/>

  <rect x="200" y="140" width="118" height="76" rx="2" class="dispatch"/>
  <text x="212" y="160" class="art-t" font-size="10">run dir</text>
  <text x="212" y="178" class="art-t" font-size="10">stage name</text>
  <text x="212" y="196" class="art-t" font-size="10">skill path</text>
  <text x="259" y="232" class="edge-t" text-anchor="middle" font-size="9">and nothing else</text>

  <line x1="322" y1="160" x2="368" y2="128" class="edge" marker-end="url(#c-ar)"/>
  <line x1="322" y1="196" x2="368" y2="264" class="edge" marker-end="url(#c-ar)"/>

  <rect x="372" y="94" width="196" height="62" rx="2" class="box-prompt"/>
  <rect x="372" y="94" width="4.5" height="62" class="prompt-edge"/>
  <text x="388" y="120" class="st-name" font-size="14">reconcile</text>
  <text x="388" y="139" class="st-runs" font-size="10">rb-reconcile</text>

  <rect x="372" y="236" width="196" height="62" rx="2" class="box-prompt"/>
  <rect x="372" y="236" width="4.5" height="62" class="prompt-edge"/>
  <text x="388" y="262" class="st-name" font-size="14">propose</text>
  <text x="388" y="281" class="st-runs" font-size="10">rb-propose</text>

  <line x1="470" y1="160" x2="470" y2="232" class="edge cut"/>
  <line x1="452" y1="212" x2="488" y2="182" class="cut-x"/>
  <line x1="452" y1="182" x2="488" y2="212" class="cut-x"/>
  <text x="496" y="192" class="cut-t" font-size="9.5">no conversational</text>
  <text x="496" y="205" class="cut-t" font-size="9.5">context is threaded</text>

  <rect x="700" y="58" width="224" height="26" rx="2" class="artifact"/>
  <text x="712" y="75" class="art-t" font-size="10">manifest.json</text>
  <rect x="700" y="94" width="224" height="26" rx="2" class="artifact"/>
  <text x="712" y="111" class="art-t" font-size="10">01-claims/&lt;artifact_id&gt;.json</text>
  <rect x="700" y="156" width="224" height="26" rx="2" class="artifact hi"/>
  <text x="712" y="173" class="art-t" font-size="10">01-world-model.json</text>
  <rect x="700" y="240" width="224" height="26" rx="2" class="artifact"/>
  <text x="712" y="257" class="art-t" font-size="10">02-scenarios.json</text>
  <rect x="700" y="276" width="224" height="26" rx="2" class="artifact"/>
  <text x="712" y="293" class="art-t" font-size="10">03-coverage/latest.json</text>

  <line x1="696" y1="71" x2="574" y2="108" class="edge" marker-end="url(#c-ar)"/>
  <line x1="696" y1="107" x2="574" y2="118" class="edge" marker-end="url(#c-ar)"/>
  <text x="662" y="100" class="edge-t" text-anchor="middle" font-size="9">reads</text>

  <line x1="574" y1="136" x2="696" y2="164" class="edge" marker-end="url(#c-ar)"/>
  <text x="640" y="142" class="edge-t" text-anchor="middle" font-size="9">writes</text>

  <line x1="696" y1="176" x2="574" y2="250" class="edge" marker-end="url(#c-ar)"/>
  <line x1="696" y1="289" x2="574" y2="278" class="edge" marker-end="url(#c-ar)"/>
  <text x="628" y="228" class="edge-t" text-anchor="middle" font-size="9">reads</text>

  <line x1="574" y1="264" x2="696" y2="252" class="edge" marker-start="url(#c-ar-s)"
    marker-end="url(#c-ar)"/>
  <text x="636" y="272" class="edge-t" text-anchor="middle" font-size="9">reads + appends</text>

  <line x1="16" y1="330" x2="924" y2="330" class="rule-hair"/>
<text x="16" y="352" class="g-note" font-size="10.5">The orchestrator may append exactly two things
    to a re-dispatch, both verbatim machine text, never paraphrased:</text>
<text x="16" y="370" class="g-note" font-size="10.5">a repair's gate findings, and a re-seed's
    verdict fields. A paraphrase is the orchestrator's own conclusion in a finding's clothes.</text>
</svg>
"""


# --------------------------------------------- figure 3: the exit-code contract
def fig_exits() -> str:
    return """
<svg viewBox="0 0 900 292" class="dia" role="img" aria-label="A gate's exit code decides the
orchestrator's next move: zero records the stage and dispatches the next one, one is a repairable
stage defect worth exactly one re-dispatch with the findings appended verbatim, and two means the
harness is misconfigured, so retrying cannot help.">
  <defs><marker id="e-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
    orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class="ar"/></marker>
  <marker id="e-ar-p" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6"
    orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class="ar-s"/></marker></defs>

  <rect x="16" y="98" width="152" height="58" rx="2" class="box-code"/>
  <text x="92" y="123" class="st-name" text-anchor="middle" font-size="13">stage N runs</text>
<text x="92" y="141" class="st-runs" text-anchor="middle" font-size="10">writes its artifact</text>

  <line x1="172" y1="127" x2="212" y2="127" class="edge" marker-end="url(#e-ar)"/>
  <rect x="216" y="90" width="128" height="74" rx="2" class="box-gate"/>
  <text x="280" y="114" class="st-name" text-anchor="middle" font-size="12">the gate</text>
  <text x="280" y="132" class="st-runs" text-anchor="middle" font-size="9.5">validate</text>
  <text x="280" y="147" class="st-runs" text-anchor="middle" font-size="9.5">check-refs</text>

  <line x1="348" y1="104" x2="470" y2="62" class="edge ok" marker-end="url(#e-ar)"/>
  <line x1="348" y1="127" x2="470" y2="127" class="edge warn" marker-end="url(#e-ar)"/>
  <path d="M250 168 V240 H466" class="edge stop" marker-end="url(#e-ar)"/>

  <text x="398" y="84" class="code-0" font-size="16">0</text>
  <text x="410" y="120" class="code-1" font-size="16">1</text>
  <text x="236" y="212" class="code-2" text-anchor="end" font-size="16">2</text>

  <rect x="474" y="34" width="410" height="48" rx="2" class="out ok-b"/>
<text x="490" y="54" class="out-t" font-size="11.5">clean — record-stage, then dispatch stage
    N+1</text>
<text x="490" y="72" class="out-s" font-size="10">the manifest keeps the model, the effort, and a
    hash of the skill file this run used</text>

  <rect x="474" y="94" width="410" height="70" rx="2" class="out warn-b"/>
<text x="490" y="114" class="out-t" font-size="11.5">findings on stdout, one per line — a repairable
    defect</text>
<text x="490" y="132" class="out-s" font-size="10">re-dispatch that stage exactly once, the findings
    appended verbatim.</text>
<text x="490" y="148" class="out-s" font-size="10">Fails its gate a second time → halt and report.
    An exit 1 always names an artifact.</text>

  <rect x="474" y="214" width="410" height="52" rx="2" class="out stop-b"/>
<text x="490" y="234" class="out-t" font-size="11.5">usage error, or a run that cannot be
    read</text>
<text x="490" y="252" class="out-s" font-size="10">halt: the harness is wrong, not the stage, and
    retrying cannot help</text>

  <path d="M560 164 V188 H300 V168" class="edge back" marker-end="url(#e-ar-p)"/>
<text x="430" y="204" class="back-t" text-anchor="middle" font-size="9.5">one repair, then this same
    gate again</text>
</svg>
"""


# ------------------------------------------- figure 4: fan-out and the barrier -
def fig_barrier() -> str:
    return """
<svg viewBox="0 0 900 284" class="dia" role="img" aria-label="Timeline of the challenge fan-out:
three members finish at different times, and because the verdict checker reports every instance
without a verdict from the moment the verdicts directory exists, the reference check is only
meaningful once the last member has finished.">
  <defs><marker id="b-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
    orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class="ar"/></marker></defs>

  <text x="16" y="24" class="hd" font-size="11">dispatch</text>
  <text x="180" y="24" class="hd" font-size="11">members, running concurrently</text>
  <text x="714" y="24" class="hd" font-size="11">barrier, then the gate</text>
  <line x1="16" y1="36" x2="884" y2="36" class="rule-hd"/>

  <rect x="16" y="96" width="120" height="58" rx="2" class="box-prompt"/>
  <rect x="16" y="96" width="4.5" height="58" class="prompt-edge"/>
  <text x="32" y="120" class="st-name" font-size="13">challenge</text>
  <text x="32" y="138" class="st-runs" font-size="9.5">one per instance</text>

  <line x1="140" y1="116" x2="176" y2="70" class="edge" marker-end="url(#b-ar)"/>
  <line x1="140" y1="125" x2="176" y2="125" class="edge" marker-end="url(#b-ar)"/>
  <line x1="140" y1="134" x2="176" y2="180" class="edge" marker-end="url(#b-ar)"/>

  <rect x="180" y="56" width="320" height="28" rx="14" class="member"/>
  <text x="196" y="74" class="art-t" font-size="10">scn-001 → 05-verdicts/scn-001.json</text>
  <rect x="180" y="111" width="500" height="28" rx="14" class="member"/>
  <text x="196" y="129" class="art-t" font-size="10">scn-002 → 05-verdicts/scn-002.json</text>
  <rect x="180" y="166" width="250" height="28" rx="14" class="member"/>
  <text x="196" y="184" class="art-t" font-size="10">scn-003 → 05-verdicts/scn-003.json</text>

  <line x1="430" y1="46" x2="430" y2="216" class="tick"/>
<text x="440" y="234" class="cut-t" font-size="9.5">the first verdict lands, so 05-verdicts/ now
    exists —</text>
<text x="440" y="248" class="cut-t" font-size="9.5">run check-refs here and it condemns the other
    two as missing</text>

  <text x="180" y="236" class="edge-t" font-size="9">bar length = elapsed time  →</text>
  <line x1="700" y1="46" x2="700" y2="206" class="barrier"/>
  <text x="714" y="66" class="barrier-t" font-size="10">every member finished</text>
  <rect x="714" y="112" width="86" height="19" rx="9.5" class="g-pill"/>
  <text x="757" y="125.5" class="g-pill-t" text-anchor="middle" font-size="10.5">check-refs</text>
  <text x="714" y="154" class="g-note" font-size="10">now, and only now, a</text>
  <text x="714" y="168" class="g-note" font-size="10">missing verdict is a</text>
  <text x="714" y="182" class="g-note" font-size="10">real finding</text>
</svg>
"""


# ------------------------------------------------------------------- page -----
CSS = """
:root{
  --ground:#E7EAE7; --paper:#F8F9F7; --sunk:#DEE2DE;
  --ink:#141917; --ink2:#4B5754; --ink3:#77827E; --rule:#C2CAC5; --rule2:#D5DBD6;
  --stamp:#A81E5B; --stamp-ink:#8E1A4D; --stamp-soft:rgba(168,30,91,.09);
  --ok:#1E6B4A; --warn:#8A5806; --stop:#A32B1C;
  --ok-b:rgba(30,107,74,.08); --warn-b:rgba(138,88,6,.08); --stop-b:rgba(163,43,28,.08);
  --mono:ui-monospace,"SF Mono","JetBrains Mono","IBM Plex Mono",Menlo,Consolas,monospace;
  --serif:Charter,"Iowan Old Style","Source Serif 4",Georgia,"Times New Roman",serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#121514; --paper:#1B1F1D; --sunk:#0D100F;
    --ink:#E7EAE6; --ink2:#A2ACA7; --ink3:#7B857F; --rule:#333A36; --rule2:#272D2A;
    --stamp:#F1749F; --stamp-ink:#F79CBC; --stamp-soft:rgba(241,116,159,.13);
    --ok:#63C295; --warn:#D7A24C; --stop:#EA8875;
    --ok-b:rgba(99,194,149,.10); --warn-b:rgba(215,162,76,.10); --stop-b:rgba(234,136,117,.10);
  }
}
:root[data-theme="dark"]{
  --ground:#121514; --paper:#1B1F1D; --sunk:#0D100F;
  --ink:#E7EAE6; --ink2:#A2ACA7; --ink3:#7B857F; --rule:#333A36; --rule2:#272D2A;
  --stamp:#F1749F; --stamp-ink:#F79CBC; --stamp-soft:rgba(241,116,159,.13);
  --ok:#63C295; --warn:#D7A24C; --stop:#EA8875;
  --ok-b:rgba(99,194,149,.10); --warn-b:rgba(215,162,76,.10); --stop-b:rgba(234,136,117,.10);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--serif); font-size:17px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1200px; margin:0 auto; padding:64px 32px 96px}


/* ---- masthead */
.mast{border-bottom:2px solid var(--ink); padding-bottom:22px; margin-bottom:14px}
.eyebrow{
  font-family:var(--mono); font-size:11px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--ink3); display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px;
}
h1{
  font-family:var(--mono); font-weight:600; font-size:clamp(30px,5.4vw,52px);
  letter-spacing:-.02em; line-height:1.02; margin:0; text-wrap:balance;
}
h1 .dim{color:var(--ink3)}
.standfirst{
  max-width:63ch; margin:20px 0 0; font-size:19px; line-height:1.55; color:var(--ink2);
}
.standfirst em{color:var(--ink); font-style:italic}

/* ---- prose */
section{margin-top:60px}
h2{
  font-family:var(--mono); font-size:13px; letter-spacing:.14em; text-transform:uppercase;
font-weight:600; color:var(--stamp-ink); margin:0 0 6px; display:flex; align-items:baseline;
    gap:12px;
}
h2::after{content:""; flex:1; height:1px; background:var(--rule)}
h3{
  font-family:var(--mono); font-size:15px; font-weight:600; letter-spacing:-.01em;
  margin:34px 0 8px; color:var(--ink);
}
p{max-width:66ch; margin:14px 0}
.lede{font-size:18px; max-width:64ch}
code,kbd{
  font-family:var(--mono); font-size:.86em; background:var(--sunk);
  padding:.12em .34em; border-radius:2px; color:var(--ink);
}
strong{font-weight:600}
a{color:var(--stamp-ink); text-decoration-thickness:1px; text-underline-offset:2px}
a:focus-visible{outline:2px solid var(--stamp); outline-offset:2px; border-radius:2px}

/* ---- figures */
figure{margin:34px 0 0; padding:0}
.plate{
  background:var(--paper); border:1px solid var(--rule);
  padding:26px 26px 18px; overflow-x:auto;
}
.plate.wide{
  /* the hero breaks the reading column on wide screens */
  /* capped under the .wrap padding (32px) so the bleed can never scroll the body */
  margin-left:calc(-1 * min(3.4vw, 30px)); margin-right:calc(-1 * min(3.4vw, 30px));
}
svg.dia{display:block; width:100%; height:auto; min-width:0; color:var(--ink)}
svg.hero{min-width:940px}
figcaption{
  font-family:var(--mono); font-size:11px; line-height:1.6; color:var(--ink3);
  margin-top:12px; max-width:90ch;
}
figcaption b{color:var(--ink2); font-weight:600}
figcaption code,.legend code{background:none; padding:0; color:var(--ink2)}

/* ---- svg element classes */
.hd{font-family:var(--mono); fill:var(--ink3); letter-spacing:.1em; text-transform:uppercase}
.rule-hd{stroke:var(--ink); stroke-width:1}
.dir{font-family:var(--mono); fill:var(--ink3)}
.box-code{fill:var(--paper); stroke:var(--ink2); stroke-width:1.4}
.box-prompt{fill:var(--paper); stroke:var(--ink2); stroke-width:1.4;
  stroke-dasharray:none}
.prompt-edge{fill:var(--ink)}
.box-gate{fill:var(--sunk); stroke:var(--ink2); stroke-width:1.4}
.dispatch{fill:none; stroke:var(--ink2); stroke-width:1; stroke-dasharray:3 2.6}
.rule-hair{stroke:var(--rule); stroke-width:1}
.ghost{opacity:.34; fill:none}
.st-name{font-family:var(--mono); fill:var(--ink); font-weight:600}
.st-runs{font-family:var(--mono); fill:var(--ink2)}
.artifact{fill:none; stroke:var(--rule); stroke-width:1; stroke-dasharray:3 2.6}
.artifact.hi{stroke:var(--ink2); stroke-dasharray:3 2.6}
.art-t{font-family:var(--mono); fill:var(--ink2)}
.edge{stroke:var(--ink2); stroke-width:1.2; fill:none}
.edge.ok{stroke:var(--ok)} .edge.warn{stroke:var(--warn)} .edge.stop{stroke:var(--stop)}
.edge.cut{stroke:var(--ink3); stroke-dasharray:4 4}
.cut-x{stroke:var(--stop); stroke-width:1.6}
.cut-t{font-family:var(--mono); fill:var(--ink3)}
.ar{fill:var(--ink2)} .ar-s{fill:var(--stamp)}
.edge-t{font-family:var(--mono); fill:var(--ink3); letter-spacing:.06em}
.g-pill{fill:none; stroke:var(--ink2); stroke-width:1}
.g-pill-t{font-family:var(--mono); fill:var(--ink2)}
.g-note{font-family:var(--mono); fill:var(--ink3)}
.band{fill:var(--stamp-soft); stroke:var(--stamp); stroke-width:1}
.band-edge{fill:var(--stamp)}
.band-n{font-family:var(--mono); fill:var(--stamp-ink); font-weight:700; letter-spacing:.1em}
.band-t{font-family:var(--mono); fill:var(--ink); font-weight:600}
.band-s{font-family:var(--serif); fill:var(--ink2)}
.barrier{stroke:var(--ink); stroke-width:3.4}
.barrier-t{font-family:var(--mono); fill:var(--ink2); letter-spacing:.04em}
.fan-t{font-family:var(--mono); fill:var(--ink3)}
.loop{stroke:var(--ink); stroke-width:1.4}
.loop-t{font-family:var(--mono); fill:var(--ink2); letter-spacing:.1em; text-transform:uppercase}
.loop-note{font-family:var(--mono); fill:var(--ink2); letter-spacing:.04em}
.back{stroke:var(--stamp); stroke-width:1.3; stroke-dasharray:5 3}
.back-t{font-family:var(--mono); fill:var(--stamp-ink); letter-spacing:.06em}
.vd-lab{font-family:var(--mono); fill:var(--ink3)}
.vd-pill{fill:var(--sunk); stroke:var(--rule); stroke-width:1}
.vd-pill-t{font-family:var(--mono); fill:var(--ink)}
.vd-eff{font-family:var(--mono); fill:var(--ink3)}
.member{fill:var(--sunk); stroke:var(--rule); stroke-width:1}
.tick{stroke:var(--ink3); stroke-width:1; stroke-dasharray:3 3}
.out{fill:none; stroke-width:1}
.ok-b{fill:var(--ok-b); stroke:var(--ok)}
.warn-b{fill:var(--warn-b); stroke:var(--warn)}
.stop-b{fill:var(--stop-b); stroke:var(--stop)}
.out-t{font-family:var(--mono); fill:var(--ink); font-weight:600}
.out-s{font-family:var(--serif); fill:var(--ink2)}
.code-0{font-family:var(--mono); fill:var(--ok); font-weight:700}
.code-1{font-family:var(--mono); fill:var(--warn); font-weight:700}
.code-2{font-family:var(--mono); fill:var(--stop); font-weight:700}

/* ---- legend */
.legend{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); gap:14px 26px;
  border-top:1px solid var(--rule); margin-top:16px; padding-top:16px;
}
.legend div{display:flex; gap:11px; align-items:flex-start;
  font-family:var(--mono); font-size:10.5px; line-height:1.5; color:var(--ink3)}
.legend b{display:block; color:var(--ink2); font-weight:600; letter-spacing:.03em}
.swatch{flex:0 0 30px; height:17px; margin-top:1px}

/* ---- tables */
.tbl{width:100%; border-collapse:collapse; margin-top:20px; font-size:14px}
.tbl caption{
  font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--ink3); text-align:left; padding-bottom:8px;
}
.tbl th{
  font-family:var(--mono); font-size:10.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--ink3); font-weight:600; text-align:left; padding:0 14px 8px 0;
  border-bottom:1px solid var(--ink);
}
.tbl td{padding:11px 14px 11px 0; border-bottom:1px solid var(--rule2); vertical-align:top}
.tbl td:first-child{font-family:var(--mono); font-size:12.5px; white-space:nowrap; color:var(--ink)}
.tbl .n{font-family:var(--mono); color:var(--stamp-ink); font-weight:700}
.scroll{overflow-x:auto}

/* ---- callouts */
.rail{
  border-left:3px solid var(--stamp); background:var(--stamp-soft);
  padding:16px 20px; margin:28px 0 0; max-width:72ch;
}
.rail p{margin:0; max-width:none; font-size:16px}
.rail p + p{margin-top:10px}
.rail .tag{
  font-family:var(--mono); font-size:10.5px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--stamp-ink); display:block; margin-bottom:6px;
}
.cols.two{grid-template-columns:repeat(auto-fit,minmax(400px,1fr))}
.cols{display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:28px;
  margin-top:26px}
.cols > div > h3{margin-top:0}
.cols p{max-width:46ch}

footer{
  margin-top:72px; padding-top:20px; border-top:1px solid var(--rule);
  font-family:var(--mono); font-size:11px; color:var(--ink3); line-height:1.7;
}
@media (prefers-reduced-motion:reduce){*{transition:none!important; animation:none!important}}

/* Responsive overrides live last on purpose: an earlier copy of this block lost
   the cascade to the .plate.wide bleed declared further down, and the page
   scrolled sideways by the few pixels the bleed exceeded the padding by. */
@media (max-width:720px){
  body{font-size:16px}
  .wrap{padding:40px 18px 64px}
  .plate{padding:18px 16px 14px}
  .plate.wide{margin-left:0; margin-right:0}
  .standfirst{font-size:17px}
  .cols{gap:22px}
}
"""


def page() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Rubrica Run</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header class="mast">
<div class="eyebrow"><span>rubrica</span><span>pipeline plate</span><span>artifacts on disk are the
    only channel</span></div>
  <h1>The Rubrica Run<br><span class="dim">the stages, the gates, and the
  artifacts between them</span></h1>
  <p class="standfirst">Rubrica builds an agent test suite for a target system out of the
  artifacts that describe it — specs, captured trajectories, source — by chaining AI skills over a
  schema-validated on-disk contract. The experiment it runs is falsifiable: <em>does
  prompt-carried judgment survive a chain of artifact handoffs well enough to produce a suite worth
  running?</em> Everything below is the apparatus that makes the answer readable.</p>
</header>

<section>
  <h2>The run, end to end</h2>
  <p class="lede">Read top to bottom. Each row is one stage: what dispatches it, the artifact it
  leaves in the run directory, and the deterministic gates that must pass before the next stage is
  dispatched at all. The magenta bands are where the run stops for a human.</p>

  <figure>
    <div class="plate wide">{hero()}
    <div class="legend">
<div><svg class="swatch" viewBox="0 0 30 17" aria-hidden="true"><rect x="1" y="1" width="28"
        height="15" class="box-code"/></svg>
        <span><b>code</b>deterministic; no skill file, no manifest.stages entry</span></div>
<div><svg class="swatch" viewBox="0 0 30 17" aria-hidden="true"><rect x="1" y="1" width="28"
        height="15" class="box-prompt"/><rect x="1" y="1" width="3" height="15"
        class="prompt-edge"/></svg>
        <span><b>prompt</b>a dispatched rb-* skill; judgment lives in its prose</span></div>
<div><svg class="swatch" viewBox="0 0 30 17" aria-hidden="true"><rect x="4" y="4" width="24"
        height="12" class="box-prompt ghost"/><rect x="1" y="1" width="24" height="12"
        class="box-prompt"/></svg>
<span><b>fan-out</b>concurrent members, one per slice, each blind to its siblings</span></div>
<div><svg class="swatch" viewBox="0 0 30 17" aria-hidden="true"><line x1="0" y1="9" x2="30" y2="9"
        class="barrier"/></svg>
        <span><b>barrier</b>the gate runs once, after the last member finishes</span></div>
<div><svg class="swatch" viewBox="0 0 30 17" aria-hidden="true"><rect x="1" y="1" width="28"
        height="15" class="artifact"/></svg>
<span><b>artifact</b>a file or directory in the run — the only channel between stages</span></div>
<div><svg class="swatch" viewBox="0 0 30 17" aria-hidden="true"><rect x="1" y="1" width="28"
        height="15" class="band"/><rect x="1" y="1" width="3" height="15" class="band-edge"/></svg>
        <span><b>human gate</b>the run stops; only <code>--no-gate</code> skips one</span></div>
    </div></div>
    <figcaption><b>Fig. 1</b> — Stage order and on-disk numbering come from
    <code>paths.STAGES</code>; the artifact each stage must produce comes from
    <code>validate.STAGE_ARTIFACTS</code>. <code>survey</code> and <code>triage</code> carry no
    <code>0N</code> prefix of their own: they write ahead of the <code>00-inputs/</code> and
    <code>manifest.json</code> that <code>intake</code> mints once gate 0 has passed, and the
    numbering stays intake's, because intake is still what fixes the run's identity.
    <code>decisions.md</code> is not shown as a row — the orchestrator appends to it throughout,
    through <code>rubrica decide</code>.</figcaption>
  </figure>
</section>

<section>
  <h2>Artifacts on disk are the only channel</h2>
  <p class="lede">This is the one architectural rule, and the reason the experiment can be read at
  all. A stage is dispatched with exactly three things — the run directory, the stage name, and its
skill file path. If a stage needs a fact, it reads it from an artifact, or it does not have it.</p>

  <figure>
    <div class="plate">{fig_channel()}</div>
    <figcaption><b>Fig. 2</b> — The missing edge is the point. <code>propose</code> never hears
    from <code>reconcile</code>; it reads <code>01-world-model.json</code>. Fan-out members get a
    fourth thing — the id of their own slice — and never a sibling's. One read edge is left out to
    keep the rest legible: <code>propose</code> also reads <code>manifest.json</code>, for the
    limits it must respect.</figcaption>
  </figure>

  <p>The cost of that rule is real: no stage can lean on a fact it was not handed a file for. The
  payoff is that every handoff is inspectable after the fact. When a suite comes out wrong, the
  artifact that carried the mistake is on disk with a name, and the stage that wrote it is the one
  to blame — which is what makes a bad run evidence instead of an anecdote.</p>

  <div class="rail">
    <span class="tag">Before you raise a finding against a stage</span>
    <p>Check what the stage's <code>reads</code> actually gives it. A finding that requires
    knowledge outside the contract is a finding against the <em>contract or the fixture</em>, never
    against the prompt.</p>
  </div>
</section>

<section>
  <h2>Two check layers, and what neither of them checks</h2>
  <div class="cols">
    <div>
      <h3>Layer 1 · rubrica validate</h3>
      <p>JSON Schema, one schema per artifact kind, shipped as package data.
      <code>validate.STAGE_ARTIFACTS</code> says which kinds a stage must have produced, so a stage
      that wrote nothing fails rather than passing trivially.</p>
    </div>
    <div>
      <h3>Layer 2 · rubrica check-refs</h3>
      <p>Cross-artifact references, seed conformance, reachability, invariant evaluation. It runs
      every checker the run currently has inputs for — there is no such thing as a stage-scoped
      <code>check-refs</code>.</p>
    </div>
  </div>
  <p>Layer 2 checks that an element <em>references</em> a resolvable claim. It never checks that
  the claim <em>supports</em> it. Support is semantic, and no mechanical check for it exists here on
  purpose — two real defects once lived under that hole in the golden fixture itself. What no check
  reaches at all is whether a dispatched model actually followed its prompt; that is what the live
  exercises are for, and one recorded dispatch is one sample.</p>
</section>

<section>
  <h2>The exit-code contract</h2>
  <p class="lede">The orchestrator has no judgment of its own about whether a stage went well. It
  branches on three integers, and the whole repair policy follows from them.</p>
  <figure>
    <div class="plate">{fig_exits()}</div>
    <figcaption><b>Fig. 3</b> — Two invariants hold the contract up, and both have been violated in
    this repo before: <b>a stage defect must never surface as 2</b>, and <b>a 1 must never have
    empty stdout</b>. A third was learned the hard way — a 1 must name the <em>right</em> artifact.
    <code>check-refs</code> over an unreadable <code>01-claims/</code> once reported four fabricated
    “no such claim” findings against a world model that was perfectly correct.</figcaption>
  </figure>
</section>

<section>
  <h2>Fan-outs, and why the barrier is not decoration</h2>
  <p class="lede">Three stages fan out: <code>extract</code> per admitted input,
  <code>instantiate</code> per active scenario, <code>challenge</code> per instance. Members are
  concurrent and mutually blind. The gate that follows is not.</p>
  <figure>
    <div class="plate">{fig_barrier()}</div>
    <figcaption><b>Fig. 4</b> — <code>refs.check_verdicts</code> reports every instance without a
    verdict from the moment <code>05-verdicts/</code> exists, so run mid-fan-out it condemns the
    members that simply have not finished yet. Run the gate <em>once</em>, after the last member
    returns.</figcaption>
  </figure>
  <p><code>propose</code> looks like a fan-out and is not. It declares <code>scenarios</code> under
  both <code>reads</code> and <code>writes</code>, because <code>02-scenarios.json</code> is a
  single append-only document: two members appending at once would each read the same file and
  overwrite the other's scenarios, with no gate anywhere able to report the loss. One dispatch per
  round, holding every hole that round targets.</p>
</section>

<section>
  <h2>The human gates</h2>
  <p class="lede">Gates 1 through 3 review a judgment made from evidence already in the run; a
  human overturning one corrects an inference about the target. Gate 0 decides what the run can
  ever know — which makes it different in kind, and is why <code>rb-triage</code> cannot also hold
  it. The same party selecting the inputs and ratifying the selection would make the whole run
  unfalsifiable.</p>
  <div class="scroll">
  <table class="tbl">
    <caption>What is on the table at each stop, and who is holding it</caption>
<thead><tr><th>Gate</th><th>Sits after</th><th>Held by</th><th>What the human is ruling
      on</th></tr></thead>
    <tbody>
<tr><td><span class="n">0</span> the triage record</td><td>triage</td><td>the operator — the
        orchestrator is not yet dispatched</td>
        <td>The objective verdict and the grouped declines. A candidate <code>rb-triage</code>
        declined is gone as completely as if the corpus never contained it, so this is the only
        moment the run's evidence base is negotiable.</td></tr>
      <tr><td><span class="n">1</span> the world model</td><td>reconcile</td><td>rb-orchestrate</td>
        <td>Claim utilisation per input and the implied suite size. An input the world model cites
        nothing from is exactly the fact this gate exists to surface.</td></tr>
<tr><td><span class="n">2</span> scenarios and coverage</td><td>the round
        loop</td><td>rb-orchestrate</td>
        <td>The coverage matrix, and the bill. Every scenario past here is paid for twice — once to
        instantiate, once to challenge — so this is the cost gate.</td></tr>
<tr><td><span class="n">3</span> rejects and re-seeds</td><td>challenge</td><td>rb-orchestrate</td>
        <td>The verdict tally. A re-seed buys one more <code>instantiate</code> dispatch with the
        adversary's alternatives appended verbatim; a reject goes back to <code>score</code> to be
        marked and recounted.</td></tr>
    </tbody>
  </table>
  </div>
  <div class="rail">
    <span class="tag">--no-gate</span>
    <p>The only way to skip a human gate, and it substitutes an assumption — that the human would
    have approved — for the gate's entire content. Recording that it was passed is what keeps the
reproducibility claim honest; claiming to have gated while skipping is worse than not gating.</p>
  </div>
</section>

<section>
  <h2>What is on the plate but is not a stage</h2>
  <div class="cols two">
    <div>
      <h3>rb-orchestrate</h3>
      <p>A skill that declares no <code>stage</code> and no <code>schemas</code>. It dispatches
      <code>extract</code> through <code>emit</code>, holds gates 1–3, and writes
      <code>decisions.md</code>. It never runs <code>survey</code>, never dispatches
      <code>rb-triage</code>, and never holds gate 0 — all three are finished before it is
      dispatched at all.</p>
    </div>
    <div>
      <h3>The code stages</h3>
      <p><code>survey</code>, <code>intake</code> and <code>smoke</code> run as code, so they have
      no skill file and no <code>manifest.stages</code> entry. Their absence there is not a
      finding.</p>
    </div>
    <div>
      <h3>The measurement tools</h3>
      <p><code>compare-gold</code> and <code>sample-for-review</code> write under
      <code>measurement/</code>, deliberately outside the numbered prefixes: those are the stage
      contract, and no orchestrator dispatches a tool. <code>diff-runs</code> and
      <code>claim-utilisation</code> write nothing at all — they print.</p>
    </div>
    <div>
      <h3>The reports that are not gates</h3>
      <p><code>claim-utilisation</code> and <code>gate-brief</code> always exit clean on a readable
      run. <code>gate-brief</code> composes what already exists into the reading surface at each
      human gate — it does not decide anything.</p>
    </div>
  </div>
</section>

<footer>
  Drawn from the repository, not from memory: <code>src/rubrica/paths.py</code> (stage order and
  every artifact path) · <code>src/rubrica/validate.py</code> (what each stage must produce) ·
  <code>src/rubrica/skills/rb-*/SKILL.md</code> (each contract's reads, writes and invokes) ·
  <code>src/rubrica/cli.py</code> (the subcommand roster and the exit codes) ·
  <code>CLAUDE.md</code> and <code>docs/design/rationale.md</code> (the rulings).<br>
  Where this page and the repository disagree, the repository is right.
</footer>

</div>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed page against a fresh render instead of writing it",
    )
    parser.add_argument("--out", default=str(OUTPUT), metavar="PATH")
    args = parser.parse_args(argv)

    out = Path(args.out)
    rendered = page()
    if args.check:
        # One finding on stdout at exit 1, the same shape the rubrica
        # subcommands use, so a CI step can read it the same way.
        current = out.read_text(encoding="utf-8") if out.is_file() else None
        if current == rendered:
            return 0
        why = "does not exist" if current is None else "is stale"
        print(f"{out.relative_to(REPO_ROOT)} {why}: re-run scripts/{Path(__file__).name}")
        return 1

    out.write_text(rendered, encoding="utf-8")
    print(f"wrote {out.relative_to(REPO_ROOT)} ({len(rendered)} chars, spine {HEIGHT} units tall)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
