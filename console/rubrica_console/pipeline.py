"""The run, as an ordered list of steps a human can see and the console can run.

A pure function of what is on disk, plus the console's own ledger of what it has
already done (which scenarios it re-seeded, which steps a human accepted with
findings). It reads; it never writes, and it never raises on a run's *content*:
an artifact that cannot be read is treated as absent, because a report that
crashes on a broken run is the least useful reading of it, and the stage whose
output is broken is the one this view has to show as not done.

**This is a second copy of `rb-orchestrate`'s walk (B0-B11), in code, and that
is a cost, not a convenience.** The skill is the thing this project tests; a run
driven from here does not exercise it, and nothing mechanical keeps this order
in step with the skill's prose. `docs/design/limitations.md` records both.
Each step below names the section of the walk it follows, so a reader who changes
the skill can find the line here that has to change with it.

A step's *recipe* is data, not code: a list of operations (`dispatch`, `fanout`,
`cli`, `validate`, `check-refs`, `record`, and a few named special cases) that
`jobs.py` interprets. Keeping it data is what lets the UI show, before anything
runs, exactly which commands a click will execute.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rubrica import summary
from rubrica.artifacts import read_json
from rubrica.paths import RunPaths, is_safe_segment

# The five step kinds. `prompt` and `fanout` call a model; `code` runs a rubrica
# subcommand; `gate` waits for a human; `followup` is gate 3's verdict handling,
# which mixes dispatches and seals.
CODE, PROMPT, FANOUT, GATE, FOLLOWUP = "code", "prompt", "fanout", "gate", "followup"
MODEL_KINDS = frozenset({PROMPT, FANOUT, FOLLOWUP})

DONE, READY, WAITING, FAILED = "done", "ready", "waiting", "failed"

# The reconcile band's single-dispatch passes after the contradiction sweep, in
# the order B3 dispatches them.
_RECONCILE_PASSES = (
    "reconcile-capabilities",
    "reconcile-outcomes",
    "reconcile-entities",
    "reconcile-goals",
    "reconcile-gaps",
    "reconcile-services",
)

# decisions.md lines. The first form is what this console writes; the second is
# what a human or `rb-orchestrate` has written by hand in real runs ("Gate 1: user
# approved ..."). Anchored after the timestamp so a gate mentioned mid-sentence
# ("... Gate 2 passed without review ...") is not read as that gate's approval --
# a later stage having run is what proves that one, and `inferred` says so.
_GATE_LINE = re.compile(r"^- \S+ (?:human )?gate ([0-3])\b", re.IGNORECASE)
_NO_HOLES_LINE = re.compile(r"^- \S+ round (\d+): no closable holes", re.IGNORECASE)
_STOP_LINE = re.compile(r"^- \S+ round loop stopped after round (\d+)", re.IGNORECASE)


# One plain-English line per step, shown under its title in the UI. Keyed by the
# step id with any `round-N/` prefix removed, so every round shares one line.
SUMMARIES = {
    "triage-slices": (
        "Splits the list of candidate files into small groups so each can be judged on its own."
    ),
    "triage-objective": (
        "Checks whether the files on offer can actually support what this run is trying to test."
    ),
    "triage-rule": (
        "Decides, group by group, which candidate files the run should read and which to leave out."
    ),
    "triage-audit": "Looks at the files that were let in and lists what they still cannot tell us.",
    "triage-seal": "Combines the triage decisions into one record for you to review.",
    "gate-0": "You decide which files the run may read; nothing left out here can be read later.",
    "extract": (
        "Reads each input file and writes down the facts (claims) it states about the system."
    ),
    "reconcile-subjects": "Groups the claims from all inputs by what they talk about.",
    "reconcile-contradict": "Checks each group of claims for places where the inputs disagree.",
    "reconcile-capabilities": "Works out what the system can do, from the claims.",
    "reconcile-outcomes": (
        "Works out what each capability should produce when it succeeds or fails."
    ),
    "reconcile-entities": "Works out what kinds of data the system holds and how they relate.",
    "reconcile-goals": "Works out what the system's users are trying to get done.",
    "reconcile-gaps": "Lists what the inputs leave unclear or never say.",
    "reconcile-services": "Groups the system's tools into the services they belong to.",
    "synthesise-interfaces": (
        "Writes one API description (OpenAPI) for each service, from the grouping."
    ),
    "reconcile-seal": (
        "Puts all the pieces together into one description of the system (the world model)."
    ),
    "gate-1": "You check the description of the system before any tests are planned from it.",
    "propose-batches": (
        "Picks the untested areas this round should cover and splits them into batches."
    ),
    "propose": "Writes test scenarios for each batch of untested areas.",
    "propose-seal": "Collects every batch's scenarios into one list.",
    "score": "Rates the scenarios, marks duplicates and weak ones, and judges what they cover.",
    "propose-seal-2": "Updates the scenario list with the scoring decisions.",
    "score-seal": "Works out how much is covered now and whether another round is needed.",
    "gate-2": "You approve the scenarios before paying for each one to be turned into a test.",
    "instantiate": "Turns each approved scenario into a concrete, runnable test.",
    "challenge": "Has a second model look for problems in each test and say keep, redo or reject.",
    "followup": "Redoes the tests marked for another try and drops the rejected ones.",
    "gate-3": "You review which tests were redone or rejected before the suite is built.",
    "emit": "Builds the final test suite from the approved tests.",
    "smoke": "Runs the suite against a few agents to make sure it works end to end.",
}


@dataclass
class Step:
    id: str
    title: str
    kind: str
    stage: str | None = None
    status: str = WAITING
    # Why the step is in its status, in plain English. Empty when obvious.
    reason: str = ""
    phase: str = ""
    round: int | None = None
    gate: int | None = None
    members_done: list[str] = field(default_factory=list)
    members_todo: list[str] = field(default_factory=list)
    recipe: list[dict] = field(default_factory=list)
    # Facts the UI shows beside a step: a gate's blocking gaps, a round's verdict.
    notes: list[str] = field(default_factory=list)
    done_on_disk: bool = False
    # Dispatches of this step that did not finish last time (see Ledger.incomplete):
    # what "Resume" runs.
    unfinished: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return SUMMARIES.get(self.id.rsplit("/", 1)[-1], "")

    @property
    def calls_model(self) -> bool:
        return self.kind in MODEL_KINDS

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "kind": self.kind,
            "stage": self.stage,
            "status": self.status,
            "reason": self.reason,
            "phase": self.phase,
            "round": self.round,
            "gate": self.gate,
            "members_done": self.members_done,
            "members_todo": self.members_todo,
            "members_total": len(self.members_done) + len(self.members_todo),
            "recipe": self.recipe,
            "notes": self.notes,
            "calls_model": self.calls_model,
            "unfinished": self.unfinished,
        }


@dataclass
class Ledger:
    """What the console itself remembers about a run, beyond what is on disk.

    `reseeded`: scenario ids whose `re-seed` verdict was already acted on once
    (B9's once-only budget; nothing in the verdict file says which pass it is).
    `failed`: step ids whose latest job ended with findings a human has not yet
    accepted -- shown as failed and not counted as done, even though the stage's
    artifact is on disk, because a stage whose gate is red is not finished.
    `accepted`: step ids a human ruled finished as they stand -- a fan-out whose
    remaining members refused, say. Recorded in decisions.md when it is set.
    `incomplete`: step id -> the members whose dispatch did not finish (`""` for a
    single-dispatch step) -- a lost connection, a killed process. Such a member is
    still to do even when its output file exists, because a dispatch that died may
    have written half of it; a later dispatch that finishes takes it off the list.
    """

    reseeded: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    accepted: set[str] = field(default_factory=set)
    incomplete: dict[str, set[str]] = field(default_factory=dict)


def _quietly(path: Path):
    try:
        return read_json(path)
    except Exception:  # deliberate: an unreadable artifact reads as absent here
        return None


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return -1


def _ids(document, key: str, field_name: str = "id") -> list[str]:
    """`document[key][*][field_name]`, keeping only safe, string ids."""
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        return []
    out = []
    for row in document[key]:
        if isinstance(row, dict):
            value = row.get(field_name)
            if isinstance(value, str) and is_safe_segment(value):
                out.append(value)
    return out


def _decision_lines(run: RunPaths) -> list[str]:
    try:
        return run.decisions.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def approved_gates(run: RunPaths) -> set[int]:
    gates = set()
    for line in _decision_lines(run):
        match = _GATE_LINE.match(line)
        if match:
            gates.add(int(match.group(1)))
    return gates


def _rounds_marked(run: RunPaths, pattern: re.Pattern) -> set[int]:
    return {int(m.group(1)) for line in _decision_lines(run) if (m := pattern.match(line))}


def _non_empty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def _instance_ids(run: RunPaths) -> list[str]:
    try:
        return [s for s in run.scenario_ids_with_instances() if _non_empty_dir(run.instance_dir(s))]
    except Exception:
        return []


def _suite_built(run: RunPaths) -> bool:
    try:
        return bool(run.scenario_ids_with_tasks())
    except Exception:
        return False


def _scenarios_by_status(run: RunPaths) -> dict[str, str]:
    doc = _quietly(run.scenarios)
    out = {}
    if isinstance(doc, dict) and isinstance(doc.get("scenarios"), list):
        for row in doc["scenarios"]:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                out[row["id"]] = row.get("status")
    return out


def _verdicts(run: RunPaths, ids: list[str]) -> dict[str, str]:
    out = {}
    for sid in ids:
        doc = _quietly(run.verdict(sid))
        if isinstance(doc, dict) and isinstance(doc.get("verdict"), str):
            out[sid] = doc["verdict"]
    return out


def blocking_gaps(run: RunPaths) -> list[dict]:
    """Gaps whose `blocks` names a stage still to come (B4). Read, never ruled on."""
    world = _quietly(run.world_model)
    if not isinstance(world, dict) or not isinstance(world.get("gaps"), list):
        return []
    return [
        gap
        for gap in world["gaps"]
        if isinstance(gap, dict) and isinstance(gap.get("blocks"), list) and gap["blocks"]
    ]


# -- recipes -----------------------------------------------------------------


def _single(stage: str, *, refs: bool = True) -> list[dict]:
    recipe: list[dict] = [{"op": "dispatch", "stage": stage}, {"op": "validate", "stage": stage}]
    if refs:
        recipe.append({"op": "check-refs"})
    recipe.append({"op": "record", "stage": stage})
    return recipe


def _fanout(stage: str, todo: list[str], *, record: bool = True) -> list[dict]:
    recipe: list[dict] = [
        {"op": "fanout", "stage": stage, "ids": list(todo)},
        {"op": "validate", "stage": stage},
        # Once, after every member: every fan-out checker reports each missing
        # slice from the moment its directory exists (CLAUDE.md, B2/B3/B8/B9).
        {"op": "check-refs"},
    ]
    if record:
        recipe.append({"op": "record", "stage": stage})
    return recipe


def _code(args: list[str], stage: str | None, *, refs: bool = False) -> list[dict]:
    recipe: list[dict] = [{"op": "cli", "args": args}]
    if stage:
        recipe.append({"op": "validate", "stage": stage})
    if refs:
        recipe.append({"op": "check-refs"})
    return recipe


# -- the walk ----------------------------------------------------------------


def _triage_steps(run: RunPaths) -> list[Step]:
    """The survey path, before intake. `rb-orchestrate` never runs these."""
    phase = "Triage"
    slice_plan = _quietly(run.slices)
    slice_ids = _ids(slice_plan, "slices")
    rule_done = [s for s in slice_ids if _exists(run.disposition_part(s))]
    rule_todo = [s for s in slice_ids if s not in rule_done]
    # The triage passes are not recorded here: record-stage writes manifest.json,
    # which does not exist until gate 0 is held and intake mints it. Gate 0's
    # approval records them, with the model and effort the console used.
    steps = [
        Step(
            "triage-slices",
            "Partition the catalogue into slices",
            CODE,
            "triage-slices",
            phase=phase,
            done_on_disk=_exists(run.slices),
            recipe=_code(["triage-slices"], "triage-slices"),
        ),
        Step(
            "triage-objective",
            "Judge the objective against the corpus",
            PROMPT,
            "triage-objective",
            phase=phase,
            done_on_disk=_exists(run.objective),
            recipe=[
                {"op": "dispatch", "stage": "triage-objective"},
                {"op": "validate", "stage": "triage-objective"},
            ],
        ),
        Step(
            "triage-rule",
            "Rule on each slice's candidates",
            FANOUT,
            "triage-rule",
            phase=phase,
            members_done=rule_done,
            members_todo=rule_todo,
            done_on_disk=bool(slice_ids) and not rule_todo,
            recipe=_fanout("triage-rule", rule_todo, record=False),
        ),
        Step(
            "triage-audit",
            "Audit what the admitted set cannot cover",
            PROMPT,
            "triage-audit",
            phase=phase,
            done_on_disk=_exists(run.audit),
            recipe=[
                {"op": "dispatch", "stage": "triage-audit"},
                {"op": "validate", "stage": "triage-audit"},
                {"op": "check-refs"},
            ],
        ),
        Step(
            "triage-seal",
            "Seal the triage record",
            CODE,
            "triage-seal",
            phase=phase,
            done_on_disk=_exists(run.triage),
            recipe=_code(["triage-seal"], "triage-seal", refs=True),
        ),
        Step(
            "gate-0",
            "Gate 0: approve what the run may read",
            GATE,
            phase=phase,
            gate=0,
            # Gate 0 is held exactly when intake has minted the manifest: nothing
            # but this gate's approval runs intake on a survey run.
            done_on_disk=_exists(run.manifest),
            recipe=[{"op": "approve-gate-0"}],
        ),
    ]
    return steps


def _reconcile_steps(run: RunPaths, manifest) -> list[Step]:
    phase = "World model"
    inputs = _ids(manifest, "inputs", "artifact_id")
    extract_done = [a for a in inputs if _exists(run.claims(a))]
    extract_todo = [a for a in inputs if a not in extract_done]
    subjects = _ids(_quietly(run.subjects), "subjects")
    contradict_done = [s for s in subjects if _exists(run.contradiction_part(s))]
    contradict_todo = [s for s in subjects if s not in contradict_done]
    steps = [
        Step(
            "extract",
            "Extract claims from each input",
            FANOUT,
            "extract",
            phase=phase,
            members_done=extract_done,
            members_todo=extract_todo,
            done_on_disk=bool(inputs) and not extract_todo,
            recipe=_fanout("extract", extract_todo),
        ),
        Step(
            "reconcile-subjects",
            "Group claims into subjects",
            PROMPT,
            "reconcile-subjects",
            phase=phase,
            done_on_disk=_exists(run.subjects),
            recipe=_single("reconcile-subjects"),
        ),
        Step(
            "reconcile-contradict",
            "Look for contradictions in each subject",
            FANOUT,
            "reconcile-contradict",
            phase=phase,
            members_done=contradict_done,
            members_todo=contradict_todo,
            done_on_disk=bool(subjects) and not contradict_todo,
            recipe=_fanout("reconcile-contradict", contradict_todo),
        ),
    ]
    part_paths = {
        "reconcile-capabilities": run.capabilities_part,
        "reconcile-outcomes": run.outcomes_part,
        "reconcile-entities": run.entities_part,
        "reconcile-goals": run.goals_part,
        "reconcile-gaps": run.gaps_part,
        "reconcile-services": run.services_part,
    }
    titles = {
        "reconcile-capabilities": "Reconcile capabilities",
        "reconcile-outcomes": "Reconcile outcomes",
        "reconcile-entities": "Reconcile entities",
        "reconcile-goals": "Reconcile goals",
        "reconcile-gaps": "Record gaps",
        "reconcile-services": "Group tools into services",
    }
    for stage in _RECONCILE_PASSES:
        steps.append(
            Step(
                stage,
                titles[stage],
                PROMPT,
                stage,
                phase=phase,
                done_on_disk=_exists(part_paths[stage]),
                recipe=_single(stage),
            )
        )
    steps.append(
        Step(
            "synthesise-interfaces",
            "Derive one interface document per service",
            CODE,
            "synthesise-interfaces",
            phase=phase,
            # Up to date when the directory exists and is no older than the
            # grouping it derives from: re-running reconcile-services makes it stale.
            done_on_disk=_exists(run.interfaces_dir)
            and _mtime(run.interfaces_dir) >= _mtime(run.services_part),
            # A special op, because B3 forbids `validate` when nothing was printed.
            recipe=[{"op": "synthesise-interfaces"}],
        )
    )
    steps.append(
        Step(
            "reconcile-seal",
            "Seal the world model",
            CODE,
            "reconcile-seal",
            phase=phase,
            done_on_disk=_exists(run.world_model),
            recipe=_code(["reconcile-seal"], "reconcile-seal", refs=True),
        )
    )
    gaps = blocking_gaps(run)
    gate = Step(
        "gate-1",
        "Gate 1: approve the world model",
        GATE,
        phase=phase,
        gate=1,
        recipe=[{"op": "approve-gate"}],
    )
    if gaps:
        # B4: a blocking gap is gate 1 arriving early with a question attached.
        # Approving the gate is the human's ruling on it, so the note says which.
        gate.notes.append(
            f"{len(gaps)} gap(s) say they block a later stage; approving this gate is "
            "your ruling that the run may go on regardless:"
        )
        gate.notes += [
            f"{g.get('id', '?')}: blocks {', '.join(map(str, g['blocks']))}" for g in gaps
        ]
    steps.append(gate)
    return steps


def _round_steps(run: RunPaths, r: int) -> list[Step]:
    phase = f"Round {r}"
    batches_path = run.batches(r)
    plan = _quietly(batches_path)
    batch_ids = _ids(plan, "batches")
    parts = [run.scenario_part(r, b) for b in batch_ids]
    done = [b for b, p in zip(batch_ids, parts, strict=True) if _exists(p)]
    todo = [b for b in batch_ids if b not in done]
    newest_part = max((_mtime(p) for p in parts), default=-1)
    score_part = run.score_part(r)
    coverage = run.coverage_round(r)
    no_holes = r in _rounds_marked(run, _NO_HOLES_LINE)
    steps = [
        Step(
            f"round-{r}/propose-batches",
            "Plan this round's batches",
            CODE,
            "propose-batches",
            phase=phase,
            round=r,
            done_on_disk=_exists(batches_path) or no_holes,
            recipe=[{"op": "propose-batches", "round": r}],
        )
    ]
    if no_holes:
        steps[0].notes.append("No closable holes: there was no round to run.")
        return steps
    seal_1_done = _exists(run.scenarios) and _mtime(run.scenarios) >= newest_part
    score_done = _exists(score_part)
    steps += [
        Step(
            f"round-{r}/propose",
            "Propose scenarios for each batch",
            FANOUT,
            "propose",
            phase=phase,
            round=r,
            members_done=done,
            members_todo=todo,
            done_on_disk=bool(batch_ids) and not todo,
            recipe=_fanout("propose", todo),
        ),
        Step(
            f"round-{r}/propose-seal",
            "Assemble the scenario list",
            CODE,
            "propose-seal",
            phase=phase,
            round=r,
            done_on_disk=seal_1_done,
            recipe=_code(["propose-seal"], "propose-seal"),
        ),
        Step(
            f"round-{r}/score",
            "Score the scenarios",
            PROMPT,
            "score",
            phase=phase,
            round=r,
            done_on_disk=score_done,
            recipe=[
                {"op": "dispatch", "stage": "score"},
                {"op": "validate", "stage": "score"},
                {"op": "record", "stage": "score"},
            ],
        ),
        Step(
            f"round-{r}/propose-seal-2",
            "Fold the score's rulings into the scenario list",
            CODE,
            "propose-seal",
            phase=phase,
            round=r,
            # B6.5: the second seal is what folds this round's rulings in, so it is
            # done only once the scenario list is no older than the score part.
            done_on_disk=score_done and _mtime(run.scenarios) >= _mtime(score_part),
            recipe=_code(["propose-seal"], "propose-seal"),
        ),
        Step(
            f"round-{r}/score-seal",
            "Compute coverage for the round",
            CODE,
            "score-seal",
            phase=phase,
            round=r,
            done_on_disk=_exists(coverage) and _mtime(coverage) >= _mtime(score_part),
            recipe=[{"op": "score-seal", "round": r}],
        ),
    ]
    verdict = _verdict_of(run, r)
    if verdict:
        steps[-1].notes.append(f"Coverage verdict: {verdict}")
    return steps


def _verdict_of(run: RunPaths, r: int) -> str | None:
    doc = _quietly(run.coverage_round(r))
    if isinstance(doc, dict) and isinstance(doc.get("verdict"), str):
        return doc["verdict"]
    return None


def _max_rounds(manifest) -> int:
    limits = manifest.get("limits") if isinstance(manifest, dict) else None
    value = limits.get("max_rounds") if isinstance(limits, dict) else None
    return value if isinstance(value, int) and value >= 1 else 1


def _loop_steps(run: RunPaths, manifest) -> tuple[list[Step], bool]:
    """Every round on disk, plus the next one while the loop is open (B6.8).

    Returns the steps and whether the loop has ended. The loop ends on a verdict
    other than `continue`, on the round cap, on a round with no closable holes, on
    a human's "stop rounds" ruling, or -- inferred -- once instantiate has run.
    """
    k = _max_rounds(manifest)
    try:
        on_disk = set(run.batches_rounds()) | set(run.score_part_rounds())
    except Exception:
        on_disk = set()
    stopped = _rounds_marked(run, _STOP_LINE)
    no_holes = _rounds_marked(run, _NO_HOLES_LINE)
    steps: list[Step] = []
    r = 1
    ended = False
    while True:
        steps += _round_steps(run, r)
        if r in no_holes or r in stopped:
            ended = True
            break
        verdict = _verdict_of(run, r)
        if verdict is None:
            # This round is still in progress.
            break
        if verdict != "continue" or r >= k:
            ended = True
            break
        if r + 1 not in on_disk and (_instance_ids(run) or _suite_built(run)):
            ended = True
            break
        r += 1
    if not ended and (_instance_ids(run) or _suite_built(run)):
        ended = True
    return steps, ended


def _late_steps(run: RunPaths, ledger: Ledger, latest_round: int) -> list[Step]:
    phase = "Suite"
    status = _scenarios_by_status(run)
    active = sorted(s for s, st in status.items() if st == "active" and is_safe_segment(s))
    instances = _instance_ids(run)
    inst_todo = [s for s in active if s not in instances]
    verdicts = _verdicts(run, instances)
    chal_todo = [s for s in instances if s not in verdicts]
    reseed_todo = sorted(
        s
        for s, v in verdicts.items()
        if v == "re-seed" and status.get(s) == "active" and s not in ledger.reseeded
    )
    # B9: a reject, and a re-seed already spent once, both end as `rejected` in the
    # scenario list -- through one score re-dispatch and both seals, never an edit.
    reject_todo = sorted(
        s
        for s, v in verdicts.items()
        if status.get(s) == "active"
        and (v == "reject" or (v == "re-seed" and s in ledger.reseeded))
    )
    steps = [
        Step(
            "gate-2",
            "Gate 2: approve the scenarios before paying for them",
            GATE,
            phase=phase,
            gate=2,
            recipe=[{"op": "approve-gate"}],
        ),
        Step(
            "instantiate",
            "Build a test instance for each active scenario",
            FANOUT,
            "instantiate",
            phase=phase,
            members_done=[s for s in active if s in instances],
            members_todo=inst_todo,
            done_on_disk=bool(instances) and not inst_todo,
            recipe=_fanout("instantiate", inst_todo),
        ),
        Step(
            "challenge",
            "Challenge each instance",
            FANOUT,
            "challenge",
            phase=phase,
            members_done=[s for s in instances if s in verdicts],
            members_todo=chal_todo,
            done_on_disk=bool(instances) and not chal_todo,
            recipe=_fanout("challenge", chal_todo),
        ),
        Step(
            "followup",
            "Act on re-seed and reject verdicts",
            FOLLOWUP,
            phase=phase,
            members_done=[],
            members_todo=reseed_todo + reject_todo,
            done_on_disk=bool(verdicts) and not chal_todo and not reseed_todo and not reject_todo,
            recipe=[
                {
                    "op": "followup",
                    "reseed": reseed_todo,
                    "reject": reject_todo,
                    "round": latest_round,
                },
            ],
        ),
        Step(
            "gate-3",
            "Gate 3: review rejects and re-seeds",
            GATE,
            phase=phase,
            gate=3,
            recipe=[{"op": "approve-gate"}],
        ),
        Step(
            "emit",
            "Compile the suite",
            PROMPT,
            "emit",
            phase=phase,
            done_on_disk=_suite_built(run),
            recipe=_single("emit"),
        ),
        Step(
            "smoke",
            "Smoke-test the suite against agents",
            CODE,
            "smoke",
            phase=phase,
            done_on_disk=_exists(run.report),
            reason="needs an agents roster file",
            recipe=[{"op": "smoke"}],
        ),
    ]
    if reseed_todo:
        steps[3].notes.append(f"{len(reseed_todo)} re-seed(s) to re-instantiate once")
    if reject_todo:
        steps[3].notes.append(f"{len(reject_todo)} scenario(s) to rule rejected via score")
    return steps


def steps(run: RunPaths, ledger: Ledger | None = None) -> list[Step]:
    """Every step of the run, in order, with its status.

    Statuses: a step is `done` when its output is on disk (and, for a step a gate
    found fault with, a human accepted the findings); the first step that is not
    done is `ready` -- or, for a gate, `ready` meaning "waiting for you"; every
    step after it that is not done is `waiting`. A step after the first not-done
    one can still be `done` -- a seal made stale by a later re-score is exactly
    that shape, and showing it is the point.
    """
    ledger = ledger or Ledger()
    out: list[Step] = []
    survey = _exists(run.catalogue)
    if survey:
        out += _triage_steps(run)
    manifest = _quietly(run.manifest)
    if manifest is not None or not survey:
        out += _reconcile_steps(run, manifest)
        loop, ended = _loop_steps(run, manifest)
        out += loop
        latest = max((s.round for s in loop if s.round), default=1)
        if ended:
            out += _late_steps(run, ledger, latest)

    # Gates 1-3: approved by a decisions.md line, or inferred from a later stage
    # having run. Gate 0's state is the manifest's existence, set above.
    approved = approved_gates(run)
    spine = {row.name: row.produced for row in summary.stage_spine(run)}
    inferred = {
        1: any(spine.get(s) for s in ("propose-batches", "propose", "propose-seal")),
        2: bool(_instance_ids(run)) or _suite_built(run),
        3: _suite_built(run),
    }
    for step in out:
        if step.kind == GATE and step.gate in (1, 2, 3):
            step.done_on_disk = step.gate in approved or inferred[step.gate]
            if step.gate not in approved and inferred[step.gate]:
                step.reason = "passed: a later stage already ran (no approval line recorded)"
        if step.kind == GATE and step.gate == 0 and step.done_on_disk and 0 not in approved:
            step.reason = "passed: intake has admitted the inputs"

    for step in out:
        _apply_unfinished(step, ledger.incomplete.get(step.id))

    first_open = True
    for step in out:
        effective_done = (step.done_on_disk or step.id in ledger.accepted) and (
            step.id not in ledger.failed
        )
        if step.id in ledger.accepted and not step.done_on_disk:
            step.reason = "accepted as it stands by a human ruling"
        if step.id in ledger.failed:
            step.status = FAILED
            first_open = False
        elif effective_done:
            step.status = DONE
        elif first_open:
            step.status = READY
            first_open = False
        else:
            step.status = WAITING
    return out


def _apply_unfinished(step: Step, unfinished: set[str] | None) -> None:
    """Put back on the to-do list every dispatch of `step` that did not finish.

    The step is then not done, whatever is on disk, and its recipe re-dispatches
    exactly those members -- plus any whose output is simply missing -- and no
    member that finished. That is what makes a lost connection resumable rather
    than a failure: nothing that completed is paid for twice.
    """
    if not unfinished or step.kind not in MODEL_KINDS:
        return
    members = sorted(m for m in unfinished if m)
    step.unfinished = members or [""]
    step.done_on_disk = False
    if members:
        step.members_done = [m for m in step.members_done if m not in unfinished]
        step.members_todo = sorted(set(step.members_todo) | set(members))
        for op in step.recipe:
            if op.get("op") == "fanout":
                op["ids"] = sorted(set(op.get("ids") or []) | set(members))
    count = len(step.unfinished)
    step.reason = (
        f"interrupted: {count} dispatch{'es' if count != 1 else ''} did not finish "
        "(a lost connection, or the process was stopped); Resume runs only "
        f"{'those' if count != 1 else 'that one'}, and nothing that finished"
    )


def find(all_steps: list[Step], step_id: str) -> Step | None:
    return next((s for s in all_steps if s.id == step_id), None)


def next_step(all_steps: list[Step]) -> Step | None:
    return next((s for s in all_steps if s.status in (READY, FAILED)), None)
