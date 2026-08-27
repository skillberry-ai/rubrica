#!/usr/bin/env python3
"""Render the README's drawing: one Rubrica run at the altitude a newcomer reads at.

docs/concepts/pipeline-diagram.html is the detailed counterpart, and it is the
wrong drawing for a README: it gives every stage its own row with the artifact it
writes and the gates that follow, which is exactly the detail someone deciding
whether to read further does not want yet. So this page collapses every stage of
paths.STAGES into five phases, keeps the human gates because they are what a
reader is signing up for, and drops everything else. A phase may fold a family of
stages that share a name prefix into one line as well (`folds`, drawn by
`fold_lines`) -- a second altitude control, and the one that keeps a box from
spilling past its own bottom edge when a family grows.

Two files, not one. GitHub's dark theme is chosen independently of the OS
`prefers-color-scheme` that an <img>-referenced SVG resolves against, so a single
theme-adaptive file shows a light plate on a dark page for anyone whose two
settings disagree. Rendering a pair and letting the README's <picture> element
pick is GitHub's own documented mechanism, and it costs one palette argument.

PHASES below is the whole content model. tests/unit/test_docs_accuracy.py holds
it to paths.STAGES in order, to brief.GATES, and -- since a fold that matched
nothing would drop a stage silently -- to a drawn line per stage in both
directions, and re-renders both files to compare against the committed bytes --
so a hand-edited SVG, or a stage added without a phase to hold it, fails the
suite rather than quietly describing an older pipeline. Re-render with `python
scripts/render-readme-diagram.py`, or verify with `--check`.

Type sizes are chosen against the width GitHub actually renders at: the canvas is
a little over 1000 units and README content is ~880px, so the drawing scales by
~0.86 and the smallest label lands near 10px. Widening the canvas to fit more
text makes every label smaller, not larger -- the five columns are the budget.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from string import Template

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "docs" / "assets"
OUTPUTS = {"light": ASSETS / "how-it-works.svg", "dark": ASSETS / "how-it-works-dark.svg"}

# ---------------------------------------------------------------- geometry ---
PAD = 16
LOOP = 36  # headroom above the boxes for the propose/score round arc and its label
PLATE_W = 104  # the input and output plates: what you bring, what you get
BOX_W, BOX_H = 120, 118
CONN = 16  # plate to first phase, last phase to plate
GCONN = 40  # between two phases: the gap a gate marker sits in
GATE_R = 10
CAP_GAP = 28
CAP_LINE = 20  # advance between legend rows; the legend wraps (see CAPTIONS)

MONO_W = 0.60  # advance width per em, monospace -- the only font we measure

# ------------------------------------------------------------------ phases ---
# stages: paths.STAGES, partitioned in order. The partition is the only claim
# this table makes that the code can check, and the test checks it.
PHASES: list[dict] = [
    dict(
        verb="select",
        note=["choose what is", "worth reading"],
        stages=[
            "survey",
            "triage-slices",
            "triage-objective",
            "triage-rule",
            "triage-audit",
            "triage-seal",
        ],
        # Folded, because this phase would otherwise draw six stage lines out of a
        # box sized for three and spill past its own bottom edge. The staged-triage
        # family is one idea at this altitude -- deciding what is worth reading --
        # and naming its passes here spends the reader's attention on the pipeline's
        # least newcomer-facing detail. `fold_lines` derives the drawn lines; the
        # unfolded list above stays complete so the partition test still sees every
        # stage.
        folds=["triage-"],
        gate=0,
    ),
    dict(
        verb="understand",
        note=["one world model", "of claims"],
        stages=[
            "intake",
            "extract",
            "reconcile-subjects",
            "reconcile-contradict",
            "reconcile-capabilities",
            "reconcile-outcomes",
            "reconcile-entities",
            "reconcile-goals",
            "reconcile-gaps",
            "reconcile-seal",
        ],
        # Folded for the same two reasons the triage family is. paths.STAGES holds
        # each reconcile pass separately -- it has to, because check-skills binds
        # one skill to one stage and manifest.stages records model, effort and
        # digest per stage -- but they are one logical step engineered as substeps,
        # and this drawing is the newcomer's altitude. Listing them all would also
        # not fit: phase() draws one line per entry from a fixed BOX_H, so ten
        # lines would overflow the box rather than crowd it.
        folds=["reconcile-"],
        gate=1,
    ),
    dict(
        verb="cover",
        note=["scenarios, round", "after round"],
        stages=[
            "propose-batches",
            "propose",
            "propose-seal",
            "score",
            "score-seal",
        ],
        # Folded for the reason the triage and reconcile families are, and the
        # unfolded list above stays complete so the partition test still sees
        # every stage. Two prefixes rather than five names because `phase()`
        # draws one line per entry from a fixed BOX_H -- three fit, five spill
        # past the bottom edge -- and because the batcher and the two seals are
        # not concepts a newcomer needs: at this altitude the phase is "propose,
        # then score, until coverage stops improving". Note the prefixes carry no
        # trailing dash: `propose` and `score` are themselves stages, so a
        # dashed prefix would leave each of them drawing its own line beside its
        # own family.
        folds=["propose", "score"],
        gate=2,
        loop="until coverage stops improving",
    ),
    dict(
        verb="build",
        note=["concrete tests,", "then attack each"],
        stages=["instantiate", "challenge"],
        gate=3,
    ),
    dict(
        verb="compile",
        note=["build the suite,", "then run it once"],
        stages=["emit", "smoke"],
        gate=None,
    ),
]

PLATE_IN = dict(label="you bring", items=["specs", "traces", "source"])
PLATE_OUT = dict(label="you get", items=["a runnable", "test suite"])

# Rows, not one row. Measured: the two entries below advance to x≈929 on a canvas
# of W=1032, leaving ~87 units before the right margin -- less than any useful
# third entry needs, and widening W is not available (see the module docstring:
# the five columns are the type-size budget, and a wider canvas downscales every
# label). So the legend wraps to a second row instead.
CAPTIONS: list[list[tuple[str, str]]] = [
    [
        ("gate", "a gate you hold — nothing moves past it until you say so"),
        ("arrow", "every arrow is a file on disk, never a message between stages"),
    ],
    [("fold", "one line standing for a family of stages")],
]

N = len(PHASES)
BOX_Y = PAD + LOOP
MID = BOX_Y + BOX_H / 2
CAP_Y = BOX_Y + BOX_H + CAP_GAP
H = CAP_Y + 16  # a one-row legend; plate_h() adds the rows it wraps to
W = 2 * PAD + 2 * PLATE_W + 2 * CONN + N * BOX_W + (N - 1) * GCONN


def mono_w(text: str, size: float) -> float:
    return len(text) * size * MONO_W


def box_x(i: int) -> float:
    return PAD + PLATE_W + CONN + i * (BOX_W + GCONN)


PLATE_OUT_X = box_x(N - 1) + BOX_W + CONN

# ---------------------------------------------------------------- palettes ---
# Lifted from render-pipeline-diagram.py's CSS custom properties, so the two
# drawings are visibly the same publication: sage ground, near-black ink, and the
# magenta stamp reserved here for the thing a human owns.
LIGHT = dict(
    ground="#E7EAE7",
    paper="#F8F9F7",
    sunk="#DEE2DE",
    ink="#141917",
    ink2="#4B5754",
    ink3="#77827E",
    rule="#C2CAC5",
    rule2="#D5DBD6",
    stamp="#A81E5B",
    stamp_ink="#8E1A4D",
)
DARK = dict(
    ground="#121514",
    paper="#1B1F1D",
    sunk="#0D100F",
    ink="#E7EAE6",
    ink2="#A2ACA7",
    ink3="#7B857F",
    rule="#333A36",
    rule2="#272D2A",
    stamp="#F1749F",
    stamp_ink="#F79CBC",
)
PALETTES = {"light": LIGHT, "dark": DARK}

# The dark palette's stamp is a light pink, so a number knocked out of it must be
# dark rather than paper-coloured. One value, keyed by theme, rather than a second
# palette entry that would be unused in both.
GATE_NUM_INK = {"light": "paper", "dark": "sunk"}

CSS = Template("""
  .bg{fill:$ground}
  .plate{fill:$sunk;stroke:$rule2;stroke-width:1}
  .box{fill:$paper;stroke:$rule;stroke-width:1}
  .hair{stroke:$rule2;stroke-width:1}
  .verb{font-family:$mono;font-weight:600;fill:$stamp_ink;letter-spacing:1.3px}
  .note{font-family:$serif;fill:$ink}
  .stage{font-family:$mono;fill:$ink3}
  .plabel{font-family:$mono;fill:$ink3;letter-spacing:1.1px}
  .pitem{font-family:$mono;fill:$ink}
  .edge{stroke:$ink3;stroke-width:1.25;fill:none}
  .ar{fill:$ink3}
  .gate{fill:$stamp}
  .gnum{font-family:$mono;font-weight:600;fill:$gate_num}
  .glab{font-family:$mono;fill:$stamp_ink;letter-spacing:.9px}
  .loop{stroke:$stamp;stroke-width:1.25;fill:none;opacity:.7}
  .arl{fill:$stamp;opacity:.7}
  .looplab{font-family:$serif;font-style:italic;fill:$ink2}
  .cap{font-family:$mono;fill:$ink3}
