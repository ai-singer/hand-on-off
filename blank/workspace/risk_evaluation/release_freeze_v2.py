"""Evaluation freeze v2 — the Phase 7.5 evaluator, taxonomy and benchmark.

`evaluation_freeze.json` (v1) pins the Phase 7.2 evaluators against the v1/v2
benchmarks. It is *not* rewritten: an evaluator change is a new freeze, never an
edit of the old one.

This module records the second freeze, in `evaluation_freeze_v2.json`:

    taxonomy_hash          taxonomy_v2's categories and dimensions
    evaluator_hash         semantic-intent-v2's complete decision surface
    benchmark_hash         semantic/v3 (as measured) and semantic/v4 (governed)
    annotation_version     the labelling protocol the v3/v4 labels follow
    config_hash            the governance parameters of this freeze
    timestamp              when the freeze was taken

The v1 freeze and this one differ in one important way. v1 covered the benchmark
versions it was taken against; this freeze records the *governed* version
explicitly, because semantic/v3 fails its contamination audit and must never be
the dataset a frozen claim rests on. `governed_benchmark` names the version that
passed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import semantic_evaluator_v2 as evaluator_v2
from .benchmark_audit import NEAR_DUPLICATE_THRESHOLD
from .benchmark_registry import (
    ANNOTATION_PROTOCOL_V2,
    ANNOTATION_VERSION_V2,
    BenchmarkRegistry,
)
from .regression import PRIMARY_METRIC, REGRESSION_TOLERANCE
from .taxonomy_v2 import (
    AUTHOR_VOICE_CATEGORIES,
    CERTAINTY_LEVELS,
    MARKET_CLAIM_CASES,
    STATEMENT_SOURCES,
    TAXONOMY_VERSION,
    taxonomy_v2_payload,
)


FREEZE_V2_PATH = Path(__file__).resolve().parent / "evaluation_freeze_v2.json"
FREEZE_V2_SCHEMA_VERSION = "2.0.0"

#: semantic/v3 is measured and reported, but it reuses 32 texts from the
#: evaluator development benchmark, so the auditor fails it. semantic/v4 is the
#: decontaminated subset and is the version a frozen claim may rest on.
MEASURED_BENCHMARK = "semantic/v3"
GOVERNED_BENCHMARK = "semantic/v4"

EVALUATION_CONFIG_V2: Mapping[str, Any] = {
    "taxonomy_version": TAXONOMY_VERSION,
    "annotation_version": ANNOTATION_VERSION_V2,
    "annotation_protocol": ANNOTATION_PROTOCOL_V2,
    "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
    "primary_metric": PRIMARY_METRIC,
    "regression_tolerance": REGRESSION_TOLERANCE,
    "measured_benchmark": MEASURED_BENCHMARK,
    "governed_benchmark": GOVERNED_BENCHMARK,
    "benchmark_scope": [MEASURED_BENCHMARK, GOVERNED_BENCHMARK],
}


class EvaluationFreezeV2Error(Exception):
    """Raised when the v2 freeze cannot be taken or verified."""


@dataclass(frozen=True, slots=True)
class FreezeV2Verification:
    matches: bool
    mismatches: tuple[str, ...]
    frozen: Mapping[str, Any]
    current: Mapping[str, Any]

    def render(self) -> str:
        if self.matches:
            return "evaluation freeze v2 MATCH"
        return "evaluation freeze v2 CHANGED: " + ", ".join(self.mismatches)


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluator_v2_decision_surface() -> dict[str, Any]:
    """The complete decision surface of semantic-intent-v2.

    Covers the pattern data and the declared dimensions, not the module's
    implementation: reformatting must not invalidate a freeze, but changing a
    pattern or a dimension must.
    """

    return {
        "evaluator": evaluator_v2.EVALUATOR_NAME,
        "statement_sources": list(STATEMENT_SOURCES),
        "certainty_levels": list(CERTAINTY_LEVELS),
        "author_voice_categories": list(AUTHOR_VOICE_CATEGORIES),
        "reader_pressure_patterns": list(evaluator_v2.READER_PRESSURE_PATTERNS),
        "conditional_patterns": list(evaluator_v2.CONDITIONAL_PATTERNS),
        "possibility_patterns": list(evaluator_v2.POSSIBILITY_PATTERNS),
        "probability_patterns": list(evaluator_v2.PROBABILITY_PATTERNS),
        "third_party_patterns": list(evaluator_v2.THIRD_PARTY_PATTERNS),
        "quotation_patterns": list(evaluator_v2.QUOTATION_PATTERNS),
        "rejection_patterns": list(evaluator_v2.REJECTION_PATTERNS),
        "intent_patterns": [
            {
                "category": pattern.category,
                "required": list(pattern.required),
                "rationale": pattern.rationale,
            }
            for pattern in evaluator_v2.V2_INTENT_PATTERNS
        ],
        "confidence": {
            "base": evaluator_v2._CONFIDENCE_BASE,
            "step": evaluator_v2._CONFIDENCE_STEP,
            "cap": evaluator_v2._CONFIDENCE_CAP,
        },
        "dimensions": {
            name: list(values)
            for name, values in sorted(evaluator_v2.supported_dimensions().items())
        },
    }


def evaluator_hash() -> str:
    return _hash_payload(evaluator_v2_decision_surface())


def taxonomy_hash() -> str:
    return _hash_payload(taxonomy_v2_payload())


def benchmark_hash(
    registry: BenchmarkRegistry | None = None,
    *,
    versions: Iterable[str] | None = None,
) -> str:
    active = registry if registry is not None else BenchmarkRegistry()
    scope = (
        tuple(EVALUATION_CONFIG_V2["benchmark_scope"])
        if versions is None
        else tuple(versions)
    )
    wanted = set(scope)
    return _hash_payload(
        {
            f"{record.benchmark_id}/{record.version}": {
                "dataset_hash": record.dataset_hash,
                "case_count": record.case_count,
                "status": record.status,
            }
            for record in active.list_benchmarks()
            if f"{record.benchmark_id}/{record.version}" in wanted
        }
    )


def config_hash() -> str:
    return _hash_payload(EVALUATION_CONFIG_V2)


def benchmark_facts(registry: BenchmarkRegistry | None = None) -> dict[str, Any]:
    """The measured/governed case counts and hashes, recorded for the reader."""

    active = registry if registry is not None else BenchmarkRegistry()
    facts: dict[str, Any] = {}
    for name in (MEASURED_BENCHMARK, GOVERNED_BENCHMARK):
        benchmark_id, version = name.split("/")
        record = active.get(benchmark_id, version)
        facts[name] = {
            "dataset_hash": record.dataset_hash,
            "case_count": record.case_count,
            "status": record.status,
        }
    return facts


def build_freeze(registry: BenchmarkRegistry | None = None) -> dict[str, Any]:
    active = registry if registry is not None else BenchmarkRegistry()
    return {
        "freeze_schema_version": FREEZE_V2_SCHEMA_VERSION,
        "evaluator_name": evaluator_v2.EVALUATOR_NAME,
        "taxonomy_version": TAXONOMY_VERSION,
        "evaluator_hash": evaluator_hash(),
        "taxonomy_hash": taxonomy_hash(),
        "benchmark_hash": benchmark_hash(active),
        "annotation_version": ANNOTATION_VERSION_V2,
        "annotation_protocol": ANNOTATION_PROTOCOL_V2,
        "config_hash": config_hash(),
        "measured_benchmark": MEASURED_BENCHMARK,
        "governed_benchmark": GOVERNED_BENCHMARK,
        "benchmarks": benchmark_facts(active),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_evaluation_freeze(
    path: str | Path | None = None,
    registry: BenchmarkRegistry | None = None,
) -> Path:
    target = Path(path) if path is not None else FREEZE_V2_PATH
    target.write_text(
        json.dumps(build_freeze(registry), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_evaluation_freeze(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_V2_PATH
    if not target.is_file():
        raise EvaluationFreezeV2Error(f"no v2 evaluation freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


VERIFIED_KEYS = (
    "evaluator_hash",
    "taxonomy_hash",
    "benchmark_hash",
    "annotation_version",
    "config_hash",
)


def verify_evaluation_freeze(
    path: str | Path | None = None,
    registry: BenchmarkRegistry | None = None,
) -> FreezeV2Verification:
    """Recompute every recorded component and report which one moved."""

    frozen = load_evaluation_freeze(path)
    current = build_freeze(registry)
    mismatches = tuple(
        key for key in VERIFIED_KEYS if frozen.get(key) != current.get(key)
    )
    return FreezeV2Verification(
        matches=not mismatches,
        mismatches=mismatches,
        frozen=frozen,
        current=current,
    )


#: Unambiguous alias for the package export table, where the v1 freeze already
#: occupies `verify_evaluation_freeze`.
verify_evaluation_freeze_v2 = verify_evaluation_freeze


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_evaluation_freeze()}")
        return 0
    result = verify_evaluation_freeze()
    print(result.render())
    if not result.matches:
        for key in result.mismatches:
            print(f"  {key}: {result.frozen.get(key)} -> {result.current.get(key)}")
        return 1
    frozen = result.frozen
    for key in ("evaluator_hash", "taxonomy_hash", "benchmark_hash", "config_hash"):
        print(f"  {key:16} {str(frozen[key])[:16]}")
    print(f"  {'annotation':16} {frozen['annotation_version']}")
    print(f"  {'governed':16} {frozen['governed_benchmark']}")
    print(f"  {'timestamp':16} {frozen['timestamp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
