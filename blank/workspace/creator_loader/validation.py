"""Validation for a Creator Instance artifact.

**Before** loading, seven layers run, each raising its own typed error so a caller
can tell a shape problem from a policy problem:

1. :func:`validate_modules` — the artifact carries all seven modules and provenance.
2. :func:`validate_schema` — the artifact matches the C0.1 contract schema.
3. :func:`validate_contract` — the artifact satisfies C0.1's own validation
   (schema, dependencies, capability declaration, isolation).
4. :func:`validate_fields` — every field C0.4-A's rules declare is present.
5. :func:`validate_provenance_block` — provenance is present and complete.
6. :func:`validate_capabilities` — no capability claims more than its recorded
   availability supports.
7. :func:`validate_traceability` — every field of a *mapped* instance is traced.

**After** loading, :func:`assert_immutable` proves the result resists modification.

The loader **never repairs**. A missing field is reported with
``INSTANCE_FIELD_MISSING`` so the artifact can be regenerated; filling it in would
be the fabrication every phase of this programme exists to prevent.

A note on the two shapes. A *mapped* instance (C0.4-A) records a per-field
availability payload, so capability state is read from it. A *projected* instance
(C0.2) records only per-module provenance; its capability state is read from that,
and a field with no mapping trace is not an error, because the shape never claimed
to have one. The distinction is made from the artifact's own structure, never
assumed.
"""

from __future__ import annotations

from typing import Any, Mapping

from creator_contract import validate as contract_validate
from creator_contract import validate_schema as contract_validate_schema
from creator_mapping import CAPABILITY_MODULES, MAPPED_MODULES, REQUIRED_PATHS

from .errors import (
    InstanceCapabilityError,
    InstanceContractError,
    InstanceFieldMissingError,
    InstanceModuleMissingError,
    InstanceProvenanceError,
    InstanceSchemaError,
)
from .model import CapabilityState, ProvenanceKind, assert_immutable
from .provenance import (
    CONTRACT_PROVENANCE_MODULES,
    contract_block,
    normalize_provenance,
    provenance_kind,
    untraced_fields,
    untraced_projection_fields,
)

#: Modules an artifact must carry. ``provenance`` is checked separately.
REQUIRED_MODULES: tuple[str, ...] = MAPPED_MODULES

#: The three legitimate capability states a capability module may report.
VALID_CAPABILITY_STATES: tuple[str, ...] = (
    CapabilityState.AVAILABLE.value,
    CapabilityState.DECLARED.value,
    CapabilityState.UNAVAILABLE.value,
)


# --------------------------------------------------------------------------
# 1. Schema
# --------------------------------------------------------------------------