""")

MONO = 'ui-monospace,"SF Mono","JetBrains Mono","IBM Plex Mono",Menlo,Consolas,monospace'
SERIF = 'Charter,"Iowan Old Style","Source Serif 4",Georgia,"Times New Roman",serif'


# ------------------------------------------------------------------- parts ---
def txt(x: float, y: float, s: str, cls: str, size: float, anchor: str = "start") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" '
        f'text-anchor="{anchor}">{s}</text>'
    )


def plate(x: float, spec: dict) -> str:
    """An input or output plate: sunk rather than paper, so the phases read as the
    drawing's subject and these two as its edges."""
    out = [f'<rect x="{x}" y="{BOX_Y}" width="{PLATE_W}" height="{BOX_H}" rx="2" class="plate"/>']
    out.append(txt(x + 12, BOX_Y + 21, spec["label"].upper(), "plabel", 9))
    # The item block is centred on a fixed line rather than started at one, so a
    # two-item plate does not leave the bottom half of its box empty next to a
    # three-item one.
    first = BOX_Y + 66 - (len(spec["items"]) - 1) * 9
    for n, item in enumerate(spec["items"]):
        out.append(txt(x + 12, first + n * 18, item, "pitem", 11.5))
    return "".join(out)


def fold_lines(spec: dict) -> list[tuple[str, list[str]]]:
    """One phase's drawn stage lines, each paired with the stages it accounts for.

    `folds` is a list of stage-name prefixes. Every stage starting with one
    collapses into a single `<prefix>*` line, placed where the first such stage
    sat; every other stage draws its own line and accounts for itself alone.

    A declared prefix that matches no stage still draws its line, with an empty
    stage list, and that is deliberate rather than sloppy: the alternative --
    creating a line only once some stage matches -- makes a fold prefix that
    matches nothing indistinguishable from no fold at all, which is precisely the
    defect the test is supposed to catch and would leave it unable to reach it.
    Such a line has no stage position to sit at, so it sorts after the ones that
    do.

    The two properties the test holds, in both directions: every stage in `stages`
    is accounted for by exactly one drawn line, and every drawn line accounts for
    at least one stage.
    """
    lines: list[tuple[str, list[str]]] = []
    at: dict[str, int] = {}

    def label_of(prefix: str) -> str:
        return f"{prefix.rstrip('-')}*"

    for stage in spec["stages"]:
        prefix = next((p for p in spec.get("folds", ()) if stage.startswith(p)), None)
        if prefix is None:
            lines.append((stage, [stage]))
            continue
        label = label_of(prefix)
        if label not in at:
            at[label] = len(lines)
            lines.append((label, []))
        lines[at[label]][1].append(stage)

    for prefix in spec.get("folds", ()):
        if label_of(prefix) not in at:
            lines.append((label_of(prefix), []))
    return lines


