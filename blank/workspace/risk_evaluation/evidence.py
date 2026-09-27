"""Evidence requirements for risk categories.

A risk judgement is not only "does this text look risky" but "does the claim
carry the evidence its category requires". This module declares which evidence
each category needs and reports how much of it the artifact can actually
demonstrate.

The important honesty rule: only a requirement the artifact can prove is
reported as satisfied or unsatisfied. Anything the current artifact cannot
express is reported as **unknown**, which is not the same as absent. Silently
treating unknown as unsatisfied would overstate what the framework checks;
treating it as satisfied would overstate what the content proves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .taxonomy import category as taxonomy_category


#: Human description of each evidence identifier used by the taxonomy.
EVIDENCE_DESCRIPTIONS: Mapping[str, str] = {
    "source": "a named, checkable origin for the claim",
    "verification": "independent confirmation that the claim holds",
    "data": "the figures the claim rests on, with units and period",
    "time_range": "the period the projection covers",
    "disclaimer": "an explicit statement that this is not investment advice",
    "evidence": "the reasoning and material behind the recommendation",
    "uncertainty": "an explicit statement of what could make the claim wrong",
    "basis": "the mechanism that would make the promised outcome possible",
    "counter_evidence": "the strongest case against the guarantee",
    "neutral_restatement": "the same fact stated without emotional framing",
}

#: Evidence the current artifact can demonstrate today. Everything else is
#: reported as unknown rather than guessed at.
_DERIVABLE_EVIDENCE = ("source",)


class EvidenceError(Exception):
    """Raised when evidence assessment input is malformed."""


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    evidence_id: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {"evidence_id": self.evidence_id, "description": self.description}


@dataclass(frozen=True, slots=True)
class EvidenceStatus:
    """Which requirements are met, unmet, or not expressible by the artifact."""

    category: str
    satisfied: tuple[str, ...]
    unsatisfied: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """True only when every requirement is demonstrably satisfied."""

        return not self.unsatisfied and not self.unknown

    @property
    def checkable(self) -> bool:
        """True when at least one requirement could be assessed at all."""

        return bool(self.satisfied or self.unsatisfied)

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "satisfied": list(self.satisfied),
            "unsatisfied": list(self.unsatisfied),
            "unknown": list(self.unknown),
            "complete": self.complete,
            "checkable": self.checkable,
        }

    def render(self) -> str:
        return (
            f"{self.category}: satisfied={list(self.satisfied)} "
            f"unsatisfied={list(self.unsatisfied)} unknown={list(self.unknown)}"
        )


def requirements_for(category_name: str) -> tuple[EvidenceRequirement, ...]:
    """Return the evidence the category requires, in declaration order."""

    entry = taxonomy_category(category_name)
    return tuple(
        EvidenceRequirement(
            evidence_id=evidence_id,
            description=EVIDENCE_DESCRIPTIONS.get(evidence_id, "unspecified"),
        )
        for evidence_id in entry.evidence_required
    )


def assess_evidence(
    category_name: str,
    *,
    source_ids: Sequence[str] = (),
    artifact: Mapping[str, Any] | None = None,
) -> EvidenceStatus:
    """Assess how much required evidence the material can demonstrate.

    ``source_ids`` are the sources the risk applies to. ``artifact`` is the
    artifact the judgement came from, if one exists; it is accepted so a future
    evaluator can derive more requirements without changing this interface.
    """

    requirements = requirements_for(category_name)
    satisfied: list[str] = []
    unsatisfied: list[str] = []
    unknown: list[str] = []

    for requirement in requirements:
        evidence_id = requirement.evidence_id
        if evidence_id not in _DERIVABLE_EVIDENCE:
            unknown.append(evidence_id)
            continue
        if evidence_id == "source":
            if source_ids:
                satisfied.append(evidence_id)
            else:
                unsatisfied.append(evidence_id)
            continue
        unknown.append(evidence_id)

    return EvidenceStatus(
        category=category_name,
        satisfied=tuple(satisfied),
        unsatisfied=tuple(unsatisfied),
        unknown=tuple(unknown),
    )


def derivable_evidence() -> tuple[str, ...]:
    """Evidence identifiers the current artifact can actually demonstrate."""

    return _DERIVABLE_EVIDENCE
