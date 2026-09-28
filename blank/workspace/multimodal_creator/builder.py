"""Construct multimodal artifacts from caller-supplied structural observations.

The builder is deliberately mechanical: it maps each observation onto the
contract's family/kind table and emits records. It performs no perception, so
"Phase M1 does not generate images or train models" is a property of the code,
not a promise in a document.

Design constraints honoured here
--------------------------------
* **Additive, never destructive.** :func:`build_multimodal_artifact` starts from
  a base text artifact and *adds* families. It never rewrites the text signals,
  which is what keeps older artifacts and older consumers working.
* **Two-way compatibility.** :func:`merge_multimodal_artifact` asserts the
  merged result still validates against the *baseline* text-only schema, so a
  multimodal artifact remains a legal text artifact.
* **Layout stands alone.** Layout records are emitted from ``layout_patterns``
  directly, never derived from a cross-modal record.
* **Plugins interpret.** :func:`merge_creator_extension` attaches domain meaning
  and is rejected if it tries to redefine universal vocabulary.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.schema_validation import validate_schema_instance

from .roles import SourceStructure
from .taxonomy import (
    LAYER_UNIVERSAL,
    MULTIMODAL_CONTRACT_VERSION,
    PLUGIN_MAY_NOT_REDEFINE,
    SIGNAL_BINDING,
    StructuralObservation,
    VisualSignal,
    MultimodalContractError,
)

#: Evidence reported when an observation's own evidence set is empty. Never
#: ``ocr_text``: the builder refuses to manufacture transcription-grounded
#: structure.
_FALLBACK_EVIDENCE = ("region_geometry",)

#: The observation fields each signal needs before the builder will emit a
#: record for it. A signal whose requirement is absent is skipped rather than
#: defaulted, because emitting a record with a placeholder class would be
#: claiming a visual regularity that was never observed. ``regions`` is required
#: by the region-bearing signals; ``None`` means the signal needs no extra field.
SIGNAL_REQUIREMENTS: Mapping[VisualSignal, tuple[str, ...]] = {
    VisualSignal.VISUAL_TEMPLATE: ("regions",),
    VisualSignal.LAYOUT_PATTERN: ("regions", "layout_template_class"),
    VisualSignal.COMPOSITION_PATTERN: ("density",),
    VisualSignal.COLOR_PATTERN: ("palette_relation",),
    VisualSignal.TYPOGRAPHY_PATTERN: ("type_scale_relation",),
    VisualSignal.SUBJECT_PATTERN: ("subject_class",),
    VisualSignal.IMAGE_ASSET_PATTERN: ("placement",),
    VisualSignal.CHART_PATTERN: ("chart_class",),
    VisualSignal.COVER_PATTERN: ("cover_role",),
}

#: Signals emitted when a caller does not name any. This is the broad structural
#: set that a layout-rich observation can justify; each is still gated by
#: ``SIGNAL_REQUIREMENTS``, so naming them cannot manufacture evidence.
DEFAULT_SIGNALS: tuple[VisualSignal, ...] = (
    VisualSignal.VISUAL_TEMPLATE,
    VisualSignal.COMPOSITION_PATTERN,
    VisualSignal.COLOR_PATTERN,
    VisualSignal.TYPOGRAPHY_PATTERN,
    VisualSignal.SUBJECT_PATTERN,
    VisualSignal.IMAGE_ASSET_PATTERN,
    VisualSignal.CHART_PATTERN,
    VisualSignal.COVER_PATTERN,
)


def signal_is_supported(
    observation: StructuralObservation, signal: VisualSignal
) -> bool:
    """True when the observation actually carries what the signal requires."""

    for field_name in SIGNAL_REQUIREMENTS.get(signal, ()):
        value = getattr(observation, field_name, None)
        if value is None or value == () or value == []:
            return False
    return True


def _unique(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def _evidence(observation: StructuralObservation) -> list[str]:
    kinds = [kind for kind in observation.evidence_kinds]
    return _unique(kinds) or list(_FALLBACK_EVIDENCE)


def _base_record(
    observation: StructuralObservation,
    *,
    pattern_id: str,
    family_field: str,
    kind_field: str,
    kind_value: str,
    origin: str,
) -> dict[str, Any]:
    return {
        "pattern_id": pattern_id,
        kind_field: kind_value,
        "evidence_kinds": _evidence(observation),
        "source_ids": [observation.source_id],
        "structural_recurrence": observation.recurrence,
        "confidence": observation.confidence,
        "origin": origin,
        "layer": LAYER_UNIVERSAL,
    }


def observation_to_records(
    observation: StructuralObservation,
    *,
    signal: VisualSignal,
    index: int = 0,
    origin: str = "common",
) -> list[tuple[str, dict[str, Any]]]:
    """Map one observation onto ``(family, record)`` pairs.

    Returns a list because a single observation may legitimately justify more
    than one family — the same reason a single source carries multiple roles.
    """

    if signal not in SIGNAL_BINDING:
        raise MultimodalContractError(f"unknown visual signal {signal!r}")
    family, kind_field, kind_value = SIGNAL_BINDING[signal]
    pattern_id = f"{observation.observation_id}:{signal.value}:{index}"
    origin = origin if origin in {"common", "framework"} else "common"

    if family == "visual_patterns":
        record = _base_record(
            observation,
            pattern_id=pattern_id,
            family_field=family,
            kind_field=kind_field,
            kind_value=kind_value,
            origin=origin,
        )
        # ``observation_kind`` records the named *signal* that justified this
        # record, while the type field records what the family stores. Keeping
        # both makes the trace from named signal to stored artifact
        # machine-checkable.
        record["observation_kind"] = signal.value
        record["roles"] = list(observation.roles)
        if observation.regions:
            record["regions"] = [deepcopy(dict(region)) for region in observation.regions]
            record["evidence_kinds"] = _unique(
                list(record["evidence_kinds"]) + ["region_layout"]
            )
        if observation.alignment:
            record["alignment"] = observation.alignment
        if observation.density:
            record["density"] = observation.density
        if observation.palette_relation:
            record["palette_relation"] = observation.palette_relation
        if observation.type_scale_relation:
            record["type_scale_relation"] = observation.type_scale_relation
        return [(family, record)]

    if family == "asset_patterns":
        record = _base_record(
            observation,
            pattern_id=pattern_id,
            family_field=family,
            kind_field=kind_field,
            kind_value=kind_value,
            origin=origin,
        )
        record["observation_kind"] = signal.value
        record["recurrence"] = observation.recurrence
        record.pop("structural_recurrence", None)
        if observation.subject_class:
            record["subject_class"] = observation.subject_class
        if observation.chart_class:
            record["chart_class"] = observation.chart_class
        if observation.cover_role:
            record["cover_role"] = observation.cover_role
        if observation.asset_reuse:
            record["asset_reuse"] = observation.asset_reuse
        if observation.aspect_band:
            record["aspect_band"] = observation.aspect_band
        if observation.placement:
            record["placement"] = observation.placement
        if kind_value == "chart_pattern" and "chart_class" not in record:
            record["chart_class"] = "none"
        return [(family, record)]

    raise MultimodalContractError(
        f"{signal.value!r} is a cross-modal signal and needs both a text and a "
        "visual anchor; use build_cross_modal_records"
    )


def build_layout_records(
    observation: StructuralObservation,
    *,
    index: int = 0,
    origin: str = "common",
) -> list[tuple[str, dict[str, Any]]]:
    """Emit a ``layout_patterns`` record: space without any text anchor."""

    if not observation.layout_template_class:
        raise MultimodalContractError(
            f"observation {observation.observation_id!r} has no layout_template_class; "
            "a layout pattern cannot be inferred from text"
        )
    regions = [deepcopy(dict(region)) for region in observation.regions]
    ids = _unique(str(region.get("region_id")) for region in regions)
    record: dict[str, Any] = {
        "pattern_id": f"{observation.observation_id}:layout_pattern:{index}",
        "visual_pattern_type": "layout_template",
        "observation_kind": "layout_pattern",
        "template_class": observation.layout_template_class,
        "region_grid": {
            "columns": max(1, len(ids)),
            "rows": 1,
            "regions": regions,
        },
        "reading_order": ids,
        "evidence_kinds": _evidence(observation),
        "source_ids": [observation.source_id],
        "recurrence": observation.recurrence,
        "confidence": observation.confidence,
        "origin": origin if origin in {"common", "framework"} else "common",
        "layer": LAYER_UNIVERSAL,
    }
    if observation.alignment:
        record["alignment"] = observation.alignment
    if observation.density:
        record["density"] = observation.density
    return [("layout_patterns", record)]


def build_cross_modal_records(
    *,
    text_signal: str,
    text_role: str,
    relation: str,
    visual_family: str,
    visual_pattern_id: str,
    visual_evidence: Sequence[str],
    source_ids: Sequence[str],
    cross_modal_type: str = "text_visual_alignment",
    page_sequence: Sequence[Mapping[str, Any]] | None = None,
    excerpt: str | None = None,
    confidence: float = 0.6,
    origin: str = "common",
    index: int = 0,
) -> list[tuple[str, dict[str, Any]]]:
    """Build a cross-modal record joining one text anchor to one visual anchor.

    The record carries *both* anchors by construction, so a cross-modal claim
    can never be made about text alone or vision alone.
    """

    from .taxonomy import ALL_EVIDENCE_KINDS, TEXT_SIGNALS, TEXT_SIGNAL_ALIASES

    canonical = TEXT_SIGNAL_ALIASES.get(text_signal, text_signal)
    if canonical not in TEXT_SIGNALS:
        raise MultimodalContractError(
            f"cross-modal text_signal must be one of {list(TEXT_SIGNALS)!r}, "
            f"got {text_signal!r}"
        )
    if visual_family not in {"visual_patterns", "layout_patterns", "asset_patterns"}:
        raise MultimodalContractError(
            f"cross-modal visual_family must name a visual family, got {visual_family!r}"
        )
    evidence = [kind for kind in visual_evidence if kind in ALL_EVIDENCE_KINDS]
    if not evidence:
        raise MultimodalContractError(
            "cross-modal record needs visual evidence; text alone cannot ground it"
        )

    text_anchor: dict[str, Any] = {"text_signal": canonical, "text_role": text_role}
    if excerpt:
        text_anchor["excerpt"] = excerpt

    record: dict[str, Any] = {
        "pattern_id": f"{canonical}:{cross_modal_type}:{index}",
        "cross_modal_type": cross_modal_type,
        "relation": relation,
        "text_anchor": text_anchor,
        "visual_anchor": {
            "family": visual_family,
            "pattern_id": visual_pattern_id,
            "evidence_kinds": evidence,
        },
        "source_ids": list(source_ids),
        "confidence": confidence,
        "origin": origin if origin in {"common", "framework"} else "common",
        "layer": LAYER_UNIVERSAL,
    }
    if page_sequence:
        record["page_sequence"] = [deepcopy(dict(page)) for page in page_sequence]
    return [("cross_modal_patterns", record)]


def build_multimodal_envelope(
    structures: Sequence[SourceStructure],
    *,
    visual_capability: str = "contract_only",
    motif_policy: str = "aggregate_only",
) -> dict[str, Any]:
    """Build the envelope that declares which roles each source carries."""

    if visual_capability not in {"contract_only", "observed"}:
        raise MultimodalContractError(
            f"visual_capability must be contract_only or observed, got {visual_capability!r}"
        )
    return {
        "contract_version": MULTIMODAL_CONTRACT_VERSION,
        "visual_capability": visual_capability,
        "motif_policy": motif_policy,
        "geometry_units": "normalized_xywh",
        "source_roles": [structure.as_envelope_entry() for structure in structures],
    }


def build_multimodal_artifact(
    base_artifact: Mapping[str, Any],
    *,
    structures: Sequence[SourceStructure],
    observations: Sequence[StructuralObservation] = (),
    signals: Sequence[VisualSignal] = (),
    cross_modal: Sequence[Mapping[str, Any]] = (),
    visual_capability: str = "contract_only",
) -> dict[str, Any]:
    """Additive build: base text artifact plus the four multimodal families.

    ``base_artifact`` is left untouched. When no observation is supplied the
    result is a contract-only artifact: the extension surface exists and
    validates, but no visual structure is claimed. That is exactly the Phase M1
    deliverable — a protocol, not a capability.
    """

    artifact = deepcopy(dict(base_artifact))
    artifact["multimodal_envelope"] = build_multimodal_envelope(
        structures, visual_capability=visual_capability
    )
    for family in (
        "visual_patterns",
        "layout_patterns",
        "asset_patterns",
        "cross_modal_patterns",
    ):
        artifact[family] = []

    requested = list(signals)
    if not requested:
        requested = list(DEFAULT_SIGNALS)

    for observation in observations:
        for index, signal in enumerate(requested):
            if signal in (
                VisualSignal.TEXT_VISUAL_ALIGNMENT,
                VisualSignal.HOOK_VISUAL_ALIGNMENT,
                VisualSignal.PAGE_SEQUENCE_PATTERN,
            ):
                continue
            if not signal_is_supported(observation, signal):
                continue
            for family, record in observation_to_records(
                observation, signal=signal, index=index
            ):
                artifact[family].append(record)
        if observation.layout_template_class:
            for family, record in build_layout_records(observation):
                artifact[family].append(record)

    for entry in cross_modal:
        payload = dict(entry)
        builder = payload.pop("builder", "text_visual_alignment")
        records = build_cross_modal_records(
            cross_modal_type=builder,
            **payload,
        )
        for family, record in records:
            artifact[family].append(record)

    return artifact


#: Directory holding both the baseline and the multimodal artifact schemas.
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

#: Basename of the unmodified text-only artifact schema.
BASELINE_SCHEMA_NAME = "unified_distillation_artifact.json"

#: The baseline text-signal fields. When a multimodal artifact also carries
#: these, its own values win during a merge so a broken core cannot be masked.
_TEXT_CORE_FIELDS = frozenset(
    {
        "artifact_version",
        "plugin",
        "topic_candidate",
        "content_template",
        "knowledge_unit",
        "style_pattern",
        "domain_extension",
        "risk_constraints",
        "evaluation_result",
    }
)


def _baseline_path(baseline_schema_path: str | Path | None) -> Path:
    return Path(baseline_schema_path or (SCHEMA_DIR / BASELINE_SCHEMA_NAME))


def project_text_core(
    artifact: Mapping[str, Any],
    *,
    baseline_schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Project a multimodal artifact onto the baseline text-only field set.

    The baseline schema declares ``additionalProperties: false``, so it is
    *sealed*: it cannot be extended with multimodal fields without editing it,
    which the Phase M1 isolation rules forbid. Compatibility therefore means
    something precise and checkable:

        a multimodal artifact, projected onto the baseline's own declared field
        set, still validates against the unmodified baseline schema.

    The projection is derived from the baseline schema itself, not hardcoded, so
    this proof cannot drift if the baseline ever changes.
    """

    baseline = _baseline_path(baseline_schema_path)
    if not baseline.is_file():
        raise MultimodalContractError(f"baseline artifact schema not found: {baseline}")
    try:
        schema = json.loads(baseline.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MultimodalContractError(f"baseline artifact schema is not JSON: {exc}") from exc
    declared = set(schema.get("properties", {}))
    return {key: deepcopy(value) for key, value in artifact.items() if key in declared}


def merge_multimodal_artifact(
    base_artifact: Mapping[str, Any],
    multimodal: Mapping[str, Any],
    *,
    baseline_schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge families into a base artifact and prove two-way compatibility.

    Two assertions are made:

    1. the artifact still validates against the **multimodal** schema, and
    2. its projection onto the baseline field set still validates against the
       **unmodified baseline** schema.

    If (2) ever fails, the multimodal track has broken the existing artifact
    contract and must be fixed rather than shipped.
    """

    merged = deepcopy(dict(base_artifact))
    for family in (
        "multimodal_envelope",
        "visual_patterns",
        "layout_patterns",
        "asset_patterns",
        "cross_modal_patterns",
        "creator_extension",
    ):
        if family in multimodal:
            merged[family] = deepcopy(multimodal[family])

    # ``multimodal`` is the artifact under test, so whenever it also carries a
    # text-core field that field wins. Without this, the base would silently
    # repair a broken text core and the compatibility proof below would pass on
    # data the caller never produced.
    for key, value in multimodal.items():
        if key not in merged or key in _TEXT_CORE_FIELDS:
            merged[key] = deepcopy(value)

    # A merge must not repair an incomplete text core. If the multimodal artifact
    # is missing a baseline field, fall back to the base for that field but
    # refuse the merge, because the result would no longer be a faithful
    # projection of what the multimodal run actually produced.
    repaired = [
        field
        for field in _TEXT_CORE_FIELDS
        if field not in multimodal and field in base_artifact
    ]
    if repaired:
        raise MultimodalContractError(
            "cannot merge: the multimodal artifact is missing baseline text-core "
            "fields that the base artifact would silently supply: "
            + ", ".join(sorted(repaired))
        )

    from .validation import validate_multimodal_artifact

    core = project_text_core(merged, baseline_schema_path=baseline_schema_path)
    try:
        validate_schema_instance(core, _baseline_path(baseline_schema_path), root_name="artifact")
    except Exception as exc:
        raise MultimodalContractError(
            "the text core of the merged artifact no longer validates against the "
            f"unmodified baseline schema: {exc}"
        ) from exc

    validate_multimodal_artifact(merged)
    return merged


def merge_creator_extension(
    artifact: Mapping[str, Any],
    *,
    plugin: str,
    domain_vocabulary: Mapping[str, Sequence[str]] | None = None,
    pattern_bindings: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Attach a Creator plugin's domain interpretation.

    The extension can explain what a structural pattern *means* in a domain. It
    cannot rename or extend the universal vocabulary, and it must acknowledge
    that constraint in ``may_not_redefine``.
    """

    from .validation import assert_creator_extension_is_interpretive

    merged = deepcopy(dict(artifact))
    merged["creator_extension"] = {
        "plugin": plugin,
        "domain_vocabulary": {
            key: list(values) for key, values in dict(domain_vocabulary or {}).items()
        },
        "pattern_bindings": [deepcopy(dict(binding)) for binding in pattern_bindings],
        "may_not_redefine": list(PLUGIN_MAY_NOT_REDEFINE),
    }
    assert_creator_extension_is_interpretive(merged["creator_extension"])
    return merged
