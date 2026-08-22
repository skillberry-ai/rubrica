#!/usr/bin/env python3
"""Render the README's drawing: one Rubrica run at the altitude a newcomer reads at.

docs/concepts/pipeline-diagram.html is the detailed counterpart, and it is the
wrong drawing for a README: it gives every stage its own row with the artifact it
writes and the gates that follow, which is exactly the detail someone deciding
whether to read further does not want yet. So this page collapses the eleven
stages of paths.STAGES into five phases, keeps the human gates because they are
what a reader is signing up for, and drops everything else.

Two files, not one. GitHub's dark theme is chosen independently of the OS
`prefers-color-scheme` that an <img>-referenced SVG resolves against, so a single
theme-adaptive file shows a light plate on a dark page for anyone whose two
settings disagree. Rendering a pair and letting the README's <picture> element
pick is GitHub's own documented mechanism, and it costs one palette argument.

PHASES below is the whole content model. tests/unit/test_docs_accuracy.py holds
it to paths.STAGES in order and to brief.GATES, and re-renders both files to
compare against the committed bytes -- so a hand-edited SVG, or a stage added
without a phase to hold it, fails the suite rather than quietly describing an
older pipeline. Re-render with `python scripts/render-readme-diagram.py`, or
verify with `--check`.

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

MONO_W = 0.60  # advance width per em, monospace -- the only font we measure

# ------------------------------------------------------------------ phases ---
# stages: paths.STAGES, partitioned in order. The partition is the only claim
# this table makes that the code can check, and the test checks it.
PHASES: list[dict] = [
    dict(
        verb="select",
        note=["choose what is", "worth reading"],
        stages=["survey", "triage", "triage-slices"],
        gate=0,
    ),
    dict(
        verb="understand",
        note=["one world model", "of claims"],
        stages=["intake", "extract", "reconcile"],
        gate=1,
    ),
    dict(
        verb="cover",
        note=["scenarios, round", "after round"],
        stages=["propose", "score"],
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

CAPTIONS = [
    ("gate", "a gate you hold — nothing moves past it until you say so"),
    ("arrow", "every arrow is a file on disk, never a message between stages"),
]

N = len(PHASES)
BOX_Y = PAD + LOOP
MID = BOX_Y + BOX_H / 2
CAP_Y = BOX_Y + BOX_H + CAP_GAP
H = CAP_Y + 16
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
    for n, stage in enumerate(spec["stages"]):
        out.append(txt(x + 11, BOX_Y + 82 + n * 14, stage, "stage", 11.5))
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
    """Both glyphs are the real mark from the drawing rather than a text stand-in:
    a legend that redraws its subject can drift from it."""
    out, x = [], float(PAD + 2)
    for kind, words in CAPTIONS:
        if kind == "gate":
            out.append(f'<circle cx="{x + 5}" cy="{CAP_Y - 4}" r="5" class="gate"/>')
        else:
            out.append(
                f'<line x1="{x}" y1="{CAP_Y - 4}" x2="{x + 11}" y2="{CAP_Y - 4}" '
                'class="edge" marker-end="url(#ar)"/>'
            )
        out.append(txt(x + 18, CAP_Y, words, "cap", 11.5))
        x += 18 + mono_w(words, 11.5) + 34
    return "".join(out)


def svg(theme: str) -> str:
    pal = dict(PALETTES[theme], mono=MONO, serif=SERIF)
    pal["gate_num"] = PALETTES[theme][GATE_NUM_INK[theme]]
    body = [
        f'<rect width="{W}" height="{H}" class="bg"/>',
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
    desc = (
        f"Left to right: the artifacts you bring, five phases -- {phases} -- and the "
        "runnable test suite that comes out. A numbered marker between phases is a gate "
        "a human holds; the phase that proposes and scores scenarios loops until "
        "coverage stops improving. Each phase lists the stages it covers."
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" role="img" aria-labelledby="t d">'
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
            print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}  {W}x{H}")
    if stale:
        print("stale or hand-edited: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
