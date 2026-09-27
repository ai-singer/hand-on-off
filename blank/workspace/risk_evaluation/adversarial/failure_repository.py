"""Failure repository: the misses worth keeping, and the candidates they yield.

The rule from Phase 8.1 is narrow on purpose:

    expected_detection is True  AND  detected is False  ->  failure

Nothing else is stored. A false positive is a finding and is reported, but it is
not a *failure to detect*, and mixing the two would let a flood of false
positives bury the misses that matter.

Records are one JSON file each, named by failure id, under `failures/`. The
documented shape is exactly:

    {"id", "text", "strategy", "expected", "actual", "severity", "created_at"}

plus `case_id`, `target_category` and `evidence`, which make a record traceable
back to the case and the evaluator output that produced it. Duplicate texts are
rejected: the same attack recorded twice would inflate every count it appears in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .case import normalize_text
from .evaluator_bridge import DetectionResult


FAILURE_ROOT = Path(__file__).resolve().parent / "failures"
CANDIDATES_PATH = Path(__file__).resolve().parent / "regression_candidates.json"
FAILURE_SCHEMA_VERSION = "1.0.0"

#: Fixed timestamps keep the committed repository byte-stable across re-runs.
DEFAULT_CREATED_AT = "2026-09-27T00:00:00Z"

FAILURE_ID_PREFIX = "ADV-F"


class FailureRepositoryError(Exception):
    """Raised when a failure record cannot be written or read."""


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """One recorded miss."""

    failure_id: str
    case_id: str
    text: str
    strategy: str
    expected: str
    actual: str
    severity: str
    created_at: str
    target_category: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", dict(self.evidence))

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)

    def as_dict(self) -> dict[str, Any]:
        """The documented shape first, then the traceability fields."""

        return {
            "id": self.failure_id,
            "text": self.text,
            "strategy": self.strategy,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity,
            "created_at": self.created_at,
            "case_id": self.case_id,
            "target_category": self.target_category,
            "evidence": dict(sorted(self.evidence.items())),
        }

    @property
    def path_name(self) -> str:
        return f"{self.failure_id}.json"


def failure_id_for(index: int) -> str:
    """ADV-F001, ADV-F002, ... Zero-padded so ids sort as text."""

    return f"{FAILURE_ID_PREFIX}{index:03d}"


def record_from(result: DetectionResult, *, index: int, created_at: str) -> FailureRecord:
    """Build a failure record from a miss. Refuses anything that is not one."""

    if not result.miss:
        raise FailureRepositoryError(
            f"{result.case_id} is not a failure: expected_detection="
            f"{result.expected_detection} detected={result.detected}"
        )
    return FailureRecord(
        failure_id=failure_id_for(index),
        case_id=result.case_id,
        text=str(result.evidence.get("text", "")),
        strategy=str(result.evidence.get("attack_strategy", "")),
        expected=result.target_category,
        actual="none",
        severity=str(result.evidence.get("severity", "medium")),
        created_at=created_at,
        target_category=result.target_category,
        evidence={
            "detected_categories": list(result.detected_categories),
            "statement_source": result.evidence.get("statement_source"),
            "certainty_level": result.evidence.get("certainty_level"),
            "market_claim_case": result.evidence.get("market_claim_case"),
            "suppressed": list(result.evidence.get("suppressed", ())),
            "expectation_basis": result.evidence.get("expectation_basis"),
            "evaluator": result.evaluator,
        },
    )


class FailureRepository:
    """Read and write failure records under one directory."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else FAILURE_ROOT

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, record: FailureRecord) -> Path:
        return self._root / record.path_name

    def load(self) -> tuple[FailureRecord, ...]:
        """Every stored record, ordered by id."""

        if not self._root.is_dir():
            return ()
        records: list[FailureRecord] = []
        for path in sorted(self._root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(
                FailureRecord(
                    failure_id=str(payload["id"]),
                    case_id=str(payload.get("case_id", "")),
                    text=str(payload["text"]),
                    strategy=str(payload["strategy"]),
                    expected=str(payload["expected"]),
                    actual=str(payload["actual"]),
                    severity=str(payload["severity"]),
                    created_at=str(payload["created_at"]),
                    target_category=str(payload.get("target_category", "")),
                    evidence=dict(payload.get("evidence", {})),
                )
            )
        return tuple(sorted(records, key=lambda item: item.failure_id))

    def texts(self) -> frozenset[str]:
        """Normalized texts already recorded, for duplicate suppression."""

        return frozenset(record.normalized_text for record in self.load())

    def existing_case_ids(self) -> frozenset[str]:
        return frozenset(record.case_id for record in self.load())

    def collect(
        self,
        results: Sequence[DetectionResult],
        *,
        created_at: str = DEFAULT_CREATED_AT,
        skip_recorded: bool = True,
    ) -> tuple[FailureRecord, ...]:
        """Turn every miss into a record, skipping ids and texts already held.

        Ids are assigned after the skips, so the repository stays gap-free and
        re-running discovery does not renumber what is already there.
        """

        known_ids = self.existing_case_ids() if skip_recorded else frozenset()
        known_texts = self.texts() if skip_recorded else frozenset()
        next_index = len(self.load()) + 1 if skip_recorded else 1

        records: list[FailureRecord] = []
        for result in results:
            if not result.miss:
                continue
            if result.case_id in known_ids:
                continue
            text = normalize_text(str(result.evidence.get("text", "")))
            if text and text in known_texts:
                continue
            record = record_from(result, index=next_index, created_at=created_at)
            records.append(record)
            next_index += 1
        return tuple(records)

    def write(
        self,
        records: Iterable[FailureRecord],
        *,
        prune: bool = False,
    ) -> tuple[Path, ...]:
        """Write records as one JSON file each."""

        self._root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for record in records:
            target = self.path_for(record)
            target.write_text(
                json.dumps(record.as_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            written.append(target)

        if prune:
            keep = {path.name for path in written}
            for path in sorted(self._root.glob("*.json")):
                if path.name not in keep:
                    path.unlink()
        return tuple(written)

    def counts(self) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for record in self.load():
            counts[record.strategy] = counts.get(record.strategy, 0) + 1
        return dict(sorted(counts.items()))


def regression_candidates(
    records: Sequence[FailureRecord],
) -> tuple[dict[str, Any], ...]:
    """Failures re-expressed as candidate cases for a future benchmark version.

    A candidate keeps the expectation that was missed, so adding it to a
    benchmark turns the failure into a permanent, measured requirement rather
    than a note in a report. These are *candidates*: a new benchmark version is
    a governance act, and this function only proposes the material.
    """

    candidates: list[dict[str, Any]] = []
    for record in records:
        candidates.append(
            {
                "id": record.failure_id,
                "origin_case_id": record.case_id,
                "text": record.text,
                "expected_categories": [record.target_category],
                "group": "risk",
                "attack_strategy": record.strategy,
                "severity": record.severity,
                "discovered_by": "phase-8.1-adversarial-discovery",
                "expectation_basis": record.evidence.get("expectation_basis", ""),
                "status": "candidate",
            }
        )
    return tuple(candidates)


def write_candidates(
    path: str | Path,
    records: Sequence[FailureRecord],
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "created_at": DEFAULT_CREATED_AT,
        "count": len(records),
        "candidates": list(regression_candidates(records)),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    """One end-to-end pass of the Phase 8.1 loop."""

    cases: tuple[Any, ...]
    results: tuple[DetectionResult, ...]
    failures: tuple[FailureRecord, ...]
    counts: Mapping[str, Any] = field(default_factory=dict)

    @property
    def candidates(self) -> tuple[dict[str, Any], ...]:
        return regression_candidates(self.failures)

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": dict(self.counts),
            "failures": [record.as_dict() for record in self.failures],
            "candidates": [dict(item) for item in self.candidates],
        }


def run_discovery(
    *,
    cases: Sequence[Any] | None = None,
    evaluator: Any | None = None,
    repository: FailureRepository | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    write: bool = False,
) -> DiscoveryRun:
    """Generate, evaluate, collect the misses, and optionally persist them.

    `write=False` is the default so that running discovery while exploring does
    not mutate the committed repository. Callers that mean to record pass
    `write=True` explicitly.
    """

    from .evaluator_bridge import evaluate_cases, summarise
    from .generator import default_cases

    active_cases = tuple(cases) if cases is not None else default_cases()
    active_repository = repository if repository is not None else FailureRepository()

    results = evaluate_cases(active_cases, evaluator)
    failures = active_repository.collect(
        results, created_at=created_at, skip_recorded=False
    )
    if write:
        active_repository.write(failures)

    return DiscoveryRun(
        cases=active_cases,
        results=results,
        failures=failures,
        counts=summarise(results),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run discovery from the command line.

    Without `--write` this only reports, so an exploratory run cannot mutate the
    committed repository by accident.
    """

    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    write = "--write" in args
    run = run_discovery(write=write)

    counts = run.counts
    print(
        f"cases={counts['cases']} attacks={counts['attacks']} "
        f"controls={counts['controls']}"
    )
    print(
        f"hits={counts['hits']} misses={counts['misses']} "
        f"false_positives={counts['false_positives']} "
        f"(debatable expectations: {counts['misses_debatable_expectation']})"
    )
    for name, bucket in counts["by_strategy"].items():
        print(
            f"  {name:26} cases={bucket['cases']:3} hits={bucket['hits']:3} "
            f"misses={bucket['misses']:3} fp={bucket['false_positives']:3}"
        )

    if not write:
        print("(report only; pass --write to persist failures and candidates)")
        return 0

    repository = FailureRepository()
    written = repository.write(run.failures, prune=True)
    target = write_candidates(CANDIDATES_PATH, run.failures)
    print(f"wrote {len(written)} failure records to {repository.root}")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
