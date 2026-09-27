"""The v3 composition benchmark: cases, labels and metrics.

`benchmark/` is a package so the case table, the metrics and the artifact
writer stay separable.
"""

from __future__ import annotations

from typing import Any

from .cases import (
    AMBIGUOUS,
    AUTHOR_ENDORSED,
    AUTHOR_REJECTION,
    BENCHMARK_NAME,
    BENCHMARK_VERSION,
    BENCHMARK_CASES,
    GROUP_BASIS,
    GROUP_NAMES,
    NEUTRAL_EDUCATION,
    REQUIRED_GROUP_SIZES,
    THIRD_PARTY_QUOTED,
    BenchmarkCase,
    ClaimLabel,
    case_index,
    group_cases,
    group_sizes,
    label_source,
)
from .metrics import (
    REPORT_PATH,
    AttributionMetrics,
    DecisionMetrics,
    IntentMetrics,
    TraceMetrics,
    V3Metrics,
    evaluate_benchmark,
    metrics_payload,
    run_case,
    write_report,
)

__all__ = sorted(
    [
        "AMBIGUOUS",
        "AUTHOR_ENDORSED",
        "AUTHOR_REJECTION",
        "BENCHMARK_NAME",
        "BENCHMARK_VERSION",
        "BENCHMARK_CASES",
        "GROUP_BASIS",
        "GROUP_NAMES",
        "NEUTRAL_EDUCATION",
        "REPORT_PATH",
        "REQUIRED_GROUP_SIZES",
        "THIRD_PARTY_QUOTED",
        "AttributionMetrics",
        "BenchmarkCase",
        "ClaimLabel",
        "DecisionMetrics",
        "IntentMetrics",
        "TraceMetrics",
        "V3Metrics",
        "case_index",
        "evaluate_benchmark",
        "group_cases",
        "group_sizes",
        "label_source",
        "metrics_payload",
        "run_case",
        "write_report",
    ]
)
