"""Mapping provenance: every instance field traced to a skill, an asset and a rule.

The brief requires each instance field to record four things::

    source skill  ->  skill_id
    source asset  ->  asset_id
    source version->  version
    mapping rule  ->  rule_id

:class:`MappingProvenanceBuilder` collects exactly that, keyed by ``module.field``,
and raises if any of the four is missing. A field that cannot be traced is a
failure, not a warning.

The collected map is written into the instance's existing
``provenance.field_provenance`` key - which the C0.1 contract already declares -
so mapping provenance is part of the artifact without changing the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import MappingProvenanceError

#: The keys every field mapping record must carry.
REQUIRED_MAPPING_KEYS: tuple[str, ...] = (
    "field",
    "skill_id",
    "asset_id",
    "version",
    "rule_id",
    "mode",
)

#: Deterministic default timestamp, matching the projection and skill layers.
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

#: Value used when a field has no available asset behind it.
NO_ASSET = "(none)"


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """Where one instance field came from."""

    field: str
    skill_id: str
    asset_id: str
    version: str
    rule_id: str
    mode: str
    skill_type: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        for name in ("field", "skill_id", "asset_id", "version", "rule_id", "mode"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise MappingProvenanceError(
                    f"field mapping for {self.field!r} has an empty {name}"
                )

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "field": self.field,
            "skill_id": self.skill_id,
            "asset_id": self.asset_id,
            "version": self.version,
            "rule_id": self.rule_id,
            "mode": self.mode,
        }
        if self.skill_type:
            record["skill_type"] = self.skill_type
        if self.note:
            record["note"] = self.note
        return record


class MappingProvenanceBuilder:
    """Collects one :class:`FieldMapping` per instance field."""

    def __init__(self, *, timestamp: str = DEFAULT_TIMESTAMP) -> None:
        self._timestamp = timestamp
        self._records: dict[str, FieldMapping] = {}

    @property
    def timestamp(self) -> str:
        return self._timestamp

    def __len__(self) -> int:
        return len(self._records)

    def add(
        self,
        module: str,
        field: str,
        *,
        skill_id: str,
        asset_id: str,
        version: str,
        rule_id: str,
        mode: str,
        skill_type: str = "",
        note: str = "",
    ) -> FieldMapping:
        """Record the mapping for one field, rejecting a duplicate or incomplete one."""

        if not str(module).strip():
            raise MappingProvenanceError("mapping provenance needs a module name")
        key = f"{module}.{field}"
        if key in self._records:
            raise MappingProvenanceError(
                f"field {key!r} already has a mapping record; a field is mapped once"
            )
        record = FieldMapping(
            field=key,
            skill_id=skill_id,
            asset_id=asset_id,
            version=version,
            rule_id=rule_id,
            mode=mode,
            skill_type=skill_type,
            note=note,
        )
        self._records[key] = record
        return record

    def get(self, module: str, field: str) -> FieldMapping:
        key = f"{module}.{field}"
        try:
            return self._records[key]
        except KeyError as exc:
            raise MappingProvenanceError(f"field {key!r} has no mapping record") from exc

    def has(self, module: str, field: str) -> bool:
        return f"{module}.{field}" in self._records

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def fields(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def as_dict(self) -> dict[str, Any]:
        """Return ``{field: record}`` with keys sorted for a deterministic artifact."""

        return {
            key: self._records[key].as_dict() for key in sorted(self._records)
        }

    def by_module(self) -> dict[str, dict[str, Any]]:
        """Return ``{module: {field: record}}``, for a per-module instance block."""

        grouped: dict[str, dict[str, Any]] = {}
        for key in sorted(self._records):
            module, _, field = key.partition(".")
            grouped.setdefault(module, {})[field] = self._records[key].as_dict()
        return grouped

    def modules(self) -> tuple[str, ...]:
        return tuple(sorted({key.partition(".")[0] for key in self._records}))


def assert_fields_mapped(
    provenance: Mapping[str, Any], module: str, fields: tuple[str, ...]
) -> None:
    """Raise unless every named field has a complete mapping record."""

    for field in fields:
        key = f"{module}.{field}"
        record = provenance.get(key)
        if not isinstance(record, Mapping):
            raise MappingProvenanceError(f"field {key!r} has no mapping record")
        missing = [name for name in REQUIRED_MAPPING_KEYS if name not in record]
        if missing:
            raise MappingProvenanceError(
                f"mapping record for {key!r} is missing: " + ", ".join(missing)
            )
        for name in ("skill_id", "asset_id", "version", "rule_id", "mode"):
            if not str(record.get(name, "")).strip():
                raise MappingProvenanceError(
                    f"mapping record for {key!r} has an empty {name}"
                )


def assert_no_unknown_rules(
    provenance: Mapping[str, Any], known_rule_ids: tuple[str, ...]
) -> None:
    """Raise when a mapping record cites a rule that does not exist."""

    known = set(known_rule_ids)
    for key, record in provenance.items():
        if not isinstance(record, Mapping):
            continue
        rule_id = str(record.get("rule_id", ""))
        if rule_id and rule_id not in known:
            raise MappingProvenanceError(
                f"mapping record for {key!r} cites unknown rule {rule_id!r}"
            )


def describe(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Summarise a mapping provenance document."""

    records = [r for r in provenance.values() if isinstance(r, Mapping)]
    skills = sorted({str(r.get("skill_id")) for r in records})
    assets = sorted({str(r.get("asset_id")) for r in records})
    rules = sorted({str(r.get("rule_id")) for r in records})
    modes: dict[str, int] = {}
    for record in records:
        mode = str(record.get("mode"))
        modes[mode] = modes.get(mode, 0) + 1
    return {
        "fields": len(records),
        "skills": skills,
        "assets": assets,
        "rules": rules,
        "modes": dict(sorted(modes.items())),
    }


__all__ = [
    "DEFAULT_TIMESTAMP",
    "FieldMapping",
    "MappingProvenanceBuilder",
    "NO_ASSET",
    "REQUIRED_MAPPING_KEYS",
    "assert_fields_mapped",
    "assert_no_unknown_rules",
    "describe",
]
