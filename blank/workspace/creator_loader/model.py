"""The loaded instance: an immutable snapshot of a Creator Instance artifact.

Every object here is a frozen dataclass, and every nested mapping is wrapped in
:class:`~types.MappingProxyType`. A loaded instance therefore **cannot be modified
at run time**: an attempted write raises ``TypeError`` from the proxy or
``FrozenInstanceError`` from the dataclass, both of which
:mod:`creator_loader.validation` converts into a typed loader error for a caller
that wants one.

This is a *reader*. Nothing here executes an asset, opens a connection, calls a
model, or generates content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .errors import InstanceImmutableError

#: The seven configuration modules a loaded instance carries, in contract order.
CONFIG_MODULES: tuple[str, ...] = (
    "identity",
    "source",
    "text_rules",
    "visual_rules",
    "risk_policy",
    "generation",
    "publishing",
)

#: Every module an instance directory holds, including provenance.
ALL_MODULES: tuple[str, ...] = CONFIG_MODULES + ("provenance",)

#: Capability modules: the ones that may be enabled or disabled.
CAPABILITY_MODULES: tuple[str, ...] = ("generation", "publishing")


class CapabilityState(str, Enum):
    """How much of a module's capability actually exists.

    The three states the brief names, plus one for a module the artifact does not
    carry at all. The loader reports the state it finds; it never promotes one.
    """

    #: A real, resolved source backs the module.
    AVAILABLE = "available"
    #: The module is named, but its source is a declared but unimplemented asset.
    DECLARED = "declared"
    #: The module's source could not be resolved at all.
    UNAVAILABLE = "unavailable"
    #: The artifact carries no capability record for this module.
    ABSENT = "absent"


class ProvenanceKind(str, Enum):
    """Which artifact shape an instance's provenance takes.

    Two shapes exist in this repository and the loader reads both, but it never
    conflates them: a *mapped* instance (C0.4-A) traces every field to a skill,
    asset and rule; a *projected* instance (C0.2) records only where each module
    came from. Tracing the second as though it were the first would invent a chain.
    """

    #: ``field_provenance.fields`` + ``field_provenance.modules`` — C0.4-A.
    MAPPED = "mapped"
    #: Per-module contract provenance records — C0.2.
    PROJECTED = "projected"
    #: No recognised provenance shape.
    ABSENT = "absent"


def freeze(document: Any) -> Any:
    """Recursively wrap a document so it cannot be mutated.

    Mappings become :class:`MappingProxyType`; sequences become tuples. Scalars pass
    through unchanged.
    """

    if isinstance(document, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in document.items()})
    if isinstance(document, (list, tuple)):
        return tuple(freeze(item) for item in document)
    return document


def thaw(document: Any) -> Any:
    """Return a mutable copy of a frozen document, for serialisation."""

    if isinstance(document, Mapping):
        return {str(k): thaw(v) for k, v in document.items()}
    if isinstance(document, (tuple, list)):
        return [thaw(item) for item in document]
    return document


@dataclass(frozen=True, slots=True)
class AssetReference:
    """A pointer to an asset, resolved **without reading or executing it**.

    The loader records what the instance references and whether that reference is
    well-formed and registered. It deliberately does not load the asset's content:
    reading a visual profile is a configuration concern, rendering one is not.
    """

    asset_id: str
    asset_type: str
    asset_status: str
    reason: str = ""
    location: str = ""
    skill_id: str = ""
    registered: bool = False
    version: str = ""

    @property
    def resolvable(self) -> bool:
        """Whether the reference names an asset the registry knows about."""

        return self.registered

    @property
    def available(self) -> bool:
        return self.asset_status == "available"

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "asset_status": self.asset_status,
            "reason": self.reason,
            "location": self.location,
            "skill_id": self.skill_id,
            "registered": self.registered,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class LoadedCapability:
    """One module's capability state, exactly as the artifact records it."""

    module: str
    state: CapabilityState
    enabled: bool | None
    reason: str
    skill_type: str
    skill_ids: tuple[str, ...]
    asset_id: str
    asset_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "state": self.state.value,
            "enabled": self.enabled,
            "reason": self.reason,
            "skill_type": self.skill_type,
            "skill_ids": list(self.skill_ids),
            "asset_id": self.asset_id,
            "asset_status": self.asset_status,
        }


