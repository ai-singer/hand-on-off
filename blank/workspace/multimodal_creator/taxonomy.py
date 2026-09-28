"""Signal taxonomy for multimodal Creator distillation (Phase M1).

The taxonomy is split into two authority levels, and that split is the whole
point of this module:

``UNIVERSAL``
    Structure vocabulary. What a region is, what a layout template is, which
    structural evidence counts. A Creator plugin may *read* this and attach
    domain meaning, but may never extend or redefine it.

``PLUGIN``
    Domain interpretation. Which financial chart deserves attention, what a
    colour choice means for a finance audience. Free-form per plugin.

Every signal family is tagged with the authority that owns its *vocabulary*.
This is what makes "do not put all visual information into the plugin" a
checkable rule instead of a style preference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class MultimodalContractError(Exception):
    """Raised when data violates the multimodal distillation contract."""


class SignalFamily(str, Enum):
    """The four signal families of the contract, in fixed order."""

    TEXT = "text_signals"
    VISUAL = "visual_patterns"
    ASSET = "asset_patterns"
    CROSS_MODAL = "cross_modal_patterns"


class VisualSignal(str, Enum):
    """Named visual signal kinds, grouped exactly as the contract groups them."""

    # B. Visual signals
    VISUAL_TEMPLATE = "visual_template"
    LAYOUT_PATTERN = "layout_pattern"
    COMPOSITION_PATTERN = "composition_pattern"
    COLOR_PATTERN = "color_pattern"
    TYPOGRAPHY_PATTERN = "typography_pattern"

    # C. Asset signals
    SUBJECT_PATTERN = "subject_pattern"
    IMAGE_ASSET_PATTERN = "image_asset_pattern"
    CHART_PATTERN = "chart_pattern"
    COVER_PATTERN = "cover_pattern"

    # D. Cross-modal signals
    TEXT_VISUAL_ALIGNMENT = "text_visual_alignment"
    HOOK_VISUAL_ALIGNMENT = "hook_visual_alignment"
    PAGE_SEQUENCE_PATTERN = "page_sequence_pattern"


#: Text signals, preserved verbatim from the existing text-centric artifact.
#: ``style_pattern`` is the *stored field* name; the contract's taxonomy name is
#: ``text_style_pattern``. Both are accepted so existing artifacts keep working.
TEXT_SIGNALS: tuple[str, ...] = (
    "topic_candidate",
    "content_template",
    "knowledge_unit",
    "text_style_pattern",
)

#: Stored field name for each taxonomy text signal, where it differs.
TEXT_SIGNAL_STORAGE: Mapping[str, str] = {
    "text_style_pattern": "style_pattern",
}

TEXT_SIGNAL_ALIASES: Mapping[str, str] = {
    "style_pattern": "text_style_pattern",
}

#: Structural evidence: describes space, geometry, rhythm or visual encoding.
#: OCR word counts, reading strings and extracted lines are *not* here.
STRUCTURAL_EVIDENCE: tuple[str, ...] = (
    "region_layout",
    "region_geometry",
    "dominance_order",
    "color_distribution",
    "palette_relation",
    "type_scale_relation",
    "type_placement",
    "reading_order",
    "negative_space_ratio",
    "alignment_relation",
    "page_rhythm",
    "temporal_rhythm",
    "subject_salience",
    "chart_encoding",
)

#: Evidence that is transcription rather than structure. Permitted only as an
#: auxiliary label channel: never sufficient on its own to ground a visual
#: signal, because that would collapse visual distillation into OCR.
NON_STRUCTURAL_EVIDENCE: tuple[str, ...] = ("ocr_text",)

#: Roles a source may carry. The taxonomy name is the contract's term; the
#: legacy text-only material roles are the first two entries' text siblings.
SOURCE_ROLES: tuple[str, ...] = (
    "knowledge_source",
    "visual_style_source",
    "layout_source",
    "composition_source",
    "color_source",
    "typography_source",
    "subject_source",
    "chart_source",
    "cover_source",
    "sequence_source",
    "hook_source",
)

#: Maps the existing single-label material roles onto their multi-role
#: successors, so a legacy ``distillation_role`` still classifies sensibly.
LEGACY_ROLE_SUCCESSOR: Mapping[str, str] = {
    "topic_candidate": "knowledge_source",
    "content_template": "layout_source",
    "knowledge_unit": "knowledge_source",
    "style_pattern": "visual_style_source",
}

ALL_EVIDENCE_KINDS: tuple[str, ...] = STRUCTURAL_EVIDENCE + NON_STRUCTURAL_EVIDENCE

#: Closed universal vocabularies. Plugins may not add members to these.
REGION_ROLES: tuple[str, ...] = (
    "background",
    "header",
    "title",
    "subtitle",
    "body",
    "caption",
    "label",
    "subject",
    "logo",
    "watermark",
    "footer",
    "chart",
    "data_table",
    "annotation",
)

LAYOUT_TEMPLATE_CLASSES: tuple[str, ...] = (
    "single_column",
    "two_column",
    "three_card",
    "image_left_text_right",
    "image_top_text_bottom",
    "full_bleed_overlay",
    "grid_matrix",
    "list_stack",
    "timeline_band",
    "mixed_irregular",
)

VISUAL_PATTERN_TYPES: tuple[str, ...] = (
    "background_template",
    "layout_template",
    "composition_pattern",
    "color_pattern",
    "typography_pattern",
)

ASSET_PATTERN_TYPES: tuple[str, ...] = (
    "subject_pattern",
    "image_asset_pattern",
    "chart_pattern",
    "cover_pattern",
)

CROSS_MODAL_TYPES: tuple[str, ...] = (
    "text_visual_alignment",
    "hook_visual_alignment",
    "page_sequence_pattern",
)

#: Maps each signal kind onto the family field that stores it in the artifact,
#: plus the record's ``visual_pattern_type`` / ``observation_kind`` binding. A
#: record whose stored family disagrees with this table is a contract breach.
SIGNAL_BINDING: Mapping[VisualSignal, tuple[str, str, str]] = {
    VisualSignal.VISUAL_TEMPLATE: (
        "visual_patterns",
        "visual_pattern_type",
        "background_template",
    ),
    VisualSignal.LAYOUT_PATTERN: ("visual_patterns", "visual_pattern_type", "layout_template"),
    VisualSignal.COMPOSITION_PATTERN: (
        "visual_patterns",
        "visual_pattern_type",
        "composition_pattern",
    ),
    VisualSignal.COLOR_PATTERN: ("visual_patterns", "visual_pattern_type", "color_pattern"),
    VisualSignal.TYPOGRAPHY_PATTERN: (
        "visual_patterns",
        "visual_pattern_type",
        "typography_pattern",
    ),
    VisualSignal.SUBJECT_PATTERN: ("asset_patterns", "asset_pattern_type", "subject_pattern"),
    VisualSignal.IMAGE_ASSET_PATTERN: (
        "asset_patterns",
        "asset_pattern_type",
        "image_asset_pattern",
    ),
    VisualSignal.CHART_PATTERN: ("asset_patterns", "asset_pattern_type", "chart_pattern"),
    VisualSignal.COVER_PATTERN: ("asset_patterns", "asset_pattern_type", "cover_pattern"),
    VisualSignal.TEXT_VISUAL_ALIGNMENT: (
        "cross_modal_patterns",
        "cross_modal_type",
        "text_visual_alignment",
    ),
    VisualSignal.HOOK_VISUAL_ALIGNMENT: (
        "cross_modal_patterns",
        "cross_modal_type",
        "hook_visual_alignment",
    ),
    VisualSignal.PAGE_SEQUENCE_PATTERN: (
        "cross_modal_patterns",
        "cross_modal_type",
        "page_sequence_pattern",
    ),
}

SUBJECT_CLASSES: tuple[str, ...] = (
    "human_figure",
    "human_group",
    "product_object",
    "document_scan",
    "screenshot",
    "data_chart",
    "icon_symbol",
    "scene_environment",
    "abstract_texture",
    "text_only",
    "composite",
    "unknown",
)

CHART_CLASSES: tuple[str, ...] = (
    "bar",
    "line",
    "area",
    "pie_donut",
    "scatter",
    "table",
    "candlestick",
    "waterfall",
    "kpi_tile",
    "mixed",
    "none",
)

COVER_ROLES: tuple[str, ...] = (
    "series_cover",
    "article_cover",
    "chapter_divider",
    "end_card",
    "none",
)

ASSET_REUSE_STATES: tuple[str, ...] = ("recurring_family", "single_use", "unknown")

ASPECT_BANDS: tuple[str, ...] = (
    "portrait",
    "square",
    "landscape",
    "ultrawide",
    "mixed",
    "unknown",
)

PLACEMENTS: tuple[str, ...] = (
    "full_bleed",
    "background",
    "inset_upper",
    "inset_lower",
    "side_panel",
    "center_stage",
    "inline_with_text",
    "unknown",
)

ALIGNMENTS: tuple[str, ...] = ("left", "right", "center", "top", "bottom", "grid", "free", "none")
DENSITIES: tuple[str, ...] = ("sparse", "balanced", "dense")
PALETTE_RELATIONS: tuple[str, ...] = (
    "monochrome",
    "analogous",
    "complementary",
    "triadic",
    "high_contrast_accent",
    "muted",
    "mixed",
)
TYPE_SCALE_RELATIONS: tuple[str, ...] = (
    "single_level",
    "two_level",
    "three_plus_levels",
    "mixed",
)
ALIGNMENT_RELATIONS: tuple[str, ...] = (
    "reinforces",
    "contrasts",
    "illustrates",
    "labels",
    "duplicates",
    "replaces",
    "sequences",
    "unrelated",
)
SEQUENCE_ROLES: tuple[str, ...] = (
    "opener",
    "build",
    "turn",
    "proof",
    "summary",
    "cta",
    "interstitial",
)
TEXT_ROLES: tuple[str, ...] = ("hook", "title", "subtitle", "body", "caption", "label", "cta")
MODALITIES: tuple[str, ...] = ("textual", "visual", "temporal", "structured")

#: The single signal kind each cross-modal family is allowed to use. This keeps
#: "text and visual are not confused" machine-checkable: a cross-modal record
#: must anchor *both* a text signal and a visual family.
CROSS_MODAL_SIGNAL: Mapping[str, VisualSignal] = {
    "text_visual_alignment": VisualSignal.TEXT_VISUAL_ALIGNMENT,
    "hook_visual_alignment": VisualSignal.HOOK_VISUAL_ALIGNMENT,
    "page_sequence_pattern": VisualSignal.PAGE_SEQUENCE_PATTERN,
}

#: Maps a signal kind onto the artifact family that stores it. Derived from
#: ``SIGNAL_BINDING`` so the two can never drift apart.
SIGNAL_FAMILY_BY_KIND: Mapping[VisualSignal, SignalFamily] = {
    kind: SignalFamily(binding[0]) for kind, binding in SIGNAL_BINDING.items()
}

#: The ``layer`` value every structural pattern record must carry.
LAYER_UNIVERSAL = "universal"

#: Version of the Phase M1 multimodal contract surface.
MULTIMODAL_CONTRACT_VERSION = "m1.0.0"

#: Authority level per signal family. Plugins own domain meaning only.
PATTERN_LAYER: Mapping[SignalFamily, str] = {
    SignalFamily.VISUAL: "universal",
    SignalFamily.ASSET: "universal",
    SignalFamily.CROSS_MODAL: "universal",
    SignalFamily.TEXT: "universal",
}

#: Names a Creator plugin is forbidden from redefining in its extension.
PLUGIN_MAY_NOT_REDEFINE: tuple[str, ...] = (
    "visual_pattern_type",
    "asset_pattern_type",
    "cross_modal_type",
    "observation_kind",
    "evidence_kinds",
    "structural_evidence_vocabulary",
    "region_role_vocabulary",
    "layout_template_class_vocabulary",
    "layer",
)


@dataclass(frozen=True, slots=True)
class StructuralObservation:
    """One caller-supplied structural reading of one source.

    This is the single extension point that lets images and videos carry
    multiple signals without a new record type per medium. ``medium`` is
    ``image`` for a still and ``video`` for a temporal source; the geometry and
    evidence vocabularies are shared, while a video may additionally report
    ``temporal_rhythm`` and page-like sequence roles.

    No field here is extracted from pixels by this package. Producing these
    observations is a perception concern owned by a later phase.
    """

    observation_id: str
    medium: str
    source_id: str
    roles: Sequence[str]
    evidence_kinds: Sequence[str]
    regions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    layout_template_class: str | None = None
    alignment: str | None = None
    density: str | None = None
    palette_relation: str | None = None
    type_scale_relation: str | None = None
    subject_class: str | None = None
    chart_class: str | None = None
    cover_role: str | None = None
    asset_reuse: str | None = None
    aspect_band: str | None = None
    placement: str | None = None
    sequence_role: str | None = None
    recurrence: int = 1
    confidence: float = 0.6

    def __post_init__(self) -> None:
        if self.medium not in {"image", "video"}:
            raise MultimodalContractError(
                f"structural observation medium must be image or video, got {self.medium!r}"
            )
        if not self.roles:
            raise MultimodalContractError(
                f"observation {self.observation_id!r} must declare at least one source role"
            )
        if not self.evidence_kinds:
            raise MultimodalContractError(
                f"observation {self.observation_id!r} must report at least one evidence kind"
            )
        if self.medium == "image" and "temporal_rhythm" in self.evidence_kinds:
            raise MultimodalContractError(
                f"image observation {self.observation_id!r} cannot claim temporal_rhythm"
            )


def authority_of(kind: VisualSignal) -> str:
    """Return the authority level owning a signal kind's vocabulary."""

    return PATTERN_LAYER[SIGNAL_FAMILY_BY_KIND[kind]]


def canonical_text_signal(name: str) -> str:
    """Normalize a text signal name to its taxonomy form."""

    return TEXT_SIGNAL_ALIASES.get(name, name)


def storage_field_for(signal: str) -> str:
    """Return the artifact field that stores a taxonomy text signal."""

    return TEXT_SIGNAL_STORAGE.get(signal, signal)
