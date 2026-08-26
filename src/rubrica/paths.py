"""Run-directory layout: the single source of truth for artifact paths.

Every module reads and writes artifacts through this module, so the on-disk
contract is expressed in exactly one place.
"""

from __future__ import annotations

import re
from pathlib import Path

from rubrica.errors import UsageError

# Stage names in pipeline order. The validate and check-refs CLIs accept
# these, and the orchestrator names the stage it is dispatching with them.
STAGES = (
    "survey",
    "triage-slices",
    "triage-objective",
    "triage-rule",
    # The last of the staged-triage family's prompt passes: the self-audit,
    # reading every triage-rule part plus 00-objective.json and writing what
    # the admitted set cannot cover. It has to sort immediately before
    # triage-seal: it cannot start until every fan-out member has finished
    # (the same barrier reconcile and score hold for their own fan-outs), and
    # triage-seal folds its 00-audit.json into the sealed record right after.
    "triage-audit",
    # triage-seal has to sort last in the family regardless of which of the
    # above has landed yet: it is the pass that seals every one of their
    # outputs into 00-triage.json, and this tuple is both the on-disk
    # numbering and the documentation of that ordering -- placing it any
    # earlier would draw both generated diagrams with the seal running
    # before the passes it seals.
    "triage-seal",
    "intake",
    "extract",
    # One logical step, engineered as substeps. Separate stages rather than one
    # skill branching on a slice id, for two reasons that are both load-bearing:
    # check-skills binds one skill file to one stage name, and manifest.stages
    # records model, effort and skill digest per stage -- which is what lets a
    # think-heavy pass carry a different budget from a mechanical one. The name
    # prefix keeps the family legible here, where the ordering is the pipeline's
    # documentation.
    "reconcile-subjects",
    "reconcile-contradict",
    "reconcile-capabilities",
    "reconcile-outcomes",
    "reconcile-entities",
    "reconcile-goals",
    "reconcile-gaps",
    "reconcile-seal",
    "propose",
    "score",
    "instantiate",
    "challenge",
    "emit",
    "smoke",
)

_SAFE_SEGMENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

# The one definition of a round-part name, shared by scenario_part_rounds and
# score_part_rounds so the two can never disagree about what counts as a round.
#
# A regex rather than str.isdigit(), because isdigit() is *wider* than int() in
# one direction and equally wide in the other, and both hurt. Measured (codepoints
# spelled out rather than pasted: U+0663 is right-to-left and reorders the rest of
# a comment line in most editors):
#
#   - U+00B2, superscript two. isdigit() is True, int() raises a bare ValueError.
#     That is neither OSError nor UsageError, so unlike an unreadable directory it
#     is *not* in cli.py's exit-2 tuple -- it reaches the catch-all and becomes an
#     exit-1 [internal] finding, telling the orchestrator to repair a stage over a
#     directory name. Latent until a subcommand calls these, and closed here
#     rather than left to whichever caller first does.
#   - U+FF11 and U+0663, fullwidth one and Arabic-Indic three. isdigit() and int()
#     BOTH accept them, so no amount of guarding int() helps: a filter built on
#     either alone silently counts rounds 1 and 3 from names nothing ever wrote.
#
# re's `\d` is Unicode-wide too, so the explicit [0-9] class is load-bearing --
# `[1-9]\d{0,}` looks like the same pattern and accepts round-1<U+0663> as 13.
#
# `[1-9][0-9]*` rather than `\d+` on purpose, and this is a ruling, not an
# oversight: round-01 is REJECTED, not normalised to 1. `\d+` accepts it and
# int() folds it onto the same number, so round-01 beside round-1 yields
# [1, 1] -- a duplicated round makes a caller walk one round twice and every
# scenario id collide. Normalising would invent a round from a directory nobody
# writes; rejecting says the truth, that the name is not one of ours. It also
# excludes round-0, which the round_n >= 1 guards already refuse to build.
_ROUND_PART = re.compile(r"round-([1-9][0-9]*)")


class UnsafeSegment(ValueError):
    """Raised when an id from an artifact would escape the run directory."""


