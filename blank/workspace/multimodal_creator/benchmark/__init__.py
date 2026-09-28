"""Synthetic benchmark for the M2 multimodal extraction prototype.

The benchmark measures protocol and algorithm behaviour on controlled
structural input. It contains no images, reads no text, and makes no claim about
model accuracy — there is no model.
"""

from .cases import (
    BenchmarkSuite,
    CrossModalCase,
    LayoutCase,
    SimilarityCase,
    cross_modal_cases,
    layout_cases,
    similarity_cases,
)
from .runner import (
    BenchmarkReport,
    CaseResult,
    discovery_agreement,
    render_report,
    run_benchmark,
)

__all__ = [
    "BenchmarkReport",
    "BenchmarkSuite",
    "CaseResult",
    "CrossModalCase",
    "LayoutCase",
    "SimilarityCase",
    "cross_modal_cases",
    "discovery_agreement",
    "layout_cases",
    "render_report",
    "run_benchmark",
    "similarity_cases",
]
