"""Synthetic image corpus generator for Phase M3 (Phase 3 dataset source).

Purpose
-------

M3 must validate a **real** observation chain — the observer has to actually
decode pixels. That requires a corpus of real image files. Building one from
scraped social-media posts is out of scope for this phase (and would raise
licensing, privacy, and rate-limit questions that M3 is not authorised to
answer). So the corpus is **generated**:

    template spec → painted pixels → PNG on disk → observer reads PNG

The observer never sees a template spec. It receives bytes and must recover
structure from pixels alone. That is what makes this a real validation of the
observation adapter rather than a descriptor round-trip.

What this corpus is and is not
------------------------------

It **is** a controlled structural corpus: known template families, known creator
pairings, known within-family variation, rendered as genuine images with noise,
gradients, and rounded corners.

It is **not** real social-media material. No 爆款 post was collected, viewed, or
measured. Conclusions drawn here are conclusions about the pipeline's behaviour
on controlled input, and the report says so explicitly.

Ground truth is attached to the *spec*, never to the pixels. The observer's only
input is the PNG file, which is what keeps the benchmark labels independent of
the algorithm.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .pixel.png_codec import RgbImage

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Palette:
    """A four-colour scheme: ground, ink, subject fill, accent."""

    name: str
    ground: tuple[int, int, int]
    ink: tuple[int, int, int]
    subject: tuple[int, int, int]
    accent: tuple[int, int, int]
    color_family: str
    text_dark: bool = True


PALETTES: Mapping[str, Palette] = {
    "warm_warning": Palette(
        "warm_warning", (252, 240, 236), (28, 22, 22), (206, 58, 48), (250, 196, 60),
        "warm_red",
    ),
    "orange_alert": Palette(
        "orange_alert", (255, 246, 232), (34, 26, 18), (232, 128, 40), (60, 70, 120),
        "warm_orange",
    ),
    "cool_trust": Palette(
        "cool_trust", (238, 245, 252), (18, 30, 48), (44, 92, 168), (240, 178, 48),
        "cool_blue",
    ),
    "teal_calm": Palette(
        "teal_calm", (236, 250, 248), (18, 40, 40), (38, 148, 148), (232, 96, 72),
        "cool_teal",
    ),
    "dark_editorial": Palette(
        # Ink and ground must differ enough to be a readable composition. An
        # earlier version used a near-black ground with near-white ink, which
        # produced a luminance spread of only ~0.16 and made the overlaid text
        # undetectable — a corpus defect that looked like a detector failure. The
        # subject stays dark so the composition still reads as a dark editorial
        # treatment; only the ink/ground pair was corrected.
        "dark_editorial", (198, 196, 192), (26, 26, 30), (52, 50, 58), (226, 196, 120),
        "dark_monochrome", text_dark=True,
    ),
    "light_minimal": Palette(
        "light_minimal", (250, 250, 248), (40, 40, 40), (170, 170, 172), (90, 90, 92),
        "light_monochrome",
    ),
}


# --------------------------------------------------------------------------
# Template specs
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegionSpec:
    """Structural region in normalized coordinates, plus how to paint it.

    ``kind`` selects the painter: ``ground`` fills the whole frame, ``text``
    paints alternating rows to produce a text-like structural signature,
    ``block`` paints a flat rectangle, ``chart`` paints bars, ``table`` paints a
    grid. The observer must infer structural roles from pixels; it is never told
    which is which.
    """

    region_id: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    layer: int = 1
    fill: str = "subject"
    rows: int = 5

    def box(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """A visual template: a fixed arrangement of structural regions."""

    template_id: str
    layout_family: str
    regions: tuple[RegionSpec, ...]
    palette_name: str = "warm_warning"
    typography_scale: str = "two_level"
    description: str = ""
    #: The M2 layout class this template should be recognised as. Several
    #: templates can share one class — the class vocabulary is coarser than the
    #: corpus — so this is what layout detection is scored against. Family
    #: identity is scored separately, by clustering.
    expected_layout_class: str = ""

    def palette(self) -> Palette:
        return PALETTES[self.palette_name]


@dataclass(frozen=True, slots=True)
class SampleSpec:
    """One concrete image: a template rendered for a creator in a batch."""

    sample_id: str
    template_id: str
    creator_id: str
    batch_id: str
    seed: int
    #: Ground-truth quadrants used only by calibration and evaluation, never by
    #: the observer, similarity, or clustering code.
    is_hero: bool = True


def _text(
    region_id: str, x: float, y: float, w: float, h: float, rows: int = 5, layer: int = 1
) -> RegionSpec:
    return RegionSpec(region_id, "text", x, y, w, h, layer=layer, rows=rows)


def _block(
    region_id: str, x: float, y: float, w: float, h: float, fill: str = "subject", layer: int = 1
) -> RegionSpec:
    return RegionSpec(region_id, "block", x, y, w, h, fill=fill, layer=layer)


def _chart(region_id: str, x: float, y: float, w: float, h: float) -> RegionSpec:
    return RegionSpec(region_id, "chart", x, y, w, h, fill="accent")


def _table(region_id: str, x: float, y: float, w: float, h: float) -> RegionSpec:
    return RegionSpec(region_id, "table", x, y, w, h, fill="accent")


_GROUND = RegionSpec("ground", "ground", 0.0, 0.0, 1.0, 1.0, layer=0)


def _ground_overlap(a: "RegionSpec", b: "RegionSpec") -> float:
    """Overlap area of two region specs, as a fraction of the smaller one."""

    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    intersection = ix * iy
    smaller = min(a.w * a.h, b.w * b.h)
    return intersection / smaller if smaller > 0 else 0.0


def validate_templates(templates: Mapping[str, TemplateSpec]) -> None:
    """Reject templates whose regions are geometrically broken.

    Two invariants, both learned the hard way in this phase:

    1. **No text region may substantially overlap a non-text region**, *except*
       when that region is a full-frame block. A full-bleed image with a headline
       laid over it is a legitimate and common composition (template T04), and
       the observer is expected to report it as ``contained_by``. What must never
       happen is text painted across *part* of a block, which fragments the block
       at the pixel level so the observer correctly fails to find a subject. That
       is a corpus defect masquerading as an observer defect, and it must not be
       allowed to contaminate the validation.
    2. **Every region must sit inside the frame.**

    Raising here means a bad template fails loudly at corpus build time instead
    of quietly depressing the measured detection rates.
    """

    for template_id, template in templates.items():
        for region in template.regions:
            if region.x < 0.0 or region.y < 0.0:
                raise ValueError(f"{template_id}.{region.region_id} starts outside the frame")
            if region.x + region.w > 1.0001 or region.y + region.h > 1.0001:
                raise ValueError(f"{template_id}.{region.region_id} extends outside the frame")

        text_regions = [r for r in template.regions if r.kind == "text"]
        other_regions = [r for r in template.regions if r.kind not in {"text", "ground"}]
        for text in text_regions:
            for other in other_regions:
                # A block covering essentially the whole frame is a full-bleed
                # background, and overlaying text on it is designed, not broken.
                if other.w >= 0.98 and other.h >= 0.98:
                    continue
                overlap = _ground_overlap(text, other)
                if overlap > 0.15:
                    raise ValueError(
                        f"{template_id}: text region {text.region_id!r} overlaps "
                        f"{other.region_id!r} by {overlap:.2f} of the smaller region; "
                        "text must not be painted across a visual block"
                    )


def build_templates() -> dict[str, TemplateSpec]:
    """The ten template families the corpus is built from.

    Each is a genuinely distinct arrangement: the difference between them is
    structural (where regions sit and how they stack), which is exactly what the
    similarity contract is meant to detect.
    """

    templates = {
        "T01_left_text_right_image": TemplateSpec(
            "T01_left_text_right_image",
            "left_text_right_image",
            (
                _GROUND,
                # The text column must stay clear of the subject block: a
                # template that paints ink over its own image is a broken
                # template, and would make the observer's subject detection look
                # worse than it is. ``validate_templates`` enforces this.
                _text("title", 0.04, 0.12, 0.42, 0.16, rows=4),
                _text("body", 0.04, 0.34, 0.42, 0.26, rows=6),
                _block("subject", 0.54, 0.12, 0.40, 0.64),
            ),
            description="Editorial split: text column beside a tall subject block",
            expected_layout_class="image_left_text_right",
        ),
        "T02_top_image_bottom_text": TemplateSpec(
            "T02_top_image_bottom_text",
            "top_image_bottom_text",
            (
                _GROUND,
                _block("subject", 0.08, 0.06, 0.84, 0.48),
                _text("title", 0.08, 0.60, 0.84, 0.14, rows=4),
                _text("body", 0.08, 0.78, 0.84, 0.14, rows=5),
            ),
            description="Photo on top, headline and copy stacked below",
            expected_layout_class="image_top_text_bottom",
        ),
        "T03_three_card_grid": TemplateSpec(
            "T03_three_card_grid",
            "three_card_grid",
            (
                _GROUND,
                _text("title", 0.05, 0.05, 0.90, 0.12, rows=3),
                _block("card_left", 0.05, 0.22, 0.28, 0.56, fill="subject"),
                _block("card_mid", 0.36, 0.22, 0.28, 0.56, fill="accent"),
                _block("card_right", 0.67, 0.22, 0.28, 0.56, fill="subject"),
            ),
            typography_scale="two_level",
            description="Headline over a three-column card grid",
            expected_layout_class="three_card",
        ),
        "T04_full_bleed_overlay": TemplateSpec(
            "T04_full_bleed_overlay",
            "full_bleed_overlay",
            (
                _block("subject", 0.0, 0.0, 1.0, 1.0, layer=0),
                _text("title", 0.10, 0.38, 0.80, 0.16, rows=4, layer=1),
                _text("cta", 0.34, 0.62, 0.32, 0.10, rows=3, layer=1),
            ),
            palette_name="dark_editorial",
            description="Full-bleed subject with an overlaid headline and CTA",
            expected_layout_class="full_bleed_overlay",
        ),
        "T05_chart_with_caption": TemplateSpec(
            "T05_chart_with_caption",
            "chart_with_caption",
            (
                _GROUND,
                _text("title", 0.06, 0.05, 0.88, 0.11, rows=3),
                _chart("chart", 0.08, 0.20, 0.84, 0.50),
                _text("caption", 0.08, 0.76, 0.84, 0.10, rows=3),
            ),
            palette_name="cool_trust",
            description="Data chart with headline above and caption below",
            expected_layout_class="single_column",
        ),
        "T06_cover_with_logo": TemplateSpec(
            "T06_cover_with_logo",
            "cover_with_logo",
            (
                _GROUND,
                _block("subject", 0.0, 0.0, 1.0, 0.70, layer=0),
                _text("title", 0.08, 0.74, 0.68, 0.14, rows=4),
                _block("logo", 0.82, 0.76, 0.12, 0.10, fill="accent"),
            ),
            palette_name="orange_alert",
            description="Cover image with title strip and corner logo",
            expected_layout_class="full_bleed_overlay",
        ),
        "T07_data_table": TemplateSpec(
            "T07_data_table",
            "data_table",
            (
                _GROUND,
                _text("title", 0.06, 0.05, 0.88, 0.11, rows=3),
                _table("table", 0.08, 0.20, 0.84, 0.60),
                _text("footer", 0.08, 0.84, 0.84, 0.08, rows=3),
            ),
            palette_name="light_minimal",
            description="Tabular data with headline and source footer",
            expected_layout_class="single_column",
        ),
        "T08_two_column_text": TemplateSpec(
            "T08_two_column_text",
            "two_column_text",
            (
                _GROUND,
                _text("title", 0.05, 0.05, 0.90, 0.12, rows=3),
                _text("col_left", 0.05, 0.22, 0.43, 0.66, rows=9),
                _text("col_right", 0.52, 0.22, 0.43, 0.66, rows=9),
            ),
            typography_scale="three_plus_levels",
            description="Two dense text columns under a headline",
            expected_layout_class="two_column",
        ),
        "T09_list_stack": TemplateSpec(
            "T09_list_stack",
            "list_stack",
            (
                _GROUND,
                _text("title", 0.06, 0.05, 0.88, 0.12, rows=3),
                _text("item1", 0.06, 0.22, 0.88, 0.15, rows=3),
                _text("item2", 0.06, 0.41, 0.88, 0.15, rows=3),
                _text("item3", 0.06, 0.60, 0.88, 0.15, rows=3),
                _text("item4", 0.06, 0.79, 0.88, 0.13, rows=3),
            ),
            description="Numbered list of stacked full-width items",
            expected_layout_class="list_stack",
        ),
        "T10_centered_quote": TemplateSpec(
            "T10_centered_quote",
            "centered_quote",
            (
                _GROUND,
                _text("quote", 0.14, 0.34, 0.72, 0.20, rows=5),
                _text("attribution", 0.30, 0.60, 0.40, 0.09, rows=3),
            ),
            palette_name="teal_calm",
            description="Centred pull quote with attribution",
            expected_layout_class="single_column",
        ),
    }
    validate_templates(templates)
    return templates


# --------------------------------------------------------------------------
# Painting
# --------------------------------------------------------------------------


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _resolve(fill: str, palette: Palette) -> tuple[int, int, int]:
    return {
        "ground": palette.ground,
        "ink": palette.ink,
        "subject": palette.subject,
        "accent": palette.accent,
    }.get(fill, palette.subject)


class Canvas:
    """A mutable RGB raster with the painting operations the templates need."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.buffer = bytearray(width * height * 3)

    def put(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        offset = (y * self.width + x) * 3
        self.buffer[offset] = max(0, min(255, color[0]))
        self.buffer[offset + 1] = max(0, min(255, color[1]))
        self.buffer[offset + 2] = max(0, min(255, color[2]))

    def fill_rect(
        self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]
    ) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                self.put(x, y, color)

    def rect_with_gradient(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        top: tuple[int, int, int],
        bottom: tuple[int, int, int],
    ) -> None:
        span = max(1, y1 - y0)
        for y in range(max(0, y0), min(self.height, y1)):
            t = (y - y0) / span
            color = _blend(top, bottom, t)
            for x in range(max(0, x0), min(self.width, x1)):
                self.put(x, y, color)

    def rect_rounded(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: tuple[int, int, int],
        radius: int = 3,
    ) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                dx = min(x - x0, x1 - 1 - x)
                dy = min(y - y0, y1 - 1 - y)
                if dx < radius and dy < radius:
                    if (radius - dx) ** 2 + (radius - dy) ** 2 > radius * radius:
                        continue
                self.put(x, y, color)

    def to_image(self, rng: random.Random, *, grain: int = 3) -> RgbImage:
        """Finish with light sensor-like grain so the corpus is not sterile.

        Grain is small and deterministic; it exists so the observer cannot rely
        on perfectly flat blocks, which would make region detection trivially
        easy and the validation less meaningful.
        """

        if grain > 0:
            for index in range(0, len(self.buffer), 3):
                noise = rng.randint(-grain, grain)
                if noise:
                    self.buffer[index] = max(0, min(255, self.buffer[index] + noise))
                    self.buffer[index + 1] = max(
                        0, min(255, self.buffer[index + 1] + noise)
                    )
                    self.buffer[index + 2] = max(
                        0, min(255, self.buffer[index + 2] + noise)
                    )
        return RgbImage(self.width, self.height, 3, bytes(self.buffer))


