"""Creator Instance Loader — the configuration-reading layer for an instance artifact.

```
    creator_instance artifact  →  Instance Loader  →  Loaded Creator Configuration
```

This package is deliberately **not** a runtime. It does not execute an agent, run a
workflow, deploy anything, call a model, or generate content. It reads an instance
artifact written by :mod:`creator_mapping` (or projected by
:mod:`creator_contract`), validates it, and hands back an object that cannot be
modified.

Layers
------

``errors``
    :class:`LoaderError` and its subclasses, each carrying a stable
    machine-readable ``code`` such as ``INSTANCE_FIELD_MISSING``.
``model``
    The frozen result: :class:`LoadedCreatorInstance`, its provenance, its asset
    references and its capability states.
``resolver``
    :class:`AssetReferenceResolver` — resolves an asset *reference* without reading
    the asset's content.
``provenance``
    Parses the two provenance shapes this repository produces, and traces a field
    back through ``request → skill bundle → asset → instance field``.
``validation``
    Seven pre-load checks, plus :func:`assert_immutable` for the loaded result.
``loader``
    :func:`load_creator_instance` and :func:`compare_loaded_instances`.

What the loader guarantees
--------------------------

- An artifact is never modified, and a missing field is never filled in.
- A capability is never enabled by the loader; ``unavailable`` stays unavailable.
- An asset's content is never read, and nothing is rendered from it.
- Provenance the artifact does not record is reported as unrecorded, not invented.

This package imports nothing from ``runtime``, ``production``, ``workflows``,
``risk_evaluation``, ``multimodal_creator``, or Lobster.
"""

from __future__ import annotations

from .errors import (
    ERROR_CODES,
    INSTANCE_ASSET_REFERENCE_INVALID,
    INSTANCE_CAPABILITY_INVALID,
    INSTANCE_CONTRACT_INVALID,
    INSTANCE_DIFF_INVALID,
    INSTANCE_FIELD_MISSING,
    INSTANCE_IMMUTABLE,
    INSTANCE_MODULE_MISSING,
    INSTANCE_NOT_A_DIRECTORY,
    INSTANCE_NOT_FOUND,
    INSTANCE_PROVENANCE_INVALID,
    INSTANCE_PROVENANCE_MODULE_MISSING,
    INSTANCE_SCHEMA_INVALID,
    INSTANCE_UNREADABLE,
    InstanceAssetReferenceError,
    InstanceCapabilityError,
    InstanceContractError,
    InstanceDiffError,
    InstanceFieldMissingError,
    InstanceImmutableError,
    InstanceModuleMissingError,
    InstanceNotFoundError,
    InstanceProvenanceError,
    InstanceProvenanceMissingError,
    InstanceSchemaError,
    InstanceUnreadableError,
    LoaderError,
)
from .loader import (
    AGGREGATE_FILES,
    MODULES,
    PROVENANCE_FILE,
    InstanceDiff,
    build_loaded_instance,
    capability_records,
    compare_loaded_instances,
    derive_capabilities,
    load_creator_instance,
    read_artifact,
    read_json,
    resolve_artifact_path,
)
from .model import (
    ALL_MODULES,
    CAPABILITY_MODULES,
    CONFIG_MODULES,
    AssetReference,
    CapabilityState,
    FieldTrace,
    InstanceProvenance,
    LoadedCapability,
    LoadedCreatorInstance,
    ProvenanceKind,
    assert_immutable,
    freeze,
    thaw,
)
from .provenance import (
    AVAILABILITY_KEYS,
    CONTRACT_PROVENANCE_MODULES,
    CONTRACT_RECORD_KEYS,
    MAPPING_TRACE_KEYS,
    NOT_APPLICABLE,
    NOT_RECORDED,
    PROJECTION_FIELDS_KEY,
    PROJECTION_TRACE_KEYS,
    REQUIRED_TRACE_KEYS,
    availability_from_field_records,
    classify_provenance,
    contract_block,
    normalize_provenance,
    parse_provenance,
    projection_fields,
    provenance_kind,
    trace_instance,
    untraced_fields,
    untraced_projection_fields,
)
from .resolver import (
    ASSET_ID_KEYS,
    DECLARED_ASSET_STATUSES,
    AssetReferenceResolver,
    collect_asset_ids,
)
from .validation import (
    REQUIRED_MODULES,
    VALID_CAPABILITY_STATES,
    capability_state,
    schema_document,
    validate_capabilities,
    validate_contract,
    validate_fields,
    validate_instance,
    validate_loaded,
    validate_modules,
    validate_provenance_block,
    validate_schema,
    validate_traceability,
)

__all__ = [
    "AGGREGATE_FILES",
    "ALL_MODULES",
    "ASSET_ID_KEYS",
    "AVAILABILITY_KEYS",
    "AssetReference",
    "AssetReferenceResolver",
    "CAPABILITY_MODULES",
    "CONFIG_MODULES",
    "CONTRACT_PROVENANCE_MODULES",
    "CONTRACT_RECORD_KEYS",
    "CapabilityState",
    "DECLARED_ASSET_STATUSES",
    "ERROR_CODES",
    "FieldTrace",
    "INSTANCE_ASSET_REFERENCE_INVALID",
    "INSTANCE_CAPABILITY_INVALID",
    "INSTANCE_CONTRACT_INVALID",
    "INSTANCE_DIFF_INVALID",
    "INSTANCE_FIELD_MISSING",
    "INSTANCE_IMMUTABLE",
    "INSTANCE_MODULE_MISSING",
    "INSTANCE_NOT_A_DIRECTORY",
    "INSTANCE_NOT_FOUND",
    "INSTANCE_PROVENANCE_INVALID",
    "INSTANCE_PROVENANCE_MODULE_MISSING",
    "INSTANCE_SCHEMA_INVALID",
    "INSTANCE_UNREADABLE",
    "InstanceAssetReferenceError",
    "InstanceCapabilityError",
    "InstanceContractError",
    "InstanceDiff",
    "InstanceDiffError",
    "InstanceFieldMissingError",
    "InstanceImmutableError",
    "InstanceModuleMissingError",
    "InstanceNotFoundError",
    "InstanceProvenance",
    "InstanceProvenanceError",
    "InstanceProvenanceMissingError",
    "InstanceSchemaError",
    "InstanceUnreadableError",
    "LoadedCapability",
    "LoadedCreatorInstance",
    "LoaderError",
    "MAPPING_TRACE_KEYS",
    "MODULES",
    "NOT_APPLICABLE",
    "NOT_RECORDED",
    "PROJECTION_FIELDS_KEY",
    "PROJECTION_TRACE_KEYS",
    "PROVENANCE_FILE",
    "ProvenanceKind",
    "REQUIRED_MODULES",
    "REQUIRED_TRACE_KEYS",
    "VALID_CAPABILITY_STATES",
    "assert_immutable",
    "availability_from_field_records",
    "build_loaded_instance",
    "capability_records",
    "capability_state",
    "classify_provenance",
    "collect_asset_ids",
    "compare_loaded_instances",
    "contract_block",
    "derive_capabilities",
    "freeze",
    "load_creator_instance",
    "normalize_provenance",
    "parse_provenance",
    "projection_fields",
    "provenance_kind",
    "read_artifact",
    "read_json",
    "resolve_artifact_path",
    "schema_document",
    "thaw",
    "trace_instance",
    "untraced_fields",
    "untraced_projection_fields",
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
