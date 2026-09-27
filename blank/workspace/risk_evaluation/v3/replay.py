"""Historical failure replay: does v3 close the defects that were found?

Every case here was a recorded failure of an earlier phase, and each one is
re-scored under the unified pipeline with **both** results kept:

    before   semantic_evaluator_v2 on the whole text
    after    the v3 decision, with the full trace

Three groups, from the three phases whose findings this architecture exists to
address:

    phase 8.1   adversarial misses       the attribution_confusion and
                                         guarantee findings from the repository
    phase 8.3   attribution failures     the replay set that phase measured
    phase 8.4   guarantee blind spots    the positives the old rule could not see

The cases are read from the artifacts the earlier phases published, so the
replay cannot quietly use easier material than was originally recorded. Where a
case's text is taken from a published failure record, the record's own
`expected` field supplies the expectation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..adversarial.failure_repository import FailureRepository
from ..attribution_experiment.cases import REPLAY_CASES
from ..intent_patterns.evaluation import BENCHMARK_CASES as PATTERN_CASES
from ..intent_patterns.evaluation import POSITIVE as PATTERN_POSITIVE
from .model import RiskDecision
from .pipeline import RiskEvaluationPipeline


REPORT_PATH = Path(__file__).resolve().parent / "replay_report.json"

#: Alias for callers that prefer an explicit name.
REPLAY_PATH = REPORT_PATH

PHASE_81 = "phase-8.1"
PHASE_83 = "phase-8.3"
PHASE_84 = "phase-8.4"
PHASES = (PHASE_81, PHASE_83, PHASE_84)

#: The phase briefs require at least five cases per group.
REQUIRED_PER_PHASE = 5


@dataclass(frozen=True, slots=True)
class ReplayCase:
    case_id: str
    phase: str
    text: str
    expected: tuple[str, ...]
    origin: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "phase": self.phase,
            "text": self.text,
            "expected": list(self.expected),
            "origin": self.origin,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    """One historical failure, before and after."""

    case: ReplayCase
    before: tuple[str, ...]
    after: tuple[str, ...]
    actions: Mapping[str, str]
    trace: tuple[dict[str, Any], ...]
    decisions: tuple[RiskDecision, ...]

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def expected(self) -> tuple[str, ...]:
        return self.case.expected

    @property
    def before_correct(self) -> bool:
        return self.before == self.expected

    @property
    def after_correct(self) -> bool:
        return self.after == self.expected

    @property
    def transition(self) -> str:
        if self.before_correct and self.after_correct:
            return "unchanged"
        if not self.before_correct and self.after_correct:
            return "fixed"
        if self.before_correct and not self.after_correct:
            return "broken"
        # Neither right: the defect is still open, and calling that "different"
        # would blur it with a case that merely changed category.
        return "still_wrong"

    @property
    def evidence_complete(self) -> bool:
        return bool(self.trace) and all(item["evidence"] for item in self.trace)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.as_dict(),
            "before": list(self.before),
            "after": list(self.after),
            "actions": dict(sorted(self.actions.items())),
            "before_correct": self.before_correct,
            "after_correct": self.after_correct,
            "transition": self.transition,
            "evidence_complete": self.evidence_complete,
            "decisions": [item.as_dict() for item in self.decisions],
            "trace": [dict(item) for item in self.trace],
        }

    def render(self) -> str:
        lines = [
            f"{self.case_id} [{self.case.phase}] {self.transition}",
            f"    {self.case.text}",
            f"    before : {list(self.before)}",
            f"    after  : {list(self.after)}  expected {list(self.expected)}",
        ]
        for item in self.trace:
            lines.append(
                f"      {item['claim_id']} {item['speaker']}/{item['stance']} "
                f"intent={item['intent']} evidence={item['evidence']}"
            )
        return "\n".join(lines)


def _from_failures() -> tuple[ReplayCase, ...]:
    """Phase 8.1's recorded misses, read from the committed repository."""

    wanted = {
        "direct_statement",
        "attribution_confusion",
        "context_attack",
        "paraphrase",
    }
    cases: list[ReplayCase] = []
    for record in FailureRepository().load():
        if record.strategy not in wanted:
            continue
        cases.append(
            ReplayCase(
                case_id=record.failure_id,
                phase=PHASE_81,
                text=record.text,
                expected=(record.target_category,),
                origin=f"adversarial failures/{record.failure_id}.json",
                note=f"{record.strategy}: {record.evidence.get('expectation_basis', '')}",
            )
        )
    return tuple(cases)


def _from_attribution() -> tuple[ReplayCase, ...]:
    """Phase 8.3's attribution failures, from that phase's own replay set."""

    cases: list[ReplayCase] = []
    for case in REPLAY_CASES:
        if case.origin != "phase-8.1":
            continue
        cases.append(
            ReplayCase(
                case_id=f"83-{case.case_id}",
                phase=PHASE_83,
                text=case.text,
                expected=case.expected_categories,
                origin=f"attribution_experiment replay {case.case_id}",
                note=case.note,
            )
        )
    return tuple(cases)


