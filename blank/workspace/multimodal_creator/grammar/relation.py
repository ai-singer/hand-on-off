"""Relationship extraction for visual grammar (Phase M4, phase 2 layer 2).

Relations are what a layout label destroys. ``image_top_text_bottom`` says
"image and text, stacked" and cannot say *how far apart*, *how wide*, *whether
the headline overhangs the subject*, *whether the boundary is a hard contrast
edge or a soft blend*. A grammar keeps all of that as discrete, checkable
relations.

Every relation is derived from region geometry and layer order — position, size,
overlap, containment, and contrast. **Nothing here reads text.** A relation is
about where things are and how they stack, which is why it stays valid for
content the system has never seen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .model import (
    GrammarError,
    GrammarRegion,
    GrammarRelation,
    RELATION_TYPES,
)

#: Below this overlap fraction two regions are treated as non-overlapping.
_OVERLAP_FLOOR = 0.05

#: A region covering at least this share of the frame is full bleed.
_FULL_BLEED_SHARE = 0.62

#: A region is "centred" when its horizontal centre sits inside this window.
_CENTRE_WINDOW = 0.18

#: A region is "cornered" when it sits within this margin of two edges.
_CORNER_MARGIN = 0.22

#: Width ratio above which a region is considered to span the frame.
_SPAN_RATIO = 0.55


def _overlap_fraction(first: GrammarRegion, second: GrammarRegion) -> float:
    """Overlap of two regions as a share of the smaller one's area."""

    # Recover boxes from the stored shares and centres.
    def box(region: GrammarRegion) -> tuple[float, float, float, float]:
        w = region.width_share
        h = region.height_share
        cx, cy = region.position_center
        return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)

    ax0, ay0, ax1, ay1 = box(first)
    bx0, by0, bx1, by1 = box(second)
    ix = min(ax1, bx1) - max(ax0, bx0)
    iy = min(ay1, by1) - max(ay0, by0)
    if ix <= 0.0 or iy <= 0.0:
        return 0.0
    intersection = ix * iy
    smaller = min(first.area_share, second.area_share)
    return intersection / smaller if smaller > 0 else 0.0


def _contains(outer: GrammarRegion, inner: GrammarRegion) -> bool:
    return _overlap_fraction(outer, inner) >= 0.85


def _is_full_bleed(region: GrammarRegion) -> bool:
    return region.area_share >= _FULL_BLEED_SHARE


def _is_centred(region: GrammarRegion) -> bool:
    return abs(region.position_center[0] - 0.5) <= _CENTRE_WINDOW


def _is_cornered(region: GrammarRegion) -> bool:
    cx, cy = region.position_center
    horizontally = cx <= _CORNER_MARGIN or cx >= 1.0 - _CORNER_MARGIN
    vertically = cy <= _CORNER_MARGIN or cy >= 1.0 - _CORNER_MARGIN
    return horizontally and vertically


def _index(regions: Sequence[GrammarRegion]) -> dict[str, GrammarRegion]:
    return {region.region_id: region for region in regions}


def _first_of_type(
    regions: Sequence[GrammarRegion], region_type: str
) -> GrammarRegion | None:
    candidates = [region for region in regions if region.region_type == region_type]
    if not candidates:
        return None
    # Deterministic: most dominant first, then by id.
    order = {"primary": 0, "secondary": 1, "tertiary": 2, "background": 3}
    return sorted(candidates, key=lambda r: (order.get(r.dominance, 9), r.region_id))[0]


