"""Creator visual pattern distillation (Phase M3, phase 7).

Turns discovered template clusters into abstracted **visual strategy**. The
output is deliberately not an image, not a pixel copy, and not a template file:
it is a description of how a creator arranges attention, in the same spirit as
``content_template`` describes an article's structure.

What is distilled, and what is refused
--------------------------------------

Distilled (strategy):

* ``layout_strategy`` — an ordered list of abstract structural moves
  (``headline_top``, ``subject_center``, ``cta_bottom``),
* ``hierarchy`` — the attention sequence (``attention_entry`` →
  ``information_block`` → ``action_area``),
* ``style_pattern`` — abstracted style traits (``high_contrast``,
  ``large_typography``),
* ``region_recipe`` — the roles a member must have, with their normalized
  position bands.

Refused (assets):

* no pixel buffers, no cropped images, no colour swatches, no font files, and no
  path to any source asset. A :class:`CreatorVisualPattern` is constructible
  without ever opening the image it was learned from, which is what makes
  "learn the strategy, not the material" a property of the code rather than a
  claim in a document.

The abstraction is produced by *aggregating* across cluster members, so it can
only express what the members agree on. A trait present in one member and absent
in the rest does not survive into the pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..clustering.template_discovery import Cluster, TemplateDiscovery
from ..extraction.visual_sample import VisualSample

#: Attention stages, in order. A pattern's hierarchy is a subsequence of this.
HIERARCHY_STAGES: tuple[str, ...] = (
    "attention_entry",
    "information_block",
    "action_area",
)

#: Region roles that open a composition.
_ENTRY_ROLES = frozenset({"subject", "title", "chart"})
#: Roles that carry the body of the message.
_INFORMATION_ROLES = frozenset(
    {"body", "caption", "subtitle", "label", "data_table", "chart", "annotation"}
)
#: Roles that close or direct.
_ACTION_ROLES = frozenset({"cta", "footer", "logo"})

#: Agreement fraction a trait needs before it enters the pattern.
AGREEMENT_THRESHOLD = 0.6

#: Vertical band names used by the layout strategy vocabulary.
_POSITION_BANDS: tuple[tuple[str, float, float], ...] = (
    ("top", 0.0, 0.34),
    ("center", 0.28, 0.68),
    ("bottom", 0.62, 1.01),
)


class PatternDistillationError(Exception):
    """Raised when a pattern cannot be distilled from a cluster."""


def _text_region_roles(sample: VisualSample) -> set[str]:
    return {region.role for region in sample.regions}


def _band_of(value: float) -> str:
    """Map a normalized coordinate onto a named vertical band.

    Bands overlap deliberately: a region centred at 0.31 is genuinely both "upper"
    and "middle", and forcing a single answer would lose that. The caller knows
    which band it is asking about.
    """

    for name, low, high in _POSITION_BANDS:
        if low <= value < high:
            return name
    return "bottom"


def _dominant_band(sample: VisualSample, roles: set[str]) -> str | None:
    """Vertical band of the largest region among ``roles``."""

    candidates = [region for region in sample.regions if region.role in roles]
    if not candidates:
        return None
    anchor = max(
        candidates,
        key=lambda region: (
            float(region.box["w"]) * float(region.box["h"]),
            region.region_id,
        ),
    )
    centre = float(anchor.box["y"]) + float(anchor.box["h"]) / 2.0
    return _band_of(centre)


def _layout_moves(sample: VisualSample) -> tuple[str, ...]:
    """Abstract structural moves a single sample exhibits, in reading order."""

    moves: list[str] = []
    roles = _text_region_roles(sample)

    entry_band = _dominant_band(sample, _ENTRY_ROLES)
    if "subject" in roles and entry_band:
        moves.append(f"subject_{entry_band}")
    if "title" in roles:
        title_band = _dominant_band(sample, {"title"})
        moves.append(f"headline_{title_band or 'top'}")
    if "chart" in roles:
        moves.append("chart_body")
    if "data_table" in roles:
        moves.append("table_body")
    if "body" in roles:
        body_band = _dominant_band(sample, {"body"})
        moves.append(f"copy_{body_band or 'center'}")
    if "caption" in roles:
        moves.append("caption_underlay")
    if roles & {"cta", "footer"}:
        action_band = _dominant_band(sample, {"cta", "footer"})
        moves.append(f"cta_{action_band or 'bottom'}")
    if "logo" in roles:
        moves.append("logo_corner")

    # Deduplicate while preserving order.
    seen: dict[str, None] = {}
    for move in moves:
        seen.setdefault(move, None)
    return tuple(seen)


def _style_traits(samples: Sequence[VisualSample]) -> tuple[str, ...]:
    """Abstracted style traits agreed on by the cluster.

    Traits are abstract labels, never values: ``high_contrast`` rather than a
    colour triple, ``large_typography`` rather than a point size. That is the
    difference between describing a strategy and copying an asset.
    """

    traits: list[str] = []
    total = len(samples)

    def share(predicate) -> float:
        return sum(1 for sample in samples if predicate(sample)) / total if total else 0.0

    if share(lambda s: s.palette_relation in {"complementary", "high_contrast_accent"}) >= AGREEMENT_THRESHOLD:
        traits.append("high_contrast")
    if share(lambda s: s.palette_relation in {"monochrome", "muted", "analogous"}) >= AGREEMENT_THRESHOLD:
        traits.append("low_contrast")
    if share(
        lambda s: s.text_style is not None
        and s.text_style.scale_relation in {"two_level", "three_plus_levels"}
    ) >= AGREEMENT_THRESHOLD:
        traits.append("large_typography")
    if share(lambda s: s.composition_density == "dense") >= AGREEMENT_THRESHOLD:
        traits.append("dense_composition")
    if share(lambda s: s.composition_density == "sparse") >= AGREEMENT_THRESHOLD:
        traits.append("sparse_composition")
    if share(lambda s: s.color_family in {"dark_monochrome"}) >= AGREEMENT_THRESHOLD:
        traits.append("dark_ground")
    if share(lambda s: s.color_family in {"light_monochrome", "neutral_beige"}) >= AGREEMENT_THRESHOLD:
        traits.append("light_ground")
    if share(lambda s: "subject" in _text_region_roles(s) and "chart" in _text_region_roles(s)) >= AGREEMENT_THRESHOLD:
        traits.append("image_and_data")
    if share(lambda s: s.placement in {"full_bleed", "background"}) >= AGREEMENT_THRESHOLD:
        traits.append("full_bleed_framing")
    if share(lambda s: s.placement in {"side_panel", "inline_with_text"}) >= AGREEMENT_THRESHOLD:
        traits.append("split_framing")

    return tuple(traits) if traits else ("undetermined",)


def _hierarchy(samples: Sequence[VisualSample]) -> tuple[str, ...]:
    """The attention sequence the cluster's compositions express."""

    stages: list[str] = []
    total = len(samples)

    def share(predicate) -> float:
        return sum(1 for sample in samples if predicate(sample)) / total if total else 0.0

    opens_with_subject = share(lambda s: "subject" in _text_region_roles(s)) >= AGREEMENT_THRESHOLD
    opens_with_title = share(
        lambda s: "title" in _text_region_roles(s)
        and _dominant_band(s, _ENTRY_ROLES) in {"top", "center"}
    ) >= AGREEMENT_THRESHOLD
    if opens_with_subject or opens_with_title:
        stages.append("attention_entry")
    if share(lambda s: bool(_text_region_roles(s) & _INFORMATION_ROLES)) >= AGREEMENT_THRESHOLD:
        stages.append("information_block")
    if share(lambda s: bool(_text_region_roles(s) & _ACTION_ROLES)) >= AGREEMENT_THRESHOLD:
        stages.append("action_area")
    return tuple(stages) if stages else ("attention_entry",)