def list_dir(directory: Path) -> list[Path]:
    """Every entry directly inside `directory`, sorted; `[]` if it does not exist.

    The one place this package lists a run directory, because listing has a
    failure mode every caller was getting wrong in one of two ways.

    `Path.glob` *swallows* EACCES and yields nothing, so an unreadable
    `01-claims/` made `validate --stage extract` report "stage 'extract'
    produced no claims artifact" and made `check-refs` report four "no such
    claim" findings against a world model that was perfectly correct -- checks
    announcing absence, and in the refs case naming the wrong artifact
    entirely, because their input could not be read rather than was not there.
    `Path.iterdir` and `Path.is_dir` do the opposite and raise PermissionError
    (`is_dir` only swallows ENOENT/ENOTDIR/EBADF/ELOOP), which is not in
    cli.py's narrow catch tuple, so it reached the catch-all and dressed a
    filesystem problem as a repairable stage defect at exit 1.

    Neither is right: an unreadable run directory is the harness pointed at
    something it cannot read, which is exit 2. Raising the UsageError that maps
    there is what skills._skill_dirs already does for the same shape on the
    prompt directory. `is_dir()` on `directory` itself is inside the try for
    the same reason the comprehension is: it stats the path, so it raises when
    the *parent* is the unreadable one.
    """
    try:
        if not directory.is_dir():
            return []
        return sorted(directory.iterdir())
    except OSError as exc:
        raise UsageError(f"cannot read run directory: {directory} ({exc})") from exc


def list_json(directory: Path) -> list[Path]:
    """Every `*.json` file directly inside `directory`, sorted.

    The replacement for `sorted(directory.glob("*.json"))` at every call site
    that was reading a run's claims, coverage rounds or verdicts -- see
    list_dir for why the glob was the wrong tool.
    """
    try:
        return sorted(p for p in list_dir(directory) if p.suffix == ".json" and p.is_file())
    except OSError as exc:
        raise UsageError(f"cannot read run directory: {directory} ({exc})") from exc


def is_safe_segment(value: str) -> bool:
    """Whether `value` is safe to use as one path segment.

    The one definition of segment safety in the system. safe_segment raises on
    the negative answer, for call sites joining a path; callers that need to
    partition a list of names rather than abort on the first bad one ask this
    instead.
    """
    return isinstance(value, str) and bool(_SAFE_SEGMENT.match(value)) and ".." not in value


def safe_segment(value: str) -> str:
    """Return `value` if it is safe to use as one path segment, else raise.

    Ids in artifacts are produced by language models and must never be joined
    into a path unchecked: "../../etc" is a plausible thing for a confused
    stage to emit, and the run directory is the only place we write.
    """
    if not is_safe_segment(value):
        raise UnsafeSegment(f"unsafe path segment: {value!r}")
    return value


