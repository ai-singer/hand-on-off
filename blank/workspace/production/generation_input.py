"""Read-only projection from a validated artifact to generation inputs.

`GenerationRequest`
(`workflows/content_distillation_pipeline/generation_interface.py`) remains the
single generation contract. This module defines **no** new artifact format and
runs **no** distillation: it only resolves the addressed inputs a generation
module needs from sections the artifact already carries, so "can this artifact
be consumed for generation?" becomes a checkable question instead of an
assumption.

The projection is derived and never persisted, so it cannot drift from the
artifact it came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


#: Addressed inputs a generation module consumes, in reading order.
GENERATION_INPUT_FIELDS = (
    "topic",
    "structure",
    "knowledge",
    "style",
    "domain_context",
    "constraints",
)

#: Addressed input -> artifact section it is projected from.
INPUT_SOURCES = (
    ("topic", "topic_candidate"),
    ("structure", "content_template"),
    ("knowledge", "knowledge_unit"),
    ("style", "style_pattern"),
    ("domain_context", "domain_extension"),
    ("constraints", "risk_constraints"),
)

#: Inputs whose emptiness is a valid production state rather than a defect.
#: A clean artifact has no risk constraints, and a plugin-less instance has no
#: domain context; neither should be reported as incomplete. The four core
#: families are not in this set: an artifact with no topic, structure,
#: knowledge or style carries nothing to generate from.
INPUTS_ALLOWING_EMPTY = ("domain_context", "constraints")


class GenerationInputError(Exception):
    """Raised when an artifact cannot be projected for generation."""


@dataclass(frozen=True, slots=True)
class GenerationInput:
    """Resolved generation inputs plus what was missing or unacceptably empty."""

    values: Mapping[str, Any]
    missing: tuple[str, ...]
    empty: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """True when every addressed input is present and usable.

        Inputs listed in `INPUTS_ALLOWING_EMPTY` may be empty without making
        the artifact incomplete.
        """

        return not self.missing and not self.empty

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)

    def render(self) -> str:
        if self.complete:
            return "generation input complete"
        parts = []
        if self.missing:
            parts.append("missing=" + ", ".join(self.missing))
        if self.empty:
            parts.append("empty=" + ", ".join(self.empty))
        return "generation input incomplete (" + "; ".join(parts) + ")"


def resolve_generation_input(artifact: Mapping[str, Any]) -> GenerationInput:
    """Project an artifact into the addressed generation inputs.

    Returning a value is not a quality decision: the quality gate decides
    whether generation may run. This function only answers whether the artifact
    carries something for every addressed input.
    """

    if not isinstance(artifact, Mapping):
        raise GenerationInputError(
            f"artifact must be a mapping, got {type(artifact).__name__}"
        )

    values: dict[str, Any] = {}
    missing: list[str] = []
    empty: list[str] = []
    for addressed, section in INPUT_SOURCES:
        if section not in artifact:
            missing.append(addressed)
            values[addressed] = None
            continue
        value = artifact[section]
        values[addressed] = value
        if _is_empty(value) and addressed not in INPUTS_ALLOWING_EMPTY:
            empty.append(addressed)

    return GenerationInput(
        values=MappingProxyType(values),
        missing=tuple(missing),
        empty=tuple(empty),
    )


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, bytes)):
        return not value.strip()
    if isinstance(value, Mapping):
        return not value
    if isinstance(value, (list, tuple, set, frozenset)):
        return not value
    return False