class RelationExtractor:
    """Derive grammar relations from region geometry and layering.

    The extractor is a pure function of the region list: the same regions always
    yield the same relations in the same order, so a grammar is reproducible and
    two runs can be diffed.
    """

    def __init__(self, *, contrast_threshold: float = 0.35) -> None:
        if not 0.0 < contrast_threshold <= 1.0:
            raise GrammarError("contrast_threshold must be within (0, 1]")
        self._contrast_threshold = contrast_threshold

    def extract(self, regions: Sequence[GrammarRegion]) -> tuple[GrammarRelation, ...]:
        if not regions:
            raise GrammarError("cannot extract relations from no regions")

        relations: list[GrammarRelation] = []
        headline = _first_of_type(regions, "headline")
        subtitle = _first_of_type(regions, "subtitle")
        subject = _first_of_type(regions, "subject")
        supporting = _first_of_type(regions, "supporting_information")
        data = _first_of_type(regions, "data_display")
        cta = _first_of_type(regions, "cta")
        branding = _first_of_type(regions, "branding")
        background = _first_of_type(regions, "background")

        # -- headline and subject ------------------------------------------
        if headline is not None and subject is not None:
            relations.extend(self._headline_subject(headline, subject))

        # -- subject placement ---------------------------------------------
        if subject is not None:
            relations.append(self._subject_focus(subject))

        # -- action area ----------------------------------------------------
        if cta is not None:
            relations.append(self._action_anchor(cta, regions))

        # -- supporting information ----------------------------------------
        if supporting is not None:
            relations.extend(self._supporting(supporting, headline, subject))

        # -- data display ---------------------------------------------------
        if data is not None:
            relations.extend(self._data(data, headline, subtitle))

        # -- branding -------------------------------------------------------
        if branding is not None and _is_cornered(branding):
            relations.append(
                self._make(
                    "branding_corner",
                    branding,
                    branding,
                    strength=0.9,
                    rationale=(
                        f"{branding.region_id} sits within {_CORNER_MARGIN:.2f} of two "
                        "frame edges"
                    ),
                )
            )

        # -- background -----------------------------------------------------
        if background is not None:
            enclosed = [
                region
                for region in regions
                if region.region_id != background.region_id
                and _contains(background, region)
            ]
            if enclosed:
                relations.append(
                    self._make(
                        "background_encloses_all",
                        background,
                        enclosed[0],
                        strength=round(len(enclosed) / max(1, len(regions) - 1), 6),
                        rationale=(
                            f"{background.region_id} encloses {len(enclosed)} of "
                            f"{len(regions) - 1} other regions"
                        ),
                    )
                )

        # -- contrast boundary between the two most separated large regions --
        contrast = self._contrast_relation(regions)
        if contrast is not None:
            relations.append(contrast)

        # Deterministic ordering, and no duplicate relation triples.
        unique: dict[tuple[str, str, str], GrammarRelation] = {}
        for relation in relations:
            key = (relation.relation_type, relation.source_region_id, relation.target_region_id)
            unique.setdefault(key, relation)
        ordered = sorted(
            unique.values(),
            key=lambda r: (r.relation_type, r.source_region_id, r.target_region_id),
        )
        for relation in ordered:
            if relation.relation_type not in RELATION_TYPES:
                raise GrammarError(f"produced invalid relation {relation.relation_type!r}")
        return tuple(ordered)

    # -- relation families -------------------------------------------------

    def _headline_subject(
        self, headline: GrammarRegion, subject: GrammarRegion
    ) -> list[GrammarRelation]:
        overlap = _overlap_fraction(headline, subject)
        relations: list[GrammarRelation] = []

        if overlap >= _OVERLAP_FLOOR and headline.layer_order > subject.layer_order:
            relations.append(
                self._make(
                    "headline_overlay_subject",
                    headline,
                    subject,
                    strength=round(min(1.0, overlap + 0.3), 6),
                    rationale=(
                        f"headline overlaps subject by {overlap:.2f} and sits on a "
                        f"higher layer ({headline.layer_order} > {subject.layer_order})"
                    ),
                )
            )
            return relations

        headline_bottom = headline.position_center[1] + headline.height_share / 2.0
        subject_top = subject.position_center[1] - subject.height_share / 2.0
        if headline_bottom <= subject_top + 0.02:
            gap = subject_top - headline_bottom
            relations.append(
                self._make(
                    "headline_above_subject",
                    headline,
                    subject,
                    strength=round(max(0.3, 1.0 - gap), 6),
                    rationale=f"headline clears the subject by {gap:.3f}",
                )
            )
        else:
            subject_bottom = subject.position_center[1] + subject.height_share / 2.0
            headline_top = headline.position_center[1] - headline.height_share / 2.0
            if subject_bottom <= headline_top + 0.02:
                gap = headline_top - subject_bottom
                relations.append(
                    self._make(
                        "headline_below_subject",
                        headline,
                        subject,
                        strength=round(max(0.3, 1.0 - gap), 6),
                        rationale=f"subject clears the headline by {gap:.3f}",
                    )
                )
        return relations

    def _subject_focus(self, subject: GrammarRegion) -> GrammarRelation:
        if _is_full_bleed(subject):
            return self._make(
                "subject_full_bleed",
                subject,
                subject,
                strength=round(subject.area_share, 6),
                rationale=f"subject covers {subject.area_share:.2f} of the frame",
            )
        if _is_centred(subject):
            return self._make(
                "subject_center_focus",
                subject,
                subject,
                strength=round(1.0 - abs(subject.position_center[0] - 0.5), 6),
                rationale=(
                    f"subject centre x={subject.position_center[0]:.2f} is within "
                    f"{_CENTRE_WINDOW:.2f} of the frame centre"
                ),
            )
        return self._make(
            "subject_offset_focus",
            subject,
            subject,
            strength=round(abs(subject.position_center[0] - 0.5), 6),
            rationale=(
                f"subject is offset to x={subject.position_center[0]:.2f}"
            ),
        )

    def _action_anchor(
        self, cta: GrammarRegion, regions: Sequence[GrammarRegion]
    ) -> GrammarRelation:
        cy = cta.position_center[1]
        if cy >= 0.5 + _CENTRE_WINDOW:
            return self._make(
                "cta_bottom_anchor",
                cta,
                cta,
                strength=round(cy, 6),
                rationale=f"action area centre y={cy:.2f} sits in the lower frame",
            )
        return self._make(
            "cta_top_anchor",
            cta,
            cta,
            strength=round(1.0 - cy, 6),
            rationale=f"action area centre y={cy:.2f} sits in the upper frame",
        )

    def _supporting(
        self,
        supporting: GrammarRegion,
        headline: GrammarRegion | None,
        subject: GrammarRegion | None,
    ) -> list[GrammarRelation]:
        relations: list[GrammarRelation] = []
        if headline is not None:
            supporting_top = supporting.position_center[1] - supporting.height_share / 2.0
            headline_bottom = headline.position_center[1] + headline.height_share / 2.0
            if supporting_top >= headline_bottom - 0.02:
                relations.append(
                    self._make(
                        "support_below_headline",
                        supporting,
                        headline,
                        strength=0.8,
                        rationale="supporting information sits beneath the headline",
                    )
                )
        if subject is not None:
            overlap = _overlap_fraction(supporting, subject)
            if overlap < _OVERLAP_FLOOR:
                relations.append(
                    self._make(
                        "support_beside_subject",
                        supporting,
                        subject,
                        strength=0.7,
                        rationale="supporting information does not overlap the subject",
                    )
                )
        return relations

    def _data(
        self,
        data: GrammarRegion,
        headline: GrammarRegion | None,
        subtitle: GrammarRegion | None,
    ) -> list[GrammarRelation]:
        relations: list[GrammarRelation] = []
        data_top = data.position_center[1] - data.height_share / 2.0
        for anchor, relation_type in (
            (subtitle, "data_above_caption"),
            (headline, "data_below_headline"),
        ):
            if anchor is None:
                continue
            anchor_bottom = anchor.position_center[1] + anchor.height_share / 2.0
            if data_top >= anchor_bottom - 0.02:
                relations.append(
                    self._make(
                        relation_type,
                        data,
                        anchor,
                        strength=0.75,
                        rationale=f"data display sits beneath {anchor.region_type}",
                    )
                )
        return relations

    def _contrast_relation(
        self, regions: Sequence[GrammarRegion]
    ) -> GrammarRelation | None:
        """Classify the strongest boundary between two substantial regions.

        A hard edge between two large regions is a compositional device; a
        gradual one is not. The observable proxy is the *area share difference*
        plus whether their densities differ: two regions of similar size and
        different internal density produce a visible boundary.
        """

        substantial = [
            region for region in regions if region.area_share >= 0.10
        ]
        if len(substantial) < 2:
            return None

        best: tuple[float, GrammarRegion, GrammarRegion] | None = None
        for index, first in enumerate(substantial):
            for second in substantial[index + 1 :]:
                density_gap = abs(
                    DENSITY_INDEX[first.density] - DENSITY_INDEX[second.density]
                )
                area_gap = abs(first.area_share - second.area_share)
                separation = 1.0 - _overlap_fraction(first, second)
                score = 0.5 * density_gap + 0.3 * area_gap + 0.2 * separation
                if best is None or score > best[0]:
                    best = (score, first, second)

        if best is None:
            return None
        score, first, second = best
        if score >= self._contrast_threshold:
            return self._make(
                "high_contrast_boundary",
                first,
                second,
                strength=round(min(1.0, score), 6),
                rationale=(
                    f"density {first.density} vs {second.density} and area "
                    f"{first.area_share:.2f} vs {second.area_share:.2f} form a "
                    f"visible boundary (score {score:.3f})"
                ),
            )
        return self._make(
            "low_contrast_blend",
            first,
            second,
            strength=round(1.0 - score, 6),
            rationale=f"regions blend rather than separate (score {score:.3f})",
        )

    # -- helper ------------------------------------------------------------

    def _make(
        self,
        relation_type: str,
        source: GrammarRegion,
        target: GrammarRegion,
        *,
        strength: float,
        rationale: str,
    ) -> GrammarRelation:
        return GrammarRelation(
            relation_id=f"{relation_type}:{source.region_id}->{target.region_id}",
            relation_type=relation_type,
            source_region_id=source.region_id,
            target_region_id=target.region_id,
            strength=round(max(0.0, min(1.0, strength)), 6),
            rationale=rationale,
        )


#: Ordinal density index used for boundary scoring.
DENSITY_INDEX: dict[str, float] = {"sparse": 0.0, "moderate": 0.5, "dense": 1.0}


__all__ = [
    "DENSITY_INDEX",
    "RelationExtractor",
]
