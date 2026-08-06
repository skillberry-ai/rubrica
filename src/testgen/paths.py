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


def safe_segment(value: str) -> str:
    """Return `value` if it is safe to use as one path segment, else raise.

    Ids in artifacts are produced by language models and must never be joined
    into a path unchecked: "../../etc" is a plausible thing for a confused
    stage to emit, and the run directory is the only place we write.
    """
    if not isinstance(value, str) or not _SAFE_SEGMENT.match(value) or ".." in value:
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

    # -- listings --------------------------------------------------------
    def scenario_ids_with_instances(self) -> list[str]:
        """Scenario ids that have an instance directory, sorted.

        Stage 5 and stage 6 iterate over this rather than re-reading
        02-scenarios.json, so a scenario rejected after instantiation is
        still visible to them and can be reported rather than vanishing.
        """
        if not self.instances_dir.is_dir():
            return []
        return sorted(p.name for p in self.instances_dir.iterdir() if p.is_dir())
