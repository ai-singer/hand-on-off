"""The pipeline: Failure Generator, Evaluator, Analyzer, Candidates, Queue, Dataset.

The six stages the mandate names, wired in order, with the human in the middle:

    Failure Generator  ->  Risk Evaluator  ->  Failure Analyzer
           |                                            |
           v                                            v
    generated_cases/                        Coverage Expansion Candidate
                                                            |
                                                            v
                                                  Human Review Queue
                                                            |
                                                            v
                                                   Regression Dataset

The arrows are one-way. Nothing downstream of the human review queue is written by
this module: `regression_candidates.json` is a proposal list with
`approval_status: pending`, not a dataset, and no registered benchmark gains a case
from any run of this code.

What a run produces
-------------------

`failure_analysis_r1.json` — every failure of the frozen evaluator over the Phase 8.9
set, classified, explained and quoted.

`coverage_candidates/{pending,rejected}/` — one candidate per missing thing, not per
failing case. `accepted/` is never written.

`generated_cases/generated_cases_r1.json` — the structured expansion set, with what
the evaluator currently does to each case.

`regression_candidates.json` — the proposals a human may turn into the next
benchmark's cases.

`coverage_freeze_r1.json` — the three digests that make the run reproducible.

The pipeline is safe to re-run. Every artifact is rewritten from the benchmark and the
tables, byte-identically for identical inputs, and the freeze records the source
digests it was produced from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import analyzer, freeze, generator, lexicon, registry, reporter, synonyms, taxonomy
from .model import (
    ACCEPTED,
    PENDING,
    GeneratedCase,
    RegressionCandidate,
    FailureAnalysis,
    write_json,
)

PACKAGE_DIR = Path(__file__).parent
ANALYSIS_ARTIFACT = PACKAGE_DIR / "failure_analysis_r1.json"
GENERATED_ARTIFACT = PACKAGE_DIR / "generated_cases" / "generated_cases_r1.json"
REGRESSION_ARTIFACT = PACKAGE_DIR / "regression_candidates.json"
FREEZE_ARTIFACT = PACKAGE_DIR / "coverage_freeze_r1.json"

#: Artifacts a run must be able to reload and validate.
ARTIFACTS: tuple[str, ...] = (
    "failure_analysis_r1.json",
    "generated_cases/generated_cases_r1.json",
    "regression_candidates.json",
    "coverage_freeze_r1.json",
)


class PipelineError(Exception):
    """Raised when a run cannot complete or an artifact does not validate."""


@dataclass(frozen=True, slots=True)
class Run:
    """One complete run, in memory."""

    analysis: FailureAnalysis
    candidates: tuple[Any, ...]
    rejected: tuple[tuple[Any, str], ...]
    cases: tuple[GeneratedCase, ...]
    regression: tuple[RegressionCandidate, ...]
    registry: registry.RegistryReport
    artifacts: Mapping[str, Path]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "cases": self.analysis.cases,
            "failures": len(self.analysis.failures),
            "candidates": len(self.candidates),
            "rejected": len(self.rejected),
            "generated": len(self.cases),
            "regression": len(self.regression),
        }

    def describe(self) -> dict[str, object]:
        return {
            "counts": self.counts,
            "by_type": dict(self.analysis.types()),
            "artifacts": {
                name: str(path.relative_to(PACKAGE_DIR)).replace("\\", "/")
                for name, path in self.artifacts.items()
            },
        }


def _axis_in(proposal: str) -> str | None:
    """The declared axis a proposal names, if any.

    Matched against the declared axis names rather than parsed out of the sentence, so
    a rewording of the proposal text cannot silently stop the link being made.
    """

    for axis in synonyms.AXES:
        if axis.name in proposal:
            return axis.name
    return None


def regression_candidates(
    candidates: Sequence[Any], cases: Sequence[GeneratedCase]
) -> tuple[RegressionCandidate, ...]:
    """Proposals for the next benchmark, each traceable to the failure it answers.

    `approval_status` is `pending` on every one of them, and `expected_behavior` is
    written in the form a scorer can check rather than as prose.

    The exemplar text is drawn only from a generated case that exercises the same axis
    as the proposal. An earlier version attached the first generated case for the
    category, which paired a structural candidate with an unrelated sentence and made
    the artifact read as though that sentence were the thing being proposed.
    """

    by_axis: dict[str, GeneratedCase] = {}
    for case in cases:
        axis_name = _axis_in(case.generation_rule)
        if axis_name:
            by_axis.setdefault(axis_name, case)

    out: list[RegressionCandidate] = []
    for index, candidate in enumerate(candidates, start=1):
        axis_name = _axis_in(candidate.proposal)
        exemplar = by_axis.get(axis_name) if axis_name else None
        category = candidate.risk_category or ""
        if exemplar is not None:
            current = (
                f"not applied: {exemplar.case_id} ({exemplar.text!r}) currently "
                "produces no finding, and this candidate has not been scored against "
                "any benchmark"
            )
        else:
            current = (
                "not applied: this candidate proposes a structural change with no "
                "single exemplar sentence, and it has not been scored against any "
                "benchmark"
            )
        out.append(
            RegressionCandidate(
                case_id=f"REG-R1-{index:04d}",
                original_failure=candidate.source_case,
                proposed_change=candidate.proposal,
                expected_behavior=(
                    f"a text of the {category or 'named'} form should produce a finding "
                    f"naming {category or 'the category'} once the proposal is applied; "
                    "the evaluator must also keep every currently-passing case passing"
                ),
                approval_status=PENDING,
                failure_type=candidate.failure_type,
                candidate_id=candidate.candidate_id,
                text=exemplar.text if exemplar is not None else "",
                expected_categories=(category,) if category else (),
                current_behavior=current,
            )
        )
    return tuple(out)


def validate_artifacts(directory: str | Path | None = None) -> dict[str, object]:
    """Reload every artifact and check the fields a consumer depends on."""

    root = Path(directory) if directory is not None else PACKAGE_DIR
    results: list[dict[str, object]] = []
    ok = True
    for name in ARTIFACTS:
        path = root / name
        entry: dict[str, object] = {"artifact": name, "exists": path.is_file()}
        if not path.is_file():
            entry["ok"] = False
            ok = False
            results.append(entry)
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            entry.update({"ok": False, "error": f"invalid JSON: {exc}"})
            ok = False
            results.append(entry)
            continue
        entry["ok"] = True
        entry["top_level_keys"] = sorted(body)[:12]
        if name.startswith("failure_analysis"):
            entry["failures"] = len(body.get("failures", []))
            missing = [
                item.get("case_id", "?")
                for item in body.get("failures", [])
                if not item.get("evidence")
            ]
            if missing:
                ok = False
                entry["failures_without_evidence"] = missing[:10]
        if name.startswith("generated"):
            entry["cases"] = body.get("count", 0)
            leaked = [
                item.get("case_id", "?")
                for item in body.get("cases", [])
                if item.get("excludes_from_benchmark") is not True
            ]
            if leaked:
                ok = False
                entry["cases_not_excluded_from_benchmark"] = leaked[:10]
        if name.startswith("regression"):
            entry["candidates"] = len(body.get("candidates", []))
            wrong = [
                item.get("case_id", "?")
                for item in body.get("candidates", [])
                if item.get("approval_status") != PENDING
            ]
            if wrong:
                ok = False
                entry["candidates_not_pending"] = wrong[:10]
        if name.startswith("coverage_freeze"):
            for key in ("source_hash", "benchmark_hash", "evaluator_hash", "timestamp"):
                entry[key] = bool(body.get(key))
                if not body.get(key):
                    ok = False
        results.append(entry)
    return {"ok": ok, "artifacts": results}


def run(
    *,
    directory: str | Path | None = None,
    output_dir: str | Path | None = None,
    write_artifacts: bool = True,
    write_reports: bool = True,
    freeze_run: bool = True,
) -> Run:
    """Run all six stages. Read-only with respect to every frozen artifact."""

    analysis = analyzer.analyze(directory=directory)
    cases = generator.generate()
    candidates = registry.build(analysis, cases)
    pending, rejected = registry.partition(candidates)
    regression = regression_candidates(pending, cases)

    root = Path(output_dir) if output_dir is not None else PACKAGE_DIR
    artifacts: dict[str, Path] = {}
    if write_artifacts:
        analysis_path = root / "failure_analysis_r1.json"
        write_json(analysis_path, analyzer.payload(analysis))
        artifacts["failure_analysis_r1.json"] = analysis_path

        generated_path = generator.write(
            root / "generated_cases" / "generated_cases_r1.json", cases
        )
        artifacts["generated_cases/generated_cases_r1.json"] = generated_path

        report = registry.write(analysis, cases, registry_dir=root / "coverage_candidates")
        artifacts["coverage_candidates"] = root / "coverage_candidates"

        regression_body = {
            "phase": "R1",
            "artifact": "regression-candidates",
            "source_hash": freeze.source_digest(),
            "benchmark_hash": freeze.benchmark_digest(),
            "evaluator_hash": freeze.evaluator_digest(),
            "count": len(regression),
            "approval_policy": (
                "every candidate is pending; approval is a human decision recorded "
                "with ReviewDecision, and no candidate is applied by this framework"
            ),
            "candidates": [item.as_dict() for item in regression],
        }
        regression_path = root / "regression_candidates.json"
        write_json(regression_path, regression_body)
        artifacts["regression_candidates.json"] = regression_path
    else:
        report = registry.RegistryReport(pending=pending, rejected=rejected, accepted=())

    if freeze_run:
        body = freeze.write(root / "coverage_freeze_r1.json" if root != PACKAGE_DIR else None)
        artifacts["coverage_freeze_r1.json"] = (
            root / "coverage_freeze_r1.json"
            if root != PACKAGE_DIR
            else FREEZE_ARTIFACT
        )
        _ = body

    if write_reports:
        report_paths = reporter.write(
            analysis,
            analyzer.metrics(),
            report.as_dict(),
            generator.payload(cases),
            analyzer.summary(analysis),
            docs_dir=(root / "docs") if output_dir is not None else None,
        )
        artifacts.update(report_paths)

    return Run(
        analysis=analysis,
        candidates=pending,
        rejected=rejected,
        cases=cases,
        regression=regression,
        registry=report,
        artifacts=artifacts,
    )


def describe() -> dict[str, object]:
    """The framework's own description, for the report and the tests."""

    return {
        "stages": [
            "failure-generator",
            "risk-evaluator",
            "failure-analyzer",
            "coverage-expansion-candidate",
            "human-review-queue",
            "regression-dataset",
        ],
        "failure_types": list(taxonomy.FAILURE_TYPES),
        "auto_generatable": list(taxonomy.AUTO_GENERATABLE),
        "human_required": list(taxonomy.HUMAN_REQUIRED),
        "generator": generator.describe(),
        "lexicon": lexicon.describe(),
        "tables": synonyms.validate().describe(),
        "registry": registry.describe(),
        "artifacts": list(ARTIFACTS),
        "guarantees": {
            "modifies_evaluator": False,
            "modifies_benchmark_labels": False,
            "modifies_decision_policy": False,
            "writes_to_accepted": False,
            "uses_network": False,
            "uses_llm": False,
            "reaches_production": False,
        },
    }