def schema_document(
    instance: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the document as the C0.1 schema must see it.

    The only change is that a normalised provenance block's loader-private
    projection-records key is withheld: the contract's ``provenance`` object admits a
    fixed set of keys, and the loader must not present one the schema would reject.
    Nothing the artifact itself carried is added or removed.
    """

    document = {str(key): value for key, value in instance.items()}
    provenance = instance.get("provenance")
    if isinstance(provenance, Mapping):
        document["provenance"] = contract_block(normalize_provenance(provenance))
    return document


def validate_schema(
    instance: Mapping[str, Any],
    *,
    workspace_root: Any = None,
) -> None:
    """Validate the artifact against the C0.1 contract schema."""

    if not isinstance(instance, Mapping):
        raise InstanceSchemaError("a creator instance must be an object")
    try:
        contract_validate_schema(
            schema_document(instance), workspace_root=workspace_root
        )
    except Exception as exc:
        raise InstanceSchemaError(
            "creator instance does not match the contract schema", detail=str(exc)
        ) from exc


# --------------------------------------------------------------------------
# 2. Contract
# --------------------------------------------------------------------------


def validate_contract(
    instance: Mapping[str, Any],
    *,
    workspace_root: Any = None,
) -> Mapping[str, str]:
    """Run C0.1's own validation, returning its check map."""

    try:
        report = contract_validate(
            schema_document(instance), workspace_root=workspace_root
        )
    except Exception as exc:
        raise InstanceContractError(
            "creator instance fails contract validation", detail=str(exc)
        ) from exc
    return dict(report.checks)


# --------------------------------------------------------------------------
# 3. Presence and provenance
# --------------------------------------------------------------------------


def validate_modules(instance: Mapping[str, Any]) -> None:
    """Every module the loader expects must be present.

    A missing module is reported, never created.
    """

    missing = [module for module in REQUIRED_MODULES if module not in instance]
    if missing:
        raise InstanceModuleMissingError(
            "creator instance is missing modules: " + ", ".join(missing),
            detail="the loader never creates a module",
        )
    if "provenance" not in instance:
        raise InstanceModuleMissingError(
            "creator instance is missing its provenance module",
            detail="an instance with no provenance cannot be traced",
        )
    for module in REQUIRED_MODULES:
        document = instance[module]
        if not isinstance(document, Mapping):
            raise InstanceModuleMissingError(
                f"module {module!r} is not an object",
                detail=f"found {type(document).__name__}",
            )


def validate_fields(instance: Mapping[str, Any]) -> None:
    """Every field the mapping contract declares must be present.

    This is the check behind ``INSTANCE_FIELD_MISSING``. It reads C0.4-A's
    ``REQUIRED_PATHS`` so the loader and the mapper cannot disagree about what a
    complete instance contains.
    """

    absent: dict[str, list[str]] = {}
    for module, paths in REQUIRED_PATHS.items():
        document = instance.get(module)
        if not isinstance(document, Mapping):
            absent[module] = list(paths)
            continue
        missing = [path for path in paths if path not in document]
        if missing:
            absent[module] = missing
    if absent:
        detail = "; ".join(
            f"{module}: {', '.join(paths)}" for module, paths in sorted(absent.items())
        )
        raise InstanceFieldMissingError(
            "creator instance is missing required fields", detail=detail
        )


def validate_provenance_block(instance: Mapping[str, Any]) -> str:
    """The provenance block must be present, complete and recognisable.

    Returns the shape it found, so the caller can stop guessing.
    """

    provenance = instance.get("provenance")
    if not isinstance(provenance, Mapping):
        raise InstanceProvenanceError("the instance carries no provenance block")

    block = normalize_provenance(provenance)

    missing = [
        module for module in CONTRACT_PROVENANCE_MODULES if module not in block
    ]
    if missing:
        raise InstanceProvenanceError(
            "provenance is missing entries for: " + ", ".join(missing),
            detail="every module must record where it came from",
        )

    kind = provenance_kind(block)
    if kind == ProvenanceKind.ABSENT.value:
        raise InstanceProvenanceError(
            "provenance is in no shape this loader recognises",
            detail=(
                "expected a mapped payload carrying fields and modules, or "
                "per-module records for all seven modules"
            ),
        )

    for module in REQUIRED_MODULES:
        record = block.get(module)
        if not isinstance(record, Mapping) or not record:
            raise InstanceProvenanceError(
                f"provenance has no record for module {module!r}"
            )

    if kind == ProvenanceKind.MAPPED.value:
        payload = block["field_provenance"]
        fields = payload.get("fields")
        if not isinstance(fields, Mapping) or not fields:
            raise InstanceProvenanceError("provenance carries no field records")
        modules = payload.get("modules")
        if not isinstance(modules, Mapping) or not modules:
            raise InstanceProvenanceError(
                "provenance carries no per-module availability records"
            )
        for module in REQUIRED_MODULES:
            record = modules.get(module)
            if not isinstance(record, Mapping):
                raise InstanceProvenanceError(
                    f"provenance has no availability record for module {module!r}"
                )
            # The record must state availability, either explicitly or as an asset
            # status. Saying nothing would leave the capability state unjustifiable.
            if _availability_of(record) is None:
                raise InstanceProvenanceError(
                    f"module {module!r} does not record whether a source was available"
                )

    return kind


# --------------------------------------------------------------------------
# 4. Capabilities
# --------------------------------------------------------------------------


def capability_state(
    record: Mapping[str, Any],
    *,
    enabled: bool | None = None,
) -> str:
    """Derive a capability state from a module's provenance record.

    The mapping is explicit so a reader can see exactly how the loader decides, and
    so a test can pin each branch. Nothing here enables anything: the result is a
    *label* for a state the artifact already declares.

    The four outcomes, in the order they are decided:

    - ``available`` — the record says a usable source exists.
    - ``declared`` — the record names an asset the registry marks unavailable, so the
      capability is declared but not implemented.
    - ``unavailable`` — the record names an asset that is neither available nor
      declared-unavailable, so the state is genuinely unknown-but-not-usable.
    - ``absent`` — the record names no asset at all.

    ``absent`` matters. A module with no own asset — ``source`` in the C0.4-A
    mapping, for instance, whose fields are derived from other modules' assets —
    records ``asset_id: "(none)"``. That is not a missing capability, and reporting
    it as one would overstate the gap the artifact actually has.
    """

    if not isinstance(record, Mapping):
        return CapabilityState.ABSENT.value

    status = str(record.get("asset_status", "")).strip()
    has_source = record.get("has_available_source")
    if has_source is None:
        # A projected record states availability as an asset status instead.
        has_source = status == CapabilityState.AVAILABLE.value
    asset_id = str(record.get("asset_id", record.get("source", ""))).strip()
    named = bool(asset_id) and asset_id not in ("(none)", "none", "n/a")

    if has_source is True:
        return CapabilityState.AVAILABLE.value
    if status == CapabilityState.UNAVAILABLE.value:
        return CapabilityState.DECLARED.value
    if not named:
        return CapabilityState.ABSENT.value
    return CapabilityState.UNAVAILABLE.value


def _availability_of(
    record: Mapping[str, Any],
) -> bool | None:
    """Read whether a provenance record says a usable source exists.

    ``None`` means the record does not say, which is different from saying no.
    """

    if not isinstance(record, Mapping):
        return None
    explicit = record.get("has_available_source")
    if isinstance(explicit, bool):
        return explicit
    status = str(record.get("asset_status", "")).strip()
    if status == CapabilityState.AVAILABLE.value:
        return True
    if status:
        return False
    return None


def validate_capabilities(instance: Mapping[str, Any]) -> None:
    """No capability may claim more than its recorded availability supports.

    The loader reads the state the artifact records and refuses a contradiction. It
    never enables a capability, and it never reconciles a disagreement by choosing
    a side.
    """

    provenance = instance.get("provenance")
    if not isinstance(provenance, Mapping):
        raise InstanceCapabilityError("the instance carries no provenance block")
    block = normalize_provenance(provenance)

    payload = block.get("field_provenance")
    if isinstance(payload, Mapping) and isinstance(payload.get("modules"), Mapping):
        records: Mapping[str, Any] = payload["modules"]
    else:
        records = block

    for module in CAPABILITY_MODULES:
        body = instance.get(module)
        if not isinstance(body, Mapping):
            raise InstanceCapabilityError(f"instance has no {module} block")
        if not isinstance(body.get("enabled"), bool):
            raise InstanceCapabilityError(f"{module}.enabled must be a boolean")

        record = records.get(module)
        if not isinstance(record, Mapping):
            raise InstanceCapabilityError(
                f"{module} has no provenance record, so its state is unjustified"
            )

        has_source = _availability_of(record)
        enabled = body["enabled"]
        reason = str(body.get("reason", "")).strip()

        if has_source is True and enabled is not True:
            raise InstanceCapabilityError(
                f"{module} has an available source but is not enabled",
                detail="availability and enabled must agree",
            )
        if has_source is not True and enabled is not False:
            raise InstanceCapabilityError(
                f"{module}.enabled is true but its source is not available",
                detail=(
                    f"asset_status={record.get('asset_status')!r} "
                    f"reason={record.get('reason', record.get('asset_reason'))!r}"
                ),
            )
        if enabled is False and not reason:
            raise InstanceCapabilityError(
                f"{module}.enabled is false but no reason is declared"
            )


# --------------------------------------------------------------------------
# 5. Traceability
# --------------------------------------------------------------------------


def validate_traceability(instance: Mapping[str, Any], *, kind: str) -> None:
    """Every field must be accounted for by the provenance shape in use.

    For a **mapped** instance (C0.4-A) each field has its own trace, and a field
    without one is a defect: the artifact would carry a value with no record of
    where it came from.

    For a **projected** instance (C0.2) the provenance is per module, and the
    instance's provenance block describes the module — its source, its path, its
    projection method. A projected value is therefore accounted for by its module's
    record, and what is checked is that the record actually says something. Demanding
    a per-field trace from an artifact whose declared shape has none would be
    inventing a requirement rather than enforcing one.
    """

    provenance = instance.get("provenance")
    if not isinstance(provenance, Mapping):
        raise InstanceProvenanceError("the instance carries no provenance block")
    block = normalize_provenance(provenance)

    if kind == ProvenanceKind.MAPPED.value:
        payload = block.get("field_provenance")
        fields = payload.get("fields") if isinstance(payload, Mapping) else None
        if not isinstance(fields, Mapping):
            raise InstanceProvenanceError("provenance carries no field records")
        traced = set(str(key) for key in fields)
        untraced = [
            f"{module}.{field_name}"
            for module in REQUIRED_MODULES
            if isinstance(instance.get(module), Mapping)
            for field_name in instance[module]
            if f"{module}.{field_name}" not in traced
        ]
        if untraced:
            raise InstanceProvenanceError(
                f"{len(untraced)} instance field(s) have no provenance trace",
                detail=", ".join(sorted(untraced)[:12]),
            )
        return

    # Projected shape: each module's provenance record must carry real evidence.
    evidence_keys = ("source", "source_path", "projection_method", "asset_status")
    baseless: list[str] = []
    for module in CONTRACT_PROVENANCE_MODULES:
        if module not in instance:
            continue
        record = block.get(module)
        if not isinstance(record, Mapping):
            baseless.append(module)
            continue
        if not any(str(record.get(key, "")).strip() for key in evidence_keys):
            baseless.append(module)
    if baseless:
        raise InstanceProvenanceError(
            f"{len(baseless)} module(s) have a provenance record with no source",
            detail=", ".join(baseless),
        )


# --------------------------------------------------------------------------
# Combined entry point
# --------------------------------------------------------------------------


def validate_instance(
    instance: Mapping[str, Any],
    *,
    workspace_root: Any = None,
) -> dict[str, str]:
    """Run every pre-load check in order and return the check map.

    ``instance`` must already be in aggregate form: seven modules, a provenance
    block, and a contract version. :func:`creator_loader.loader.read_artifact`
    builds that shape from whichever on-disk layout it found.
    """

    checks: dict[str, str] = {}

    validate_modules(instance)
    checks["modules"] = "PASS"

    validate_schema(instance, workspace_root=workspace_root)
    checks["schema"] = "PASS"

    checks.update(validate_contract(instance, workspace_root=workspace_root))
    checks["contract"] = "PASS"

    validate_fields(instance)
    checks["fields"] = "PASS"

    kind = validate_provenance_block(instance)
    checks["provenance"] = "PASS"
    checks["provenance_kind"] = kind

    validate_capabilities(instance)
    checks["capabilities"] = "PASS"

    validate_traceability(instance, kind=kind)
    checks["traceability"] = "PASS"

    return checks


def validate_loaded(loaded: Any) -> dict[str, str]:
    """Re-check a loaded instance, including that it is immutable."""

    checks = dict(getattr(loaded, "validation", {}))
    assert_immutable(loaded)
    checks["immutable"] = "PASS"

    if getattr(loaded, "provenance_kind", "") == ProvenanceKind.MAPPED.value:
        untraced = untraced_fields(loaded)
        if untraced:
            raise InstanceProvenanceError(
                f"{len(untraced)} loaded field(s) lost their trace",
                detail=", ".join(untraced[:12]),
            )
        checks["loaded_traceability"] = "PASS"
    else:
        untraced = untraced_projection_fields(loaded)
        if untraced:
            raise InstanceProvenanceError(
                f"{len(untraced)} loaded field(s) lost their provenance record",
                detail=", ".join(untraced[:12]),
            )
        checks["loaded_traceability"] = "PASS"

    return checks


__all__ = [
    "REQUIRED_MODULES",
    "VALID_CAPABILITY_STATES",
    "capability_state",
    "schema_document",
    "validate_capabilities",
    "validate_contract",
    "validate_fields",
    "validate_instance",
    "validate_loaded",
    "validate_modules",
    "validate_provenance_block",
    "validate_schema",
    "validate_traceability",
]
