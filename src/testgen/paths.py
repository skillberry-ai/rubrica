"""Run-directory layout: the single source of truth for artifact paths.

Every module reads and writes artifacts through this module, so the on-disk
contract (design spec section 4) is expressed in exactly one place.
"""

from __future__ import annotations

import re
from pathlib import Path

# Stage names in pipeline order. The validate and check-refs CLIs accept
# these, and the orchestrator names the stage it is dispatching with them.
STAGES = (
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
    def review_dir(self) -> Path:
        return self.measurement_dir / "review"

    @property
    def review_packet(self) -> Path:
        return self.review_dir / "packet.md"

    @property
    def review_sample(self) -> Path:
        # Dead until Task 12, which replaces the review-packet stub with the real
        # sampler this file's rows come from.
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
        if not self.instances_dir.is_dir():
            return []
        return sorted(p.name for p in self.instances_dir.iterdir() if p.is_dir())

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
        later task_dir() call raise UnsafeSegment, which the CLI maps to exit 2.
        Unlike the instances directory this one is written only by emit, which
        derives every name from an id safe_segment already vetted -- so an
        unsafe name here means someone edited the run directory by hand, and
        skipping it is the honest response.
        """
        if not self.suite_dir.is_dir():
            return []
        return sorted(
            p.name for p in self.suite_dir.iterdir() if p.is_dir() and is_safe_segment(p.name)
        )

    def unsafe_instance_dir_names(self) -> list[str]:
        """Instance directory names that are not safe path segments, sorted.

        refs.check_instances turns each into an ordinary finding, so a stage
        that wrote a badly-named directory is reported at exit 1 alongside
        everything else rather than aborting the run.
        """
        return [name for name in self._instance_dir_names() if not is_safe_segment(name)]
