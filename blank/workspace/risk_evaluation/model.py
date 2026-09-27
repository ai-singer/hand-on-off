"""Serializable risk evaluation results.

One result describes one risk judgement about one subject: which taxonomy
category was matched, what intent it represents, how confident the evaluator
is, what evidence the category requires, and what the framework's default
severity and action are.

Results are plain data so any evaluator — keyword, semantic or model backed —
can produce them and any consumer can persist them without depending on the
evaluator that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

#: Allowed severity values. Mirrors the artifact's risk constraint contract.
SEVERITIES = ("info", "warning", "block")

#: Allowed actions. Mirrors the artifact's risk constraint contract.
ACTIONS = ("downrank", "require_evidence", "require_review", "block")


class RiskEvaluationError(Exception):
    """Raised when risk evaluation input or output is malformed."""


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    """One risk judgement produced by a `RiskIntentEvaluator`.

    `category` is the primary taxonomy category. `candidates` lists every
    taxonomy category the evidence is consistent with: a keyword evaluator may
    be unable to separate, for example, a guaranteed return from ordinary
    investment advice, and saying so is more useful than picking one silently.
    A semantic evaluator would normally return a single candidate.
    """

    category: str
    intent: str
    confidence: float
    evidence_required: tuple[str, ...]
    severity: str
    action: str
    evaluator: str
    detail: str = ""
    source_ids: tuple[str, ...] = field(default=())
    candidates: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.category:
            raise RiskEvaluationError("category must be non-empty")
        if not self.intent:
            raise RiskEvaluationError("intent must be non-empty")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise RiskEvaluationError(
                f"confidence must be within [0, 1], got {self.confidence!r}"
            )
        if self.severity not in SEVERITIES:
            raise RiskEvaluationError(
                f"severity must be one of {SEVERITIES}, got {self.severity!r}"
            )
        if self.action not in ACTIONS:
            raise RiskEvaluationError(
                f"action must be one of {ACTIONS}, got {self.action!r}"
            )
        if not self.candidates:
            object.__setattr__(self, "candidates", (self.category,))

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "category": self.category,
            "intent": self.intent,
            "confidence": float(self.confidence),
            "evidence_required": list(self.evidence_required),
            "severity": self.severity,
            "action": self.action,
            "evaluator": self.evaluator,
            "detail": self.detail,
            "source_ids": list(self.source_ids),
            "candidates": list(self.candidates),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RiskEvaluationResult":
        """Rebuild a result from `as_dict()` output."""

        try:
            return cls(
                category=str(payload["category"]),
                intent=str(payload["intent"]),
                confidence=float(payload["confidence"]),
                evidence_required=tuple(payload.get("evidence_required", ())),
                severity=str(payload["severity"]),
                action=str(payload["action"]),
                evaluator=str(payload.get("evaluator", "unknown")),
                detail=str(payload.get("detail", "")),
                source_ids=tuple(payload.get("source_ids", ())),
                candidates=tuple(payload.get("candidates", ())),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RiskEvaluationError(f"malformed risk evaluation result: {exc}") from exc

    def to_risk_constraint(self) -> dict[str, Any]:
        """Project into the artifact's existing risk constraint shape.

        This is the designed connection point to the quality gate: the gate
        keeps consuming `risk_constraints` exactly as it does today, and this
        framework only changes how those constraints are produced.
        """

        return {
            "rule_id": f"{self.evaluator}:{self.category}",
            "category": self.category,
            "severity": self.severity,
            "action": self.action,
            "message": self.detail or self.intent,
            "source_ids": list(self.source_ids),
        }


def severity_effect(severity: str) -> str:
    """Describe how a severity affects the existing gate, without changing it."""

    return {
        "block": "quality gate returns review_required and generation is not invoked",
        "warning": "quality gate applies the rubric penalty; content may need review",
        "info": "recorded only; no gate effect",
    }.get(severity, "unknown severity")