def _px(value: float, extent: int) -> int:
    return int(round(value * extent))


def render_sample(
    sample: SampleSpec,
    template: TemplateSpec,
    *,
    width: int = 480,
    height: int = 720,
) -> RgbImage:
    """Paint one sample as real pixels.

    Deterministic in ``sample.seed``. Within-family variation comes from a small
    jitter applied to every region box plus palette and typography switches, so
    two samples of the same template are similar but not identical — which is
    what makes similarity calibration meaningful.

    Default resolution is 480x720. A 320x480 frame puts thin headline bands under
    one working-grid cell tall, which destroys their alternation signature before
    detection ever runs — a rendering limitation that would masquerade as a
    detector failure.
    """

    rng = random.Random(sample.seed)
    palette = template.palette()
    canvas = Canvas(width, height)

    # Ground, with a slight vertical gradient so it is not a single flat value.
    canvas.rect_with_gradient(
        0, 0, width, height,
        _blend(palette.ground, (255, 255, 255), 0.25),
        palette.ground,
    )

    jitter = 0.012 if sample.is_hero else 0.03

    for region in template.regions:
        x0 = _px(region.x + rng.uniform(-jitter, jitter), width)
        y0 = _px(region.y + rng.uniform(-jitter, jitter), height)
        x1 = _px(region.x + region.w + rng.uniform(-jitter, jitter), width)
        y1 = _px(region.y + region.h + rng.uniform(-jitter, jitter), height)
        x0, x1 = min(x0, x1 - 4), max(x1, x0 + 4)
        y0, y1 = min(y0, y1 - 4), max(y1, y0 + 4)

        if region.kind == "ground":
            continue
        if region.kind == "text":
            ink = palette.ink
            if not palette.text_dark:
                ink = palette.ground
            rows = max(2, region.rows + rng.randint(-1, 1))
            band_height = max(3, (y1 - y0) // (rows * 2))
            for row in range(rows):
                ty = y0 + row * (y1 - y0) // rows
                # Ragged right edge so the band is not a perfect rectangle.
                right = x1 - rng.randint(0, max(0, (x1 - x0) // 6))
                # Paint short vertical strokes spaced across the line. This is
                # what gives a text line its defining pixel signature: the
                # luminance signal *reverses* many times across a row. Solid
                # horizontal bars would look like text to a human but contain no
                # per-row alternation at all, which would make the observer's
                # text detection trivially wrong (and would flatter it).
                span = max(1, right - x0)
                stroke = max(1, span // 34)
                step = max(stroke * 2, span // 18)
                x = x0
                while x < right:
                    # Named ``stroke_height``, not ``height``: shadowing the
                    # function's own ``height`` parameter silently corrupted the
                    # y-coordinates of every region painted afterwards, which
                    # rendered the whole corpus wrong while looking innocuous.
                    stroke_height = band_height - rng.randint(
                        0, max(0, band_height // 3)
                    )
                    if stroke_height <= 0:
                        stroke_height = band_height
                    inset = rng.randint(0, max(0, stroke_height // 4))
                    canvas.fill_rect(
                        x,
                        ty + inset,
                        min(right, x + stroke),
                        min(y1, ty + stroke_height),
                        ink,
                    )
                    x += step
        elif region.kind == "block":
            fill = _resolve(region.fill, palette)
            canvas.rect_rounded(x0, y0, x1, y1, fill, radius=4)
        elif region.kind == "chart":
            canvas.fill_rect(x0, y0, x1, y1, _blend(palette.ground, palette.accent, 0.12))
            bars = 6
            bar_width = max(2, (x1 - x0) // (bars * 2))
            for bar in range(bars):
                bx = x0 + 6 + bar * ((x1 - x0 - 12) // bars)
                bh = int((y1 - y0 - 16) * rng.uniform(0.25, 0.95))
                canvas.fill_rect(bx, y1 - 8 - bh, bx + bar_width, y1 - 8, palette.accent)
        elif region.kind == "table":
            canvas.fill_rect(x0, y0, x1, y1, _blend(palette.ground, palette.ink, 0.06))
            rows = 5
            for row in range(1, rows):
                ly = y0 + row * (y1 - y0) // rows
                canvas.fill_rect(x0, ly, x1, ly + 1, palette.ink)
            for col in range(1, 3):
                lx = x0 + col * (x1 - x0) // 3
                canvas.fill_rect(lx, y0, lx + 1, y1, palette.ink)

    return canvas.to_image(rng)


# --------------------------------------------------------------------------
# Corpus assembly
# --------------------------------------------------------------------------

#: Creators and the templates they use. Reuse across creators is what makes the
#: ``different_creator_same_template`` quadrant non-empty; a creator using
#: several templates populates ``same_creator_different_template``.
CREATOR_TEMPLATE_USAGE: Mapping[str, tuple[str, ...]] = {
    "creator_a": ("T01_left_text_right_image", "T03_three_card_grid", "T05_chart_with_caption"),
    "creator_b": ("T01_left_text_right_image", "T02_top_image_bottom_text"),
    "creator_c": ("T03_three_card_grid", "T04_full_bleed_overlay"),
    "creator_d": ("T01_left_text_right_image", "T06_cover_with_logo"),
    "creator_e": ("T02_top_image_bottom_text", "T09_list_stack"),
    "creator_f": ("T05_chart_with_caption", "T07_data_table"),
    "creator_g": ("T04_full_bleed_overlay", "T08_two_column_text"),
    "creator_h": ("T03_three_card_grid", "T10_centered_quote"),
    "creator_i": ("T01_left_text_right_image", "T09_list_stack"),
    "creator_j": ("T02_top_image_bottom_text", "T06_cover_with_logo"),
    "creator_k": ("T05_chart_with_caption", "T10_centered_quote"),
    "creator_l": ("T07_data_table", "T08_two_column_text"),
}

#: Images produced per creator per template.
SAMPLES_PER_CREATOR_TEMPLATE = 3

#: Creators used by the calibration corpus, each repeating one template enough
#: times to populate the ``same_creator_same_template`` quadrant. Without this,
#: the corpus can only ever produce three of the four quadrants, and threshold
#: calibration would have no measurement of how similar a creator's own repeats
#: actually are.
CALIBRATION_REPEAT_PLAN: Mapping[str, tuple[tuple[str, int], ...]] = {
    "creator_a": (("T01_left_text_right_image", 3), ("T03_three_card_grid", 2)),
    "creator_b": (("T01_left_text_right_image", 3), ("T02_top_image_bottom_text", 2)),
    "creator_c": (("T03_three_card_grid", 3), ("T04_full_bleed_overlay", 2)),
    "creator_d": (("T01_left_text_right_image", 3), ("T06_cover_with_logo", 2)),
    "creator_e": (("T02_top_image_bottom_text", 3), ("T09_list_stack", 2)),
    "creator_f": (("T05_chart_with_caption", 3), ("T07_data_table", 2)),
    "creator_g": (("T04_full_bleed_overlay", 2), ("T08_two_column_text", 3)),
    "creator_h": (("T03_three_card_grid", 2), ("T10_centered_quote", 3)),
}


def build_calibration_corpus() -> tuple[list[SampleSpec], dict[str, TemplateSpec]]:
    """Corpus built to populate all four provenance quadrants.

    Differs from :func:`build_corpus` in one way that matters: each creator gets
    **several samples of the same template**, so ``same_creator_same_template``
    pairs exist to be measured rather than inferred.
    """

    templates = build_templates()
    samples: list[SampleSpec] = []
    seed = 5000

    for creator_id in sorted(CALIBRATION_REPEAT_PLAN):
        for template_id, count in CALIBRATION_REPEAT_PLAN[creator_id]:
            if template_id not in templates:
                raise ValueError(f"unknown template {template_id!r} for {creator_id!r}")
            for index in range(count):
                seed += 1
                samples.append(
                    SampleSpec(
                        sample_id=f"{creator_id}__{template_id}__{index:02d}",
                        template_id=template_id,
                        creator_id=creator_id,
                        batch_id=f"batch-{creator_id}",
                        seed=seed,
                        is_hero=(index == 0),
                    )
                )
    return samples, templates


def build_corpus(
    *,
    samples_per_template: int = SAMPLES_PER_CREATOR_TEMPLATE,
    only_hero: bool = False,
) -> tuple[list[SampleSpec], dict[str, TemplateSpec]]:
    """Build the sample list and template table.

    Each ``(creator, template)`` pair yields ``samples_per_template`` images. The
    first is the hero sample (tight jitter); the rest carry wider jitter, which
    exercises the ``same_creator_different_template`` and
    ``same_creator_same_template`` quadrants with realistic within-family
    variation.
    """

    templates = build_templates()
    samples: list[SampleSpec] = []
    seed = 1000

    for creator_id in sorted(CREATOR_TEMPLATE_USAGE):
        for template_id in CREATOR_TEMPLATE_USAGE[creator_id]:
            if template_id not in templates:
                raise ValueError(f"unknown template {template_id!r} for {creator_id!r}")
            for index in range(samples_per_template):
                if only_hero and index > 0:
                    continue
                seed += 1
                samples.append(
                    SampleSpec(
                        sample_id=f"{creator_id}__{template_id}__{index:02d}",
                        template_id=template_id,
                        creator_id=creator_id,
                        batch_id=f"batch-{creator_id}",
                        seed=seed,
                        is_hero=(index == 0),
                    )
                )
    return samples, templates


def render_corpus(
    directory,
    *,
    samples: Sequence[SampleSpec] | None = None,
    templates: Mapping[str, TemplateSpec] | None = None,
    width: int = 480,
    height: int = 720,
) -> list[tuple[str, str]]:
    """Render the corpus to PNG files and return ``(sample_id, path)`` pairs."""

    from pathlib import Path

    from .pixel.png_codec import write_png

    active_samples = list(samples) if samples is not None else build_corpus()[0]
    active_templates = dict(templates) if templates is not None else build_templates()

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, str]] = []
    for sample in active_samples:
        template = active_templates[sample.template_id]
        image = render_sample(sample, template, width=width, height=height)
        path = root / f"{sample.sample_id}.png"
        write_png(path, image)
        written.append((sample.sample_id, str(path)))
    return written


def ground_truth(samples: Sequence[SampleSpec]) -> dict[str, dict[str, Any]]:
    """Ground truth per sample, for calibration and evaluation only.

    Kept in a separate function and never passed to the observer, similarity, or
    clustering code — that separation is what makes the benchmark labels
    independent of the algorithm.
    """

    return {
        sample.sample_id: {
            "sample_id": sample.sample_id,
            "template_id": sample.template_id,
            "creator_id": sample.creator_id,
            "batch_id": sample.batch_id,
            "is_hero": sample.is_hero,
        }
        for sample in samples
    }


__all__ = [
    "CALIBRATION_REPEAT_PLAN",
    "CREATOR_TEMPLATE_USAGE",
    "PALETTES",
    "SAMPLES_PER_CREATOR_TEMPLATE",
    "Canvas",
    "Palette",
    "RegionSpec",
    "SampleSpec",
    "TemplateSpec",
    "build_calibration_corpus",
    "build_corpus",
    "build_templates",
    "ground_truth",
    "render_corpus",
    "render_sample",
    "validate_templates",
]
