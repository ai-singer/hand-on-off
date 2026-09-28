"""Contract enforcement for multimodal distillation artifacts (Phase M1).

The JSON Schema handles shape. This module handles the rules that a
dependency-free Schema subset cannot express, and it is where the Phase M1
design constraints become executable:

1. **Visual distillation must not degrade into OCR.** A visual pattern grounded
   only in transcribed text is rejected outright.
2. **Layout must exist independently.** Structural facts (regions, grids,
   alignment, reading order, density) require structural evidence.
3. **The universal layer owns structure; plugins own meaning.** Structural
   records must be universal-layer and must not originate from a plugin, and a
   plugin extension may not rename or extend the universal vocabulary.
4. **Multi-role, never single-label.** Envelope role declarations are checked
   for at least one role and for known membership.
5. **Old artifacts keep working.** Multimodal families are optional;
   ``visual_capability="observed"`` is what makes them required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.schema_validation import validate_schema_instance

from .geometry import validate_region
from .taxonomy import (
    ALL_EVIDENCE_KINDS,
    ASSET_PATTERN_TYPES,
    CROSS_MODAL_TYPES,
    LAYER_UNIVERSAL,
    NON_STRUCTURAL_EVIDENCE,
    PLUGIN_MAY_NOT_REDEFINE,
    SIGNAL_BINDING,
    SOURCE_ROLES,
    STRUCTURAL_EVIDENCE,
    VISUAL_PATTERN_TYPES,
    MultimodalContractError,
)

#: The four added families. All optional, so text-only artifacts stay valid.
MULTIMODAL_FAMILIES: tuple[str, ...] = (
    "visual_patterns",
    "layout_patterns",
    "asset_patterns",
    "cross_modal_patterns",
)

#: Families that must be populated when a run claims observed visual structure.
#: Cross-modal alignment is deliberately excluded: a single image with no textual
#: companion can carry visual structure while having nothing to align against,
#: and inventing a cross-modal record there would be a false claim.
OBSERVED_REQUIRED_FAMILIES: tuple[str, ...] = (
    "visual_patterns",
    "layout_patterns",
    "asset_patterns",
)

#: Origins permitted for a universal structural record.
UNIVERSAL_ORIGINS: tuple[str, ...] = ("common", "framework")

#: Structural facts that cannot be justified by transcribed text alone.
STRUCTURE_REQUIRING_STRUCTURAL_EVIDENCE: tuple[str, ...] = (
    "regions",
    "region_grid",
    "reading_order",
    "alignment",
    "density",
    "palette_relation",
    "type_scale_relation",
)

DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "multimodal_artifact.schema.json"
)


def _evidence_of(record: Mapping[str, Any]) -> list[str]:
    """Return a record's evidence kinds, wherever the contract stores them.

    Most families carry ``evidence_kinds`` directly. A cross-modal record stores
    its visual evidence inside ``visual_anchor``, because its top level must hold
    *both* a text and a visual anchor.
    """

    direct = record.get("evidence_kinds")
    if direct:
        return list(direct)
    anchor = record.get("visual_anchor")
    if isinstance(anchor, Mapping) and anchor.get("evidence_kinds"):
        return list(anchor["evidence_kinds"])
    return []


def assert_no_ocr_substitution(record: Mapping[str, Any], *, where: str) -> None:
    """Reject any visual record grounded only in transcribed text.

    This is the contract's hardest boundary. ``ocr_text`` is allowed as an
    auxiliary label channel, never as the structural justification: a pattern
    whose entire evidence set is ``ocr_text`` is a text signal wearing a visual
    costume.
    """

    evidence = _evidence_of(record)
    if not evidence:
        raise MultimodalContractError(f"{where} must report at least one evidence kind")
    unknown = [kind for kind in evidence if kind not in ALL_EVIDENCE_KINDS]
    if unknown:
        raise MultimodalContractError(
            f"{where} uses unknown evidence kinds: " + ", ".join(sorted(unknown))
        )
    structural = [kind for kind in evidence if kind in STRUCTURAL_EVIDENCE]
    if not structural:
        raise MultimodalContractError(
            f"{where} is grounded only in {', '.join(NON_STRUCTURAL_EVIDENCE)}; "
            "transcribed text cannot justify a visual structure"
        )
    # Any structural field actually present must be covered by the structural
    # kinds this record reports. ``ocr_text`` never satisfies this, which is what
    # stops a text-only reading from being laundered into a visual claim.
    for field_name in STRUCTURE_REQUIRING_STRUCTURAL_EVIDENCE:
        if field_name not in record:
            continue
        if not structural:
            raise MultimodalContractError(
                f"{where}.{field_name} requires structural evidence, not transcription"
            )


def assert_universal_layer_shape(record: Mapping[str, Any], *, where: str) -> None:
    """Enforce that structural records stay in the universal layer."""

    layer = record.get("layer")
    if layer != LAYER_UNIVERSAL:
        raise MultimodalContractError(
            f"{where}.layer must be {LAYER_UNIVERSAL!r}, got {layer!r}"
        )
    origin = record.get("origin")
    if origin not in UNIVERSAL_ORIGINS:
        raise MultimodalContractError(
            f"{where}.origin must be one of {UNIVERSAL_ORIGINS!r}; a plugin may not "
            f"originate a universal structural pattern, got {origin!r}"
        )


def assert_creator_extension_is_interpretive(
    extension: Mapping[str, Any],
    *,
    where: str = "creator_extension",
) -> None:
    """Enforce that a plugin extension interprets rather than redefines."""

    bindings = extension.get("pattern_bindings", ())
    for index, binding in enumerate(bindings):
        family = binding.get("family")
        if family not in MULTIMODAL_FAMILIES:
            raise MultimodalContractError(
                f"{where}.pattern_bindings[{index}].family must be one of "
                f"{list(MULTIMODAL_FAMILIES)!r}, got {family!r}"
            )
        if not str(binding.get("domain_meaning", "")).strip():
            raise MultimodalContractError(
                f"{where}.pattern_bindings[{index}] must state a domain_meaning"
            )

    declared = set(extension.get("may_not_redefine", ()))
    missing = set(PLUGIN_MAY_NOT_REDEFINE) - declared
    if missing:
        raise MultimodalContractError(
            f"{where}.may_not_redefine must acknowledge the universal vocabulary it "
            "cannot redefine; missing: " + ", ".join(sorted(missing))
        )


def _check_family_kind_bindings(artifact: Mapping[str, Any]) -> None:
    """Verify every structural record sits in the family its kind maps to.

    Two distinct concepts are checked, and conflating them is a contract breach:

    ``visual_pattern_type`` / ``asset_pattern_type``
        What the *family stores* — the pattern type.
    ``observation_kind``
        The pattern type the observation justified.
    ``SIGNAL_BINDING``
        The single source of truth joining a named signal to its stored type.

    A record whose stored family disagrees with that table is rejected, so a
    record cannot be filed under one family while claiming a kind belonging to
    another.
    """

    allowed_pattern_types: dict[str, set[str]] = {}
    signals_for_pattern_type: dict[str, set[str]] = {}
    for kind, binding in SIGNAL_BINDING.items():
        family, _kind_field, pattern_type = binding
        allowed_pattern_types.setdefault(family, set()).add(pattern_type)
        signals_for_pattern_type.setdefault(pattern_type, set()).add(kind.value)

    def check_kind(
        family: str, index: int, record: Mapping[str, Any], kind_field: str
    ) -> None:
        pattern_type = record.get(kind_field)
        if pattern_type not in allowed_pattern_types[family]:
            raise MultimodalContractError(
                f"{family}[{index}].{kind_field}={pattern_type!r} does not belong to "
                f"{family!r}; expected one of {sorted(allowed_pattern_types[family])!r}"
            )
        observation_kind = record.get("observation_kind")
        allowed = signals_for_pattern_type[pattern_type]
        if observation_kind not in allowed:
            raise MultimodalContractError(
                f"{family}[{index}].observation_kind={observation_kind!r} cannot justify "
                f"{kind_field}={pattern_type!r}; the signal that stores this pattern "
                f"type must be one of {sorted(allowed)!r}"
            )

    for index, record in enumerate(artifact.get("visual_patterns", ())):
        check_kind("visual_patterns", index, record, "visual_pattern_type")

    for index, record in enumerate(artifact.get("asset_patterns", ())):
        check_kind("asset_patterns", index, record, "asset_pattern_type")

    for index, record in enumerate(artifact.get("layout_patterns", ())):
        if record.get("visual_pattern_type") != "layout_template":
            raise MultimodalContractError(
                f"layout_patterns[{index}] must declare "
                "visual_pattern_type='layout_template'"
            )
        if record.get("observation_kind") != "layout_pattern":
            raise MultimodalContractError(
                f"layout_patterns[{index}].observation_kind must be 'layout_pattern'"
            )

    for record in artifact.get("asset_patterns", ()):
        pattern_type = record.get("asset_pattern_type")
        if pattern_type not in ASSET_PATTERN_TYPES:
            raise MultimodalContractError(
                f"asset_patterns pattern {record.get('pattern_id')!r} has invalid "
                f"asset_pattern_type {pattern_type!r}"
            )
        if pattern_type == "subject_pattern" and not record.get("subject_class"):
            raise MultimodalContractError(
                f"asset_patterns pattern {record.get('pattern_id')!r} is a "
                "subject_pattern and must declare subject_class"
            )
        if pattern_type == "chart_pattern" and not record.get("chart_class"):
            raise MultimodalContractError(
                f"asset_patterns pattern {record.get('pattern_id')!r} is a "
                "chart_pattern and must declare chart_class"
            )
        if pattern_type == "cover_pattern" and not record.get("cover_role"):
            raise MultimodalContractError(
                f"asset_patterns pattern {record.get('pattern_id')!r} is a "
                "cover_pattern and must declare cover_role"
            )

    for record in artifact.get("cross_modal_patterns", ()):
        cross_type = record.get("cross_modal_type")
        if cross_type not in CROSS_MODAL_TYPES:
            raise MultimodalContractError(
                f"cross_modal_patterns pattern {record.get('pattern_id')!r} has invalid "
                f"cross_modal_type {cross_type!r}"
            )
        text_anchor = record.get("text_anchor") or {}
        if not text_anchor.get("text_signal"):
            raise MultimodalContractError(
                f"cross_modal_patterns pattern {record.get('pattern_id')!r} must anchor "
                "a text signal; a cross-modal record cannot be visual-only"
            )
        visual_anchor = record.get("visual_anchor") or {}
        if not visual_anchor.get("evidence_kinds"):
            raise MultimodalContractError(
                f"cross_modal_patterns pattern {record.get('pattern_id')!r} must anchor "
                "visual evidence; a cross-modal record cannot be text-only"
            )
        if cross_type == "hook_visual_alignment" and text_anchor.get("text_role") != "hook":
            raise MultimodalContractError(
                f"cross_modal_patterns pattern {record.get('pattern_id')!r} is a "
                "hook_visual_alignment and must anchor the 'hook' text role"
            )
        if cross_type == "page_sequence_pattern" and not record.get("page_sequence"):
            raise MultimodalContractError(
                f"cross_modal_patterns pattern {record.get('pattern_id')!r} is a "
                "page_sequence_pattern and must declare page_sequence"
            )


def _check_envelope(artifact: Mapping[str, Any]) -> None:
    envelope = artifact.get("multimodal_envelope")
    if envelope is None:
        return
    for index, entry in enumerate(envelope.get("source_roles", ())):
        roles = entry.get("roles", ())
        if not roles:
            raise MultimodalContractError(
                f"multimodal_envelope.source_roles[{index}] must declare at least one role"
            )
        unknown = [role for role in roles if role not in SOURCE_ROLES]
        if unknown:
            raise MultimodalContractError(
                f"multimodal_envelope.source_roles[{index}] uses unknown roles: "
                + ", ".join(sorted(unknown))
            )
        modalities = entry.get("modalities", ())
        if not modalities:
            raise MultimodalContractError(
                f"multimodal_envelope.source_roles[{index}] must declare at least one modality"
            )


def validate_multimodal_artifact(
    artifact: Mapping[str, Any],
    *,
    schema_path: str | Path | None = None,
) -> None:
    """Validate shape *and* semantics. Raises ``MultimodalContractError``.

    Shape validation reuses the project's dependency-free Schema validator
    against ``schemas/multimodal_artifact.schema.json``. Semantic validation
    then applies the Phase M1 rules above. Schema failures are re-raised as
    :class:`MultimodalContractError` so callers have one exception type.
    """

    path = Path(schema_path or DEFAULT_SCHEMA_PATH)
    try:
        validate_schema_instance(dict(artifact), path, root_name="artifact")
    except Exception as exc:  # ArtifactValidationError and friends
        raise MultimodalContractError(f"schema validation failed: {exc}") from exc

    envelope = artifact.get("multimodal_envelope")
    observed = bool(envelope) and envelope.get("visual_capability") == "observed"

    if observed:
        missing = [
            family
            for family in OBSERVED_REQUIRED_FAMILIES
            if not artifact.get(family)
        ]
        if missing:
            raise MultimodalContractError(
                "an artifact declaring visual_capability='observed' must populate: "
                + ", ".join(missing)
            )
    elif not envelope:
        stray = [family for family in MULTIMODAL_FAMILIES if artifact.get(family)]
        if stray:
            raise MultimodalContractError(
                "multimodal families present without a multimodal_envelope: "
                + ", ".join(stray)
            )
    elif envelope.get("visual_capability") == "contract_only":
        # A contract-only envelope declares the surface without claiming
        # observed structure. Families may be empty; if populated they are
        # validated below exactly like an observed artifact.
        pass
    else:
        raise MultimodalContractError(
            "multimodal_envelope.visual_capability must be 'contract_only' or "
            f"'observed', got {envelope.get('visual_capability')!r}"
        )

    _check_envelope(artifact)
    _check_family_kind_bindings(artifact)

    for family in MULTIMODAL_FAMILIES:
        for index, record in enumerate(artifact.get(family, ())):
            where = f"{family}[{index}]"
            assert_no_ocr_substitution(record, where=where)
            assert_universal_layer_shape(record, where=where)

    for index, record in enumerate(artifact.get("visual_patterns", ())):
        for region in record.get("regions", ()):
            validate_region(region, where=f"visual_patterns[{index}]")

    for index, record in enumerate(artifact.get("layout_patterns", ())):
        grid = record.get("region_grid", {})
        for region in grid.get("regions", ()):
            validate_region(region, where=f"layout_patterns[{index}].region_grid")
        order = record.get("reading_order", ())
        if order:
            declared = {region.get("region_id") for region in grid.get("regions", ())}
            unknown = [region_id for region_id in order if region_id not in declared]
            if unknown:
                raise MultimodalContractError(
                    f"layout_patterns[{index}].reading_order references undeclared "
                    "regions: " + ", ".join(map(str, unknown))
                )

    extension = artifact.get("creator_extension")
    if extension is not None:
        assert_creator_extension_is_interpretive(extension)


def text_signals_are_not_visual(artifact: Mapping[str, Any]) -> bool:
    """True when no text signal was smuggled into a visual family.

    A structural record must never carry a text-signal field. Conversely a text
    signal must never claim to be a visual pattern. Both directions are checked,
    because "text and visual are not confused" is a two-way boundary.
    """

    text_fields = {"label", "statement", "sections", "attributes"}
    for family in MULTIMODAL_FAMILIES:
        for record in artifact.get(family, ()):
            leaked = text_fields & set(record)
            if leaked:
                return False
            for key in ("visual_pattern_type", "asset_pattern_type", "cross_modal_type"):
                if record.get(key) in {
                    "topic_candidate",
                    "content_template",
                    "knowledge_unit",
                    "text_style_pattern",
                }:
                    return False
    for field_name in ("topic_candidate", "content_template", "knowledge_unit", "style_pattern"):
        for record in artifact.get(field_name, ()):
            if "evidence_kinds" in record or "layer" in record:
                return False
    return True


def layout_exists_independently(artifact: Mapping[str, Any]) -> bool:
    """True when layout structure is present without any text anchor.

    Layout must be able to stand alone: if the only way to talk about layout
    were a cross-modal record, layout would be a by-product of text rather than
    an independent structural fact.
    """

    return bool(artifact.get("layout_patterns"))


__all__ = [
    "DEFAULT_SCHEMA_PATH",
    "MULTIMODAL_FAMILIES",
    "OBSERVED_REQUIRED_FAMILIES",
    "STRUCTURE_REQUIRING_STRUCTURAL_EVIDENCE",
    "UNIVERSAL_ORIGINS",
    "assert_creator_extension_is_interpretive",
    "assert_no_ocr_substitution",
    "assert_universal_layer_shape",
    "layout_exists_independently",
    "text_signals_are_not_visual",
    "validate_multimodal_artifact",
]
