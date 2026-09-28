"""Parsing and tracing the provenance a Creator Instance carries.

Two artifact shapes exist in this repository, and the loader reads both:

**Mapped (C0.4-A)** — the instance's ``provenance`` block carries a
``field_provenance`` payload holding ``fields`` (one record per instance field)
and ``modules`` (one availability record per module)::

    provenance.field_provenance.fields["visual_rules.profile_id"]
        = {field, skill_id, asset_id, version, rule_id, mode}

**Projected (C0.2)** — the instance carries no mapping payload at all. Its
provenance is per-module::

    provenance.visual_rules = {source, source_path, projection_method, timestamp,
                               confidence, asset_status, assets[], ...}

The loader reports which shape it found instead of guessing. A projected instance
is **not** a broken mapped instance; it is a different, legitimate artifact, and
the difference is exactly what :func:`trace_instance` has to be honest about.

### The honest boundary

A mapped instance records the **bundle id**, the skill that derived each field, the
asset it read, the rule that performed the mapping, and the version. It does
**not** record the originating ``CreatorRequest`` — that lived in the composing
process. :func:`trace_instance` therefore reports the request step as
``recorded: false`` rather than reconstructing a plausible one. Reconstructing it
would fabricate provenance, which is worse than admitting the gap.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .errors import InstanceProvenanceError, InstanceProvenanceMissingError
from .model import AssetReference, FieldTrace, InstanceProvenance, ProvenanceKind
from .resolver import AssetReferenceResolver, collect_asset_ids

#: Keys a mapped field trace must carry.
REQUIRED_TRACE_KEYS: tuple[str, ...] = (
    "field",
    "skill_id",
    "asset_id",
    "version",
    "rule_id",
    "mode",
)

#: The keys the C0.1 contract declares inside the provenance block.
CONTRACT_PROVENANCE_MODULES: tuple[str, ...] = (
    "identity",
    "source",
    "text_rules",
    "visual_rules",
    "risk_policy",
    "generation",
    "publishing",
)

#: Keys that only a mapped (C0.4-A) field record carries.
MAPPING_TRACE_KEYS: tuple[str, ...] = ("skill_id", "rule_id", "mode")

#: Keys that only a projected (C0.2) field record carries.
PROJECTION_TRACE_KEYS: tuple[str, ...] = ("projection_method", "source_asset")

#: ``generated_by`` shape, e.g. ``creator_mapping.mapper c0.4-a bundle=<id> rules=46``.
_GENERATED_BY = re.compile(
    r"^(?P<generator>[\w.\-]+)\s+(?P<generator_version>[\w.\-]+)"
    r"(?:\s+bundle=(?P<bundle>[\w.\-]+))?"
    r"(?:\s+rules=(?P<rules>\d+))?$"
)

#: Placeholder for a value the artifact does not record.
NOT_RECORDED = "(not recorded)"

#: Placeholder for "this artifact shape has no such step at all".
NOT_APPLICABLE = "(not applicable)"

#: Key under which :func:`normalize_provenance` carries a C0.2 layout's per-field
#: projection records. It is deliberately *not* a name the C0.1 contract declares:
#: the loader keeps the records for a caller to inspect, and removes them before the
#: block is validated, so it never presents a key the schema would reject as though
#: the artifact had carried it.
PROJECTION_FIELDS_KEY = "__loader_projection_fields__"


def classify_provenance(block: Mapping[str, Any]) -> str:
    """Return the shape a provenance block takes, and what evidence it rests on.

    Three shapes are recognised, and the difference between the last two matters:

    - **mapped** — a ``field_provenance`` payload holding ``fields`` and ``modules``.
      Claimed by the keys being *present*, not by them being non-empty: an artifact
      whose payload was emptied is a damaged mapped artifact, and must not be
      re-labelled as a projected one merely because nothing is left inside it.
    - **projected** — a contract provenance record per module, with no mapping
      payload. The record's own projection keys are the evidence, so a plain
      hand-written record with none of them is not accepted as a projection.
    - **absent** — everything else, including a mapping payload that has lost its
      ``fields`` or ``modules`` map.

    Shared by :func:`provenance_kind` and :func:`parse_provenance` so the two can
    never disagree about what they are looking at.
    """

    if not isinstance(block, Mapping):
        return ProvenanceKind.ABSENT.value

    payload = block.get("field_provenance")
    if isinstance(payload, Mapping):
        if "fields" in payload and "modules" in payload:
            return ProvenanceKind.MAPPED.value
        # A mapping payload that is not a mapping payload. Whatever the module
        # records below look like, this artifact is damaged, and reading it as a
        # projection would hide that.
        return ProvenanceKind.ABSENT.value

    present = [
        block.get(module)
        for module in CONTRACT_PROVENANCE_MODULES
        if isinstance(block.get(module), Mapping)
    ]
    if len(present) != len(CONTRACT_PROVENANCE_MODULES):
        return ProvenanceKind.ABSENT.value
    if isinstance(block.get(PROJECTION_FIELDS_KEY), Mapping):
        return ProvenanceKind.PROJECTED.value
    if any(
        any(key in record for key in CONTRACT_RECORD_KEYS) for record in present
    ):
        return ProvenanceKind.PROJECTED.value
    return ProvenanceKind.ABSENT.value


def provenance_kind(block: Mapping[str, Any]) -> str:
    """Classify a provenance block as mapped, projected, or unrecognised.

    Reads the *shape*, never the content's meaning. See
    :func:`classify_provenance`.
    """

    return classify_provenance(block)


#: Keys that only a mapped (C0.4-A) module availability record carries.
AVAILABILITY_KEYS: tuple[str, ...] = (
    "has_available_source",
    "enabled_by_mapping",
    "declared_absent_fields",
)

#: Keys that only a contract provenance block carries.
CONTRACT_RECORD_KEYS: tuple[str, ...] = (
    "projection_method",
    "source_path",
    "timestamp",
)


def availability_from_field_records(
    fields: Mapping[str, Any],
    module_blocks: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Derive one availability record per module from a flat ``{field: record}`` map.

    A C0.4-A directory's ``provenance.json`` stores the per-field mapping records
    bare, without the per-module availability map the aggregate carries. The facts
    are still there — each field record names the asset it read and the mode it was
    mapped in, and each module's contract block states the module's own asset status
    — so the state can be recovered rather than invented:

    - ``asset_status`` is the module's own declared status when it declares one.
      That declaration wins, because it is the artifact speaking about itself: a
      capability module that says its capability is unavailable is unavailable, even
      though its fields were still mapped from the declared asset.
    - Failing that, ``asset_status`` is ``available`` when at least one field actually
      reads an asset (its mode is not ``not_available``).
    - ``asset_id`` is the first asset any of the module's fields cites, in id order.

    Nothing is assumed. A module whose fields cite no asset at all yields no record,
    so the caller sees the gap rather than a filled-in guess.
    """

    blocks = module_blocks if isinstance(module_blocks, Mapping) else {}

    per_module: dict[str, dict[str, Any]] = {}
    for key, record in fields.items():
        if not isinstance(record, Mapping):
            continue
        module = str(key).partition(".")[0]
        if module not in CONTRACT_PROVENANCE_MODULES:
            continue
        bucket = per_module.setdefault(
            module, {"assets": set(), "reads_an_asset": False, "modes": set()}
        )
        asset_id = str(record.get("asset_id", "")).strip()
        if asset_id and asset_id not in _NON_ASSET_MARKERS:
            bucket["assets"].add(asset_id)
        mode = str(record.get("mode", "")).strip()
        if mode:
            bucket["modes"].add(mode)
            if mode != "not_available":
                bucket["reads_an_asset"] = True

    records: dict[str, dict[str, Any]] = {}
    for module, bucket in per_module.items():
        assets = sorted(bucket["assets"])
        declared = blocks.get(module)
        declared_status = ""
        if isinstance(declared, Mapping):
            declared_status = str(declared.get("asset_status", "")).strip()

        if declared_status in ("available", "unavailable"):
            status = declared_status
        else:
            status = "available" if bucket["reads_an_asset"] else "unavailable"

        records[module] = {
            "asset_id": assets[0] if assets else "(none)",
            "asset_status": status,
            "has_available_source": status == "available",
            "asset_type": "",
            "asset_reason": "",
            # Which rule modes the module's fields were mapped in, so a caller can
            # see that every field was declared-absent rather than assumed present.
            "modes": sorted(bucket["modes"]),
            "derived_from_field_records": True,
        }
    return records


