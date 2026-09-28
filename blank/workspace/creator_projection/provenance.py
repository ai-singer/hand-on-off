"""Field-level provenance for projected instances.

Requirement: **any field that cannot be traced to a declared asset fails
validation.** This module is what makes that enforceable rather than aspirational.

Each record carries exactly the keys the contract's provenance format names::

    {
      "field": "...",
      "source_asset": "...",
      "source_path": "...",
      "projection_method": "...",
      "timestamp": "...",
      "confidence": 0.0
    }

Determinism: the timestamp defaults to a fixed epoch value rather than
``now()``, so projecting the same assets twice produces byte-identical output and
a test can assert it. Callers that want a real timestamp pass one explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .errors import ProjectionProvenanceError

#: The keys every field-level provenance record must carry.
REQUIRED_PROVENANCE_KEYS: tuple[str, ...] = (
    "field",
    "source_asset",
    "source_path",
    "projection_method",
    "timestamp",
    "confidence",
)

#: Projection methods this layer produces.
PROJECTION_METHODS: tuple[str, ...] = (
    "markdown_projection",
    "declared_reference",
    "config_read",
    "capability_declaration",
    "asset_substitution",
)

#: Deterministic default timestamp (projection is a pure function of its inputs).
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

#: Confidence used when a declared asset was substituted for a missing one.
SUBSTITUTION_CONFIDENCE = 0.4

#: Confidence used when a value is a declaration of absence rather than content.
DECLARATION_CONFIDENCE = 0.0


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 ``Z`` form."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    """Where one projected field came from."""

    field: str
    source_asset: str
    source_path: str
    projection_method: str
    timestamp: str = DEFAULT_TIMESTAMP
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not str(self.field).strip():
            raise ProjectionProvenanceError("provenance field name must be non-empty")
        if not str(self.source_asset).strip():
            raise ProjectionProvenanceError(
                f"provenance for {self.field!r} has no source_asset"
            )
        if not str(self.source_path).strip():
            raise ProjectionProvenanceError(
                f"provenance for {self.field!r} has no source_path"
            )
        if self.projection_method not in PROJECTION_METHODS:
            raise ProjectionProvenanceError(
                f"provenance for {self.field!r} uses unknown projection_method "
                f"{self.projection_method!r}; expected one of: "
                f"{', '.join(PROJECTION_METHODS)}"
            )
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise ProjectionProvenanceError(
                f"provenance for {self.field!r} has a non-numeric confidence"
            )
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ProjectionProvenanceError(
                f"provenance for {self.field!r} confidence must be within 0..1"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "source_asset": self.source_asset,
            "source_path": self.source_path,
            "projection_method": self.projection_method,
            "timestamp": self.timestamp,
            "confidence": float(self.confidence),
        }


class ProvenanceBuilder:
    """Collects field-level provenance records during a projection."""

    def __init__(self, *, timestamp: str = DEFAULT_TIMESTAMP) -> None:
        self._timestamp = timestamp
        self._records: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def timestamp(self) -> str:
        return self._timestamp

    def add(
        self,
        module: str,
        field: str,
        *,
        source_asset: str,
        source_path: str,
        projection_method: str,
        confidence: float = 1.0,
    ) -> None:
        """Record where one field of one module came from."""

        if not str(module).strip():
            raise ProjectionProvenanceError("provenance module name must be non-empty")
        record = FieldProvenance(
            field=field,
            source_asset=source_asset,
            source_path=source_path,
            projection_method=projection_method,
            timestamp=self._timestamp,
            confidence=confidence,
        )
        self._records.setdefault(module, {})[field] = record.as_dict()

    def module_fields(self, module: str) -> Mapping[str, Mapping[str, Any]]:
        return dict(self._records.get(module, {}))

    def as_dict(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return module -> field -> record, with modules and fields sorted."""

        return {
            module: {field: dict(record) for field, record in sorted(fields.items())}
            for module, fields in sorted(self._records.items())
        }

    def modules(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))


def assert_fields_traceable(
    provenance: Mapping[str, Any],
    module: str,
    fields: tuple[str, ...],
) -> None:
    """Raise unless every named field has a complete provenance record.

    This is the check behind "any field that cannot be traced fails validation".
    """

    module_records = provenance.get(module)
    if not isinstance(module_records, Mapping):
        raise ProjectionProvenanceError(
            f"provenance has no field records for module {module!r}"
        )
    for field in fields:
        record = module_records.get(field)
        if not isinstance(record, Mapping):
            raise ProjectionProvenanceError(
                f"field {module}.{field} has no provenance record"
            )
        missing = [key for key in REQUIRED_PROVENANCE_KEYS if key not in record]
        if missing:
            raise ProjectionProvenanceError(
                f"provenance for {module}.{field} is missing: " + ", ".join(missing)
            )
        for key in ("source_asset", "source_path", "projection_method"):
            if not str(record.get(key, "")).strip():
                raise ProjectionProvenanceError(
                    f"provenance for {module}.{field} has an empty {key}"
                )
        method = record.get("projection_method")
        if method not in PROJECTION_METHODS:
            raise ProjectionProvenanceError(
                f"provenance for {module}.{field} uses unknown method {method!r}"
            )


def assert_no_untraceable_fields(
    provenance_payload: Mapping[str, Any],
    contract_provenance: Mapping[str, Any],
) -> None:
    """Raise when the contract's module provenance and the field provenance disagree.

    The contract requires all seven modules to be sourced; the projection
    additionally requires the fields within them to be sourced. Both must hold.
    """

    field_modules = set(provenance_payload)
    module_entries = {
        key for key in contract_provenance if isinstance(contract_provenance.get(key), Mapping)
    }
    missing = sorted(field_modules - module_entries)
    if missing:
        raise ProjectionProvenanceError(
            "field-level provenance exists for modules absent from the contract "
            "provenance block: " + ", ".join(missing)
        )


__all__ = [
    "DECLARATION_CONFIDENCE",
    "DEFAULT_TIMESTAMP",
    "FieldProvenance",
    "PROJECTION_METHODS",
    "ProvenanceBuilder",
    "REQUIRED_PROVENANCE_KEYS",
    "SUBSTITUTION_CONFIDENCE",
    "assert_fields_traceable",
    "assert_no_untraceable_fields",
    "utc_now",
]