@dataclass(frozen=True, slots=True)
class RegionRecipeEntry:
    """One role a pattern's members must have, with its position band."""

    role: str
    band: str
    presence: float
    mean_area: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "band": self.band,
            "presence": self.presence,
            "mean_area": self.mean_area,
        }


@dataclass(frozen=True, slots=True)
class CreatorVisualPattern:
    """An abstracted visual strategy learned from a cluster of real images.

    Carries no pixel data and references no asset path. Everything here is a
    label, a band, or a ratio — the vocabulary of strategy rather than the
    material of a picture.
    """

    pattern_id: str
    cluster_id: str
    layout_strategy: tuple[str, ...]
    hierarchy: tuple[str, ...]
    style_pattern: tuple[str, ...]
    region_recipe: tuple[RegionRecipeEntry, ...]
    member_ids: tuple[str, ...]
    creator_ids: tuple[str, ...]
    support: int
    cohesion: float
    confidence: float
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "cluster_id": self.cluster_id,
            "layout_strategy": list(self.layout_strategy),
            "hierarchy": list(self.hierarchy),
            "style_pattern": list(self.style_pattern),
            "region_recipe": [entry.as_dict() for entry in self.region_recipe],
            "member_ids": list(self.member_ids),
            "creator_ids": list(self.creator_ids),
            "support": self.support,
            "cohesion": self.cohesion,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }

    def summary_line(self) -> str:
        return (
            f"{self.pattern_id}: support={self.support} creators={len(self.creator_ids)} "
            f"cohesion={self.cohesion:.3f} strategy=[{', '.join(self.layout_strategy)}] "
            f"hierarchy=[{', '.join(self.hierarchy)}]"
        )


