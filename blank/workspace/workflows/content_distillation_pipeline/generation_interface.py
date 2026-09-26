"""Injection boundary for content generation implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    artifact: Mapping[str, Any]
    format_name: str = "content_plan"
    constraints: Mapping[str, Any] = field(default_factory=dict)


class GenerationAdapter(Protocol):
    """Generate from a validated artifact without mutating it.

    Implementations must document network use, credentials, timeouts, and any
    publishing side effects. The default pipeline has no generation adapter.
    """

    def generate(self, request: GenerationRequest) -> Any:
        ...