class RunPaths:
    """Resolves every artifact path for one run directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def __repr__(self) -> str:
        return f"RunPaths({str(self.root)!r})"

    # -- singleton artifacts ---------------------------------------------
    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def inputs_dir(self) -> Path:
        return self.root / "00-inputs"

    @property
    def catalogue(self) -> Path:
        """Every candidate survey found, with one bounded digest each.

        In the 00 family beside 00-inputs/ because survey, triage and intake are
        00a, 00b and 00c -- the same relationship 01-claims/ and
        01-world-model.json already have.
        """
        return self.root / "00-catalogue.json"

    @property
    def triage(self) -> Path:
        """One disposition per candidate, plus deficiencies and projections."""
        return self.root / "00-triage.json"

    @property
    def slices(self) -> Path:
        """The catalogue partitioned into fixed-size slices for triage's passes.

        Still in the 00 band: the band means "what this run will be allowed to
        know," a property of the whole survey/triage/intake family rather than
        of the catalogue alone, and the 00-numbering stays intake's -- 00a/00b/00c
        -- no matter how many artifacts triage now writes on the way to its
        sealed record. Splitting triage into a slicer, three prompt passes and a
        seal turns one logical step into bounded substeps engineered for scale;
        every substep's own artifact still belongs where the single triage
        artifact used to sit, because the substep boundary is an engineering
        choice about *how* triage decides, not a new thing this run is allowed
        to know.
        """
        return self.root / "00-slices.json"

    @property
    def slices_dir(self) -> Path:
        return self.root / "00-slices"

    @property
    def objective(self) -> Path:
        return self.root / "00-objective.json"

    @property
    def dispositions_dir(self) -> Path:
        return self.root / "00-dispositions"

    @property
    def audit(self) -> Path:
        return self.root / "00-audit.json"

    @property
    def adoptions(self) -> Path:
        return self.root / "00-adoptions.json"

    @property
    def claims_dir(self) -> Path:
        return self.root / "01-claims"

    @property
    def subjects(self) -> Path:
        """The claim subject cover: every claim, assigned to one or more subjects.

        In the 01 family with the rest of world-model construction, because that
        is what the band means -- the numbering stays intake's, and everything
        between 01-claims/ and 01-world-model.json is one logical step engineered
        as substeps.
        """
        return self.root / "01-subjects.json"

    @property
    def contradictions_dir(self) -> Path:
        return self.root / "01-contradictions"

    @property
    def capabilities_part(self) -> Path:
        return self.root / "01-capabilities.json"

    @property
    def outcomes_part(self) -> Path:
        return self.root / "01-outcomes.json"

    @property
    def entities_part(self) -> Path:
        return self.root / "01-entities.json"

    @property
    def goals_part(self) -> Path:
        return self.root / "01-goals.json"

    @property
    def gaps_part(self) -> Path:
        return self.root / "01-gaps.json"

    @property
    def world_model(self) -> Path:
        return self.root / "01-world-model.json"

    @property
    def scenarios(self) -> Path:
        return self.root / "02-scenarios.json"

    @property
    def batches(self) -> Path:
        return self.root / "02-batches.json"

    @property
    def scenario_parts_dir(self) -> Path:
        return self.root / "02-scenarios"

    def scenario_round_dir(self, round_n: int) -> Path:
        if round_n < 1:
            raise ValueError(f"scenario round must be >= 1, got {round_n}")
        return self.scenario_parts_dir / f"round-{round_n}"

    def scenario_part(self, round_n: int, batch_id: str) -> Path:
        return self.scenario_round_dir(round_n) / f"{safe_segment(batch_id)}.json"

    def scenario_part_rounds(self) -> list[int]:
        """Every round number that has a part directory, ascending.

        Sorted numerically rather than lexically: round-10 must not sort between
        round-1 and round-2, which is exactly what sorted() on the stem does.

        Names that are not _ROUND_PART are skipped rather than raising -- a stray
        02-scenarios/notes.json, a round-x/, a plain file named round-3 -- for
        the reason score_part_rounds gives: this is what the seal iterates, and
        one stray entry must not stop a real round from being assembled.
        """
        rounds: list[int] = []
        try:
            for entry in list_dir(self.scenario_parts_dir):
                match = _ROUND_PART.fullmatch(entry.name)
                if match and entry.is_dir():
                    rounds.append(int(match.group(1)))
        except OSError as exc:
            # The same catch _instance_dir_names carries, for the same reason:
            # list_dir converts the failure of listing this directory, but a
            # directory that can be listed and not stat'ed through (mode 0o444)
            # makes `entry.is_dir()` on a *child* raise instead, and list_dir
            # never touches the child.
            #
            # This is message fidelity, not an exit-code repair: cli.py's
            # `except (OSError, UsageError, ArtifactError, UnknownStage)` already
            # maps both to exit 2. What the bare error got wrong is *which
            # artifact it named* -- it names an arbitrary child it happened to
            # stat first (.../02-scenarios/round-1) where every sibling listing
            # names the directory the accessor actually reads. Same exception
            # type and the same message shape as _instance_dir_names, so a
            # caller cannot tell the two apart.
            raise UsageError(
                f"cannot read run directory: {self.scenario_parts_dir} ({exc})"
            ) from exc
        return sorted(rounds)

    def _scenario_part_stems(self, round_n: int) -> list[str]:
        return [p.stem for p in list_json(self.scenario_round_dir(round_n))]

    def scenario_part_batch_ids(self, round_n: int) -> list[str]:
        """The safe batch ids with a part in this round, sorted."""
        return sorted(s for s in self._scenario_part_stems(round_n) if is_safe_segment(s))

    def unsafe_scenario_part_names(self, round_n: int) -> list[str]:
        """Part stems this package refuses to join into a path.

        Split from scenario_part_batch_ids for the reason
        unsafe_contradiction_part_names is split from subject_part_ids: an
        id-listing accessor that raised made the failure surface at a call site
        with no way to report it, and these belong in a finding instead.
        """
        return sorted(s for s in self._scenario_part_stems(round_n) if not is_safe_segment(s))

    @property
    def score_parts_dir(self) -> Path:
        return self.root / "03-score"

    def score_part(self, round_n: int) -> Path:
        if round_n < 1:
            raise ValueError(f"score round must be >= 1, got {round_n}")
        return self.score_parts_dir / f"round-{round_n}.json"

    def score_part_rounds(self) -> list[int]:
        """Every round number that has a score part, ascending.

        Sorted numerically for the reason scenario_part_rounds is, and a file
        whose stem is not _ROUND_PART is ignored rather than raising: this is
        the accessor the seal iterates, and a stray file in the directory must
        not be able to stop a round from being assembled.
        """
        rounds: list[int] = []
        for path in list_json(self.score_parts_dir):
            match = _ROUND_PART.fullmatch(path.stem)
            if match:
                rounds.append(int(match.group(1)))
        return sorted(rounds)

    @property
    def coverage_dir(self) -> Path:
        return self.root / "03-coverage"

    @property
    def coverage_latest(self) -> Path:
        return self.coverage_dir / "latest.json"

    @property
    def instances_dir(self) -> Path:
        return self.root / "04-instances"

    @property
    def verdicts_dir(self) -> Path:
        return self.root / "05-verdicts"

    @property
    def suite_dir(self) -> Path:
        return self.root / "06-suite"

    @property
    def report(self) -> Path:
        return self.root / "07-report.json"

    @property
    def decisions(self) -> Path:
        return self.root / "decisions.md"

    # -- per-id artifacts ------------------------------------------------
    def input_file(self, stored_as: str) -> Path:
        """The registered copy of one input artifact, by its manifest name.

        `stored_as` comes from manifest.inputs[].stored_as, which intake writes.
        That is what makes the manifest self-describing: a reader re-verifying a
        digest does not have to re-derive intake's naming rule, and there is only
        one definition of that rule to keep correct.
        """
        return self.inputs_dir / safe_segment(stored_as)

    def claims(self, artifact_id: str) -> Path:
        return self.claims_dir / f"{safe_segment(artifact_id)}.json"

    def contradiction_part(self, subject_id: str) -> Path:
        return self.contradictions_dir / f"{safe_segment(subject_id)}.json"

    def _contradiction_part_stems(self) -> list[str]:
        """Every contradictions part filename on disk, without its suffix, sorted.

        The shared half of the two listings below, the way _instance_dir_names is
        for scenario_ids_with_instances and unsafe_instance_dir_names: one read of
        the directory, partitioned twice, so the two can never disagree about what
        is there.
        """
        return [path.stem for path in list_json(self.contradictions_dir)]

    def subject_part_ids(self) -> list[str]:
        """Subject ids that have a contradictions part on disk, from the filenames.

        Derived from the directory rather than from 01-subjects.json on purpose:
        this is what the fan-out actually produced, and comparing it against the
        cover is exactly the check refs.check_contradiction_parts performs. A
        helper that read the cover instead could never report a part nobody
        asked for.

        Names that are not safe path segments are excluded and surfaced by
        unsafe_contradiction_part_names() instead, for the reason
        scenario_ids_with_instances records further down this file -- an incident,
        not a precaution: every caller joins these back onto a path, here through
        contradiction_part(), and returning an unsafe one made the later call
        raise UnsafeSegment, which cli.py mapped to exit 2, so one badly-named
        entry both misreported a repairable stage defect as a misconfigured
        harness and discarded every other finding in the run. A fan-out member
        told to write `01-contradictions/<subject_id>.json` can emit
        `01-contradictions/subject 1.json`, and this listing is what
        refs.check_contradiction_parts consumes.
        """
        return [name for name in self._contradiction_part_stems() if is_safe_segment(name)]

    def unsafe_contradiction_part_names(self) -> list[str]:
        """Contradictions part names that are not safe path segments, sorted.

        What unsafe_instance_dir_names is to the instances directory:
        refs.check_contradiction_parts turns each into an ordinary finding, so a
        pass that wrote a badly-named part is reported at exit 1 alongside
        everything else rather than being silently dropped by the listing above.
        """
        return [name for name in self._contradiction_part_stems() if not is_safe_segment(name)]

    def slice_shard(self, slice_id: str) -> Path:
        return self.slices_dir / f"{safe_segment(slice_id)}.json"

    def disposition_part(self, slice_id: str) -> Path:
        return self.dispositions_dir / f"{safe_segment(slice_id)}.json"

    def coverage_round(self, round_n: int) -> Path:
        if round_n < 1:
            raise ValueError(f"coverage round must be >= 1, got {round_n}")
        return self.coverage_dir / f"round-{round_n}.json"

    def instance_dir(self, scenario_id: str) -> Path:
        return self.instances_dir / safe_segment(scenario_id)

    def seed(self, scenario_id: str) -> Path:
        return self.instance_dir(scenario_id) / "seed.json"

    def expected(self, scenario_id: str) -> Path:
        return self.instance_dir(scenario_id) / "expected.json"

    def rationale(self, scenario_id: str) -> Path:
        return self.instance_dir(scenario_id) / "rationale.md"

    def verdict(self, scenario_id: str) -> Path:
        return self.verdicts_dir / f"{safe_segment(scenario_id)}.json"

    def task_dir(self, scenario_id: str) -> Path:
        return self.suite_dir / safe_segment(scenario_id)

    @property
    def measurement_dir(self) -> Path:
        """Outputs of the measurement tools, which are not pipeline stages.

        Kept out of the numbered prefixes on purpose: those are the stage
        contract, and STAGES/STAGE_ARTIFACTS must not grow an entry for a tool
        that no orchestrator dispatches.
        """
        return self.root / "measurement"

    @property
    def recall(self) -> Path:
        return self.measurement_dir / "recall.json"

    @property
    def recall_md(self) -> Path:
        """The human-facing rendering of recall.json.

        Here rather than joined inline by recall.compare_run: this module is the
        single source of truth for artifact paths, and its sibling recall.json
        was already a property, so the one file the tool writes outside this
        module was the one nothing else could find by name.
        """
        return self.measurement_dir / "recall.md"

    @property
    def review_dir(self) -> Path:
        return self.measurement_dir / "review"

    @property
    def review_packet(self) -> Path:
        return self.review_dir / "packet.md"

    @property
    def review_sample(self) -> Path:
        return self.review_dir / "sample.json"

    def smoke_dir(self, role: str, scenario_id: str) -> Path:
        """Where one (role, task) execution's logs go.

        The `agent/` and `verifier/` children below this mirror Harbor's
        /logs/agent and /logs/verifier, so the verifier is handed the same paths
        it is handed in the container.
        """
        return self.measurement_dir / "smoke" / safe_segment(role) / safe_segment(scenario_id)

    # -- listings --------------------------------------------------------
    def _instance_dir_names(self) -> list[str]:
        try:
            return sorted(p.name for p in list_dir(self.instances_dir) if p.is_dir())
        except OSError as exc:
            # list_dir already converts the failure of listing the directory
            # itself. This catch is for the narrower shape: a directory that can
            # be listed but not stat'ed through (mode 0o444), where iterdir
            # succeeds and `p.is_dir()` on a *child* is what raises.
            raise UsageError(f"cannot read run directory: {self.instances_dir} ({exc})") from exc

    def scenario_ids_with_instances(self) -> list[str]:
        """Scenario ids that have an instance directory, sorted.

        Stage 5 and stage 6 iterate over this rather than re-reading
        02-scenarios.json, so a scenario rejected after instantiation is
        still visible to them and can be reported rather than vanishing.

        Names that are not safe path segments are excluded and surfaced by
        unsafe_instance_dir_names() instead. Returning them raw made every
        later seed()/expected() call raise UnsafeSegment, which cli.py mapped
        to exit 2 -- so one badly-named directory both misreported a
        repairable stage defect as a misconfigured harness and discarded every
        other finding in the run.
        """
        return [name for name in self._instance_dir_names() if is_safe_segment(name)]

    def scenario_ids_with_tasks(self) -> list[str]:
        """Scenario ids that have an emitted task directory, sorted.

        Names that are not safe path segments are excluded, for the same reason
        scenario_ids_with_instances excludes them: returning one makes every
        later task_dir() call raise UnsafeSegment, and UnsafeSegment is not in
        cli.py's narrow catch tuple, so it reaches the catch-all and becomes a
        single `[internal]` finding at exit 1 -- one badly-named directory
        discarding every other finding the run would have reported.
        Unlike the instances directory this one is written only by emit, which
        derives every name from an id safe_segment already vetted -- so an
        unsafe name here means someone edited the run directory by hand, and
        skipping it is the honest response.
        """
        try:
            return sorted(
                p.name for p in list_dir(self.suite_dir) if p.is_dir() and is_safe_segment(p.name)
            )
        except OSError as exc:
            # Same narrow shape _instance_dir_names catches: a listable but not
            # traversable directory, where `p.is_dir()` on a child is the raise.
            raise UsageError(f"cannot read run directory: {self.suite_dir} ({exc})") from exc

    def slice_ids_with_parts(self) -> list[str]:
        """Slice ids that have a written disposition part on disk, sorted.

        Mirrors scenario_ids_with_tasks's shape but over files rather than
        directories: list_json already converts an unreadable dispositions_dir
        into a UsageError (both the EACCES-at-listing and the
        not-stat-able-child shapes), so this only has to filter, not re-guard
        the listing. Names that are not safe path segments are excluded rather
        than returned, since returning one would make the next
        disposition_part() call raise UnsafeSegment at a call site that cannot
        report it usefully.
        """
        return sorted(p.stem for p in list_json(self.dispositions_dir) if is_safe_segment(p.stem))

    def unsafe_instance_dir_names(self) -> list[str]:
        """Instance directory names that are not safe path segments, sorted.

        refs.check_instances turns each into an ordinary finding, so a stage
        that wrote a badly-named directory is reported at exit 1 alongside
        everything else rather than aborting the run.
        """
        return [name for name in self._instance_dir_names() if not is_safe_segment(name)]