@dataclass(frozen=True, slots=True)
class FieldTrace:
    """One instance field and the chain that produced it."""

    field: str
    module: str
    skill_id: str
    asset_id: str
    version: str
    rule_id: str
    mode: str
    skill_type: str = ""
    asset_ref: AssetReference | None = None

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "field": self.field,
            "module": self.module,
            "skill_id": self.skill_id,
            "asset_id": self.asset_id,
            "version": self.version,
            "rule_id": self.rule_id,
            "mode": self.mode,
        }
        if self.skill_type:
            record["skill_type"] = self.skill_type
        if self.asset_ref is not None:
            record["asset"] = self.asset_ref.as_dict()
        return record


@dataclass(frozen=True, slots=True)
class InstanceProvenance:
    """The provenance a loaded instance carries, frozen and separated by kind.

    The three mapping fields are wrapped on construction, so a loaded instance's
    provenance is immutable whether it was built by the loader or assembled directly.
    """

    kind: str
    generated_by: str
    bundle_id: str
    factory_version: str
    mapping_version: str
    mapping_rule_count: int
    field_traces: Mapping[str, FieldTrace] = field(default_factory=dict)
    module_records: Mapping[str, Any] = field(default_factory=dict)
    asset_references: Mapping[str, AssetReference] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_traces", freeze(self.field_traces))
        object.__setattr__(self, "module_records", freeze(self.module_records))
        object.__setattr__(self, "asset_references", freeze(self.asset_references))

    @property
    def mapped(self) -> bool:
        """Whether field-level mapping traces are present."""

        return self.kind == ProvenanceKind.MAPPED.value

    def trace(self, field: str) -> FieldTrace:
        """Return the trace for one field, rejecting an untraced field."""

        try:
            return self.field_traces[field]
        except KeyError as exc:
            from .errors import InstanceProvenanceError

            raise InstanceProvenanceError(
                f"field {field!r} has no provenance trace",
                detail=(
                    f"provenance kind is {self.kind!r}; "
                    f"traced fields: {len(self.field_traces)}"
                ),
            ) from exc

    def skills(self) -> tuple[str, ...]:
        """Every skill the instance's fields were derived from, sorted."""

        return tuple(
            sorted({trace.skill_id for trace in self.field_traces.values()})
        )

    def assets(self) -> tuple[str, ...]:
        return tuple(sorted(self.asset_references))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "generated_by": self.generated_by,
            "bundle_id": self.bundle_id,
            "factory_version": self.factory_version,
            "mapping_version": self.mapping_version,
            "mapping_rule_count": self.mapping_rule_count,
            "field_traces": {
                key: trace.as_dict() for key, trace in sorted(self.field_traces.items())
            },
            "module_records": thaw(self.module_records),
            "asset_references": {
                key: ref.as_dict() for key, ref in sorted(self.asset_references.items())
            },
        }


