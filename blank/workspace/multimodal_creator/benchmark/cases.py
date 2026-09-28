"""Synthetic benchmark cases for the M2 prototype (30 cases in three groups).

These cases test **protocol and algorithm behaviour**, not model accuracy. Every
case is a controlled structural declaration — no image, no pixel, no text
content — so a failure points at the contract or the algorithm rather than at a
model's judgement.

Groups
------

**Layout cases (10)** — ``layout``
    Declared structure must extract to the expected layout class, region roles,
    and cross-modal anchor. Exercises the extraction prototype.

**Template similarity cases (10)** — ``template_similarity``
    Labeled pairs stating whether they belong to the same visual family, with a
    declared expected margin. Exercises the similarity contract.

**Cross-modal alignment cases (10)** — ``cross_modal_alignment``
    Text/visual region pairs with the geometric and semantic relation they must
    produce. Exercises geometric derivation and the anti-OCR boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..extraction.visual_sample import (
    RegionSpec,
    SampleProvenance,
    SubjectSpec,
    TextStyleSpec,
    VisualSample,
)

# --------------------------------------------------------------------------
# Shared structural helpers
# --------------------------------------------------------------------------


def region(
    region_id: str,
    role: str,
    x: float,
    y: float,
    w: float,
    h: float,
    layer: int = 0,
) -> RegionSpec:
    return RegionSpec(region_id, role, {"x": x, "y": y, "w": w, "h": h}, layer)


def jitter_box(box: Mapping[str, float], *, scale: float, shift: float) -> dict[str, float]:
    """Scale and shift a box inside the frame.

    Used to build "same family, different execution" variants: real creators
    repeat a layout without reproducing it pixel-for-pixel. The perturbation is
    fixed per case, never random.
    """

    x = box["x"] * scale + shift
    y = box["y"] * scale + shift
    w = box["w"] * scale
    h = box["h"] * scale
    # Keep the box inside the normalized frame after perturbation.
    x = min(max(x, 0.0), 1.0 - w)
    y = min(max(y, 0.0), 1.0 - h)
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _base_sample(
    sample_id: str,
    regions: Sequence[RegionSpec],
    *,
    creator: str,
    layout: str | None,
    color: str = "warm_red",
    palette: str = "high_contrast_accent",
    subject: str = "human_figure",
    salience: str = "subject_dominant",
    alignment: str | None = "left",
    density: str = "balanced",
    negative_space: str = "generous",
    placement: str = "side_panel",
    text_scale: str = "two_level",
    hierarchy: int = 2,
    chart_class: str | None = None,
    cover_role: str | None = None,
    media_kind: str = "image",
    media_role: str | None = None,
    text_region_ids: Sequence[str] = (),
    declared_relations: Mapping[str, str] | None = None,
    aspect_band: str = "portrait",
) -> VisualSample:
    return VisualSample(
        sample_id=sample_id,
        regions=tuple(regions),
        color_family=color,
        subject=SubjectSpec(subject, salience),
        provenance=SampleProvenance(creator),
        media_kind=media_kind,
        layout_template_class=layout,
        alignment=alignment,
        composition_density=density,
        negative_space=negative_space,
        palette_relation=palette,
        text_style=TextStyleSpec(text_scale, hierarchy),
        chart_class=chart_class,
        cover_role=cover_role,
        placement=placement,
        aspect_band=aspect_band,
        media_role=media_role,
        text_region_ids=tuple(text_region_ids),
        cross_modal_relations=dict(declared_relations or {}),
    )


# --------------------------------------------------------------------------
# Canonical layout region sets
# --------------------------------------------------------------------------

_BG_FULL = region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0)


def layout_left_text_right_image(prefix: str = "l1") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.06, 0.10, 0.40, 0.20, 1),
        region(f"{prefix}-body", "body", 0.06, 0.34, 0.40, 0.30, 1),
        region(f"{prefix}-img", "subject", 0.55, 0.10, 0.40, 0.60, 1),
    )


def layout_image_top_text_bottom(prefix: str = "l2") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-img", "subject", 0.10, 0.05, 0.80, 0.50, 1),
        region(f"{prefix}-title", "title", 0.10, 0.62, 0.80, 0.18, 1),
        region(f"{prefix}-body", "body", 0.10, 0.82, 0.80, 0.12, 1),
    )


def layout_three_card(prefix: str = "l3") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.05, 0.04, 0.90, 0.12, 1),
        region(f"{prefix}-c1", "body", 0.05, 0.22, 0.28, 0.55, 1),
        region(f"{prefix}-c2", "body", 0.36, 0.22, 0.28, 0.55, 1),
        region(f"{prefix}-c3", "body", 0.67, 0.22, 0.28, 0.55, 1),
    )


def layout_full_bleed_overlay(prefix: str = "l4") -> tuple[RegionSpec, ...]:
    return (
        region(f"{prefix}-img", "subject", 0.0, 0.0, 1.0, 1.0, 0),
        region(f"{prefix}-title", "title", 0.10, 0.38, 0.80, 0.18, 1),
        region(f"{prefix}-label", "label", 0.10, 0.60, 0.40, 0.08, 1),
    )


def layout_chart_with_caption(prefix: str = "l5") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.06, 0.05, 0.88, 0.12, 1),
        region(f"{prefix}-chart", "chart", 0.08, 0.20, 0.84, 0.52, 1),
        region(f"{prefix}-caption", "caption", 0.08, 0.76, 0.84, 0.10, 1),
    )


def layout_cover_with_logo(prefix: str = "l6") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-img", "subject", 0.0, 0.0, 1.0, 0.72, 0),
        region(f"{prefix}-title", "title", 0.08, 0.76, 0.70, 0.14, 1),
        region(f"{prefix}-logo", "logo", 0.82, 0.78, 0.12, 0.10, 1),
    )


def layout_data_table(prefix: str = "l7") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.06, 0.05, 0.88, 0.12, 1),
        region(f"{prefix}-table", "data_table", 0.08, 0.20, 0.84, 0.60, 1),
        region(f"{prefix}-foot", "footer", 0.08, 0.84, 0.84, 0.08, 1),
    )


def layout_two_column(prefix: str = "l8") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.05, 0.05, 0.90, 0.12, 1),
        region(f"{prefix}-left", "body", 0.05, 0.20, 0.43, 0.68, 1),
        region(f"{prefix}-right", "body", 0.52, 0.20, 0.43, 0.68, 1),
    )


def layout_list_stack(prefix: str = "l9") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.06, 0.05, 0.88, 0.12, 1),
        region(f"{prefix}-r1", "body", 0.06, 0.22, 0.88, 0.16, 1),
        region(f"{prefix}-r2", "body", 0.06, 0.42, 0.88, 0.16, 1),
        region(f"{prefix}-r3", "body", 0.06, 0.62, 0.88, 0.16, 1),
        region(f"{prefix}-r4", "body", 0.06, 0.82, 0.88, 0.10, 1),
    )


def layout_single_column(prefix: str = "l10") -> tuple[RegionSpec, ...]:
    return (
        _BG_FULL,
        region(f"{prefix}-title", "title", 0.08, 0.10, 0.84, 0.18, 1),
        region(f"{prefix}-body", "body", 0.08, 0.34, 0.84, 0.50, 1),
    )


# --------------------------------------------------------------------------
# Case record types
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LayoutCase:
    """A structure whose extraction result is known in advance."""

    case_id: str
    sample: VisualSample
    expected_layout_class: str
    expected_region_roles: tuple[str, ...]
    expected_text_region_count: int
    expected_visual_region_count: int
    expected_anchor_role: str | None
    expected_roles_include: tuple[str, ...] = ()
    expected_evidence_include: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": "layout",
            "sample_id": self.sample.sample_id,
            "expected_layout_class": self.expected_layout_class,
            "expected_region_roles": list(self.expected_region_roles),
        }


@dataclass(frozen=True, slots=True)
class SimilarityCase:
    """A labeled pair with the direction its similarity must take."""

    case_id: str
    left: VisualSample
    right: VisualSample
    same_family: bool
    note: str
    expected_min_score: float | None = None
    expected_max_score: float | None = None
    expected_codes_include: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": "template_similarity",
            "left": self.left.sample_id,
            "right": self.right.sample_id,
            "same_family": self.same_family,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class CrossModalCase:
    """A text/visual geometry whose derived relation is known in advance."""

    case_id: str
    sample: VisualSample
    expected_geometric_relation: str
    expected_semantic_relation: str
    expected_anchor_role: str
    declared: bool
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": "cross_modal_alignment",
            "sample_id": self.sample.sample_id,
            "expected_geometric_relation": self.expected_geometric_relation,
            "expected_semantic_relation": self.expected_semantic_relation,
            "declared": self.declared,
        }


# --------------------------------------------------------------------------
# Group 1 — layout cases (10)
# --------------------------------------------------------------------------


def layout_cases() -> tuple[LayoutCase, ...]:
    """Ten layouts spanning the closed template-class vocabulary."""

    def case(
        index: int,
        regions: Sequence[RegionSpec],
        layout_class: str,
        *,
        anchor: str | None,
        extra_roles: tuple[str, ...] = (),
        extra_evidence: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> LayoutCase:
        sample_id = f"L{index:02d}"
        sample = _base_sample(
            sample_id,
            regions,
            creator=f"creator-{index:02d}",
            layout=layout_class,
            **kwargs,
        )
        # Region roles are a multiset: three cards means three ``body`` roles.
        roles = tuple(region.role for region in regions)
        text_count = len(sample.text_regions())
        visual_count = len(sample.visual_regions())
        return LayoutCase(
            case_id=f"layout-{index:02d}-{layout_class}",
            sample=sample,
            expected_layout_class=layout_class,
            expected_region_roles=roles,
            expected_text_region_count=text_count,
            expected_visual_region_count=visual_count,
            expected_anchor_role=anchor,
            expected_roles_include=extra_roles,
            expected_evidence_include=extra_evidence,
        )

    return (
        case(
            1,
            layout_left_text_right_image("l1"),
            "image_left_text_right",
            anchor="subject",
            extra_roles=("hook_source",),
            extra_evidence=("reading_order",),
        ),
        case(
            2,
            layout_image_top_text_bottom("l2"),
            "image_top_text_bottom",
            anchor="subject",
            extra_evidence=("reading_order",),
        ),
        case(
            3,
            layout_three_card("l3"),
            "three_card",
            anchor="background",
            extra_evidence=("type_placement",),
        ),
        case(
            4,
            layout_full_bleed_overlay("l4"),
            "full_bleed_overlay",
            anchor="subject",
            extra_evidence=("dominance_order",),
            density="dense",
            negative_space="tight",
        ),
        case(
            5,
            layout_chart_with_caption("l5"),
            "single_column",
            anchor="chart",
            extra_roles=("chart_source",),
            extra_evidence=("chart_encoding",),
            subject="data_chart",
        ),
        case(
            6,
            layout_cover_with_logo("l6"),
            "full_bleed_overlay",
            anchor="subject",
            extra_roles=("cover_source",),
            cover_role="article_cover",
            placement="full_bleed",
        ),
        case(
            7,
            layout_data_table("l7"),
            "single_column",
            anchor="data_table",
            extra_evidence=("reading_order",),
            subject="document_scan",
        ),
        case(
            8,
            layout_two_column("l8"),
            "two_column",
            anchor="background",
            extra_evidence=("reading_order",),
            density="dense",
        ),
        case(
            9,
            layout_list_stack("l9"),
            "list_stack",
            anchor="background",
            density="dense",
        ),
        case(
            10,
            layout_single_column("l10"),
            "single_column",
            anchor="background",
            extra_evidence=("reading_order",),
            text_scale="three_plus_levels",
            hierarchy=3,
        ),
    )


# --------------------------------------------------------------------------
# Group 2 — template similarity cases (10)
# --------------------------------------------------------------------------


def similarity_cases() -> tuple[SimilarityCase, ...]:
    """Ten labeled pairs: five same-family, four different-family, one near-miss."""

    def sample(
        sample_id: str,
        regions: Sequence[RegionSpec],
        creator: str,
        **kwargs: Any,
    ) -> VisualSample:
        return _base_sample(sample_id, regions, creator=creator, **kwargs)

    def jitter(regions: Sequence[RegionSpec], *, scale: float, shift: float) -> tuple[RegionSpec, ...]:
        return tuple(
            RegionSpec(
                r.region_id,
                r.role,
                jitter_box(r.box, scale=scale, shift=shift),
                r.layer_order,
            )
            for r in regions
        )

    lxr = layout_left_text_right_image("s")
    itt = layout_image_top_text_bottom("s")
    cards = layout_three_card("s")
    overlay = layout_full_bleed_overlay("s")

    return (
        # -- same family (5) -------------------------------------------------
        SimilarityCase(
            case_id="similar-01-identical",
            left=sample(
                "S01a", lxr, "c01", layout="image_left_text_right"
            ),
            right=sample("S01b", lxr, "c02", layout="image_left_text_right"),
            same_family=True,
            note="identical structure, different creators",
            expected_min_score=0.999,
        ),
        SimilarityCase(
            case_id="similar-02-mild-jitter",
            left=sample("S02a", lxr, "c03", layout="image_left_text_right"),
            right=sample(
                "S02b",
                jitter(lxr, scale=0.97, shift=0.01),
                "c04",
                layout="image_left_text_right",
            ),
            same_family=True,
            note="same layout, slightly rescaled",
            expected_min_score=0.90,
        ),
        SimilarityCase(
            case_id="similar-03-color-only-change",
            left=sample("S03a", itt, "c05", layout="image_top_text_bottom", color="cool_blue", alignment=None),
            right=sample(
                "S03b",
                itt,
                "c06",
                layout="image_top_text_bottom",
                color="cool_teal",
                alignment=None,
            ),
            same_family=True,
            note="layout identical, colour family differs",
            expected_min_score=0.85,
            expected_codes_include=("color_family_mismatch",),
        ),
        SimilarityCase(
            case_id="similar-04-subject-only-change",
            left=sample(
                "S04a", lxr, "c07", layout="image_left_text_right", subject="human_figure"
            ),
            right=sample(
                "S04b",
                lxr,
                "c08",
                layout="image_left_text_right",
                subject="product_object",
                color="cool_blue",
            ),
            same_family=True,
            note="same layout, different subject class and colour",
            expected_min_score=0.80,
            expected_codes_include=("subject_class_mismatch",),
        ),
        SimilarityCase(
            case_id="similar-05-three-card-variant",
            left=sample("S05a", cards, "c09", layout="three_card", density="dense"),
            right=sample(
                "S05b",
                jitter(cards, scale=0.98, shift=0.005),
                "c10",
                layout="three_card",
                density="dense",
            ),
            same_family=True,
            note="three-card variant with adjusted card sizes",
            expected_min_score=0.90,
        ),
        # -- different family (4) --------------------------------------------
        SimilarityCase(
            case_id="different-01-left-vs-top",
            left=sample("S06a", lxr, "c11", layout="image_left_text_right"),
            right=sample(
                "S06b", itt, "c12", layout="image_top_text_bottom", alignment=None
            ),
            same_family=False,
            note="text beside image vs text below image",
            expected_max_score=0.90,
            expected_codes_include=("layout_template_class_mismatch",),
        ),
        SimilarityCase(
            case_id="different-02-cards-vs-overlay",
            left=sample("S07a", cards, "c13", layout="three_card", density="dense"),
            right=sample(
                "S07b",
                overlay,
                "c14",
                layout="full_bleed_overlay",
                density="dense",
                negative_space="tight",
            ),
            same_family=False,
            note="three-card grid vs full-bleed overlay",
            expected_max_score=0.90,
        ),
        SimilarityCase(
            case_id="different-03-stack-vs-column",
            left=sample(
                "S08a",
                layout_list_stack("s"),
                "c15",
                layout="list_stack",
                density="dense",
            ),
            right=sample(
                "S08b",
                layout_single_column("s"),
                "c16",
                layout="single_column",
                density="sparse",
            ),
            same_family=False,
            note="list stack vs single column",
            expected_max_score=0.90,
        ),
        SimilarityCase(
            case_id="different-04-chart-vs-cover",
            left=sample(
                "S09a",
                layout_chart_with_caption("s"),
                "c17",
                layout="single_column",
                subject="data_chart",
                chart_class="bar",
            ),
            right=sample(
                "S09b",
                layout_cover_with_logo("s"),
                "c18",
                layout="full_bleed_overlay",
                placement="full_bleed",
                cover_role="article_cover",
            ),
            same_family=False,
            note="chart with caption vs image cover",
            expected_max_score=0.90,
        ),
        # -- the honest near-miss (1) ----------------------------------------
        SimilarityCase(
            case_id="nearmiss-01-same-class-different-geometry",
            left=sample(
                "S10a",
                layout_left_text_right_image("s"),
                "c19",
                layout="image_left_text_right",
            ),
            right=sample(
                "S10b",
                (
                    _BG_FULL,
                    region("s-b-title", "title", 0.50, 0.70, 0.42, 0.18, 1),
                    region("s-b-img", "subject", 0.05, 0.05, 0.42, 0.60, 1),
                ),
                "c20",
                layout="image_left_text_right",
                alignment="right",
            ),
            same_family=False,
            note="same declared class but mirrored geometry: a disagreement the "
            "prototype should surface, not hide",
            expected_max_score=0.95,
            expected_codes_include=("region_role_absent_on_right",),
        ),
    )


# --------------------------------------------------------------------------
# Group 3 — cross-modal alignment cases (10)
# --------------------------------------------------------------------------


def cross_modal_cases() -> tuple[CrossModalCase, ...]:
    """Ten text/visual geometries with their required derived relations."""

    def case(
        index: int,
        regions: Sequence[RegionSpec],
        *,
        geometric: str,
        semantic: str,
        anchor: str,
        note: str,
        declared: bool = False,
        declared_relations: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> CrossModalCase:
        sample = _base_sample(
            f"C{index:02d}",
            regions,
            creator=f"creator-c{index:02d}",
            layout="image_left_text_right",
            declared_relations=declared_relations,
            **kwargs,
        )
        return CrossModalCase(
            case_id=f"cross-modal-{index:02d}",
            sample=sample,
            expected_geometric_relation=geometric,
            expected_semantic_relation=semantic,
            expected_anchor_role=anchor,
            declared=declared,
            note=note,
        )

    return (
        case(
            1,
            (
                _BG_FULL,
                region("t", "title", 0.05, 0.10, 0.40, 0.20, 1),
                region("v", "subject", 0.55, 0.10, 0.40, 0.60, 1),
            ),
            geometric="left_of",
            semantic="labels",
            anchor="subject",
            note="text beside image",
        ),
        case(
            2,
            (
                _BG_FULL,
                region("t", "title", 0.05, 0.62, 0.90, 0.18, 1),
                region("v", "subject", 0.10, 0.05, 0.80, 0.50, 1),
            ),
            geometric="below",
            semantic="illustrates",
            anchor="subject",
            note="text below image",
        ),
        case(
            3,
            (
                _BG_FULL,
                region("t", "title", 0.10, 0.05, 0.80, 0.18, 1),
                region("v", "subject", 0.10, 0.30, 0.80, 0.55, 1),
            ),
            geometric="above",
            semantic="illustrates",
            anchor="subject",
            note="text above image",
        ),
        case(
            4,
            (
                region("v", "subject", 0.05, 0.05, 0.90, 0.90, 0),
                region("t", "title", 0.15, 0.40, 0.70, 0.20, 1),
            ),
            geometric="contained_by",
            semantic="reinforces",
            anchor="subject",
            note="title overlaid on image",
            negative_space="tight",
        ),
        case(
            5,
            (
                _BG_FULL,
                region("v", "chart", 0.08, 0.20, 0.84, 0.42, 1),
                region("t", "caption", 0.08, 0.66, 0.84, 0.10, 1),
            ),
            geometric="below",
            semantic="illustrates",
            anchor="chart",
            note="caption below chart",
            chart_class="bar",
            subject="data_chart",
        ),
        case(
            6,
            (
                _BG_FULL,
                region("v", "subject", 0.55, 0.10, 0.40, 0.60, 1),
                region("t", "label", 0.06, 0.12, 0.40, 0.12, 1),
            ),
            geometric="left_of",
            semantic="labels",
            anchor="subject",
            note="label to the left of image",
        ),
        case(
            7,
            (
                _BG_FULL,
                region("v", "data_table", 0.08, 0.18, 0.84, 0.50, 1),
                region("t", "title", 0.08, 0.04, 0.84, 0.12, 1),
            ),
            geometric="above",
            semantic="illustrates",
            anchor="data_table",
            note="title above data table",
            subject="document_scan",
        ),
        case(
            8,
            (
                _BG_FULL,
                region("v", "subject", 0.05, 0.10, 0.42, 0.60, 1),
                region("t", "title", 0.52, 0.10, 0.42, 0.20, 1),
            ),
            geometric="right_of",
            semantic="labels",
            anchor="subject",
            note="text to the right of image",
        ),
        case(
            9,
            (
                region("v", "subject", 0.0, 0.0, 1.0, 1.0, 0),
                region("t", "label", 0.70, 0.80, 0.28, 0.12, 1),
            ),
            geometric="contained_by",
            semantic="reinforces",
            anchor="subject",
            note="corner label on full-bleed image",
            density="dense",
            negative_space="tight",
        ),
        case(
            10,
            (
                _BG_FULL,
                region("v", "subject", 0.55, 0.10, 0.40, 0.60, 1),
                region("t", "title", 0.06, 0.10, 0.40, 0.20, 1),
            ),
            geometric="left_of",
            semantic="contrasts",
            anchor="subject",
            note="author declares a contrasting relation where geometry says adjacency",
            declared=True,
            declared_relations={"t": "contrasts"},
        ),
    )


# --------------------------------------------------------------------------
# Suite assembly
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    """All 30 cases plus the template-discovery scenario."""

    layouts: tuple[LayoutCase, ...] = field(default_factory=layout_cases)
    similarities: tuple[SimilarityCase, ...] = field(default_factory=similarity_cases)
    cross_modal: tuple[CrossModalCase, ...] = field(default_factory=cross_modal_cases)

    @property
    def case_count(self) -> int:
        return len(self.layouts) + len(self.similarities) + len(self.cross_modal)

    def all_samples(self) -> tuple[VisualSample, ...]:
        """Every sample in the suite, uniquely identified."""

        samples: dict[str, VisualSample] = {}
        for case in self.layouts:
            samples[case.sample.sample_id] = case.sample
        for case in self.similarities:
            samples[case.left.sample_id] = case.left
            samples[case.right.sample_id] = case.right
        for case in self.cross_modal:
            samples[case.sample.sample_id] = case.sample
        return tuple(samples[key] for key in sorted(samples))

    def describe(self) -> str:
        return (
            f"benchmark suite: {self.case_count} cases "
            f"({len(self.layouts)} layout, {len(self.similarities)} similarity, "
            f"{len(self.cross_modal)} cross-modal)"
        )


__all__ = [
    "BenchmarkSuite",
    "CrossModalCase",
    "LayoutCase",
    "SimilarityCase",
    "cross_modal_cases",
    "jitter_box",
    "layout_cases",
    "layout_chart_with_caption",
    "layout_cover_with_logo",
    "layout_data_table",
    "layout_full_bleed_overlay",
    "layout_image_top_text_bottom",
    "layout_left_text_right_image",
    "layout_list_stack",
    "layout_single_column",
    "layout_three_card",
    "layout_two_column",
    "region",
    "similarity_cases",
]