#: Values that stand in for "no asset".
_NON_ASSET_MARKERS = frozenset({"(none)", "", "none", "n/a"})


def _looks_like_availability_records(records: Mapping[str, Any]) -> bool:
    """Whether a ``modules`` map holds mapped availability records.

    Both shapes carry ``asset_status``, so that key cannot tell them apart. What can
    is the pair of keys only one of them has: an availability record states
    ``has_available_source``; a contract block states ``projection_method``.
    """

    for module in CONTRACT_PROVENANCE_MODULES:
        record = records.get(module)
        if not isinstance(record, Mapping):
            continue
        if any(key in record for key in CONTRACT_RECORD_KEYS):
            return False
        if any(key in record for key in AVAILABILITY_KEYS):
            return True
    return False


def _is_mapping_payload(value: Any) -> bool:
    """Whether a ``field_provenance`` value is the aggregate payload, not a flat map.

    The aggregate payload carries a ``fields`` map and a ``modules`` availability map.
    The C0.4-A *directory* file instead stores ``field_provenance`` as the bare
    ``{field: record}`` map, because the availability records sit beside it as the
    contract module blocks.
    """

    return (
        isinstance(value, Mapping)
        and isinstance(value.get("fields"), Mapping)
        and isinstance(value.get("modules"), Mapping)
    )


