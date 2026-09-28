"""Visual grammar extraction (Phase M4, phase 2).

Turns an M3 :class:`StructuralObservation` into a :class:`VisualGrammar`.

This is the representation change M4 is built around. M3's observer produced a
layout *label* plus a flat region list; M4 keeps the region list and derives
structure from it — functional region types, ordinal dominance, discrete
relations, and an attention sequence. Nothing downstream has to accept a single
label as the summary of a composition any more.

Region typing
-------------

M3's region roles describe *appearance* (``body``, ``caption``, ``label``). Grammar
needs *function* (``supporting_information``, ``data_display``, ``cta``). The
mapping is fixed and published, so a grammar region type can always be traced
back to the observation that justified it.

No text is read anywhere in this module. Region function comes from role,
geometry, and layer, which is exactly why it survives content the system has
never seen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..taxonomy import StructuralObservation
from .model import (
    AttentionFlow,
    GrammarError,
    GrammarRegion,
    VisualGrammar,
    column_band_of,
    position_band_of,
)
from .relation import RelationExtractor

#: Observation role → grammar region type.
ROLE_TO_GRAMMAR_TYPE: Mapping[str, str] = {
    "title": "headline",
    "header": "headline",
    "subtitle": "subtitle",
    "subject": "subject",
    "body": "supporting_information",
    "caption": "supporting_information",
    "label": "supporting_information",
    "annotation": "supporting_information",
    "chart": "data_display",
    "data_table": "data_display",
    "cta": "cta",
    "footer": "cta",
    "logo": "branding",
    "watermark": "branding",
    "background": "background",
}

#: Folded line height above which a text region counts as dense.
_DENSE_HEIGHT = 0.28
#: Below this height a text region is sparse.
_SPARSE_HEIGHT = 0.08

#: Area share at which a region stops being part of the content layer.
_BACKGROUND_AREA = 0.82


@dataclass(frozen=True, slots=True)
class GrammarExtractionResult:
    """A grammar plus the mapping decisions that produced it.

    ``decisions`` records which observation role became which grammar type, so a
    reviewer can audit the typing rather than take it on trust.
    """

    grammar: VisualGrammar
    decisions: Mapping[str, str]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "grammar": self.grammar.as_dict(),
            "decisions": dict(self.decisions),
            "warnings": list(self.warnings),
        }


class GrammarExtractor:
    """Derive a :class:`VisualGrammar` from a real observation."""

    def __init__(
        self,
        *,
        relation_extractor: RelationExtractor | None = None,
        evidence_source: str | None = None,
    ) -> None:
        self._relations = relation_extractor or RelationExtractor()
        self._evidence_override = evidence_source

    def extract(self, observation: StructuralObservation) -> GrammarExtractionResult:
        if not observation.regions:
            raise GrammarError(
                f"observation {observation.observation_id!r} has no regions; a grammar "
                "cannot be derived from an empty composition"
            )

        warnings: list[str] = []
        decisions: dict[str, str] = {}

        # -- regions --------------------------------------------------------
        typed: list[tuple[dict[str, Any], str]] = []
        for raw in observation.regions:
            role = str(raw.get("role"))
            grammar_type = ROLE_TO_GRAMMAR_TYPE.get(role)
            if grammar_type is None:
                warnings.append(f"observation role {role!r} has no grammar type; dropped")
                continue
            typed.append((dict(raw), grammar_type))
            decisions[str(raw.get("region_id"))] = f"{role}->{grammar_type}"

        if not typed:
            raise GrammarError(
                f"no observation role in {observation.observation_id!r} maps to a "
                "grammar region type"
            )

        areas = {
            str(raw.get("region_id")): float(raw["box"]["w"]) * float(raw["box"]["h"])
            for raw, _type in typed
        }
        ranks = self._dominance_ranks(typed, areas)

        regions = [
            self._build_region(raw, grammar_type, areas, ranks)
            for raw, grammar_type in typed
        ]

        # -- relationships --------------------------------------------------
        relationships = self._relations.extract(regions)

        # -- attention flow -------------------------------------------------
        attention = self._attention_flow(regions, relationships, warnings)

        grammar = VisualGrammar(
            grammar_id=f"{observation.observation_id}:grammar",
            source_id=observation.source_id,
            regions=tuple(regions),
            relationships=relationships,
            attention_flow=attention,
            evidence_source=self._evidence_override or "observation",
            confidence=observation.confidence,
            notes=tuple(warnings),
        )
        return GrammarExtractionResult(
            grammar=grammar, decisions=decisions, warnings=tuple(warnings)
        )

    # -- internals ---------------------------------------------------------

    def _dominance_ranks(
        self,
        typed: Sequence[tuple[dict[str, Any], str]],
        areas: Mapping[str, float],
    ) -> dict[str, str]:
        """Assign ordinal dominance by type function, then by area.

        Type takes precedence over raw size. A full-bleed background is the
        largest thing in the frame and would win an area-only ranking, which
        would make ``dominant_region`` useless. Dominance is about what the
        composition is *about*.
        """

        priority = {
            "subject": 0,
            "headline": 1,
            "cta": 2,
            "data_display": 3,
            "subtitle": 4,
            "supporting_information": 5,
            "branding": 6,
            "background": 7,
        }
        ordered = sorted(
            typed,
            key=lambda item: (
                priority.get(item[1], 9),
                -areas.get(str(item[0].get("region_id")), 0.0),
                str(item[0].get("region_id")),
            ),
        )

        ranks: dict[str, str] = {}
        content = [item for item in ordered if item[1] != "background"]
        for index, (raw, grammar_type) in enumerate(content):
            region_id = str(raw.get("region_id"))
            if index == 0:
                ranks[region_id] = "primary"
            elif index == 1:
                ranks[region_id] = "secondary"
            else:
                ranks[region_id] = "tertiary"
        for raw, grammar_type in ordered:
            if grammar_type == "background":
                ranks[str(raw.get("region_id"))] = "background"
        return ranks

    def _build_region(
        self,
        raw: Mapping[str, Any],
        grammar_type: str,
        areas: Mapping[str, float],
        ranks: Mapping[str, str],
    ) -> GrammarRegion:
        box = raw["box"]
        width = float(box["w"])
        height = float(box["h"])
        cx = float(box["x"]) + width / 2.0
        cy = float(box["y"]) + height / 2.0
        region_id = str(raw.get("region_id"))

        # Density is only meaningful for regions that hold content. A flat block
        # is "dense" by area and "sparse" by structure, so area-based density is
        # used for backgrounds and height-based density for content.
        if grammar_type == "background":
            density = "dense" if areas.get(region_id, 0.0) >= _BACKGROUND_AREA else "moderate"
        elif grammar_type in {"subject", "data_display"}:
            density = "dense" if areas.get(region_id, 0.0) >= 0.25 else "moderate"
        elif height >= _DENSE_HEIGHT:
            density = "dense"
        elif height <= _SPARSE_HEIGHT:
            density = "sparse"
        else:
            density = "moderate"

        return GrammarRegion(
            region_id=region_id,
            region_type=grammar_type,
            position_band=position_band_of(cy),
            column_band=column_band_of(cx),
            width_share=round(width, 6),
            height_share=round(height, 6),
            area_share=round(areas.get(region_id, 0.0), 6),
            density=density,
            dominance=ranks.get(region_id, "tertiary"),
            layer_order=int(raw.get("layer_order", 0)),
            position_center=(round(cx, 6), round(cy, 6)),
        )

    def _attention_flow(
        self,
        regions: Sequence[GrammarRegion],
        relationships: Sequence[Any],
        warnings: list[str],
    ) -> AttentionFlow:
        """Build the attention sequence from dominance, position, and relations.

        The order is *structural*, not perceptual: a viewer's eye is not
        simulated. Entry is the highest-layer large region in the upper frame;
        primary focus is the most dominant content region; the action area is a
        ``cta`` if one exists.
        """

        stages: list[str] = []
        assignments: dict[str, str] = {}

        def top_of(region_type: str) -> GrammarRegion | None:
            for region in regions:
                if region.region_type == region_type:
                    return region
            return None

        # Entrance point: an overlaid headline, else the topmost content region.
        overlay = next(
            (
                relation
                for relation in relationships
                if relation.relation_type == "headline_overlay_subject"
            ),
            None,
        )
        entrance: GrammarRegion | None = None
        if overlay is not None:
            entrance = next(
                (r for r in regions if r.region_id == overlay.source_region_id), None
            )
        if entrance is None:
            candidates = [
                region
                for region in regions
                if region.region_type != "background" and region.position_band == "top"
            ]
            if candidates:
                order = {"primary": 0, "secondary": 1, "tertiary": 2, "background": 3}
                entrance = sorted(
                    candidates, key=lambda r: (order.get(r.dominance, 9), r.region_id)
                )[0]

        # Primary focus: the dominant content region.
        content = [r for r in regions if r.region_type != "background"]
        primary = None
        if content:
            order = {"primary": 0, "secondary": 1, "tertiary": 2}
            primary = sorted(
                content, key=lambda r: (order.get(r.dominance, 9), r.region_id)
            )[0]

        if entrance is not None:
            stages.append("entrance_point")
            assignments["entrance_point"] = entrance.region_id
        if primary is not None and primary.region_id not in assignments.values():
            stages.append("primary_focus")
            assignments["primary_focus"] = primary.region_id
            try:
                primary.region_id  # noqa: B018 - presence check only
            except AttributeError:  # pragma: no cover - defensive
                warnings.append("primary focus region was malformed and was skipped")

        # Secondary information: the largest remaining content region.
        remaining = [
            region
            for region in content
            if region.region_id not in assignments.values()
        ]
        if remaining:
            secondary = sorted(
                remaining, key=lambda r: (-r.area_share, r.region_id)
            )[0]
            stages.append("secondary_information")
            assignments["secondary_information"] = secondary.region_id

        # Action area: an explicit cta, else a bottom-anchored branding region.
        action = top_of("cta")
        if action is None:
            action = next(
                (
                    region
                    for region in regions
                    if region.region_type == "branding"
                    and region.position_band == "bottom"
                ),
                None,
            )
        if action is not None and action.region_id not in assignments.values():
            stages.append("action_area")
            assignments["action_area"] = action.region_id

        return AttentionFlow(stages=tuple(stages), assignments=assignments)


def extract_grammar(
    observation: StructuralObservation,
    *,
    evidence_source: str | None = None,
) -> GrammarExtractionResult:
    """Convenience wrapper around :class:`GrammarExtractor`."""

    return GrammarExtractor(evidence_source=evidence_source).extract(observation)


__all__ = [
    "ROLE_TO_GRAMMAR_TYPE",
    "GrammarExtractionResult",
    "GrammarExtractor",
    "extract_grammar",
]
