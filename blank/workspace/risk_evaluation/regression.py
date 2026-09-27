"""Regression runner for versioned benchmarks.

Answers the governance question a one-off benchmark cannot: *did this change
make the evaluator better or worse, on a published dataset, against a recorded
score?*

The baseline is stored next to the benchmark version (`baseline.json`) and
holds the metric snapshot plus per-case correctness at the time it was
recorded. A regression report then shows the previous score, the current score,
the delta, and every case whose outcome changed — so a drop is attributable to
specific cases rather than to a number.

No baseline file exists until one is written deliberately:
`python -m risk_evaluation.regression --write-baseline`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .benchmark_registry import BenchmarkRecord, BenchmarkRegistry
from .evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from .semantic_evaluator import SemanticRiskEvaluator
from .validation import run_validation


BASELINE_NAME = "baseline.json"

#: The metric a regression is judged on.
PRIMARY_METRIC = "macro_f1"

#: A drop smaller than this is treated as unchanged. The metrics are rounded to
#: four decimals, so exact comparison is safe; the tolerance exists to make the
#: intent explicit rather than to absorb noise.
REGRESSION_TOLERANCE = 0.0

IMPROVED = "IMPROVED"
UNCHANGED = "UNCHANGED"
REGRESSED = "REGRESSED"

EVALUATORS: Mapping[str, type[RiskIntentEvaluator]] = {
    "keyword": KeywordRiskEvaluator,
    "semantic": SemanticRiskEvaluator,
}


class RegressionError(Exception):
    """Raised when a regression cannot be evaluated."""


@dataclass(frozen=True, slots=True)
class ChangedCase:
    case_id: str
    previous: bool
    current: bool

    def as_dict(self) -> dict[str, Any]:
        direction = "fixed" if self.current else "broken"
        return {
            "case_id": self.case_id,
            "previous": self.previous,
            "current": self.current,
            "direction": direction,
        }


@dataclass(frozen=True, slots=True)
class RegressionReport:
    benchmark_id: str
    version: str
    evaluator: str
    metric: str
    previous_score: float
    current_score: float
    changed_cases: tuple[ChangedCase, ...]
    current_metrics: Mapping[str, float]

    @property
    def delta(self) -> float:
        return round(self.current_score - self.previous_score, 4)

    @property
    def status(self) -> str:
        if self.delta > REGRESSION_TOLERANCE:
            return IMPROVED
        if self.delta < -REGRESSION_TOLERANCE:
            return REGRESSED
        return UNCHANGED

    @property
    def regressed(self) -> bool:
        return self.status == REGRESSED

    @property
    def fixed_cases(self) -> tuple[str, ...]:
        return tuple(item.case_id for item in self.changed_cases if item.current)

    @property
    def broken_cases(self) -> tuple[str, ...]:
        return tuple(item.case_id for item in self.changed_cases if not item.current)

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "version": self.version,
            "evaluator": self.evaluator,
            "metric": self.metric,
            "previous_score": self.previous_score,
            "current_score": self.current_score,
            "delta": self.delta,
            "status": self.status,
            "changed_cases": [item.as_dict() for item in self.changed_cases],
            "current_metrics": dict(self.current_metrics),
        }

    def render(self) -> str:
        lines = [
            f"{self.benchmark_id}/{self.version} [{self.evaluator}]",
            f"  metric   : {self.metric}",
            f"  previous : {self.previous_score:.4f}",
            f"  current  : {self.current_score:.4f}",
            f"  delta    : {self.delta:+.4f}",
            f"  status   : {self.status}",
        ]
        if self.changed_cases:
            lines.append(
                f"  changed  : {len(self.changed_cases)} "
                f"(fixed {len(self.fixed_cases)}, broken {len(self.broken_cases)})"
            )
        return "\n".join(lines)


def baseline_path(record: BenchmarkRecord, registry: BenchmarkRegistry) -> Path:
    return registry.directory(record) / BASELINE_NAME


def snapshot(
    record: BenchmarkRecord,
    registry: BenchmarkRegistry,
    evaluator: RiskIntentEvaluator,
) -> dict[str, Any]:
    """Metric snapshot plus per-case correctness for one evaluator."""

    cases = registry.load_cases(record)
    report = run_validation(
        cases,
        keyword=evaluator if evaluator.name.startswith("keyword") else KeywordRiskEvaluator(),
        semantic=(
            evaluator
            if not evaluator.name.startswith("keyword")
            else SemanticRiskEvaluator()
        ),
    )
    side = "keyword" if evaluator.name.startswith("keyword") else "semantic"
    metrics = report.metrics[side]
    correctness = {
        row["id"]: bool(row[f"{side}_correct"]) for row in report.case_table()
    }
    return {
        "benchmark_id": record.benchmark_id,
        "version": record.version,
        "evaluator": evaluator.name,
        "dataset_hash": record.dataset_hash,
        "metrics": metrics.as_dict(),
        "case_results": correctness,
    }


def write_baseline(
    registry: BenchmarkRegistry | None = None,
    *,
    evaluators: Mapping[str, type[RiskIntentEvaluator]] | None = None,
    versions: Iterable[str] | None = None,
) -> tuple[Path, ...]:
    """Record the current scores as the baseline for each benchmark version.

    `versions` restricts the write to a named subset, so adding a benchmark
    version does not require rewriting every recorded baseline.
    """

    active = registry if registry is not None else BenchmarkRegistry()
    factories = evaluators if evaluators is not None else EVALUATORS
    wanted = None if versions is None else set(versions)
    written: list[Path] = []
    for record in active.list_benchmarks():
        if wanted is not None and record.version not in wanted:
            continue
        payload = {
            "evaluators": {
                name: snapshot(record, active, factory())
                for name, factory in factories.items()
            }
        }
        target = baseline_path(record, active)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        written.append(target)
    return tuple(written)


def load_baseline(record: BenchmarkRecord, registry: BenchmarkRegistry) -> dict[str, Any]:
    target = baseline_path(record, registry)
    if not target.is_file():
        raise RegressionError(
            f"no baseline recorded for {record.benchmark_id}/{record.version}; "
            "run with --write-baseline first"
        )
    return json.loads(target.read_text(encoding="utf-8"))


def run_regression(
    record: BenchmarkRecord,
    evaluator: RiskIntentEvaluator,
    *,
    registry: BenchmarkRegistry | None = None,
    side: str | None = None,
    metric: str = PRIMARY_METRIC,
    baseline: Mapping[str, Any] | None = None,
) -> RegressionReport:
    """Compare an evaluator's current score against its recorded baseline."""

    active = registry if registry is not None else BenchmarkRegistry()
    stored = baseline if baseline is not None else load_baseline(record, active)
    key = side or ("keyword" if evaluator.name.startswith("keyword") else "semantic")
    try:
        previous = stored["evaluators"][key]
    except KeyError as exc:
        raise RegressionError(
            f"baseline has no entry for evaluator {key!r}"
        ) from exc

    if previous["dataset_hash"] != record.dataset_hash:
        raise RegressionError(
            "baseline was recorded against a different dataset hash; "
            "the benchmark changed and the baseline must be re-recorded"
        )

    current = snapshot(record, active, evaluator)
    previous_cases = previous["case_results"]
    changed = tuple(
        ChangedCase(
            case_id=case_id,
            previous=bool(previous_cases[case_id]),
            current=bool(current["case_results"][case_id]),
        )
        for case_id in current["case_results"]
        if bool(previous_cases.get(case_id)) != bool(current["case_results"][case_id])
    )

    return RegressionReport(
        benchmark_id=record.benchmark_id,
        version=record.version,
        evaluator=evaluator.name,
        metric=metric,
        previous_score=float(previous["metrics"][metric]),
        current_score=float(current["metrics"][metric]),
        changed_cases=changed,
        current_metrics={
            name: float(value)
            for name, value in current["metrics"].items()
            if isinstance(value, (int, float))
        },
    )


def run_all(
    registry: BenchmarkRegistry | None = None,
    *,
    evaluators: Mapping[str, type[RiskIntentEvaluator]] | None = None,
) -> tuple[RegressionReport, ...]:
    active = registry if registry is not None else BenchmarkRegistry()
    factories = evaluators if evaluators is not None else EVALUATORS
    reports: list[RegressionReport] = []
    for record in active.list_benchmarks():
        for name, factory in factories.items():
            reports.append(
                run_regression(record, factory(), registry=active, side=name)
            )
    return tuple(reports)


def main() -> int:
    import sys

    registry = BenchmarkRegistry()
    if "--write-baseline" in sys.argv:
        for path in write_baseline(registry):
            print(f"wrote {path.name} in {path.parent.name}")
        return 0

    reports = run_all(registry)
    exit_code = 0
    for report in reports:
        print(report.render())
        print()
        if report.regressed:
            exit_code = 1
    print(
        "regressions:",
        [f"{r.benchmark_id}/{r.version}:{r.evaluator}" for r in reports if r.regressed]
        or "none",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
