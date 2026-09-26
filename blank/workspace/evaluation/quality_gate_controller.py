"""Control whether downstream generation may run after quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


class GateDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    decision: GateDecision
    quality_report: dict[str, Any]

    @property
    def can_continue(self) -> bool:
        return self.decision is GateDecision.PASS


@dataclass(frozen=True, slots=True)
class GenerationExecution:
    output: Any | None
    invoked: bool


class GenerationTarget(Protocol):
    def generate(self, request: Any) -> Any:
        ...


class QualityGateController:
    """Turn an evaluation report into an enforced generation decision."""

    def decide(self, quality_report: Mapping[str, Any]) -> QualityGateResult:
        report = dict(quality_report)
        passed = bool(report.get("passed")) and report.get("status") == "pass"
        decision = GateDecision.PASS if passed else GateDecision.FAIL
        report["gate_decision"] = decision.value
        return QualityGateResult(decision=decision, quality_report=report)

    def execute_generation(
        self,
        gate_result: QualityGateResult,
        generation_target: GenerationTarget | None,
        request: Any,
    ) -> GenerationExecution:
        """Invoke generation only when the gate passes."""

        if not gate_result.can_continue or generation_target is None:
            return GenerationExecution(output=None, invoked=False)
        return GenerationExecution(
            output=generation_target.generate(request),
            invoked=True,
        )
