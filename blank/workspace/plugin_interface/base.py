"""Versioned Python interface implemented by every Creator plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from core.models import RawSource


@dataclass(frozen=True, slots=True)
class PluginIdentity:
    name: str
    version: str
    domain: str
    creator_target: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "domain": self.domain,
            "creator_target": self.creator_target,
        }


@dataclass(frozen=True, slots=True)
class PluginContribution:
    """Domain contribution merged into the one final artifact.

    `field_enhancements` may contain only the four common distillation fields.
    It extends their candidate lists; it never replaces common extraction.
    """

    domain_extension: Mapping[str, Any]
    risk_constraints: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    evaluation_result: Mapping[str, Any] = field(default_factory=dict)
    field_enhancements: Mapping[str, Sequence[Mapping[str, Any]]] = field(
        default_factory=dict
    )


@runtime_checkable
class CreatorDistillationPlugin(Protocol):
    @property
    def identity(self) -> PluginIdentity:
        """Return immutable plugin identity metadata."""

    def enhance(
        self,
        raw_sources: Sequence[RawSource],
        common_signals: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> PluginContribution:
        """Contribute domain rules during the same distillation engine run."""
