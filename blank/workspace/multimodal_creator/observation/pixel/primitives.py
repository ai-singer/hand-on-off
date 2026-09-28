"""Dependency-free pixel analysis primitives (Phase M3).

These are the tools the real observer uses to turn a raster into structural
facts. Everything here is deterministic and explainable — no learned weights, no
model, no randomness.

What it computes, and what it deliberately does not
---------------------------------------------------

Computes: connected components over a colour-quantised grid, component bounding
boxes with fill ratio and aspect, luminance statistics, colour-family
classification, text-line band detection via row-run regularity, and
high-frequency energy as a proxy for chart-like content.

Does **not** compute: any character recognition. There is no glyph matching, no
template matching against letterforms, and no OCR anywhere in this package. Text
regions are located by their *pixel statistics* — many short, evenly spaced,
high-contrast horizontal runs — and their role is then decided by **position,
size, and layer**, never by what they say.

That is the M1 anti-OCR boundary expressed at the pixel level: an image reading
"BUY NOW" cannot produce a CTA layout, because the observer never learns what the
words are. A bottom, full-width, high-contrast text band produces a bottom action
area regardless of its content.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .png_codec import PngCodecError, RgbImage

# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------

#: Coarse colour families, matching the M2 extraction vocabulary so observations
#: produced by the real backend remain comparable with the mock backend.
COLOR_FAMILY_KEYWORDS: Mapping[str, tuple[float, float, float]] = {
    # family -> approximate (hue_degrees, saturation, value)
    "warm_red": (0.0, 0.7, 0.8),
    "warm_orange": (30.0, 0.8, 0.9),
    "warm_yellow": (55.0, 0.8, 0.9),
    "cool_green": (120.0, 0.6, 0.6),
    "cool_teal": (175.0, 0.5, 0.6),
    "cool_blue": (220.0, 0.6, 0.7),
}


def rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert an RGB triple to (hue degrees, saturation, value) in 0..1."""

    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    maximum = max(rf, gf, bf)
    minimum = min(rf, gf, bf)
    delta = maximum - minimum

    if delta == 0.0:
        hue = 0.0
    elif maximum == rf:
        hue = (60.0 * ((gf - bf) / delta)) % 360.0
    elif maximum == gf:
        hue = 60.0 * (((bf - rf) / delta) + 2.0)
    else:
        hue = 60.0 * (((rf - gf) / delta) + 4.0)

    saturation = 0.0 if maximum == 0.0 else delta / maximum
    return hue, saturation, maximum


def luminance(r: int, g: int, b: int) -> float:
    """Rec. 601 relative luminance in 0..1."""

    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def classify_color_family(r: int, g: int, b: int) -> str:
    """Classify a colour into the shared colour-family vocabulary.

    Low-saturation colours resolve to a monochrome or neutral family; saturated
    colours resolve to the nearest hue family. The thresholds are fixed and
    published, so the classification can be audited and argued with.
    """

    hue, saturation, value = rgb_to_hsv(r, g, b)
    if saturation < 0.15:
        if value < 0.25:
            return "dark_monochrome"
        if value > 0.8:
            return "light_monochrome"
        return "neutral_grey"
    if saturation < 0.30 and 20.0 <= hue <= 60.0:
        return "neutral_beige"

    best_family = "mixed"
    best_distance = float("inf")
    for family, (target_hue, _target_sat, _target_val) in COLOR_FAMILY_KEYWORDS.items():
        distance = min(abs(hue - target_hue), 360.0 - abs(hue - target_hue))
        if distance < best_distance:
            best_distance = distance
            best_family = family
    # Beyond 40 degrees from every named hue, the colour is genuinely ambiguous.
    return best_family if best_distance <= 40.0 else "mixed"


