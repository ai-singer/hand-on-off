"""Frame observer: backend output → evidence-complete M1 observation.

This is the component that replaces M2's ``MockVisionExtractor`` for real input.
It depends only on the :class:`VisionBackend` protocol, so the same producer runs
against the pixel backend, a manual annotation backend, or the M2 mock without a
branch anywhere.

Four evidence families, all mandatory
-------------------------------------

Every observation must report ``layout_evidence``, ``visual_evidence``,
``asset_evidence``, and ``cross_modal_evidence``. A backend that returns nothing
for a family produces a *zero-strength* record for it, not a missing one, so
"this backend could not see that" is visible in the artifact instead of being
silently absent. :meth:`ObservationResult.assert_complete` then rejects the
observation outright.

That is deliberately strict. An observation missing a family is not a partial
observation; it is an unsupported claim, and the M1 contract already says
transcription alone may never ground visual structure.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..taxonomy import (
    ALIGNMENT_RELATIONS,
    DENSITIES,
    LAYOUT_TEMPLATE_CLASSES,
    PALETTE_RELATIONS,
    PLACEMENTS,
    REGION_ROLES,
    STRUCTURAL_EVIDENCE,
    TYPE_SCALE_RELATIONS,
    StructuralObservation,
)
from .interface import (
    EVIDENCE_FAMILIES,
    EvidenceRecord,
    ObservationResult,
    ObserverError,
    VisionBackend,
    VisualSource,
)

#: Roles that make a region text-bearing, and therefore ineligible as the
#: composition anchor for an asset evidence claim.
_TEXT_ROLES = frozenset(
    {"title", "subtitle", "body", "caption", "label", "cta", "header", "footer"}
)
_VISUAL_ROLES = frozenset({"subject", "chart", "data_table", "background"})

#: Anchor weight by role. A ground covers the frame but is not what the
#: composition is about, so it is weighted down — the same rule M2 applied.
_ANCHOR_WEIGHT: Mapping[str, float] = {
    "subject": 4.0,
    "chart": 4.0,
    "data_table": 4.0,
    "background": 0.25,
}


def _area(box: Mapping[str, float]) -> float:
    return float(box["w"]) * float(box["h"])


class FrameObserver:
    """Produce a complete :class:`ObservationResult` from one visual source."""

    def __init__(self, backend: VisionBackend) -> None:
        if not isinstance(backend, VisionBackend):
            raise ObserverError(
                "backend does not satisfy the VisionBackend protocol; it must expose "
                "backend_id, evidence_source, detect_regions, detect_visual_roles, "
                "detect_style_features and detect_text_visual_alignment"
            )
        self._backend = backend

    @property
    def backend(self) -> VisionBackend:
        return self._backend

    # -- public API --------------------------------------------------------

    def observe(self, source: VisualSource) -> ObservationResult:
        """Run all four detections and assemble a validated observation.

        A failing detection is recorded as a named backend failure and yields a
        zero-strength evidence record for that family, rather than aborting. That
        way an incomplete observation is *reported and rejected*, not silently
        downgraded into a partial one that looks complete.
        """

        failures: list[str] = []
        warnings: list[str] = []

        regions_raw = self._call(source, "detect_regions", failures, default=[])
        visual_raw = self._call(source, "detect_visual_roles", failures, default={})
        style_raw = self._call(source, "detect_style_features", failures, default={})
        cross_raw = self._call(
            source, "detect_text_visual_alignment", failures, default=[]
        )

        regions = self._validate_regions(regions_raw, warnings)
        layout_template = self._infer_layout_template(regions)

        if not cross_raw:
            # Recorded, not hidden. A composition whose text sits below the
            # detection floor has no text/visual relation to report, and the
            # contract requires that gap to be visible rather than papered over
            # with an invented relation.
            warnings.append(
                "cross_modal_evidence is empty: no text/visual relation could be "
                "established from the detected structure"
            )

        palette_relation = self._coerce(
            visual_raw.get("palette_relation"), PALETTE_RELATIONS, "mixed"
        )
        density = self._coerce(visual_raw.get("density"), DENSITIES, "balanced")
        type_scale = self._coerce(
            style_raw.get("type_scale_relation"), TYPE_SCALE_RELATIONS, None
        )
        alignment = style_raw.get("alignment")
        if alignment is not None and not isinstance(alignment, str):
            warnings.append("alignment was not a string and has been dropped")
            alignment = None

        anchor = self._anchor(regions)
        subject_class = self._subject_class(regions, anchor)
        chart_class = "mixed" if anchor is not None and anchor["role"] == "chart" else None
        placement = self._placement(regions, anchor)

        evidence = self._build_evidence(
            regions=regions,
            layout_template=layout_template,
            visual_raw=visual_raw,
            style_raw=style_raw,
            anchor=anchor,
            cross_raw=cross_raw,
            placement=placement,
        )

        observation = StructuralObservation(
            observation_id=f"{source.source_id}:observed",
            medium="video" if source.source_type == "video_frame" else "image",
            source_id=source.source_id,
            roles=self._roles(regions, visual_raw, style_raw, cross_raw),
            evidence_kinds=self._evidence_kinds(
                regions=regions,
                layout_template=layout_template,
                visual_raw=visual_raw,
                style_raw=style_raw,
                cross_raw=cross_raw,
                source=source,
            ),
            regions=tuple(regions),
            layout_template_class=layout_template,
            alignment=alignment if isinstance(alignment, str) else None,
            density=density,
            palette_relation=palette_relation,
            type_scale_relation=type_scale,
            subject_class=subject_class,
            chart_class=chart_class,
            placement=placement,
            recurrence=1,
            confidence=self._confidence(evidence),
        )

        result = ObservationResult(
            observation=observation,
            source=source,
            backend_id=self._backend.backend_id,
            evidence_source=self._backend.evidence_source,
            evidence=evidence,
            confidence=self._confidence(evidence),
            warnings=tuple(warnings),
            backend_failures=tuple(failures),
        )
        result.assert_complete()
        return result

    def observe_all(
        self, sources: Sequence[VisualSource]
    ) -> tuple[ObservationResult, ...]:
        ids = [source.source_id for source in sources]
        duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
        if duplicates:
            raise ObserverError("duplicate source ids: " + ", ".join(duplicates))
        return tuple(self.observe(source) for source in sources)

    # -- internals ---------------------------------------------------------

    def _call(
        self,
        source: VisualSource,
        method: str,
        failures: list[str],
        *,
        default: Any,
    ) -> Any:
        try:
            return getattr(self._backend, method)(source)
        except ObserverError:
            raise
        except Exception as exc:  # backend-specific failure, recorded not swallowed
            failures.append(f"{method}:{type(exc).__name__}")
            return default

    def _validate_regions(
        self, raw: Sequence[Mapping[str, Any]], warnings: list[str]
    ) -> list[dict[str, Any]]:
        """Keep only regions that satisfy the universal region contract."""

        regions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(raw or ()):
            if not isinstance(item, Mapping):
                warnings.append(f"region {index} was not an object and was dropped")
                continue
            role = item.get("role")
            if role not in REGION_ROLES:
                warnings.append(
                    f"region {index} used unknown role {role!r} and was dropped"
                )
                continue
            region_id = str(item.get("region_id", f"r{index:02d}"))
            if region_id in seen:
                region_id = f"{region_id}_{index}"
            seen.add(region_id)
            box = item.get("box")
            if not isinstance(box, Mapping):
                warnings.append(f"region {region_id!r} had no box and was dropped")
                continue
            try:
                cleaned = {
                    "x": float(box["x"]),
                    "y": float(box["y"]),
                    "w": float(box["w"]),
                    "h": float(box["h"]),
                }
            except (KeyError, TypeError, ValueError):
                warnings.append(f"region {region_id!r} had a malformed box and was dropped")
                continue
            if cleaned["w"] <= 0.0 or cleaned["h"] <= 0.0:
                warnings.append(f"region {region_id!r} had zero extent and was dropped")
                continue
            if not all(0.0 <= value <= 1.0 for value in cleaned.values()):
                warnings.append(
                    f"region {region_id!r} was not normalized to 0..1 and was dropped"
                )
                continue
            layer = item.get("layer_order", 0)
            if isinstance(layer, bool) or not isinstance(layer, int):
                layer = 0
            regions.append(
                {
                    "region_id": region_id,
                    "role": role,
                    "box": cleaned,
                    "layer_order": layer,
                }
            )
        if not regions:
            raise ObserverError(
                "backend produced no valid regions; an observation without layout "
                "structure cannot ground a visual claim"
            )
        return regions

    def _coerce(self, value: Any, allowed: Sequence[str], fallback: Any) -> Any:
        return value if value in allowed else fallback

    def _infer_layout_template(self, regions: Sequence[Mapping[str, Any]]) -> str | None:
        """Infer a layout class from region roles, their count, and their geometry.

        The class is derived from structure the observer already found, never
        from content. When the arrangement matches no known class the honest
        answer is ``mixed_irregular`` rather than a guess.

        Order matters here. Text-band count is checked before body-region count,
        because a real observer splits a body column into several bands — one per
        text line group — so counting ``body`` regions would make every text-heavy
        layout look like a card grid.
        """

        roles = [region["role"] for region in regions]
        text_count = sum(1 for role in roles if role in _TEXT_ROLES)
        has_subject = "subject" in roles
        has_chart = "chart" in roles or "data_table" in roles
        subject_count = sum(1 for role in roles if role == "subject")
        chart_count = sum(1 for role in roles if role in {"chart", "data_table"})

        boxes: dict[str, Mapping[str, float]] = {}
        for region in regions:
            # Keep the largest region per role: that is the one that defines the
            # layout, not a sliver of residual ink.
            current = boxes.get(region["role"])
            if current is None or _area(region["box"]) > _area(current):
                boxes[region["role"]] = region["box"]

        title = boxes.get("title") or boxes.get("subtitle")
        subject = boxes.get("subject")

        if title and subject:
            # Overlay: the title sits inside the subject's own area.
            if self._contains(subject, title) and _area(subject) >= 0.5:
                return "full_bleed_overlay"
            # Side by side: little horizontal overlap, and vertical ranges meet.
            horizontal_overlap = self._overlap_span(title, subject, "x")
            if horizontal_overlap <= 0.15 and subject["y"] < title["y"] + title["h"]:
                return "image_left_text_right"
            if subject["y"] + subject["h"] <= title["y"] + 0.05:
                return "image_top_text_bottom"
            if title["y"] + title["h"] <= subject["y"] + 0.05:
                # Text band above a visual block. The M2 vocabulary has no
                # dedicated class for it, and inventing one would break the
                # closed universal vocabulary, so it maps onto the nearest
                # declared arrangement rather than escaping the contract.
                return "image_top_text_bottom"

        # A chart or table beside text is a single-column composition.
        if has_chart and text_count:
            return "single_column"

        # Genuinely separate visual blocks side by side: a card grid or columns.
        if subject_count >= 3:
            return "three_card" if self._columns_aligned(regions) else "list_stack"
        if chart_count >= 2:
            return "grid_matrix"
        if subject_count == 2 and self._columns_aligned(regions):
            return "two_column"

        # Text columns first: two vertically-aligned runs of bands are a
        # two-column composition, and no amount of body-band counting will reveal
        # that on its own because a single dense column also has many bands.
        if self._text_column_count(regions) >= 2:
            return "two_column"

        # Text-dominant frames: distinguish stacked lines from a single block.
        stacked = self._stacked_bands(regions)
        if text_count >= 4 and stacked:
            return "list_stack"
        if subject is None and title is not None:
            return "single_column"
        if len({region["layer_order"] for region in regions}) > 1 and has_subject:
            return "full_bleed_overlay"
        if text_count:
            return "single_column"
        return "mixed_irregular"

    def _text_column_count(self, regions: Sequence[Mapping[str, Any]]) -> int:
        """How many distinct horizontal text columns the bands form.

        Bands are clustered by left edge with a tolerance of half a band width.
        Two well-separated vertical runs of bands mean two columns; one run means
        a single column however many lines it contains.
        """

        bands = [
            region["box"]
            for region in regions
            if region["role"] in {"body", "caption", "label", "subtitle"}
        ]
        if len(bands) < 2:
            return 1

        lefts = sorted(box["x"] for box in bands)
        tolerance = 0.12
        columns = 1
        anchor = lefts[0]
        for left in lefts[1:]:
            if left - anchor > tolerance:
                columns += 1
                anchor = left
        # Only call it multi-column when the separation is substantial, so ragged
        # single-column bands are not mistaken for columns.
        spread = lefts[-1] - lefts[0]
        return columns if spread >= 0.25 else 1

    def _stacked_bands(self, regions: Sequence[Mapping[str, Any]]) -> bool:
        """True when text bands form a vertical stack of similar width."""

        bands = [
            region["box"]
            for region in regions
            if region["role"] in {"body", "label", "caption", "subtitle"}
        ]
        if len(bands) < 3:
            return False
        widths = [_area(box) for box in bands]
        spread = max(widths) - min(widths)
        return spread <= 0.5 * max(widths)

    def _contains(self, outer: Mapping[str, float], inner: Mapping[str, float]) -> bool:
        return (
            inner["x"] >= outer["x"] - 0.05
            and inner["y"] >= outer["y"] - 0.05
            and inner["x"] + inner["w"] <= outer["x"] + outer["w"] + 0.05
            and inner["y"] + inner["h"] <= outer["y"] + outer["h"] + 0.05
        )

    def _overlap_span(
        self, a: Mapping[str, float], b: Mapping[str, float], axis: str
    ) -> float:
        start = max(a[axis], b[axis])
        end = min(a[axis] + a["w" if axis == "x" else "h"], b[axis] + b["w" if axis == "x" else "h"])
        return max(0.0, end - start)

    def _columns_aligned(self, regions: Sequence[Mapping[str, Any]]) -> bool:
        """True when body regions sit side by side rather than stacked."""

        bodies = [region["box"] for region in regions if region["role"] == "body"]
        if len(bodies) < 2:
            return False
        lefts = sorted(round(box["x"], 2) for box in bodies)
        distinct = len({left for left in lefts})
        return distinct >= 2

    def _anchor(self, regions: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        visuals = [region for region in regions if region["role"] in _VISUAL_ROLES]
        if not visuals:
            return None
        return max(
            visuals,
            key=lambda region: (
                _area(region["box"]) * _ANCHOR_WEIGHT.get(region["role"], 1.0),
                region["region_id"],
            ),
        )

    def _subject_class(
        self, regions: Sequence[Mapping[str, Any]], anchor: Mapping[str, Any] | None
    ) -> str:
        """Classify the subject from the *region role it occupies*.

        A subject occupying a chart or table region is a ``data_chart``; a
        subject that shares the frame with a text band is a document-like
        composition. No image content is interpreted — this is region
        composition, not recognition.
        """

        roles = {region["role"] for region in regions}
        if "chart" in roles or "data_table" in roles:
            return "data_chart"
        if anchor is None:
            return "text_only"
        if anchor["role"] == "background":
            return "text_only"
        if any(region["role"] in {"caption", "body"} for region in regions):
            return "document_scan"
        return "composite"

    def _placement(
        self, regions: Sequence[Mapping[str, Any]], anchor: Mapping[str, Any] | None
    ) -> str:
        """Where the dominant visual sits in the frame.

        Derived from the anchor's *geometry*, not its role: the asset placement
        vocabulary describes position, and reusing the region role here would
        conflate two different vocabularies.
        """

        if anchor is None:
            return "unknown"
        box = anchor["box"]
        if _area(box) >= 0.72:
            return "full_bleed"
        if anchor["role"] == "background":
            return "background"
        if box["y"] + box["h"] <= 0.5:
            return "inset_upper"
        if box["y"] >= 0.42:
            return "inset_lower"
        if box["x"] >= 0.45:
            return "side_panel"
        if 0.2 <= box["x"] and box["x"] + box["w"] <= 0.8:
            return "center_stage"
        return "inline_with_text"

    def _roles(
        self,
        regions: Sequence[Mapping[str, Any]],
        visual_raw: Mapping[str, Any],
        style_raw: Mapping[str, Any],
        cross_raw: Sequence[Mapping[str, Any]],
    ) -> tuple[str, ...]:
        roles = ["visual_style_source", "layout_source"]
        region_roles = {region["role"] for region in regions}
        if "subject" in region_roles:
            roles.append("subject_source")
        if "chart" in region_roles or "data_table" in region_roles:
            roles.append("chart_source")
        if style_raw.get("type_scale_relation"):
            roles.append("typography_source")
        if visual_raw.get("palette_relation") not in (None, "mixed"):
            roles.append("color_source")
        if any(region["role"] in _TEXT_ROLES for region in regions):
            roles.append("hook_source")
        return tuple(roles)

    def _evidence_kinds(
        self,
        *,
        regions: Sequence[Mapping[str, Any]],
        layout_template: str | None,
        visual_raw: Mapping[str, Any],
        style_raw: Mapping[str, Any],
        cross_raw: Sequence[Mapping[str, Any]],
        source: VisualSource,
    ) -> tuple[str, ...]:
        """Derive M1 evidence kinds from what the backend actually reported.

        Every kind is drawn from the M1 structural vocabulary. ``ocr_text`` is
        never emitted: the backends have no text to offer, and this method has no
        branch that could produce it.
        """

        kinds: list[str] = []
        if regions:
            kinds.append("region_layout")
            kinds.append("region_geometry")
        if len({region["layer_order"] for region in regions}) > 1:
            kinds.append("dominance_order")
        if layout_template is not None:
            kinds.append("reading_order")
        if visual_raw.get("palette_relation") not in (None, "mixed"):
            kinds.append("color_distribution")
        kinds.append("palette_relation")
        if style_raw.get("type_scale_relation"):
            kinds.append("type_placement")
            kinds.append("type_scale_relation")
        if visual_raw.get("density") not in (None, "balanced"):
            kinds.append("negative_space_ratio")
        if style_raw.get("alignment"):
            kinds.append("alignment_relation")
        if cross_raw:
            kinds.append("dominance_order")
        if source.source_type == "video_frame":
            kinds.append("temporal_rhythm")

        seen: dict[str, None] = {}
        for kind in kinds:
            if kind in STRUCTURAL_EVIDENCE:
                seen.setdefault(kind, None)
        if not seen:
            raise ObserverError(
                f"no structural evidence could be derived for {source.source_id!r}; "
                "an observation must rest on structure"
            )
        return tuple(seen)

    def _build_evidence(
        self,
        *,
        regions: Sequence[Mapping[str, Any]],
        layout_template: str | None,
        visual_raw: Mapping[str, Any],
        style_raw: Mapping[str, Any],
        anchor: Mapping[str, Any] | None,
        cross_raw: Sequence[Mapping[str, Any]],
        placement: str = "unknown",
    ) -> dict[str, EvidenceRecord]:
        """Assemble the four mandatory evidence families."""

        source = (self._backend.evidence_source,)

        layout_strength = 0.0
        if regions:
            layout_strength = min(1.0, 0.4 + 0.1 * len(regions))
        if layout_template is not None:
            layout_strength = min(1.0, layout_strength + 0.2)

        visual_strength = 0.0
        if visual_raw.get("palette_relation") not in (None, "mixed"):
            visual_strength += 0.5
        if visual_raw.get("density"):
            visual_strength += 0.25
        if visual_raw.get("color_family") not in (None, "mixed"):
            visual_strength += 0.25

        asset_strength = 0.0
        if anchor is not None:
            asset_strength = 0.6 if anchor["role"] != "background" else 0.3
        if anchor is not None and anchor["role"] in {"chart", "data_table"}:
            asset_strength = min(1.0, asset_strength + 0.2)

        cross_strength = 0.0
        if cross_raw:
            cross_strength = min(1.0, 0.5 + 0.1 * len(cross_raw))

        return {
            "layout_evidence": EvidenceRecord(
                family="layout_evidence",
                sources=source,
                strength=round(layout_strength, 6),
                detail={
                    "region_count": len(regions),
                    "layout_template_class": layout_template,
                    "layer_count": len({region["layer_order"] for region in regions}),
                },
            ),
            "visual_evidence": EvidenceRecord(
                family="visual_evidence",
                sources=source,
                strength=round(min(1.0, visual_strength), 6),
                detail={
                    "palette_relation": visual_raw.get("palette_relation"),
                    "density": visual_raw.get("density"),
                    "color_family": visual_raw.get("color_family"),
                    "contrast_role": visual_raw.get("contrast_role"),
                },
            ),
            "asset_evidence": EvidenceRecord(
                family="asset_evidence",
                sources=source,
                strength=round(asset_strength, 6),
                detail={
                    "anchor_role": anchor["role"] if anchor else None,
                    "anchor_region_id": anchor["region_id"] if anchor else None,
                    "placement": placement,
                },
            ),
            "cross_modal_evidence": EvidenceRecord(
                family="cross_modal_evidence",
                sources=source,
                strength=round(cross_strength, 6),
                detail={
                    "relation_count": len(cross_raw),
                    "relations": [
                        {
                            "text_region_id": item.get("text_region_id"),
                            "visual_region_id": item.get("visual_region_id"),
                            "geometric_relation": item.get("geometric_relation"),
                        }
                        for item in cross_raw
                    ],
                },
            ),
        }

    def _confidence(self, evidence: Mapping[str, EvidenceRecord]) -> float:
        total = sum(evidence[family].strength for family in EVIDENCE_FAMILIES)
        return round(total / len(EVIDENCE_FAMILIES), 6)


class VideoSequenceObserver:
    """Observe an ordered sequence of frames and record page rhythm.

    Frame observation reuses :class:`FrameObserver` unchanged; this class adds
    only what is genuinely temporal — the ordering, the layout transitions
    between frames, and the sequence roles. Frames are supplied already extracted,
    because decoding video is out of scope for M3.
    """

    def __init__(self, backend: VisionBackend) -> None:
        self._frame_observer = FrameObserver(backend)

    def observe_sequence(
        self, frames: Sequence[VisualSource]
    ) -> tuple[ObservationResult, ...]:
        if not frames:
            raise ObserverError("a video sequence needs at least one frame")
        results = self._frame_observer.observe_all(frames)
        layouts = [result.observation.layout_template_class for result in results]
        transitions = sum(
            1 for index in range(1, len(layouts)) if layouts[index] != layouts[index - 1]
        )
        enriched: list[ObservationResult] = []
        for index, result in enumerate(results):
            existing = result.evidence["cross_modal_evidence"]
            detail = dict(existing.detail)
            # Sequence structure is additive: the frame's own cross-modal
            # relations are preserved and the temporal facts are layered on top,
            # so the record still describes the same evidence family.
            detail.update(
                {
                    "sequence_index": index,
                    "sequence_length": len(results),
                    "layout_transitions": transitions,
                    "layout_sequence": layouts,
                    "previous_layout": layouts[index - 1] if index else None,
                }
            )
            revised = dict(result.evidence)
            revised["cross_modal_evidence"] = EvidenceRecord(
                family="cross_modal_evidence",
                sources=existing.sources,
                strength=max(existing.strength, 0.5 if len(results) > 1 else 0.0),
                detail=detail,
            )
            enriched.append(
                ObservationResult(
                    observation=result.observation,
                    source=result.source,
                    backend_id=result.backend_id,
                    evidence_source=result.evidence_source,
                    evidence=revised,
                    confidence=result.confidence,
                    warnings=result.warnings,
                    backend_failures=result.backend_failures,
                )
            )
        return tuple(enriched)


__all__ = ["FrameObserver", "VideoSequenceObserver"]