def normalize_provenance(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return a provenance block in the aggregate (C0.1) shape.

    Two directory layouts exist, and both nest the contract module blocks under
    ``modules``:

    - C0.4-A — ``{"modules": {<contract blocks>}, "field_provenance": {<field>: …}}``
    - C0.2 — ``{"modules": {<contract blocks>}, "fields": {<module>: {<field>: …}}}``

    The aggregate layout stores the module blocks at the top level with the payload
    inside::

        {<contract blocks>, "field_provenance": {"fields": …, "modules": …}}

    This function accepts all three and returns the aggregate form. It **moves and
    regroups what the artifact already says**; it never adds a value the artifact did
    not carry. A layout it does not recognise is passed through unchanged, so the
    caller sees the real shape rather than a guess.
    """

    if not isinstance(block, Mapping):
        raise InstanceProvenanceMissingError(
            "the instance carries no provenance block"
        )

    # Matching on the *content* of `modules`, not on the absence of the payload key:
    # the C0.4-A directory layout carries both, and keying off `field_provenance`
    # would misread it as an aggregate.
    modules = block.get("modules")
    if isinstance(modules, Mapping):
        nested = {
            str(key): dict(value)
            for key, value in modules.items()
            if key in CONTRACT_PROVENANCE_MODULES and isinstance(value, Mapping)
        }
        if len(nested) == len(CONTRACT_PROVENANCE_MODULES):
            normalized: dict[str, Any] = dict(nested)

            payload = block.get("field_provenance")
            if _is_mapping_payload(payload):
                normalized["field_provenance"] = payload
            elif isinstance(payload, Mapping):
                # A flat ``{field: record}`` map. It may already carry its own
                # availability records, or the module blocks beside it may be
                # availability records; whichever it is, use that and say so.
                inner = payload.get("modules")
                if isinstance(inner, Mapping) and _looks_like_availability_records(inner):
                    normalized["field_provenance"] = {
                        "fields": payload,
                        "modules": {str(key): value for key, value in inner.items()},
                        "rule_count": len(payload),
                    }
                elif _looks_like_availability_records(modules):
                    normalized["field_provenance"] = {
                        "fields": payload,
                        "modules": {
                            str(key): value for key, value in modules.items()
                        },
                        "rule_count": len(payload),
                    }
                else:
                    # Neither carries availability records, so recover them from the
                    # facts the field records and module blocks do carry, rather than
                    # filling the gap with a guess or leaving the state unjustifiable.
                    recovered = availability_from_field_records(payload, nested)
                    normalized["field_provenance"] = {
                        "fields": payload,
                        "modules": recovered,
                        "rule_count": len(payload),
                    }
            else:
                # C0.2 keeps its per-field records under a plain `fields` key. They
                # are projection records, not mapping traces, so they ride under the
                # loader's own key and are stripped before any schema check.
                fields = block.get("fields")
                if isinstance(fields, Mapping):
                    normalized[PROJECTION_FIELDS_KEY] = fields

            if isinstance(block.get("generated_by"), str):
                normalized["generated_by"] = block["generated_by"]
            return normalized

    return {str(key): value for key, value in block.items()}


def parse_provenance(
    raw: Mapping[str, Any],
    *,
    resolver: AssetReferenceResolver | None = None,
) -> InstanceProvenance:
    """Parse an instance's provenance block into frozen records.

    Accepts either artifact shape. Missing contract module entries are always
    fatal; a missing mapping payload is not, because a projected instance does not
    have one.
    """

    block = normalize_provenance(raw)

    missing_modules = [
        module for module in CONTRACT_PROVENANCE_MODULES if module not in block
    ]
    if missing_modules:
        raise InstanceProvenanceMissingError(
            "provenance is missing entries for: " + ", ".join(missing_modules),
            detail="a module with no provenance cannot be audited",
        )

    kind = classify_provenance(block)
    if kind == ProvenanceKind.ABSENT.value:
        raise InstanceProvenanceMissingError(
            "provenance is in no shape this loader recognises",
            detail=(
                "expected a mapped payload carrying fields and modules, or "
                "per-module contract records for all seven modules"
            ),
        )

    generated_by = str(block.get("generated_by", "")).strip()
    generator, generator_version, bundle_id, rule_count = _parse_generated_by(
        generated_by, kind
    )

    if kind == ProvenanceKind.MAPPED.value:
        payload = block["field_provenance"]
        traces = _parse_field_traces(payload)
        module_records = {
            str(k): v for k, v in payload["modules"].items()
        }
    else:
        traces = {}
        module_records = {
            module: dict(block[module]) for module in CONTRACT_PROVENANCE_MODULES
        }

    asset_refs = _resolve_assets(block, traces, module_records, resolver)

    return InstanceProvenance(
        kind=kind,
        generated_by=generated_by,
        bundle_id=bundle_id,
        factory_version=generator_version,
        mapping_version=generator_version,
        mapping_rule_count=rule_count,
        field_traces=traces,
        module_records=module_records,
        asset_references=asset_refs,
    )


def _parse_generated_by(value: str, kind: str) -> tuple[str, str, str, int]:
    """Split ``generated_by`` into generator, version, bundle id and rule count.

    A projected instance records no ``generated_by`` at all, so the loader reports
    that as not recorded rather than inventing a producer.
    """

    if not value:
        return NOT_RECORDED, NOT_RECORDED, NOT_RECORDED, 0
    match = _GENERATED_BY.match(value)
    if match is None:
        return value, NOT_RECORDED, NOT_RECORDED, 0
    rules = match.group("rules")
    return (
        match.group("generator"),
        match.group("generator_version"),
        match.group("bundle") or NOT_RECORDED,
        int(rules) if rules else 0,
    )


def _parse_field_traces(payload: Mapping[str, Any]) -> dict[str, FieldTrace]:
    """Parse the mapped payload's ``fields`` map, rejecting a corrupted record."""

    fields = payload.get("fields")
    if not isinstance(fields, Mapping) or not fields:
        raise InstanceProvenanceMissingError(
            "field_provenance carries no field records",
            detail="every instance field must be traceable to its origin",
        )

    traces: dict[str, FieldTrace] = {}
    for key, record in fields.items():
        field_name = str(key)
        if not isinstance(record, Mapping):
            raise InstanceProvenanceError(
                f"provenance record for {field_name!r} is not an object"
            )
        missing = [name for name in REQUIRED_TRACE_KEYS if name not in record]
        if missing:
            raise InstanceProvenanceError(
                f"provenance record for {field_name!r} is missing: "
                + ", ".join(missing),
                detail="a corrupted trace is reported, never repaired",
            )
        for name in ("skill_id", "asset_id", "version", "rule_id", "mode"):
            if not str(record.get(name, "")).strip():
                raise InstanceProvenanceError(
                    f"provenance record for {field_name!r} has an empty {name}"
                )
        module, _, _path = field_name.partition(".")
        traces[field_name] = FieldTrace(
            field=field_name,
            module=module,
            skill_id=str(record["skill_id"]),
            asset_id=str(record["asset_id"]),
            version=str(record["version"]),
            rule_id=str(record["rule_id"]),
            mode=str(record["mode"]),
            skill_type=str(record.get("skill_type", "")),
        )
    return traces


def _resolve_assets(
    block: Mapping[str, Any],
    traces: Mapping[str, FieldTrace],
    module_records: Mapping[str, Any],
    resolver: AssetReferenceResolver | None,
) -> dict[str, AssetReference]:
    """Resolve every cited asset id to a reference, without reading its content."""

    asset_ids = list(collect_asset_ids(block, module_records))
    if resolver is None:
        # No registry available: record the references as unresolved rather than
        # inventing a status for them.
        return {
            asset_id: AssetReference(
                asset_id=asset_id,
                asset_type="",
                asset_status="not_resolved",
                reason="no_asset_registry_supplied",
                registered=False,
            )
            for asset_id in asset_ids
        }

    skill_by_asset: dict[str, str] = {}
    version_by_asset: dict[str, str] = {}
    for trace in traces.values():
        if trace.asset_id and trace.asset_id not in skill_by_asset:
            skill_by_asset[trace.asset_id] = trace.skill_id
            version_by_asset[trace.asset_id] = trace.version

    return {
        asset_id: resolver.resolve(
            asset_id,
            skill_id=skill_by_asset.get(asset_id, ""),
            version=version_by_asset.get(asset_id, ""),
        )
        for asset_id in asset_ids
    }


def contract_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return only what the C0.1 contract declares, for schema validation.

    :func:`normalize_provenance` may carry a C0.2 layout's per-field projection
    records under :data:`PROJECTION_FIELDS_KEY`. The contract's provenance object
    admits a fixed set of keys, so those records are withheld here and exposed to the
    caller separately — the loader never presents a key the schema would reject.
    """

    return {
        str(key): value
        for key, value in block.items()
        if key != PROJECTION_FIELDS_KEY
    }


def projection_fields(block: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a C0.2 block's per-field projection records, or an empty mapping."""

    if not isinstance(block, Mapping):
        return {}
    fields = block.get(PROJECTION_FIELDS_KEY)
    return fields if isinstance(fields, Mapping) else {}


# --------------------------------------------------------------------------
# Tracing
# --------------------------------------------------------------------------


def trace_instance(
    loaded: Any,
    *,
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return the full provenance chain for a loaded instance, or for some fields.

    The chain has four steps. The first is reported as unrecorded, because the
    request belongs to the composing process and the loader will not invent one.
    A step the artifact shape does not carry at all is reported as not applicable,
    which is different from unrecorded.
    """

    provenance = getattr(loaded, "provenance", None)
    if not isinstance(provenance, InstanceProvenance):
        raise InstanceProvenanceError("trace_instance requires a loaded instance")

    requested = (
        list(fields) if fields is not None else sorted(provenance.field_traces)
    )

    chains: list[dict[str, Any]] = []
    for field_name in requested:
        trace = provenance.trace(field_name)
        chains.append(_chain_for(trace, provenance))

    mapped = provenance.kind == ProvenanceKind.MAPPED.value

    return {
        "instance_id": getattr(loaded, "instance_id", ""),
        "source_path": str(getattr(loaded, "source_path", "")),
        "kind": provenance.kind,
        "steps": ["request", "skill_bundle", "asset", "instance_field"],
        "recorded_steps": _recorded_steps(provenance),
        "chains": chains,
        "field_count": len(chains),
        # `complete` answers one question only: is every requested chain whole? It is
        # None when the artifact carries no field chains at all, because "there is
        # nothing to trace" and "everything is traced" are different facts and a
        # caller must not read the second from the first.
        "complete": (
            all(chain["complete"] for chain in chains) if chains else None
        ),
        "traced": mapped and bool(chains),
        "detail": (
            "field-level traces present"
            if mapped
            else (
                "this instance carries projected provenance: provenance is recorded "
                "per module, and no field-level chain exists to trace"
            )
        ),
    }


def _chain_for(trace: FieldTrace, provenance: InstanceProvenance) -> dict[str, Any]:
    reference = provenance.asset_references.get(trace.asset_id)
    asset_step: dict[str, Any] = {
        "asset_id": trace.asset_id,
        "recorded": trace.asset_id not in ("", "(none)"),
        "resolved": reference.resolvable if reference is not None else False,
        "status": reference.asset_status if reference is not None else "not_resolved",
    }
    if reference is not None:
        asset_step["asset_type"] = reference.asset_type
        asset_step["reason"] = reference.reason

    return {
        "field": trace.field,
        "module": trace.module,
        "complete": (
            trace.skill_id != ""
            and trace.rule_id != ""
            and trace.version != ""
        ),
        "request": {
            "recorded": False,
            "detail": (
                "the originating CreatorRequest is not stored in the instance "
                "artifact; it belongs to the composing process"
            ),
        },
        "skill_bundle": {
            "recorded": provenance.bundle_id != NOT_RECORDED,
            "bundle_id": provenance.bundle_id,
        },
        "skill": {
            "recorded": True,
            "skill_id": trace.skill_id,
            "skill_type": trace.skill_type,
            "version": trace.version,
        },
        "asset": asset_step,
        "mapping": {
            "recorded": True,
            "rule_id": trace.rule_id,
            "mode": trace.mode,
            "mapping_version": provenance.mapping_version,
        },
        "instance_field": {"recorded": True, "field": trace.field},
    }


def _recorded_steps(provenance: InstanceProvenance) -> dict[str, bool]:
    if provenance.kind == ProvenanceKind.MAPPED.value:
        return {
            "request": False,
            "skill_bundle": provenance.bundle_id != NOT_RECORDED,
            "asset": bool(provenance.asset_references),
            "instance_field": bool(provenance.field_traces),
        }
    return {
        "request": False,
        "skill_bundle": False,
        "asset": bool(provenance.asset_references),
        "instance_field": False,
    }


def untraced_fields(loaded: Any) -> tuple[str, ...]:
    """Instance fields present in the document but absent from a mapped trace.

    Returns the gap rather than raising, so a caller can decide whether an
    untraceable field is fatal. :mod:`creator_loader.validation` treats it as fatal
    for a *mapped* instance only: a projected instance has no field traces by
    construction, and reporting all 46 fields as "untraced" would be noise, not a
    finding.
    """

    modules = getattr(loaded, "modules", {})
    provenance = getattr(loaded, "provenance", None)
    if not isinstance(provenance, InstanceProvenance):
        return ()
    if provenance.kind != ProvenanceKind.MAPPED.value:
        return ()
    traced = set(provenance.field_traces)
    untraced: list[str] = []
    for module, document in modules.items():
        if not isinstance(document, Mapping):
            continue
        for field_name in document:
            key = f"{module}.{field_name}"
            if key not in traced:
                untraced.append(key)
    return tuple(sorted(untraced))


def untraced_projection_fields(loaded: Any) -> tuple[str, ...]:
    """Modules a *projected* instance fails to record a source for.

    A projected artifact's provenance is per module, so the gap this reports is a
    module whose record carries no evidence at all — not the per-field gap a mapped
    artifact would be judged on, which the projected shape never claimed to fill.
    """

    modules = getattr(loaded, "modules", {})
    provenance = getattr(loaded, "provenance", None)
    if not isinstance(provenance, InstanceProvenance):
        return ()
    if provenance.kind != ProvenanceKind.PROJECTED.value:
        return ()
    evidence_keys = ("source", "source_path", "projection_method", "asset_status")
    unrecorded: list[str] = []
    for module in modules:
        record = provenance.module_records.get(module)
        if not isinstance(record, Mapping) or not any(
            str(record.get(key, "")).strip() for key in evidence_keys
        ):
            unrecorded.append(module)
    return tuple(sorted(unrecorded))


__all__ = [
    "AVAILABILITY_KEYS",
    "CONTRACT_PROVENANCE_MODULES",
    "CONTRACT_RECORD_KEYS",
    "MAPPING_TRACE_KEYS",
    "NOT_APPLICABLE",
    "NOT_RECORDED",
    "PROJECTION_FIELDS_KEY",
    "PROJECTION_TRACE_KEYS",
    "REQUIRED_TRACE_KEYS",
    "availability_from_field_records",
    "classify_provenance",
    "contract_block",
    "normalize_provenance",
    "parse_provenance",
    "projection_fields",
    "provenance_kind",
    "trace_instance",
    "untraced_fields",
    "untraced_projection_fields",
]
