"""Real pixel-analysis vision backend (Phase M3).

This is the adapter that replaces M2's mock observer with genuine image analysis.
It is a :class:`VisionBackend`: four structural questions, no model, no
randomness, no network.

How structure is recovered from pixels
--------------------------------------

1. Decode the asset (stdlib PNG codec) and build a reduced working grid.
2. Flood-fill the grid into connected components of similar colour.
3. Detect text-like bands by **luminance alternation**, not by recognition: a
   line of text reverses light/dark many times across a row, whereas a boundary
   between two flat blocks steps once and stays there.
4. Separate charts and tables from flat subject blocks by **internal texture
   regularity** — a table has near-constant per-row and per-column fill, a chart
   has tall irregular bars.
5. Assign region roles from *position, size, layer, saturation, and texture*.

Step 5 is where the M1 anti-OCR rule is enforced at the pixel level. A band's
role is decided by where it sits and how big it is:

===================  ==========================================================
Situation            Role assigned
===================  ==========================================================
full-width, top      ``title``
full-width, bottom   ``cta``
narrow, lower        ``caption``
narrow, small        ``label``
otherwise, text-like ``body``
===================  ==========================================================

An image reading "BUY NOW" cannot produce a bottom action area unless the band
actually occupies a full-width strip at the bottom of the frame. The words are
never read, so they cannot drive the structure. This is the structural signature
doing the work, exactly as M1's contract requires.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..taxonomy import (
    LAYOUT_TEMPLATE_CLASSES,
    STRUCTURAL_EVIDENCE,
)
from .pixel.png_codec import PngCodecError, RgbImage, read_png
from .pixel.primitives import (
    Component,
    PixelGrid,
    TextBand,
    build_grid,
    classify_color_family,
    contrast_role_of,
    count_alternations,
    detect_text_bands,
    dominant_colors,
    high_frequency_energy,
    label_components,
    luminance,
    palette_relation_of,
)
from .interface import ObserverError, VisionBackend, VisualSource

#: Working-grid resolution. The grid must stay fine enough that a text stroke
#: survives integer downscaling: a stroke is ~3 px wide in a 480 px asset, so a
#: 64-cell grid (factor 7) largely preserves it while a 48-cell grid (factor 10)
#: can drop it. Grid resolution is therefore a real design parameter, not a
#: performance knob.
DEFAULT_GRID_TARGET = 80

#: Colour distance tolerance for connected components. Slightly above the
#: primitive default because rendered assets carry sensor-like grain.
COMPONENT_TOLERANCE = 0.13

#: A component covering more than this fraction of the frame is treated as a
#: background or full-bleed subject and placed on layer 0.
FULL_FRAME_COVERAGE = 0.42

#: Minimum component size, as a fraction of grid cells, to be reported at all.
MIN_COMPONENT_SHARE = 0.004


@dataclass(frozen=True, slots=True)
class RegionEvidence:
    """One detected region plus the measurements that justified its role."""

    region_id: str
    role: str
    box: Mapping[str, float]
    layer_order: int
    coverage: float
    fill_ratio: float
    aspect: float
    mean_luma: float
    saturation: float
    texture_regularity: float
    source: str
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "role": self.role,
            "box": dict(self.box),
            "layer_order": self.layer_order,
            "coverage": self.coverage,
            "fill_ratio": self.fill_ratio,
            "aspect": self.aspect,
            "mean_luma": self.mean_luma,
            "saturation": self.saturation,
            "texture_regularity": self.texture_regularity,
            "source": self.source,
            "rationale": self.rationale,
        }


def _saturation(rgb: tuple[int, int, int]) -> float:
    from .pixel.primitives import rgb_to_hsv

    return rgb_to_hsv(*rgb)[1]


def _subgrid(grid: PixelGrid, x0: int, y0: int, x1: int, y1: int) -> PixelGrid:
    """A view restricted to one component's bounding box.

    Texture must be measured *inside* the component. Measuring whole-frame energy
    and applying it to a single block lets unrelated content elsewhere in the
    image decide what that block is — which is how a flat image block next to a
    text column was being labelled a chart.
    """

    left = max(0, min(x0, x1))
    right = min(grid.width - 1, max(x0, x1))
    top = max(0, min(y0, y1))
    bottom = min(grid.height - 1, max(y0, y1))

    rgb: list[tuple[int, int, int]] = []
    luma: list[float] = []
    families: list[str] = []
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            value = grid.rgb[y * grid.width + x]
            rgb.append(value)
            luma.append(grid.luma[y * grid.width + x])
            families.append(grid.color_family[y * grid.width + x])

    return PixelGrid(
        width=max(1, right - left + 1),
        height=max(1, bottom - top + 1),
        scale=grid.scale,
        rgb=tuple(rgb),
        luma=tuple(luma),
        color_family=tuple(families),
        source_width=grid.source_width,
        source_height=grid.source_height,
    )


def _texture_regularity(
    grid: PixelGrid, x0: int, y0: int, x1: int, y1: int
) -> float:
    """How uniform the interior of a component is, per row and per column.

    A table's rows are near-constant across their width and its grid lines recur
    at a fixed pitch, so both scores are high. A chart's bars vary in height, so
    row uniformity is lower while column uniformity stays moderate. A flat block
    scores highest of all, which is why the caller also checks colour variance
    before calling something a table.
    """

    if x1 <= x0 or y1 <= y0:
        return 0.0

    row_scores: list[float] = []
    for y in range(y0, y1 + 1):
        values = [grid.luma[y * grid.width + x] for x in range(x0, x1 + 1)]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        row_scores.append(max(0.0, 1.0 - variance * 40.0))

    column_scores: list[float] = []
    for x in range(x0, x1 + 1):
        values = [grid.luma[y * grid.width + x] for y in range(y0, y1 + 1)]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        column_scores.append(max(0.0, 1.0 - variance * 40.0))

    rows = sum(row_scores) / len(row_scores)
    columns = sum(column_scores) / len(column_scores)
    # Columns are weighted higher: a table's vertical rules are its signature.
    return round(0.35 * rows + 0.65 * columns, 6)


def count_grid_lines(
    grid: PixelGrid,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    line_threshold: float = 0.18,
) -> tuple[int, int]:
    """Count interior horizontal and vertical luminance discontinuities.

    A table is defined by having *structure* inside it: rules that cross its
    width and height at a regular pitch. A flat subject block, by contrast, has a
    perfectly uniform interior and therefore no interior discontinuities at all.

    This is the measurement that separates the two. An earlier version used
    "high regularity" as the table signal, which had it exactly backwards: a
    solid coloured block is the *most* regular thing in the frame, so plain
    subject blocks were being reported as tables. Counting actual grid lines
    fixes the direction of the test.
    """

    horizontal = 0
    for y in range(y0 + 1, y1 + 1):
        changes = 0
        for x in range(x0, x1 + 1):
            if (
                abs(grid.luma[y * grid.width + x] - grid.luma[(y - 1) * grid.width + x])
                > line_threshold
            ):
                changes += 1
        # A rule spans most of the region's width.
        if changes >= max(2, int((x1 - x0 + 1) * 0.6)):
            horizontal += 1

    vertical = 0
    for x in range(x0 + 1, x1 + 1):
        changes = 0
        for y in range(y0, y1 + 1):
            if (
                abs(grid.luma[y * grid.width + x] - grid.luma[y * grid.width + x - 1])
                > line_threshold
            ):
                changes += 1
        if changes >= max(2, int((y1 - y0 + 1) * 0.6)):
            vertical += 1

    return horizontal, vertical


class StdlibPixelBackend:
    """A real vision backend implemented on stdlib primitives only.

    Stateless between calls. Each method re-decodes the asset, which keeps the
    backend trivially correct at the cost of redundant work; a caching layer
    would be an optimisation, and M3 is not optimising.
    """

    backend_id = "stdlib_pixel_v1"
    evidence_source = "pixel_analysis"

    def __init__(self, *, grid_target: int = DEFAULT_GRID_TARGET) -> None:
        if grid_target < 8:
            raise ObserverError("grid_target must be at least 8")
        self._grid_target = grid_target
        self._cache: dict[str, tuple[RgbImage, PixelGrid]] = {}

    # -- asset access ------------------------------------------------------

    def _load(self, source: VisualSource) -> tuple[RgbImage, PixelGrid]:
        key = str(source.asset_reference)
        if key in self._cache:
            return self._cache[key]
        path = Path(key)
        if not path.is_file():
            raise ObserverError(
                f"asset for source {source.source_id!r} does not exist: {path}"
            )
        try:
            image = read_png(path)
        except PngCodecError as exc:
            raise ObserverError(
                f"cannot decode asset for source {source.source_id!r}: {exc}"
            ) from exc
        grid = build_grid(image, target=self._grid_target)
        self._cache[key] = (image, grid)
        return image, grid

    def clear_cache(self) -> None:
        self._cache.clear()

    # -- region detection --------------------------------------------------

    def detect_regions(self, source: VisualSource) -> Sequence[Mapping[str, Any]]:
        return [item.as_dict() for item in self.analyse(source)]

    def analyse(self, source: VisualSource) -> list[RegionEvidence]:
        """Full region analysis with the measurements behind each role.

        Exposed separately from :meth:`detect_regions` so tests and reports can
        inspect *why* a role was assigned, not just what it was.
        """

        image, grid = self._load(source)
        components = label_components(grid, tolerance=COMPONENT_TOLERANCE)
        bands = detect_text_bands(grid)
        total_cells = grid.width * grid.height

        # --- visual blocks first, so text bands can be clipped against them ---
        #
        # A text band's horizontal envelope can extend across a coloured block
        # that sits beside the text, because the block's antialiased edge
        # contributes the odd alternation. Left uncorrected, the band then
        # overlaps the block and the layout reads as an overlay when it is really
        # a split. Clipping the band at the block boundary fixes the geometry
        # before any role is assigned.
        #
        # Full-frame blocks are included even when they are dark and unsaturated.
        # A dark full-bleed background is not "colourless background noise" — it
        # is the backdrop an overlay composition sits on, and excluding it would
        # let the detector absorb the overlaid text into the ground. Such blocks
        # never actually clip anything: ``_clip_band`` skips them by design.
        visual_components = [
            component
            for component in components
            if component.cell_count / total_cells >= MIN_COMPONENT_SHARE
            and (
                component.cell_count / total_cells >= FULL_FRAME_COVERAGE
                or _saturation(component.mean_rgb) >= 0.12
            )
        ]

        evidences: list[RegionEvidence] = []
        covered: list[tuple[int, int, int, int]] = []

        for band in bands:
            clipped = self._clip_band(grid, band, visual_components)
            if clipped is None:
                continue
            band = clipped
            extent = band.width / grid.width
            top = band.y0 / grid.height
            bottom = band.y1 / grid.height
            role = self._text_role(extent=extent, top=top, bottom=bottom, band=band)
            evidence = RegionEvidence(
                region_id=band.band_id,
                role=role,
                box=grid.box_norm(band.x0, band.y0, band.x1, band.y1),
                layer_order=1,
                coverage=round(
                    (band.width * band.height) / total_cells, 6
                ),
                fill_ratio=round(band.transition_density, 6),
                aspect=round(band.width / max(1, band.height), 6),
                mean_luma=self._band_luma(grid, band),
                saturation=0.0,
                texture_regularity=0.0,
                source="text_band",
                rationale=(
                    f"luminance alternation with {band.run_count} runs/row, "
                    f"horizontal extent {extent:.2f}, vertical position "
                    f"{top:.2f}-{bottom:.2f}"
                ),
            )
            evidences.append(evidence)
            covered.append((band.x0, band.y0, band.x1, band.y1))

        # --- blocks: role from coverage, saturation, texture, position ------
        for component in components:
            if component.cell_count / total_cells < MIN_COMPONENT_SHARE:
                continue
            if self._overlaps_text(component, covered):
                continue
            role, rationale, regularity = self._block_role(grid, component, total_cells)
            if role is None:
                continue
            saturation = _saturation(component.mean_rgb)
            evidences.append(
                RegionEvidence(
                    region_id=component.component_id,
                    role=role,
                    box=grid.box_norm(
                        component.x0, component.y0, component.x1, component.y1
                    ),
                    layer_order=self._layer_for(component, total_cells),
                    coverage=round(component.cell_count / total_cells, 6),
                    fill_ratio=round(component.fill_ratio, 6),
                    aspect=round(component.aspect, 6),
                    mean_luma=round(component.mean_luma, 6),
                    saturation=round(saturation, 6),
                    texture_regularity=regularity,
                    source="component",
                    rationale=rationale,
                )
            )

        # Ground is required by the schema's region vocabulary and by the
        # similarity contract's coverage term, so guarantee one.
        if not any(item.role == "background" for item in evidences):
            evidences.append(self._ground_evidence(grid))

        evidences.sort(key=lambda item: (item.layer_order, item.box["y"], item.box["x"]))
        return self._dedupe_roles(evidences)

    def _clip_band(
        self,
        grid: PixelGrid,
        band: TextBand,
        visual_components: Sequence[Component],
    ) -> TextBand | None:
        """Clip a text band's horizontal extent at any block it runs into.

        Returns ``None`` when the band is reduced to less than a third of its
        original width, which means it was mostly block edge rather than ink.
        """

        original_width = band.width
        left, right = band.x0, band.x1

        for component in visual_components:
            # A backdrop is a block that spans essentially the whole frame — a
            # full-bleed image with text laid over it. Only such a block is
            # exempt from clipping.
            #
            # An earlier version exempted any block whose vertical range enclosed
            # the band. That was wrong: a headline band is only a couple of cells
            # tall, so a mid-frame subject block trivially encloses it and was
            # wrongly treated as a backdrop — which is exactly how overlaid-looking
            # bands survived and every split layout was misread as an overlay.
            if component.width >= grid.width - 1 and component.height >= grid.height - 1:
                continue
            # Only consider blocks whose vertical range actually meets the band.
            if component.y1 < band.y0 or component.y0 > band.y1:
                continue
            if component.x0 > left and component.x0 <= right:
                right = min(right, component.x0 - 1)
            elif component.x1 < right and component.x1 >= left:
                left = max(left, component.x1 + 1)

        if right - left + 1 < max(2, int(original_width / 3)):
            return None
        return TextBand(
            band_id=band.band_id,
            x0=left,
            y0=band.y0,
            x1=right,
            y1=band.y1,
            run_count=band.run_count,
            transition_density=band.transition_density,
            contrast=band.contrast,
        )

    def _text_role(self, *, extent: float, top: float, bottom: float, band: TextBand) -> str:
        """Decide a text band's role from geometry alone.

        This helper is the enforcement point for the anti-OCR rule. Every branch
        reads position and extent; none reads content, because none is available.
        """

        if extent >= 0.62:
            if top <= 0.30:
                return "title"
            if bottom >= 0.72:
                return "cta"
            if bottom >= 0.60:
                return "footer"
            return "body"
        if extent >= 0.30:
            return "subtitle" if top <= 0.35 else "body"
        return "label" if band.height <= max(2, band.width // 3) else "caption"

    def _block_role(
        self, grid: PixelGrid, component: Component, total_cells: int
    ) -> tuple[str | None, str, float]:
        """Decide a non-text component's role from coverage, saturation, texture."""

        share = component.cell_count / total_cells
        saturation = _saturation(component.mean_rgb)
        regularity = _texture_regularity(
            grid, component.x0, component.y0, component.x1, component.y1
        )
        horizontal_lines, vertical_lines = count_grid_lines(
            grid, component.x0, component.y0, component.x1, component.y1
        )

        if share >= FULL_FRAME_COVERAGE:
            # Covers most of the frame: either the ground or a full-bleed subject.
            if saturation < 0.18:
                return (
                    "background",
                    f"covers {share:.2f} of the frame with saturation "
                    f"{saturation:.2f}: ground",
                    regularity,
                )
            return (
                "subject",
                f"covers {share:.2f} of the frame at saturation "
                f"{saturation:.2f}: full-bleed subject",
                regularity,
            )

        if saturation < 0.12:
            return None, "", regularity

        # Inside the frame, with real colour: table, chart, or plain subject.
        # The discriminator is interior *structure*, not interior uniformity.
        if horizontal_lines >= 2 and vertical_lines >= 1 and share >= 0.06:
            return (
                "data_table",
                f"{horizontal_lines} horizontal and {vertical_lines} vertical "
                f"interior rules over {share:.2f} of the frame",
                regularity,
            )
        if high_frequency_energy(
            _subgrid(grid, component.x0, component.y0, component.x1, component.y1)
        ) >= 0.028 and share >= 0.06:
            return (
                "chart",
                f"high-frequency interior detail (regularity {regularity:.3f}) "
                f"over {share:.2f} of the frame",
                regularity,
            )
        return (
            "subject",
            f"flat coloured block covering {share:.2f} of the frame at saturation "
            f"{saturation:.2f} with {horizontal_lines} interior rules",
            regularity,
        )

    def _layer_for(self, component: Component, total_cells: int) -> int:
        """Frame-filling components are the layer beneath everything else."""

        return 0 if component.cell_count / total_cells >= FULL_FRAME_COVERAGE else 1

    def _overlaps_text(
        self, component: Component, covered: Sequence[tuple[int, int, int, int]]
    ) -> bool:
        """True when a component lies *substantially inside* a detected text band.

        Text ink fragments into many small components, and those must not each
        become a region. But the test has to be containment, not centre-point
        membership: two stacked text regions produce bands whose horizontal
        envelopes overlap the image block beside them, so a centre-point test
        would discard the image block entirely. Requiring most of the
        component's own area to fall inside the band keeps ink filtered while
        leaving genuine visual blocks alone.
        """

        box_area = max(1, component.width * component.height)
        for x0, y0, x1, y1 in covered:
            ix0 = max(component.x0, x0)
            iy0 = max(component.y0, y0)
            ix1 = min(component.x1, x1)
            iy1 = min(component.y1, y1)
            if ix1 < ix0 or iy1 < iy0:
                continue
            intersection = (ix1 - ix0 + 1) * (iy1 - iy0 + 1)
            if intersection / box_area >= 0.6:
                return True
        return False

    def _band_luma(self, grid: PixelGrid, band: TextBand) -> float:
        total = 0.0
        count = 0
        for y in range(band.y0, band.y1 + 1):
            for x in range(band.x0, band.x1 + 1):
                total += grid.luma[y * grid.width + x]
                count += 1
        return round(total / count, 6) if count else 0.0

    def _ground_evidence(self, grid: PixelGrid) -> RegionEvidence:
        return RegionEvidence(
            region_id="ground",
            role="background",
            box={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            layer_order=0,
            coverage=1.0,
            fill_ratio=1.0,
            aspect=round(grid.width / max(1, grid.height), 6),
            mean_luma=round(sum(grid.luma) / len(grid.luma), 6),
            saturation=0.0,
            texture_regularity=0.0,
            source="synthetic_ground",
            rationale="no component covered the frame; a ground is required by contract",
        )

    def _dedupe_roles(self, evidences: Sequence[RegionEvidence]) -> list[RegionEvidence]:
        """Drop later duplicates of a single-instance role.

        ``background``, ``subject``, ``chart``, and ``data_table`` describe one
        thing each. Keeping the largest (already first after sorting by layer and
        position, then by coverage) prevents a speckle from claiming a role that
        a real region already occupies.
        """

        single = {"background", "subject", "chart", "data_table"}
        seen: set[str] = set()
        ordered = sorted(evidences, key=lambda item: -item.coverage)
        kept: list[RegionEvidence] = []
        for evidence in ordered:
            if evidence.role in single:
                if evidence.role in seen:
                    continue
                seen.add(evidence.role)
            kept.append(evidence)
        kept.sort(key=lambda item: (item.layer_order, item.box["y"], item.box["x"]))
        return kept

    # -- visual roles ------------------------------------------------------

    def detect_visual_roles(self, source: VisualSource) -> Mapping[str, Any]:
        image, grid = self._load(source)
        families = dominant_colors(grid, top=4)
        names = [family for family, _share in families]
        shares = [share for _family, share in families]

        palette_relation = palette_relation_of(names, shares)
        luma_values = list(grid.luma)
        top_luma = max(luma_values)
        bottom_luma = min(luma_values)
        contrast = contrast_role_of(
            top_luma=top_luma, bottom_luma=bottom_luma, palette_relation=palette_relation
        )

        # Density from ink coverage: how much of the frame is text-like or busy.
        bands = detect_text_bands(grid)
        band_share = sum(band.width * band.height for band in bands) / (
            grid.width * grid.height
        )
        energy = high_frequency_energy(grid)
        if band_share >= 0.30 or energy >= 0.055:
            density = "dense"
        elif band_share <= 0.12 and energy <= 0.030:
            density = "sparse"
        else:
            density = "balanced"

        return {
            "color_family": names[0] if names else "mixed",
            "color_families": names,
            "color_shares": shares,
            "palette_relation": palette_relation,
            "contrast_role": contrast,
            "density": density,
            "high_frequency_energy": energy,
            "band_share": round(band_share, 6),
            "source_size": [image.width, image.height],
        }

    # -- style features ----------------------------------------------------

    def detect_style_features(self, source: VisualSource) -> Mapping[str, Any]:
        _image, grid = self._load(source)
        bands = detect_text_bands(grid)

        # Hierarchy depth: count text bands separated by a clear vertical gap,
        # and distinguish sizes by band height.
        heights = sorted({band.height for band in bands}, reverse=True)
        distinct_sizes = 0
        for height in heights:
            if not any(
                abs(height - chosen) <= max(1, chosen // 3)
                for chosen in heights[:distinct_sizes]
            ):
                distinct_sizes += 1
        levels = max(1, min(4, distinct_sizes or (1 if bands else 0)))

        if levels <= 1:
            scale = "single_level"
        elif levels == 2:
            scale = "two_level"
        elif levels == 3:
            scale = "three_plus_levels"
        else:
            scale = "mixed"

        # Alignment from the left edges of text bands.
        if bands:
            lefts = [round(band.x0 / grid.width, 2) for band in bands]
            widths = [band.width / grid.width for band in bands]
            if len(set(lefts)) > 1:
                alignment = "grid"
            elif widths and widths[0] >= 0.8:
                alignment = "center"
            elif min(lefts) <= 0.20:
                alignment = "left"
            else:
                alignment = "right"
        else:
            alignment = None

        return {
            "type_scale_relation": scale,
            "hierarchy_levels": levels,
            "alignment": alignment,
            "text_band_count": len(bands),
            "text_band_heights": [band.height for band in bands],
        }

    # -- cross-modal alignment --------------------------------------------

    def detect_text_visual_alignment(
        self, source: VisualSource
    ) -> Sequence[Mapping[str, Any]]:
        """Relate text bands to the dominant non-text region, from geometry.

        Uses the M1/M2 geometric relation vocabulary through the same
        ``geometric_relation`` helper the mock path used, so a real observation
        and a mock observation express relations identically.
        """

        from ..extraction.cross_modal_candidates import geometric_relation

        evidences = self.analyse(source)
        text_like = {
            "title", "subtitle", "body", "caption", "label", "cta", "header", "footer"
        }
        visual_like = {"subject", "chart", "data_table", "background"}

        text_regions = [item for item in evidences if item.role in text_like]
        visual_regions = [item for item in evidences if item.role in visual_like]
        if not text_regions or not visual_regions:
            return ()

        # Anchor weighting mirrors the M2 rule: a subject or chart is what the
        # composition is *about*, a ground is not.
        weights = {"subject": 4.0, "chart": 4.0, "data_table": 4.0, "background": 0.25}
        anchor = max(
            visual_regions,
            key=lambda item: (
                item.coverage * weights.get(item.role, 1.0),
                item.region_id,
            ),
        )

        relations: list[Mapping[str, Any]] = []
        for text in sorted(text_regions, key=lambda item: item.region_id):
            relation = geometric_relation(
                text.box, anchor.box, text_layer=text.layer_order,
                visual_layer=anchor.layer_order,
            )
            relations.append(
                {
                    "text_region_id": text.region_id,
                    "text_role": text.role,
                    "visual_region_id": anchor.region_id,
                    "visual_role": anchor.role,
                    "geometric_relation": relation,
                    "rationale": (
                        f"text band {text.region_id} is {relation} the dominant "
                        f"visual region {anchor.region_id} ({anchor.role})"
                    ),
                }
            )
        return relations