# --------------------------------------------------------------------------
# Working grid
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PixelGrid:
    """A downscaled raster plus its raw luminance and colour labels.

    The grid is the analysis substrate: connected components, bands, and
    statistics all operate here rather than at full resolution, which keeps the
    work bounded and the results stable against single-pixel noise.
    """

    width: int
    height: int
    scale: int
    rgb: tuple[tuple[int, int, int], ...]
    luma: tuple[float, ...]
    color_family: tuple[str, ...]
    source_width: int
    source_height: int

    def at(self, x: int, y: int) -> tuple[int, int, int]:
        return self.rgb[y * self.width + x]

    def box_norm(self, x0: int, y0: int, x1: int, y1: int) -> dict[str, float]:
        """Convert inclusive grid bounds to a normalized ``xywh`` box."""

        left = max(0, min(x0, x1))
        right = min(self.width - 1, max(x0, x1))
        top = max(0, min(y0, y1))
        bottom = min(self.height - 1, max(y0, y1))
        width = right - left + 1
        height = bottom - top + 1
        return {
            "x": round(left / self.width, 6),
            "y": round(top / self.height, 6),
            "w": round(width / self.width, 6),
            "h": round(height / self.height, 6),
        }


def build_grid(image: RgbImage, *, target: int = 48) -> PixelGrid:
    """Downscale an image to roughly ``target`` cells on its long edge.

    Choosing the factor from the source size keeps the grid resolution
    comparable across differently sized inputs, which matters because the
    similarity contract compares normalized geometry.
    """

    longest = max(image.width, image.height)
    factor = max(1, longest // target)
    small = image.downscale(factor) if factor > 1 else image

    rgb: list[tuple[int, int, int]] = []
    luma: list[float] = []
    families: list[str] = []
    for y in range(small.height):
        for x in range(small.width):
            r, g, b = small.pixel(x, y)
            rgb.append((r, g, b))
            luma.append(luminance(r, g, b))
            families.append(classify_color_family(r, g, b))

    return PixelGrid(
        width=small.width,
        height=small.height,
        scale=factor,
        rgb=tuple(rgb),
        luma=tuple(luma),
        color_family=tuple(families),
        source_width=image.width,
        source_height=image.height,
    )


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Component:
    """A connected region of similar colour in the working grid."""

    component_id: str
    label: int
    x0: int
    y0: int
    x1: int
    y1: int
    cell_count: int
    mean_rgb: tuple[int, int, int]

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def fill_ratio(self) -> float:
        """Fraction of the bounding box actually covered by the component."""

        return self.cell_count / self.area if self.area else 0.0

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def mean_luma(self) -> float:
        return luminance(*self.mean_rgb)


def label_components(grid: PixelGrid, *, tolerance: float = 0.10) -> list[Component]:
    """Flood-fill the grid into connected components of similar colour.

    Connectivity is 4-neighbour. Two cells join when their mean RGB distance is
    within ``tolerance`` of full scale, expressed as a normalized Euclidean
    distance. Returns components sorted by descending cell count with a stable
    tie-break on position, so results never depend on traversal order.
    """

    total = grid.width * grid.height
    labels = [-1] * total
    components: list[Component] = []
    threshold = tolerance * 441.6729  # sqrt(3) * 255

    def close(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
        dr = a[0] - b[0]
        dg = a[1] - b[1]
        db = a[2] - b[2]
        return math.sqrt(dr * dr + dg * dg + db * db) <= threshold

    next_label = 0
    for start in range(total):
        if labels[start] != -1:
            continue
        seed = grid.rgb[start]
        label = next_label
        next_label += 1
        stack = [start]
        labels[start] = label
        cells: list[int] = []

        while stack:
            index = stack.pop()
            cells.append(index)
            x = index % grid.width
            y = index // grid.width
            neighbours = []
            if x > 0:
                neighbours.append(index - 1)
            if x + 1 < grid.width:
                neighbours.append(index + 1)
            if y > 0:
                neighbours.append(index - grid.width)
            if y + 1 < grid.height:
                neighbours.append(index + grid.width)
            for neighbour in neighbours:
                if labels[neighbour] != -1:
                    continue
                if close(seed, grid.rgb[neighbour]):
                    labels[neighbour] = label
                    stack.append(neighbour)

        xs = [cell % grid.width for cell in cells]
        ys = [cell // grid.width for cell in cells]
        total_r = sum(grid.rgb[cell][0] for cell in cells)
        total_g = sum(grid.rgb[cell][1] for cell in cells)
        total_b = sum(grid.rgb[cell][2] for cell in cells)
        count = len(cells)
        components.append(
            Component(
                component_id=f"c{label:03d}",
                label=label,
                x0=min(xs),
                y0=min(ys),
                x1=max(xs),
                y1=max(ys),
                cell_count=count,
                mean_rgb=(
                    total_r // count,
                    total_g // count,
                    total_b // count,
                ),
            )
        )

    components.sort(key=lambda item: (-item.cell_count, item.y0, item.x0))
    return components


# --------------------------------------------------------------------------
# Text-band detection (structure only, never content)
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextBand:
    """A horizontal band whose pixel statistics indicate text-like content.

    "Text-like" means: alternating short runs of contrasting luminance, repeated
    across several rows, with a regular vertical period. That is a *structural*
    signature. The observer never determines what the characters are, so a band
    can be located and given a position-based role without the pipeline ever
    reading a word.
    """

    band_id: str
    x0: int
    y0: int
    x1: int
    y1: int
    run_count: int
    transition_density: float
    contrast: float

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1


def count_alternations(row: Sequence[float], *, threshold: float = 0.08) -> int:
    """Count sign reversals in a row's luminance signal, ignoring deadband.

    This is the structural difference between text and a colour boundary. A line
    of text alternates dark-light-dark-light many times, so its signal reverses
    repeatedly. A boundary between two flat blocks steps once and stays there,
    which is monotonic and scores zero.

    Counting *reversals* rather than raw deltas is what stops a large flat
    colour block from being mistaken for a text band — a distinction the
    observer must get right without ever reading characters.
    """

    last_sign = 0
    reversals = 0
    previous = row[0]
    for value in row[1:]:
        delta = value - previous
        previous = value
        if abs(delta) < threshold:
            continue
        sign = 1 if delta > 0 else -1
        if last_sign != 0 and sign != last_sign:
            reversals += 1
        last_sign = sign
    return reversals


def detect_text_bands(
    grid: PixelGrid,
    *,
    min_contrast: float = 0.22,
    min_transitions: int = 3,
    min_rows: int = 2,
) -> list[TextBand]:
    """Locate text-like bands from row luminance alternation.

    A row is "active" when its luminance signal reverses at least
    ``min_transitions`` times and its contrast (max-min luminance) exceeds
    ``min_contrast``. Consecutive active rows form a band. Nothing about the
    glyphs themselves is examined, so the band's *content* is never known —
    only that a text-like structure occupies that strip of the frame.
    """

    active: list[bool] = []
    row_stats: list[tuple[int, float, int, int]] = []

    for y in range(grid.height):
        base = y * grid.width
        row = grid.luma[base : base + grid.width]
        lowest = min(row)
        highest = max(row)
        contrast = highest - lowest
        transitions = count_alternations(row)
        is_active = contrast >= min_contrast and transitions >= min_transitions
        active.append(is_active)
        row_stats.append((transitions, contrast, lowest, highest))

    bands: list[TextBand] = []
    index = 0
    band_number = 0
    while index < grid.height:
        if not active[index]:
            index += 1
            continue
        start = index
        while index < grid.height and active[index]:
            index += 1
        end = index - 1
        if end - start + 1 < min_rows:
            continue

        transitions_total = 0
        contrast_total = 0.0
        for row in range(start, end + 1):
            transitions_total += row_stats[row][0]
            contrast_total += row_stats[row][1]
        rows_count = end - start + 1

        # Horizontal extent: the envelope of genuine alternation.
        #
        # A column counts only if some row genuinely *reverses* its luminance
        # direction there. This is a per-row property, which is what makes it
        # safe: a coloured block beside the text contributes a single monotonic
        # step at its edge and therefore contributes no alternation column at
        # all, so it can never stretch the band across itself and then be
        # swallowed as "text".
        #
        # Earlier attempts used raw transition counts (a block edge scores high,
        # because it steps once on every row) and row-span medians (fragile when
        # ink rows differ in width). Counting reversals is the property that
        # actually separates ink from a flat boundary.
        alternation_min = max(1, min_transitions // 2)
        active_columns: list[bool] = [False] * grid.width
        for row in range(start, end + 1):
            base = row * grid.width
            last_sign = 0
            previous = grid.luma[base]
            row_marks: list[int] = []
            for x in range(1, grid.width):
                delta = grid.luma[base + x] - previous
                previous = grid.luma[base + x]
                if abs(delta) < 0.08:
                    continue
                sign = 1 if delta > 0 else -1
                if last_sign != 0 and sign != last_sign:
                    row_marks.append(x)
                    row_marks.append(x - 1)
                last_sign = sign
            if len(row_marks) >= 2 * alternation_min:
                for column in row_marks:
                    active_columns[column] = True

        columns = [x for x, flag in enumerate(active_columns) if flag]
        if not columns:
            continue
        x0, x1 = min(columns), max(columns)

        band_number += 1
        bands.append(
            TextBand(
                band_id=f"t{band_number:02d}",
                x0=x0,
                y0=start,
                x1=x1,
                y1=end,
                run_count=max(1, transitions_total // rows_count),
                transition_density=round(transitions_total / (rows_count * grid.width), 6),
                contrast=round(contrast_total / rows_count, 6),
            )
        )

    return bands


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def dominant_colors(grid: PixelGrid, *, top: int = 4) -> list[tuple[str, float]]:
    """Most prevalent colour families with their share of the frame.

    Shares are quantised to a fixed precision so the result is byte-comparable.
    """

    counts: dict[str, int] = {}
    for family in grid.color_family:
        counts[family] = counts.get(family, 0) + 1
    total = len(grid.color_family) or 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [(family, round(count / total, 6)) for family, count in ordered[:top]]


def high_frequency_energy(grid: PixelGrid) -> float:
    """Mean absolute horizontal luminance gradient across the grid.

    A proxy for "busy" content: charts, tables, and dense text score high;
    flat backgrounds and full-bleed photography score low.
    """

    if grid.width < 2:
        return 0.0
    total = 0.0
    samples = 0
    for y in range(grid.height):
        base = y * grid.width
        for x in range(1, grid.width):
            total += abs(grid.luma[base + x] - grid.luma[base + x - 1])
            samples += 1
    return round(total / samples, 6) if samples else 0.0


def palette_relation_of(families: Sequence[str], shares: Sequence[float]) -> str:
    """Decide a palette relation from the dominant colour families.

    The mapping is fixed and published: two strong families at opposite hue
    extremes read as complementary, a single dominant family reads as
    monochrome, and so on.
    """

    present = [family for family, share in zip(families, shares) if share >= 0.06]
    if not present:
        return "mixed"

    dominant = present[0]
    monochromes = {"dark_monochrome", "light_monochrome", "neutral_grey"}
    if len(present) == 1 and dominant in monochromes | {"neutral_beige"}:
        return "monochrome"

    warm = {"warm_red", "warm_orange", "warm_yellow"}
    cool = {"cool_blue", "cool_teal", "cool_green"}
    warm_hits = warm & set(present)
    cool_hits = cool & set(present)

    if warm_hits and cool_hits:
        return "complementary"
    if len(present) == 1:
        return "monochrome" if dominant in monochromes else "analogous"
    if dominant in monochromes:
        return "high_contrast_accent"
    if len(present) >= 3:
        return "triadic"
    return "analogous"


def contrast_role_of(
    *, top_luma: float, bottom_luma: float, palette_relation: str
) -> str:
    """Classify the frame's contrast role from its luminance extremes."""

    spread = top_luma - bottom_luma
    if spread < 0.15:
        return "ground"
    if palette_relation == "complementary":
        return "figure"
    if spread > 0.55:
        return "accent"
    return "neutral"


__all__ = [
    "COLOR_FAMILY_KEYWORDS",
    "Component",
    "PixelGrid",
    "TextBand",
    "build_grid",
    "classify_color_family",
    "contrast_role_of",
    "count_alternations",
    "detect_text_bands",
    "dominant_colors",
    "high_frequency_energy",
    "label_components",
    "luminance",
    "palette_relation_of",
    "rgb_to_hsv",
]
