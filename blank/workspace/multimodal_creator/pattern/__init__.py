"""Creator visual pattern distillation (Phase M3, phase 7).

Turns discovered template clusters into abstracted visual **strategy** —
layout strategy, attention hierarchy, and style traits — rather than copying
pixels or emitting a template image file.

The output can be produced without ever opening the source image, which is what
makes "learn the strategy, not the material" a property of the code rather than
a claim in a report.
"""

from .distillation import (
    AGREEMENT_THRESHOLD,
    HIERARCHY_STAGES,
    CreatorVisualPattern,
    PatternDistillationError,
    RegionRecipeEntry,
    distill_cluster,
    distill_patterns,
    render_patterns,
)

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