def _from_guarantee() -> tuple[ReplayCase, ...]:
    """Phase 8.4's guarantee blind spots: positives the old rule missed."""

    cases: list[ReplayCase] = []
    for case in PATTERN_CASES:
        if case.group != PATTERN_POSITIVE:
            continue
        cases.append(
            ReplayCase(
                case_id=f"84-{case.case_id}",
                phase=PHASE_84,
                text=case.text,
                expected=("financial_guarantee",),
                origin=f"intent_pattern/v1 {case.case_id}",
                note=case.note,
            )
        )
    return tuple(cases)


def replay_cases() -> Mapping[str, tuple[ReplayCase, ...]]:
    """All three groups, keyed by phase."""

    return {
        PHASE_81: _from_failures(),
        PHASE_83: _from_attribution(),
        PHASE_84: _from_guarantee(),
    }


@dataclass(frozen=True, slots=True)
class ReplayReport:
    outcomes: tuple[ReplayOutcome, ...]

    @property
    def cases(self) -> int:
        return len(self.outcomes)

    def by_phase(self, phase: str) -> tuple[ReplayOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.phase == phase)

    def group_summary(self) -> Mapping[str, Mapping[str, Any]]:
        summary: dict[str, dict[str, Any]] = {}
        for phase in PHASES:
            items = self.by_phase(phase)
            summary[phase] = {
                "cases": len(items),
                "required": REQUIRED_PER_PHASE,
                "meets_minimum": len(items) >= REQUIRED_PER_PHASE,
                "before_correct": sum(1 for item in items if item.before_correct),
                "after_correct": sum(1 for item in items if item.after_correct),
                "fixed": [item.case_id for item in items if item.transition == "fixed"],
                "broken": [item.case_id for item in items if item.transition == "broken"],
                "still_wrong": [
                    item.case_id for item in items if item.transition == "still_wrong"
                ],
                "evidence_complete": sum(
                    1 for item in items if item.evidence_complete
                ),
            }
        return summary

    @property
    def fixed(self) -> tuple[ReplayOutcome, ...]:
        return tuple(item for item in self.outcomes if item.transition == "fixed")

    @property
    def broken(self) -> tuple[ReplayOutcome, ...]:
        return tuple(item for item in self.outcomes if item.transition == "broken")

    @property
    def evidence_complete(self) -> int:
        return sum(1 for item in self.outcomes if item.evidence_complete)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "by_phase": {k: dict(v) for k, v in self.group_summary().items()},
            "fixed_count": len(self.fixed),
            "broken_count": len(self.broken),
            "evidence_complete": self.evidence_complete,
            "outcomes": [item.as_dict() for item in self.outcomes],
        }

    def render(self) -> str:
        lines = [f"replay cases : {self.cases}", ""]
        for phase, summary in self.group_summary().items():
            mark = "ok" if summary["meets_minimum"] else "SHORT"
            lines.append(
                f"{phase}: {summary['cases']} cases ({mark}, min {summary['required']}) "
                f"before {summary['before_correct']} -> after {summary['after_correct']}"
            )
            lines.append(f"    fixed   : {summary['fixed']}")
            lines.append(f"    broken  : {summary['broken']}")
            lines.append(f"    still_wrong: {summary['still_wrong']}")
        lines.append("")
        lines.append(f"evidence complete: {self.evidence_complete}/{self.cases}")
        return "\n".join(lines)


def replay(
    cases: Sequence[ReplayCase] | None = None,
    *,
    pipeline: RiskEvaluationPipeline | None = None,
) -> ReplayReport:
    active = (
        tuple(cases)
        if cases is not None
        else tuple(case for group in replay_cases().values() for case in group)
    )
    active_pipeline = pipeline if pipeline is not None else RiskEvaluationPipeline()

    outcomes: list[ReplayOutcome] = []
    for case in active:
        result = active_pipeline.evaluate(case.text)
        outcomes.append(
            ReplayOutcome(
                case=case,
                before=result.baseline,
                after=result.categories,
                actions=result.actions,
                trace=result.trace_dicts(),
                decisions=result.final_decision,
            )
        )
    return ReplayReport(outcomes=tuple(outcomes))


def write_report(
    path: str | Path | None = None,
    report: ReplayReport | None = None,
) -> Path:
    target = Path(path) if path is not None else REPORT_PATH
    active = report if report is not None else replay()
    payload = {
        **active.as_dict(),
        "note": (
            "Cases are read from the artifacts the earlier phases published: "
            "the committed failure repository, Phase 8.3's replay set and "
            "Phase 8.4's benchmark. The replay cannot substitute easier "
            "material than was originally recorded."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    report = replay()
    print(report.render())
    print()
    for phase in PHASES:
        for item in report.by_phase(phase):
            print(item.render())
            print()
    if "--write" in sys.argv:
        print(f"wrote {write_report(report=report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
