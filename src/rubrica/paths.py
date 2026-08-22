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
    "triage",
    "triage-slices",
    # triage-objective, triage-rule and triage-audit belong here too, each
    # inserted immediately before triage-seal as its own task adds it -- the
    # three prompt passes staged-triage's design splits the old monolithic
    # triage stage into, giving the eventual order
    # survey, triage, triage-slices, triage-objective, triage-rule,
    # triage-audit, triage-seal, intake. triage-seal has to sort last in the
    # family regardless of which of those has landed yet: it is the pass that
    # seals every one of their outputs into 00-triage.json, and this tuple is
    # both the on-disk numbering and the documentation of that ordering --
    # placing it any earlier would draw both generated diagrams with the seal
    # running before the passes it seals.
    "triage-seal",
    "intake",
    "extract",
    "reconcile",
    "propose",
    "score",
    "instantiate",
    "challenge",
    "emit",
    "smoke",
)

_SAFE_SEGMENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


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
    def world_model(self) -> Path:
        return self.root / "01-world-model.json"

    @property
    def scenarios(self) -> Path:
        return self.root / "02-scenarios.json"

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
