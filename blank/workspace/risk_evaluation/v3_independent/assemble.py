"""Assemble the Phase 8.9 benchmark from the run artifacts.

    python -m risk_evaluation.v3_independent.assemble

Reads the generation, annotation and adjudication files under
`risk_evaluation/v3_independent/run/`, proves each stage covered what it claimed,
and writes `risk_evaluation/benchmarks/risk/independent/v1/`. Every stage validates
before the next one runs, so a short batch or an unknown label surfaces here rather
than as a mysterious metric later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adjudication import (
    adjudicate,
    assemble_rulings,
    write_adjudicated,
    write_rulings,
)
from .agreement import measure, write_report
from .build import assemble_annotations, validate_generated
from .dataset import (
    BENCHMARK_DIR,
    build_records,
    dataset_digest,
    describe,
    load_records,
    write_dataset,
)
from .freeze import guard


def assemble(*, root: str | Path | None = None, write: bool = True) -> dict[str, Any]:
    """Run the whole pipeline from the four frozen run artifacts."""

    guard()

    cases = validate_generated(root=root)
    labels = assemble_annotations(cases, root=root)
    agreement = measure(
        labels, groups={item.case_id: item.group for item in cases}
    )
    rulings = assemble_rulings(root=root)
    adjudicated = adjudicate(labels, rulings)
    records = build_records(cases, adjudicated)

    if write:
        write_report(report=agreement)
        write_rulings(rulings=rulings)
        write_adjudicated(cases=adjudicated)
        write_dataset(
            records,
            adjudicated=adjudicated,
            rulings=rulings,
            agreement=agreement,
            labels=labels,
        )

    return {
        "cases": len(cases),
        "labels": {name: len(items) for name, items in sorted(labels.items())},
        "disagreements": len(agreement.disagreements),
        "affected_cases": len(agreement.affected_cases),
        "rulings": len(rulings),
        "unresolved_rulings": sum(1 for item in rulings if not item.resolved),
        "resolved_cases": sum(1 for item in adjudicated if item.resolved),
        "unresolved_cases": sum(1 for item in adjudicated if not item.resolved),
        "records": len(records),
        "dataset_hash": dataset_digest() if write else "",
        "benchmark_dir": str(BENCHMARK_DIR),
        "agreement": {
            item.field: item.kappa for item in agreement.fields
        },
        "agreement_categories": {
            item.field: item.kappa for item in agreement.categories
        },
        "exact_decision_agreement": agreement.exact_decision_agreement,
    }


def main() -> int:
    import sys

    result = assemble(write="--write" in sys.argv or True)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    if "--verify" in sys.argv:
        records = load_records()
        print()
        print(json.dumps({"verified_records": len(records), **describe()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