def distill_cluster(
    cluster: Cluster, samples: Mapping[str, VisualSample]
) -> CreatorVisualPattern:
    """Distill one cluster into an abstracted visual pattern."""

    members = [samples[sample_id] for sample_id in cluster.member_ids if sample_id in samples]
    if not members:
        raise PatternDistillationError(
            f"cluster {cluster.cluster_id!r} has no reconstructable members"
        )

    # Layout strategy: moves agreed on by most members, in first-seen order.
    move_counts: dict[str, int] = {}
    for sample in members:
        for move in _layout_moves(sample):
            move_counts[move] = move_counts.get(move, 0) + 1
    threshold = max(1, int(len(members) * AGREEMENT_THRESHOLD))
    agreed_moves = {move for move, count in move_counts.items() if count >= threshold}
    ordered_moves: list[str] = []
    for sample in members:
        for move in _layout_moves(sample):
            if move in agreed_moves and move not in ordered_moves:
                ordered_moves.append(move)

    # Region recipe: role presence and typical band.
    role_presence: dict[str, int] = {}
    role_bands: dict[str, dict[str, int]] = {}
    role_areas: dict[str, list[float]] = {}
    for sample in members:
        for role in {region.role for region in sample.regions}:
            role_presence[role] = role_presence.get(role, 0) + 1
        for region in sample.regions:
            band = _band_of(float(region.box["y"]) + float(region.box["h"]) / 2.0)
            role_bands.setdefault(region.role, {})
            role_bands[region.role][band] = role_bands[region.role].get(band, 0) + 1
            role_areas.setdefault(region.role, []).append(
                float(region.box["w"]) * float(region.box["h"])
            )

    recipe: list[RegionRecipeEntry] = []
    for role in sorted(role_presence):
        presence = role_presence[role] / len(members)
        if presence < AGREEMENT_THRESHOLD:
            continue
        bands = role_bands.get(role, {})
        band = sorted(bands.items(), key=lambda item: (-item[1], item[0]))[0][0] if bands else "center"
        areas = role_areas.get(role, [0.0])
        recipe.append(
            RegionRecipeEntry(
                role=role,
                band=band,
                presence=round(presence, 6),
                mean_area=round(sum(areas) / len(areas), 6),
            )
        )

    hierarchy = _hierarchy(members)
    style = _style_traits(members)
    creators = tuple(sorted({sample.provenance.creator_id for sample in members}))
    cohesion = cluster.evidence.mean_similarity

    # Confidence combines cohesion, support, and creator diversity: a pattern
    # seen once by one creator is weak evidence no matter how clean it looks.
    confidence = round(
        min(
            1.0,
            0.5 * cohesion
            + 0.25 * min(1.0, len(members) / 5.0)
            + 0.25 * min(1.0, len(creators) / 3.0),
        ),
        6,
    )

    return CreatorVisualPattern(
        pattern_id=f"vp-{cluster.cluster_id}",
        cluster_id=cluster.cluster_id,
        layout_strategy=tuple(ordered_moves) or ("undetermined",),
        hierarchy=hierarchy,
        style_pattern=style,
        region_recipe=tuple(recipe),
        member_ids=tuple(cluster.member_ids),
        creator_ids=creators,
        support=len(members),
        cohesion=round(cohesion, 6),
        confidence=confidence,
        evidence={
            "threshold": cluster.evidence.threshold,
            "min_similarity": cluster.evidence.min_similarity,
            "dominant_layout_class": cluster.evidence.dominant_layout_class,
            "layout_class_agreement": cluster.evidence.layout_class_agreement,
            "recurring": cluster.evidence.recurring,
            "move_agreement_threshold": threshold,
            "member_count": len(members),
        },
    )


def distill_patterns(
    discovery: TemplateDiscovery,
    samples: Sequence[VisualSample],
    *,
    only_recurring: bool = False,
) -> tuple[CreatorVisualPattern, ...]:
    """Distill every cluster in a discovery result."""

    by_id = {sample.sample_id: sample for sample in samples}
    patterns: list[CreatorVisualPattern] = []
    for cluster in discovery.clusters:
        if only_recurring and not cluster.is_template():
            continue
        patterns.append(distill_cluster(cluster, by_id))
    patterns.sort(key=lambda pattern: (-pattern.support, pattern.pattern_id))
    return tuple(patterns)


def render_patterns(patterns: Sequence[CreatorVisualPattern]) -> str:
    """Human-readable listing of distilled patterns."""

    if not patterns:
        return "no visual patterns distilled"
    lines = [f"creator visual patterns: {len(patterns)}"]
    for pattern in patterns:
        lines.append("")
        lines.append(pattern.summary_line())
        lines.append(f"  style    : {', '.join(pattern.style_pattern)}")
        lines.append(
            "  recipe   : "
            + ", ".join(f"{entry.role}@{entry.band}" for entry in pattern.region_recipe)
        )
        lines.append(f"  members  : {', '.join(pattern.member_ids[:6])}"
                     + (" …" if len(pattern.member_ids) > 6 else ""))
    return "\n".join(lines)


__all__ = [
    "AGREEMENT_THRESHOLD",
    "HIERARCHY_STAGES",
    "CreatorVisualPattern",
    "PatternDistillationError",
    "RegionRecipeEntry",
    "distill_cluster",
    "distill_patterns",
    "render_patterns",
]
