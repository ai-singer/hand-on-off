"""Freeze the Phase 8.5 pipeline before it is measured.

Six components, recorded in `evaluation_freeze_v3.json`:

    evaluator hash          the v3 intent pattern set
    taxonomy hash           the categories the labels follow
    decision policy hash    the rule table and the relation-to-category map
    benchmark hash          the independent dataset
    configuration hash      the pipeline configuration the run used
    timestamp               when the freeze was taken

The order matters and is the point of the phase: **freeze, then run, then
verify.** `verify_freeze()` recomputes every component and reports which one
moved, so a result cannot be reported against a pipeline that has since changed.
Any mismatch is a FAIL, and the phase forbids adjusting a rule in response to a
result, which is exactly what a mismatch would indicate had happened.

The timestamp is recorded but excluded from verification: re-taking a freeze
with nothing changed must not look like a difference.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..taxonomy_v2 import taxonomy_v2_payload
from ..v3.decision import RELATION_CATEGORY, RULES
from ..v3.model import V3_VERSION
from ..v3.patterns import PATTERNS
from ..v3.pipeline import PipelineConfig
from .cases import BENCHMARK_ID, BENCHMARK_VERSION, CASES, ValidationCase


FREEZE_PATH = Path(__file__).resolve().parent / "evaluation_freeze_v3.json"
FREEZE_SCHEMA_VERSION = "3.0.0"

VERIFIED_KEYS = (
    "evaluator_hash",
    "taxonomy_hash",
    "decision_policy_hash",
    "benchmark_hash",
    "configuration_hash",
)


class FreezeError(Exception):
    """Raised when a freeze cannot be taken or verified."""


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_hash(cases: Sequence[ValidationCase] | None = None) -> str:
    """SHA-256 over the complete annotation records, in order."""

    active = cases if cases is not None else CASES
    return _hash_payload([case.as_dict() for case in active])


def evaluator_hash() -> str:
    """The v3 pattern set: relations, frames, entities, patterns."""

    return _hash_payload(
        {
            "name": PATTERNS.name,
            "version": PATTERNS.version,
            "surface": PATTERNS.as_dict(),
        }
    )


def taxonomy_hash() -> str:
    return _hash_payload(taxonomy_v2_payload())


def decision_policy_hash() -> str:
    """The rule table, the actions and the relation-to-category map."""

    return _hash_payload(
        {
            "rules": [
                {
                    "rule_id": item.rule_id,
                    "description": item.description,
                    "base_action": item.base_action,
                }
                for item in RULES
            ],
            "relation_category": dict(sorted(RELATION_CATEGORY.items())),
            "model_version": V3_VERSION,
        }
    )


def configuration_hash(config: PipelineConfig | None = None) -> str:
    """The pipeline configuration the evaluation is run under."""

    active = config if config is not None else PipelineConfig()
    return _hash_payload(
        {
            **active.as_dict(),
            "record_timings": active.record_timings,
            "benchmark": f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
        }
    )


def build_freeze(config: PipelineConfig | None = None) -> dict[str, Any]:
    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "pipeline": "risk-evaluation-v3",
        "pipeline_version": V3_VERSION,
        "evaluator_hash": evaluator_hash(),
        "taxonomy_hash": taxonomy_hash(),
        "decision_policy_hash": decision_policy_hash(),
        "benchmark_hash": dataset_hash(),
        "configuration_hash": configuration_hash(config),
        "benchmark": f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
        "case_count": len(CASES),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_freeze(
    path: str | Path | None = None,
    config: PipelineConfig | None = None,
) -> Path:
    target = Path(path) if path is not None else FREEZE_PATH
    target.write_text(
        json.dumps(build_freeze(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_freeze(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_PATH
    if not target.is_file():
        raise FreezeError(f"no v3 evaluation freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class FreezeVerification:
    matches: bool
    mismatches: tuple[str, ...]
    frozen: Mapping[str, Any]
    current: Mapping[str, Any]

    def render(self) -> str:
        if self.matches:
            return "evaluation freeze v3 MATCH"
        return "evaluation freeze v3 CHANGED: " + ", ".join(self.mismatches)


def verify_freeze(
    path: str | Path | None = None,
    config: PipelineConfig | None = None,
) -> FreezeVerification:
    """Recompute every component and report which one moved."""

    frozen = load_freeze(path)
    current = build_freeze(config)
    mismatches = tuple(
        key for key in VERIFIED_KEYS if frozen.get(key) != current.get(key)
    )
    return FreezeVerification(
        matches=not mismatches,
        mismatches=mismatches,
        frozen=frozen,
        current=current,
    )


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_freeze()}")
        return 0
    result = verify_freeze()
    print(result.render())
    if not result.matches:
        for key in result.mismatches:
            print(f"  {key}: {result.frozen.get(key)} -> {result.current.get(key)}")
        return 1
    frozen = result.frozen
    for key in VERIFIED_KEYS:
        print(f"  {key:24} {str(frozen[key])[:16]}")
    print(f"  {'benchmark':24} {frozen['benchmark']}")
    print(f"  {'case_count':24} {frozen['case_count']}")
    print(f"  {'timestamp':24} {frozen['timestamp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
