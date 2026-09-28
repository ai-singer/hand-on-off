"""The Phase 8.9 freeze, and the guard that makes it hold.

The phase requires the evaluator to be frozen while independent data is measured,
and requires the run to **stop** if a change turns out to be necessary rather than
making it. Both halves are enforced here.

`evaluation_freeze_v3_2.json` records:

    evaluator hash           the Phase 8.4/8.7/8.8 pattern set
    taxonomy hash            the categories and their severities
    decision policy hash     the rule table and the relation-to-category map
    benchmark hash           Phase 8.6's independent_v1, inherited unchanged
    configuration hash       the pipeline configuration the run uses
    capability hashes        the Phase 8.8 modules, by source bytes
    frozen sources           every source file a change would move, by digest

The last row is what makes the freeze a guard instead of a note. `guard()` re-hashes
every file under `FROZEN_PATHS` and raises `FreezeError` if one moved, so a change
made during the run is a test failure rather than a thing to remember. The phase's
tests call it, so the constraint cannot be satisfied by intention.

`PROPOSALS` is the other side of the same rule. When the independent data exposes a
defect, the honest output is a written proposal and a stop, not a patch: a repair
made after seeing the result would make the result meaningless. Proposals are
recorded in `proposals_v3_2.json` and reported in section 5 of the phase report.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..v3_validation.freeze import (
    VERIFIED_KEYS,
    build_freeze,
)

FREEZE_PATH = Path(__file__).resolve().parent / "evaluation_freeze_v3_2.json"
PROPOSALS_PATH = Path(__file__).resolve().parent / "proposals_v3_2.json"
FREEZE_SCHEMA_VERSION = "3.3.0"
FREEZE_KIND = "independent-validation"

#: Everything the phase forbids changing while the run is in progress. Directories
#: are expanded to their `.py` and `.json` files, so a new file appearing inside one
#: is a change too - which is the point: adding a frame is how the last three
#: phases repaired things.
FROZEN_PATHS: tuple[str, ...] = (
    "risk_evaluation/v3",
    "risk_evaluation/v3_1",
    "risk_evaluation/v3_repair",
    "risk_evaluation/taxonomy.py",
    "risk_evaluation/taxonomy_v2.py",
    "risk_evaluation/semantic_evaluator_v2.py",
)

#: Suffixes counted as source. `__pycache__` and reports are excluded: a compiled
#: artefact or a regenerated report is not a change to the evaluator.
_SOURCE_SUFFIXES = (".py",)
_SKIP_PARTS = ("__pycache__",)


class FreezeError(Exception):
    """Raised when a frozen source changed, or a freeze cannot be verified."""


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_files() -> tuple[Path, ...]:
    root = workspace_root()
    found: list[Path] = []
    for entry in FROZEN_PATHS:
        target = root / entry
        if target.is_dir():
            for path in sorted(target.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix not in _SOURCE_SUFFIXES:
                    continue
                if any(part in _SKIP_PARTS for part in path.parts):
                    continue
                found.append(path)
        elif target.is_file():
            found.append(target)
    return tuple(found)


def frozen_source_digests() -> dict[str, str]:
    """SHA-256 of every frozen source file, keyed by workspace-relative path."""

    root = workspace_root()
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _source_files()
    }


def _sha(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_freeze_v3_2() -> dict[str, Any]:
    current = build_freeze()
    from ..v3_1.freeze import capability_hashes, capability_table_hash

    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "freeze_kind": FREEZE_KIND,
        "pipeline": current["pipeline"],
        "pipeline_version": current["pipeline_version"],
        **{key: current[key] for key in VERIFIED_KEYS},
        "capability_hashes": capability_hashes(),
        "capability_table_hash": capability_table_hash(),
        "frozen_paths": list(FROZEN_PATHS),
        "frozen_sources": frozen_source_digests(),
        "frozen_source_count": len(frozen_source_digests()),
        "invariants": {
            "evaluator_frozen_during_run": True,
            "repairs_require_a_proposal": True,
            "proposals_path": PROPOSALS_PATH.name,
        },
        "supersedes": {
            "phase_8_6": "risk_evaluation/v3_validation/evaluation_freeze_v3.json",
            "phase_8_7": "risk_evaluation/v3_repair/evaluation_freeze_v3_repair.json",
            "phase_8_8": "risk_evaluation/v3_1/evaluation_freeze_v3_1.json",
        },
        "timestamp": "2026-09-28T04:00:00Z",
    }


def write_freeze_v3_2(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else FREEZE_PATH
    target.write_text(
        json.dumps(build_freeze_v3_2(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_freeze_v3_2(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_PATH
    if not target.is_file():
        raise FreezeError(f"no Phase 8.9 freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class FreezeVerification:
    matches: bool
    mismatches: tuple[str, ...]
    moved_sources: tuple[str, ...]
    frozen: Mapping[str, Any]
    current: Mapping[str, Any]

    @property
    def moved_components(self) -> tuple[str, ...]:
        return tuple(
            item for item in self.mismatches if not item.startswith("frozen_sources.")
        )

    def render(self) -> str:
        if self.matches:
            return (
                "evaluation freeze v3_2 MATCH: evaluator frozen, "
                f"{len(self.frozen.get('frozen_sources', {}))} sources unchanged"
            )
        lines = ["evaluation freeze v3_2 CHANGED"]
        for item in self.mismatches:
            lines.append(f"  {item}")
        for path in self.moved_sources:
            lines.append(f"  moved source: {path}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "mismatches": list(self.mismatches),
            "moved_sources": list(self.moved_sources),
            "moved_components": list(self.moved_components),
        }


def verify_freeze_v3_2(path: str | Path | None = None) -> FreezeVerification:
    frozen = load_freeze_v3_2(path)
    current = build_freeze_v3_2()

    mismatches = [
        key
        for key in (*VERIFIED_KEYS, "capability_table_hash")
        if frozen.get(key) != current.get(key)
    ]
    for name, digest in current["capability_hashes"].items():
        if frozen.get("capability_hashes", {}).get(name) != digest:
            mismatches.append(f"capability_hashes.{name}")

    moved: list[str] = []
    recorded = frozen.get("frozen_sources", {})
    for relative, digest in current["frozen_sources"].items():
        if recorded.get(relative) != digest:
            moved.append(relative)
    for relative in recorded:
        if relative not in current["frozen_sources"]:
            moved.append(f"{relative} (removed)")
    mismatches.extend(f"frozen_sources.{item}" for item in moved)

    return FreezeVerification(
        matches=not mismatches,
        mismatches=tuple(mismatches),
        moved_sources=tuple(moved),
        frozen=frozen,
        current=current,
    )


def guard(path: str | Path | None = None) -> None:
    """Raise unless every frozen source is byte-identical to the freeze.

    This is the phase's central constraint expressed as code. A change to the
    evaluator during the run makes this raise, so no result can be reported against
    a pipeline that moved while it was being measured.
    """

    result = verify_freeze_v3_2(path)
    if result.moved_sources:
        raise FreezeError(
            "the evaluator changed during a frozen run; the phase requires a stop "
            "and a proposal rather than a repair: "
            + ", ".join(result.moved_sources)
        )
    if result.moved_components:
        raise FreezeError(
            "a frozen component moved: " + ", ".join(result.moved_components)
        )


def describe() -> dict[str, Any]:
    return {
        "freeze_path": FREEZE_PATH.name,
        "proposals_path": PROPOSALS_PATH.name,
        "schema_version": FREEZE_SCHEMA_VERSION,
        "kind": FREEZE_KIND,
        "verified_keys": list(VERIFIED_KEYS),
        "frozen_paths": list(FROZEN_PATHS),
        "frozen_source_count": len(frozen_source_digests()),
    }


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_freeze_v3_2()}")
        return 0
    try:
        guard()
    except FreezeError as error:
        print(str(error))
        return 1
    result = verify_freeze_v3_2()
    print(result.render())
    frozen = result.frozen
    for key in (*VERIFIED_KEYS, "capability_table_hash"):
        print(f"  {key:24} {str(frozen[key])[:16]}")
    print(f"  {'frozen_source_count':24} {frozen['frozen_source_count']}")
    print(f"  {'timestamp':24} {frozen['timestamp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
