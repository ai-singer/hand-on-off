"""Evaluation freeze protocol.

One file, `evaluation_freeze.json`, binds together everything a reported
evaluation result depends on:

    evaluator_hash    both evaluators' decision surfaces
    taxonomy_hash     the category definitions the labels follow
    benchmark_hash    the benchmark datasets this freeze covers
    config_hash       the governance parameters
    timestamp         when the freeze was taken

Without this, a score is unfalsifiable: the evaluator, the labels or the
thresholds could have moved since. `verify_evaluation_freeze()` recomputes all
four and reports which one changed, so a stale claim is detectable rather than
arguable.

The timestamp is recorded but excluded from verification — re-taking a freeze
with nothing changed must not look like a difference.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .benchmark_audit import NEAR_DUPLICATE_THRESHOLD
from .benchmark_registry import ANNOTATION_PROTOCOL, ANNOTATION_VERSION, BenchmarkRegistry
from .evaluator import KeywordRiskEvaluator
from .freeze import decision_surface_hash
from .regression import PRIMARY_METRIC, REGRESSION_TOLERANCE
from .taxonomy import RISK_TAXONOMY


FREEZE_PATH = Path(__file__).resolve().parent / "evaluation_freeze.json"
FREEZE_SCHEMA_VERSION = "1.0.0"

#: Governance parameters covered by `config_hash`. Changing any of them
#: invalidates every score reported under the previous freeze.
EVALUATION_CONFIG: Mapping[str, Any] = {
    "annotation_version": ANNOTATION_VERSION,
    "annotation_protocol": ANNOTATION_PROTOCOL,
    "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
    "primary_metric": PRIMARY_METRIC,
    "regression_tolerance": REGRESSION_TOLERANCE,
    "benchmark_versions": ["semantic/v1", "semantic/v2"],
}

#: Benchmark versions `evaluation_freeze.json` covers. Kept as its own constant
#: rather than derived from EVALUATION_CONFIG so that extending the scope cannot
#: silently move `config_hash` and invalidate the recorded freeze.
#:
#: Scoping matters because Phase 7.5 registered two further versions. A freeze is
#: a record of what a score was measured against; registering a new benchmark
#: later must not retroactively invalidate a freeze that never covered it, or
#: history becomes unverifiable simply because the project progressed.
FROZEN_VERSION_SCOPE: tuple[str, ...] = ("semantic/v1", "semantic/v2")

KEYWORD_RULES = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "xiaolin_finance"
    / "rules"
    / "filter_rules.json"
)


class EvaluationFreezeError(Exception):
    """Raised when a freeze cannot be taken or verified."""


@dataclass(frozen=True, slots=True)
class FreezeVerification:
    matches: bool
    mismatches: tuple[str, ...]
    frozen: Mapping[str, Any]
    current: Mapping[str, Any]

    def render(self) -> str:
        if self.matches:
            return "evaluation freeze MATCH"
        return "evaluation freeze CHANGED: " + ", ".join(self.mismatches)


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluator_hash() -> str:
    """Both evaluators: the semantic decision surface and the keyword rules."""

    keyword_rules = json.loads(KEYWORD_RULES.read_text(encoding="utf-8"))
    return _hash_payload(
        {
            "semantic": decision_surface_hash(),
            "keyword": {
                "name": KeywordRiskEvaluator.name,
                "rules": keyword_rules,
            },
        }
    )


def taxonomy_hash() -> str:
    return _hash_payload([entry.as_dict() for entry in RISK_TAXONOMY])


def _registry_payload(
    registry: BenchmarkRegistry, versions: Iterable[str] | None
) -> dict[str, Any]:
    wanted = None if versions is None else set(versions)
    return {
        f"{record.benchmark_id}/{record.version}": {
            "dataset_hash": record.dataset_hash,
            "case_count": record.case_count,
            "status": record.status,
        }
        for record in registry.list_benchmarks()
        if wanted is None or f"{record.benchmark_id}/{record.version}" in wanted
    }


def benchmark_hash(
    registry: BenchmarkRegistry | None = None,
    *,
    versions: Iterable[str] | None = None,
) -> str:
    """Hash the benchmark datasets a freeze covers.

    `versions` defaults to `FROZEN_VERSION_SCOPE`; pass `versions=None`
    explicitly via `all_benchmarks_hash()` to cover the whole registry.
    """

    active = registry if registry is not None else BenchmarkRegistry()
    scope = FROZEN_VERSION_SCOPE if versions is None else tuple(versions)
    return _hash_payload(_registry_payload(active, scope))


def all_benchmarks_hash(registry: BenchmarkRegistry | None = None) -> str:
    """Hash every registered version, whatever its status."""

    active = registry if registry is not None else BenchmarkRegistry()
    return _hash_payload(_registry_payload(active, None))


def config_hash() -> str:
    return _hash_payload(EVALUATION_CONFIG)


def build_freeze(registry: BenchmarkRegistry | None = None) -> dict[str, Any]:
    return {
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "evaluator_hash": evaluator_hash(),
        "taxonomy_hash": taxonomy_hash(),
        "benchmark_hash": benchmark_hash(registry),
        "config_hash": config_hash(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_evaluation_freeze(
    path: str | Path | None = None,
    registry: BenchmarkRegistry | None = None,
) -> Path:
    target = Path(path) if path is not None else FREEZE_PATH
    target.write_text(
        json.dumps(build_freeze(registry), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_evaluation_freeze(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else FREEZE_PATH
    if not target.is_file():
        raise EvaluationFreezeError(f"no evaluation freeze at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


def verify_evaluation_freeze(
    path: str | Path | None = None,
    registry: BenchmarkRegistry | None = None,
) -> FreezeVerification:
    """Recompute all four hashes and report which one moved."""

    frozen = load_evaluation_freeze(path)
    current = build_freeze(registry)
    mismatches = tuple(
        key
        for key in ("evaluator_hash", "taxonomy_hash", "benchmark_hash", "config_hash")
        if frozen.get(key) != current.get(key)
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
    print(f"  timestamp        {frozen['timestamp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
