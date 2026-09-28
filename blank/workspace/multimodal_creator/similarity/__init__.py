"""Explainable structural similarity (Phase M2).

This module answers the M1 open question *"when are two visual templates the
same?"* — and it answers it in a way that can be argued with.

**It is not a visual embedding.** There is no learned representation, no vector
space, no nearest-neighbour index, and no pixel access anywhere in this module.
It is a transparent weighted comparison over structural facts that a human can
read, disagree with, and re-weight. Every score is decomposable: the result
carries the four dimension scores, the weight applied to each, the exact
structure-level agreements and differences that produced them, and machine
readable difference codes.

That auditability is the entire point. A similarity number that cannot be
explained cannot be used to justify calling something a "template".
"""

from .similarity_contract import (
    DIMENSION_WEIGHTS,
    DIMENSIONS,
    PROVENANCE_MODES,
    SCORE_PRECISION,
    STRUCTURAL_RECURRENCE_MIN,
    Contribution,
    DifferenceCode,
    DimensionScore,
    SimilarityContractError,
    SimilarityResult,
    asset_dimension,
    dimension_weights,
    geometry_dimension,
    layout_edges,
    pairwise_similarity,
    regions_by_role,
    similarity_matrix,
    structure_dimension,
    style_dimension,
)

__all__ = [
    "DIMENSION_WEIGHTS",
    "DIMENSIONS",
    "PROVENANCE_MODES",
    "SCORE_PRECISION",
    "STRUCTURAL_RECURRENCE_MIN",
    "Contribution",
    "DifferenceCode",
    "DimensionScore",
    "SimilarityContractError",
    "SimilarityResult",
    "asset_dimension",
    "dimension_weights",
    "geometry_dimension",
    "layout_edges",
    "pairwise_similarity",
    "regions_by_role",
    "similarity_matrix",
    "structure_dimension",
    "style_dimension",
]
