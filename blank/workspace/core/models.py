"""Stable data contracts shared by the core, plugins, and workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .errors import InvalidSourceError


class SourceType(str, Enum):
    VIDEO = "video"
    DOCUMENT = "document"
    DATA = "data"
    IMAGE = "image"


@dataclass(frozen=True, slots=True)
class RawSource:
    """Normalized input envelope for any supported raw material.

    Binary extraction is intentionally delegated to ingestion adapters. The
    `content` field therefore contains text or already-normalized structured
    data, while `metadata` carries provenance and optional routing hints.
    """

    source_id: str
    source_type: SourceType | str
    content: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise InvalidSourceError("source_id must be non-empty")
        try:
            normalized_type = SourceType(self.source_type)
        except ValueError as exc:
            supported = ", ".join(item.value for item in SourceType)
            raise InvalidSourceError(
                f"source_type must be one of: {supported}"
            ) from exc
        if self.content is None:
            raise InvalidSourceError("content must not be null")
        object.__setattr__(self, "source_type", normalized_type)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def as_text(self) -> str:
        """Return deterministic text for classification and reference logic."""

        if isinstance(self.content, str):
            return self.content.strip()
        try:
            return json.dumps(self.content, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(self.content).strip()

    def reference(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
        }