@dataclass(frozen=True, slots=True)
class LoadedCreatorInstance:
    """An immutable, validated Creator Instance.

    ``modules`` holds the seven configuration modules. ``provenance`` holds the
    parsed provenance. ``source_path`` records where the artifact was read from, so
    a loaded object always knows its own origin.

    Every mapping field is frozen on construction and the dataclass is frozen, so
    there is no attribute a caller can write and no nested mapping a caller can
    mutate. :func:`assert_immutable` proves it empirically.
    """

    instance_id: str
    source_path: Path
    contract_version: str
    modules: Mapping[str, Any]
    raw_provenance: Mapping[str, Any]
    provenance: InstanceProvenance
    capabilities: Mapping[str, LoadedCapability]
    asset_references: Mapping[str, AssetReference]
    validation: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", freeze(self.modules))
        object.__setattr__(self, "raw_provenance", freeze(self.raw_provenance))
        object.__setattr__(self, "capabilities", freeze(self.capabilities))
        object.__setattr__(self, "asset_references", freeze(self.asset_references))
        object.__setattr__(self, "validation", freeze(self.validation))

    # -- module access ----------------------------------------------------

    def module(self, name: str) -> Any:
        """Return one configuration module, rejecting an unknown name."""

        if name not in self.modules:
            from .errors import InstanceModuleMissingError

            raise InstanceModuleMissingError(
                f"loaded instance has no module {name!r}",
                detail=f"modules present: {', '.join(sorted(self.modules))}",
            )
        return self.modules[name]

    def get(self, module: str, field_name: str, default: Any = None) -> Any:
        """Read one field of one module, without raising on absence."""

        document = self.modules.get(module)
        if not isinstance(document, Mapping):
            return default
        return document.get(field_name, default)

    def field(self, path: str) -> Any:
        """Read ``module.field``, rejecting a malformed path or absent field."""

        module, _, field_name = path.partition(".")
        if not module or not field_name:
            from .errors import InstanceFieldMissingError

            raise InstanceFieldMissingError(
                f"{path!r} is not a module.field path"
            )
        document = self.modules.get(module)
        if not isinstance(document, Mapping) or field_name not in document:
            from .errors import InstanceFieldMissingError

            raise InstanceFieldMissingError(
                f"instance field {path!r} is not present",
                detail="the loader never repairs a missing field",
            )
        return document[field_name]

    # -- identity helpers -------------------------------------------------

    @property
    def creator_id(self) -> str:
        return str(self.get("identity", "creator_id", ""))

    @property
    def domain(self) -> str:
        return str(self.get("identity", "domain", ""))

    @property
    def platform(self) -> str:
        return str(self.get("identity", "platform", ""))

    @property
    def provenance_kind(self) -> str:
        """Which provenance shape this instance carries."""

        return self.provenance.kind

    @property
    def kind(self) -> str:
        """Alias for :attr:`provenance_kind`, for concise reporting."""

        return self.provenance.kind

    def capability(self, module: str) -> LoadedCapability:
        """Return one module's capability state."""

        if module not in self.capabilities:
            from .errors import InstanceCapabilityError

            raise InstanceCapabilityError(
                f"loaded instance has no capability record for {module!r}",
                detail=f"recorded: {', '.join(sorted(self.capabilities))}",
            )
        return self.capabilities[module]

    def enabled_capabilities(self) -> tuple[str, ...]:
        """Modules whose capability the artifact marks enabled."""

        return tuple(
            sorted(
                module
                for module, cap in self.capabilities.items()
                if cap.enabled is True
            )
        )

    def unavailable_capabilities(self) -> tuple[str, ...]:
        """Modules whose capability is declared but not implemented, or unknown.

        A module recording *no* own asset is not listed here: ``absent`` is a
        different fact from ``unavailable``, and conflating them would overstate
        what the artifact lacks.
        """

        return tuple(
            sorted(
                module
                for module, cap in self.capabilities.items()
                if cap.state in (CapabilityState.DECLARED, CapabilityState.UNAVAILABLE)
            )
        )

    def absent_capabilities(self) -> tuple[str, ...]:
        """Modules whose provenance record names no own asset at all."""

        return tuple(
            sorted(
                module
                for module, cap in self.capabilities.items()
                if cap.state == CapabilityState.ABSENT
            )
        )

    def capability_states(self) -> dict[str, str]:
        """Every module's capability state, as a plain mapping."""

        return {
            module: cap.state.value
            for module, cap in sorted(self.capabilities.items())
        }

    # -- serialisation ----------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        """Return a plain, mutable copy. The loaded object itself stays frozen."""

        return {
            "instance_id": self.instance_id,
            "source_path": str(self.source_path),
            "contract_version": self.contract_version,
            "modules": {key: thaw(value) for key, value in sorted(self.modules.items())},
            "provenance": self.provenance.as_dict(),
            "capabilities": {
                key: cap.as_dict() for key, cap in sorted(self.capabilities.items())
            },
            "asset_references": {
                key: ref.as_dict() for key, ref in sorted(self.asset_references.items())
            },
            "validation": dict(self.validation),
        }


def assert_immutable(instance: LoadedCreatorInstance) -> None:
    """Prove the loaded object resists modification, or raise a typed error.

    Used by the tests as the positive demonstration that immutability is real,
    rather than a claim about the dataclass decorator.
    """

    try:
        instance.instance_id = "tampered"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise InstanceImmutableError(
            "a loaded instance accepted a write to instance_id"
        )

    modules = instance.modules
    if not isinstance(modules, MappingProxyType):
        raise InstanceImmutableError("modules is not a mapping proxy")
    try:
        modules["identity"] = {}  # type: ignore[index]
    except TypeError:
        return
    raise InstanceImmutableError("modules accepted a write")


__all__ = [
    "ALL_MODULES",
    "AssetReference",
    "CAPABILITY_MODULES",
    "CONFIG_MODULES",
    "CapabilityState",
    "FieldTrace",
    "InstanceProvenance",
    "LoadedCapability",
    "LoadedCreatorInstance",
    "ProvenanceKind",
    "assert_immutable",
    "freeze",
    "thaw",
]