def fold_marks() -> list[str]:
    """Every drawn line that stands for more than one stage, in drawing order --
    the legend's subject, taken from the drawing rather than typed beside it."""
    return [label for spec in PHASES for label, stages in fold_lines(spec) if len(stages) > 1]


def plate_h() -> float:
    """The canvas height. H sizes a one-row legend, so this adds a line for every
    row the legend wraps to -- a constant could not, since the rows are derived
    from what the drawing actually folds."""
    return H + (len(caption_rows()) - 1) * CAP_LINE


def caption_rows() -> list[list[tuple[str, str]]]:
    """CAPTIONS with any entry whose mark the drawing does not set dropped, and any
    row left empty dropped with it -- so unfolding every phase removes the fold
    legend and its row instead of leaving a legend for a convention no longer used.
    """
    rows = [[e for e in row if e[0] != "fold" or fold_marks()] for row in CAPTIONS]
    return [row for row in rows if row]


def phase(i: int, spec: dict) -> str:
    x = box_x(i)
    out = [f'<rect x="{x}" y="{BOX_Y}" width="{BOX_W}" height="{BOX_H}" rx="2" class="box"/>']
    out.append(txt(x + 11, BOX_Y + 21, spec["verb"].upper(), "verb", 11))
    for n, line in enumerate(spec["note"]):
        out.append(txt(x + 11, BOX_Y + 42 + n * 14, line, "note", 12))
    out.append(
        f'<line x1="{x + 11}" y1="{BOX_Y + 66}" x2="{x + BOX_W - 11}" y2="{BOX_Y + 66}" '
        'class="hair"/>'
    )
    for n, (label, _) in enumerate(fold_lines(spec)):
        out.append(txt(x + 11, BOX_Y + 82 + n * 14, label, "stage", 11.5))
    if spec.get("loop"):
        out.append(loop_arc(x, spec["loop"]))
    return "".join(out)


