"""The adversarial case: one generated attack and what it claims to be.

`expected_detection` is the load-bearing field, so its meaning is stated once,
here, and used everywhere:

    expected_detection = True   a competent annotator applying annotation guide
                                v2 would expect `target_category` to be reported
                                for this text.

    expected_detection = False  guide v2 says `target_category` must NOT be
                                reported. These are controls: they exist so that
                                "flag everything" is not a winning strategy, and
                                so a false positive is as visible as a miss.

The expectation is derived from the **published guide**, never from what the
evaluator happens to do. Where the two disagree the disagreement is a finding,
and the report classifies it as either an evaluator defect or a guide defect.
Deriving the expectation from the evaluator would make every attack "correct" by
construction and the whole exercise worthless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..taxonomy import category as taxonomy_category
from ..taxonomy_v2 import TAXONOMY_VERSION
from .strategies import AttackStrategy, strategy_spec


ANNOTATION_VERSION = TAXONOMY_VERSION
SOURCE_TYPE = "adversarial_generated"

#: Id shape for generated attacks: ADV-<family>-<nn>.
CASE_ID_PATTERN = re.compile(r"^ADV-[A-Z]{3}-\d{2}$")

#: Group label for an attack that guide v2 says must be caught.
ATTACK = "attack"

#: Group label for a control that guide v2 says must not be caught.
CONTROL = "control"

GROUPS = (ATTACK, CONTROL)

_SEVERITY_TO_FAILURE = {"block": "high", "warning": "medium", "info": "low"}

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Case- and punctuation-insensitive form, used for duplicate detection."""

    lowered = _PUNCTUATION.sub(" ", text.lower())
    return _WHITESPACE.sub(" ", lowered).strip()


def case_id_for(strategy: AttackStrategy | str, index: int, *, control: bool = False) -> str:
    """Deterministic case id: family code plus a two-digit ordinal."""

    spec = strategy_spec(strategy)
    code = "CTL" if control else spec.code
    return f"ADV-{code}-{index:02d}"


@dataclass(frozen=True, slots=True)
class AdversarialCase:
    """One generated case, attack or control."""

    case_id: str
    text: str
    target_category: str
    attack_strategy: AttackStrategy
    expected_detection: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not CASE_ID_PATTERN.match(self.case_id):
            raise ValueError(
                f"case_id must look like ADV-XXX-00, got {self.case_id!r}"
            )
        if not self.text.strip():
            raise ValueError(f"{self.case_id}: text must not be empty")
        if not isinstance(self.attack_strategy, AttackStrategy):
            raise ValueError(
                f"{self.case_id}: attack_strategy must be an AttackStrategy, "
                f"got {type(self.attack_strategy).__name__}"
            )
        if not isinstance(self.expected_detection, bool):
            raise ValueError(
                f"{self.case_id}: expected_detection must be a bool, "
                f"got {type(self.expected_detection).__name__}"
            )
        # Raises for an unknown category, which is what we want: a case whose
        # target is not in the taxonomy cannot be scored.
        taxonomy_category(self.target_category)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def __hash__(self) -> int:  # metadata is a mapping and is not hashable
        return hash(self.case_id)

    @property
    def id(self) -> str:
        """Alias matching the documented record field name."""

        return self.case_id

    @property
    def group(self) -> str:
        return ATTACK if self.expected_detection else CONTROL

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)

    @property
    def severity(self) -> str:
        """Failure severity, from the target category's declared severity."""

        return _SEVERITY_TO_FAILURE[taxonomy_category(self.target_category).severity]

    @property
    def expectation_basis(self) -> str:
        """Which part of the published guide the expectation comes from."""

        return str(self.metadata.get("expectation_basis", ""))

    def as_dict(self) -> dict[str, Any]:
        """The documented record shape: id, text, target, strategy, expected."""

        return {
            "id": self.case_id,
            "text": self.text,
            "target_category": self.target_category,
            "attack_strategy": self.attack_strategy.value,
            "expected_detection": self.expected_detection,
            "metadata": dict(sorted(self.metadata.items())),
        }

    def annotation_record(self) -> dict[str, Any]:
        """The shape the benchmark registry exports and the auditor reads.

        Carries the generic benchmark fields (`expected_categories`, `group`) so
        the existing contamination auditor and registry work unchanged, plus the
        adversarial fields that make the case reproducible.
        """

        return {
            "id": self.case_id,
            "text": self.text,
            "expected_categories": [self.target_category],
            "group": self.group,
            "risk_level": (
                taxonomy_category(self.target_category).action
                if self.expected_detection
                else "none"
            ),
            "attack_strategy": self.attack_strategy.value,
            "expected_detection": self.expected_detection,
            "annotation_reason": str(self.metadata.get("rationale", "")),
            "expectation_basis": self.expectation_basis,
            "statement_source": str(self.metadata.get("statement_source", "author")),
            "certainty_level": str(self.metadata.get("certainty_level", "certain")),
            "severity": self.severity,
            "annotation_version": ANNOTATION_VERSION,
            "source_type": SOURCE_TYPE,
            "created_after_evaluator_freeze": True,
        }


def detect_duplicates(
    cases: Sequence[AdversarialCase],
) -> Mapping[str, tuple[str, ...]]:
    """Group case ids that normalize to the same text.

    Only groups with more than one member are returned. A generated attack that
    duplicates another is not a second data point; it is the same one counted
    twice, which would inflate every failure count it appears in.
    """

    grouped: dict[str, list[str]] = {}
    for case in cases:
        grouped.setdefault(case.normalized_text, []).append(case.case_id)
    return {
        text: tuple(ids) for text, ids in grouped.items() if len(ids) > 1
    }
