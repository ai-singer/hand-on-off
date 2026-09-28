"""Geometry primitives that make visual structure expressible without pixels.

Everything here operates on caller-supplied normalized boxes in a 0..1 frame.
No module in this package reads an image; geometry is the *framing substrate*
that lets a still image and a video frame be described by the same vocabulary,
which is what stops visual distillation from degrading into OCR.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .taxonomy import DENSITIES, REGION_ROLES, MultimodalContractError


def validate_region(region: Mapping[str, Any], *, where: str) -> None:
    """Check one region descriptor: known role, integral layer, in-frame box."""

    for key in ("region_id", "role", "box", "layer_order"):
        if key not in region:
            raise MultimodalContractError(f"{where} region is missing {key!r}")

    role = region["role"]
    if role not in REGION_ROLES:
        raise MultimodalContractError(
            f"{where} region {region['region_id']!r} uses unknown role {role!r}; "
            "region vocabulary is universal and closed"
        )

    if not isinstance(region["layer_order"], int) or isinstance(region["layer_order"], bool):
        raise MultimodalContractError(
            f"{where} region {region['region_id']!r} layer_order must be an integer"
        )

    box = region["box"]
    if not isinstance(box, Mapping):
        raise MultimodalContractError(
            f"{where} region {region['region_id']!r} box must be an object"
        )
    for key in ("x", "y", "w", "h"):
        if key not in box:
            raise MultimodalContractError(
                f"{where} region {region['region_id']!r} box is missing {key!r}"
            )
        value = box[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MultimodalContractError(
                f"{where} region {region['region_id']!r} box.{key} must be numeric"
            )
        if value < 0.0 or value > 1.0:
            raise MultimodalContractError(
                f"{where} region {region['region_id']!r} box.{key} must be normalized "
                f"to 0..1, got {value!r}"
            )
    if box["w"] <= 0.0 or box["h"] <= 0.0:
        raise MultimodalContractError(
            f"{where} region {region['region_id']!r} must have positive extent"
        )
    if box["x"] + box["w"] > 1.0 or box["y"] + box["h"] > 1.0:
        raise MultimodalContractError(
            f"{where} region {region['region_id']!r} extends outside the normalized frame"
        )


def box_area(box: Mapping[str, Any]) -> float:
    """Return the normalized area of a box."""

    return float(box["w"]) * float(box["h"])


def classify_density(coverage: float) -> str:
    """Map a normalized covered-area fraction onto the density vocabulary.

    Density is a coarse ordinal structural fact, deliberately not an exact
    pixel ratio: the contract stores relationships, not measurements.
    """

    if coverage < 0.0 or coverage > 1.0:
        raise MultimodalContractError(
            f"coverage must be normalized to 0..1, got {coverage!r}"
        )
    if coverage < 0.25:
        return DENSITIES[0]
    if coverage > 0.6:
        return DENSITIES[2]
    return DENSITIES[1]


def region_boxes_are_disjoint(
    regions: Sequence[Mapping[str, Any]],
    *,
    tolerance: float = 1e-9,
) -> bool:
    """True when no two same-layer regions overlap beyond ``tolerance``.

    Overlapping regions on *different* layers are meaningful (an overlay title
    sits above a background), so only same-layer overlap counts as a conflict.
    """

    for index, first in enumerate(regions):
        for second in regions[index + 1 :]:
            if first["layer_order"] != second["layer_order"]:
                continue
            a, b = first["box"], second["box"]
            overlap_x = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            overlap_y = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if overlap_x > tolerance and overlap_y > tolerance:
                return False
    return True


def grid_columns_are_declared(
    *,
    columns: int,
    rows: int,
    regions: Sequence[Mapping[str, Any]],
    template_class: str,
) -> bool:
    """Check the region count is consistent with the declared grid.

    ``three_card`` is the canonical case that motivates this: the template class
    promises three cards, so a grid declaring one region is mislabelled rather
    than merely sparse.
    """

    if columns < 1 or rows < 1:
        return False
    expected = columns * rows
    if template_class == "three_card":
        return expected >= 3 and len(regions) >= 3
    return len(regions) <= expected
