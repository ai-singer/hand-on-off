"""The Phase 8.7 freeze: a new version, alongside the one it supersedes.

Phase 8.6 froze the pipeline and verified the freeze after measuring, so its
result could not be reported against a pipeline that had since moved. Phase 8.7
changes the pipeline on purpose, which means the Phase 8.6 freeze **must** now
fail to match - that is what a freeze is for. So the old file is left exactly as
it is and a new one is written next to it:

    risk_evaluation/v3_validation/evaluation_freeze_v3.json    Phase 8.6, unmoved
    risk_evaluation/v3_repair/evaluation_freeze_v3_repair.json  Phase 8.7, current

Two things this records that a plain re-freeze would not.

**The benchmark hash is carried over, not recomputed away.** The new freeze has
to show that the Phase 8.6 labels were not touched while the pipeline under them
was repaired. It stores the Phase 8.6 benchmark hash as `supersedes` and asserts
the recomputed one is identical, so "we did not change the expected results" is a
checked property rather than a claim in a report.

**The repair code is frozen too.** The components the repair adds - the
morphology layer, the negation scope, the source typing, the rejection cues - are
hashed by source bytes, because a freeze that covered only the v3 core would not
cover the thing Phase 8.7 actually changed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3_validation.freeze import (
    FREEZE_PATH as PHASE_86_FREEZE_PATH,
)
from ..v3_validation.freeze import (
    VERIFIED_KEYS,
    build_freeze,
    load_freeze,
)
from . import attribution, negation, rejection, sources

FREEZE_PATH = Path(__file__).resolve().parent / "evaluation_freeze_v3_repair.json"
FREEZE_SCHEMA_VERSION = "3.1.0"
FREEZE_KIND = "targeted-repair"

#: The repair layers this freeze covers, by module.
REPAIR_MODULES: Mapping[str, Any] = {
    "morphology": "risk_evaluation.v3.morphology",
    "negation": "risk_evaluation.v3_repair.negation",
    "sources": "risk_evaluation.v3_repair.sources",
    "rejection": "risk_evaluation.v3_repair.rejection",
    "attribution": "risk_evaluation.v3_repair.attribution",
}

REPAIRS = (
    "R1-intent-pattern-inflection-coverage",
    "R2-attribution-source-and-rejection-coverage",
    "R3-fallback-propagation",
)


class RepairFreezeError(Exception):
    """Raised when the repair freeze cannot be taken or verified."""


def _module_path(dotted: str) -> Path:
    import importlib

    module = importlib.import_module(dotted)
    location = getattr(module, "__file__", None)
    if not location:
        raise RepairFreezeError(f"{dotted} has no source file to freeze")
    return Path(location)


def repair_hash(dotted: str) -> str:
    """SHA-256 over a repair module's source bytes."""

    path = _module_path(dotted)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repair_hashes() -> dict[str, str]:
    return {name: repair_hash(dotted) for name, dotted in REPAIR_MODULES.items()}


def table_hash() -> str:
    """The declared repair tables, independent of their source formatting."""

    from ..v3.decision import RELATION_REQUIRED

    return hashlib.sha256(
        json.dumps(
            {
                "relation_required": {
                    key: list(value)
                    for key, value in sorted(RELATION_REQUIRED.items())
                },
                "negation_scopes": list(negation.SCOPES),
                "source_types": list(sources.SOURCE_TYPES),
                "rejection_voices": list(rejection.VOICES),
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def benchmark_hash() -> str:
    """The Phase 8.6 benchmark hash, recomputed from the unmodified labels."""

    return build_freeze()["benchmark_hash"]


def supersedes() -> dict[str, Any]:
    """What the Phase 8.6 freeze recorded, for comparison."""

    frozen = load_freeze(PHASE_86_FREEZE_PATH)
    return {
        "path": str(PHASE_86_FREEZE_PATH.name),
        **{key: frozen[key] for key in VERIFIED_KEYS if key in frozen},
        "timestamp": frozen.get("timestamp", ""),
        "case_count": frozen.get("case_count", 0),
        "benchmark": frozen.get("benchmark", ""),
    }


def build_repair_freeze() -> dict[str, Any]:
    current = build_freeze()
    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "freeze_kind": FREEZE_KIND,
        "pipeline": current["pipeline"],
        "pipeline_version": current["pipeline_version"],
        "repairs": list(REPAIRS),
        **{key: current[key] for key in VERIFIED_KEYS},
        "repair_hashes": repair_hashes(),
        "repair_table_hash": table_hash(),
        "benchmark": current["benchmark"],
        "case_count": current["case_count"],
        "labels_unchanged": True,
        "supersedes": supersedes(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_repair_freeze(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else FREEZE_PATH
    target.write_text(
        json.dumps(build_repair_freeze(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_repair_freeze(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_PATH
    if not target.is_file():
        raise RepairFreezeError(f"no Phase 8.7 repair freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class RepairFreezeVerification:
    matches: bool
    mismatches: tuple[str, ...]
    labels_unchanged: bool
    frozen: Mapping[str, Any]
    current: Mapping[str, Any]

    def render(self) -> str:
        if self.matches:
            return "evaluation freeze v3_repair MATCH (labels unchanged)"
        return "evaluation freeze v3_repair CHANGED: " + ", ".join(self.mismatches)


def verify_repair_freeze(path: str | Path | None = None) -> RepairFreezeVerification:
    """Recompute every component, including the repair layers."""

    frozen = load_repair_freeze(path)
    current = build_repair_freeze()
    keys: Sequence[str] = (*VERIFIED_KEYS, "repair_table_hash")
    mismatches = [key for key in keys if frozen.get(key) != current.get(key)]
    for name, digest in current["repair_hashes"].items():
        if frozen.get("repair_hashes", {}).get(name) != digest:
            mismatches.append(f"repair_hashes.{name}")

    # The labels are Phase 8.6's. A repair that changed them would show up here
    # rather than in a report nobody can check.
    prior = frozen.get("supersedes", {}).get("benchmark_hash")
    labels_unchanged = bool(prior) and prior == current["benchmark_hash"]
    if not labels_unchanged:
        mismatches.append("benchmark_hash")

    return RepairFreezeVerification(
        matches=not mismatches,
        mismatches=tuple(mismatches),
        labels_unchanged=labels_unchanged,
        frozen=frozen,
        current=current,
    )


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_repair_freeze()}")
        return 0
    result = verify_repair_freeze()
    print(result.render())
    if not result.matches:
        for key in result.mismatches:
            print(f"  {key}: {result.frozen.get(key)} -> {result.current.get(key)}")
        return 1
    frozen = result.frozen
    for key in (*VERIFIED_KEYS, "repair_table_hash"):
        print(f"  {key:24} {str(frozen[key])[:16]}")
    for name, digest in sorted(frozen["repair_hashes"].items()):
        print(f"  repair:{name:16} {digest[:16]}")
    print(f"  {'supersedes':24} {frozen['supersedes']['path']}")
    print(f"  {'labels_unchanged':24} {frozen['labels_unchanged']}")
    print(f"  {'benchmark':24} {frozen['benchmark']}")
    print(f"  {'case_count':24} {frozen['case_count']}")
    print(f"  {'timestamp':24} {frozen['timestamp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