def loop_arc(x: float, label: str) -> str:
    """The 02/03 round loop, drawn right-to-left over the box: score sends the run
    back to propose, which is the one piece of control flow at this altitude."""
    left, right = x + 14, x + BOX_W - 14
    apex = BOX_Y - 26
    return (
        f'<path d="M{right} {BOX_Y} C {right} {apex}, {left} {apex}, {left} {BOX_Y}" '
        'class="loop" marker-end="url(#arl)"/>'
        + txt(x + BOX_W / 2, BOX_Y - 28, label, "looplab", 11, "middle")
    )


def connector(x1: float, x2: float) -> str:
    return f'<line x1="{x1}" y1="{MID}" x2="{x2}" y2="{MID}" class="edge" marker-end="url(#ar)"/>'


def gate(i: int, number: int) -> str:
    """Marker in the gap after phase i. The number lives in the disc and the word
    below it, so the pair reads as `gate 2` without setting six characters at a
    size that would not survive the downscale."""
    cx = box_x(i) + BOX_W + GCONN / 2
    return (
        connector(box_x(i) + BOX_W, cx - GATE_R - 3)
        + f'<circle cx="{cx}" cy="{MID}" r="{GATE_R}" class="gate"/>'
        + txt(cx, MID + 4.2, str(number), "gnum", 12, "middle")
        + txt(cx, MID + 24, "GATE", "glab", 8.5, "middle")
        + connector(cx + GATE_R + 3, box_x(i + 1))
    )


def captions() -> str:
    """Every mark here is the real one from the drawing rather than a text stand-in:
    a legend that redraws its subject can drift from it. The fold entry's mark is
    the folded label itself, read out of PHASES, for the same reason."""
    out = []
    for row, entries in enumerate(caption_rows()):
        y = CAP_Y + row * CAP_LINE
        x = float(PAD + 2)
        for kind, words in entries:
            if kind == "gate":
                out.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" class="gate"/>')
                gap = 18.0
            elif kind == "arrow":
                out.append(
                    f'<line x1="{x}" y1="{y - 4}" x2="{x + 11}" y2="{y - 4}" '
                    'class="edge" marker-end="url(#ar)"/>'
                )
                gap = 18.0
            else:
                mark = fold_marks()[0]
                out.append(txt(x, y, mark, "stage", 11.5))
                gap = mono_w(mark, 11.5) + 8
            out.append(txt(x + gap, y, words, "cap", 11.5))
            x += gap + mono_w(words, 11.5) + 34
    return "".join(out)


def svg(theme: str) -> str:
    pal = dict(PALETTES[theme], mono=MONO, serif=SERIF)
    pal["gate_num"] = PALETTES[theme][GATE_NUM_INK[theme]]
    body = [
        f'<rect width="{W}" height="{plate_h()}" class="bg"/>',
        plate(PAD, PLATE_IN),
        connector(PAD + PLATE_W, box_x(0)),
    ]
    for i, spec in enumerate(PHASES):
        body.append(phase(i, spec))
        if spec["gate"] is not None:
            body.append(gate(i, spec["gate"]))
    body.append(connector(box_x(N - 1) + BOX_W, PLATE_OUT_X))
    body.append(plate(PLATE_OUT_X, PLATE_OUT))
    body.append(captions())

    phases = ", then ".join(p["verb"] for p in PHASES)
    # The folded clause is conditional because desc is the whole drawing for a
    # screen-reader user: describing a convention the render does not use would be
    # as wrong as omitting one it does.
    folded = (
        " A stage name ending in an asterisk stands for a family of stages drawn as one line."
        if fold_marks()
        else ""
    )
    desc = (
        f"Left to right: the artifacts you bring, five phases -- {phases} -- and the "
        "runnable test suite that comes out. A numbered marker between phases is a gate "
        "a human holds; the phase that proposes and scores scenarios loops until "
        f"coverage stops improving. Each phase lists the stages it covers.{folded}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {plate_h()}" '
        f'width="{W}" height="{plate_h()}" role="img" aria-labelledby="t d">'
        '<title id="t">How a Rubrica run gets from your artifacts to a test suite</title>'
        f'<desc id="d">{desc}</desc>'
        f"<style>{CSS.substitute(pal)}</style>"
        '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" '
        'class="ar"/></marker>'
        '<marker id="arl" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" '
        'class="arl"/></marker></defs>' + "".join(body) + "</svg>\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a committed file is stale")
    args = ap.parse_args()

    stale = []
    for theme, path in OUTPUTS.items():
        fresh = svg(theme)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != fresh:
                stale.append(path.relative_to(REPO_ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fresh, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}  {W}x{plate_h()}")
    if stale:
        print("stale or hand-edited: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
