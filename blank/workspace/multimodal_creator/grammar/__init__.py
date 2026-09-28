"""Visual grammar distillation (Phase M4).

M3 concluded that a layout class label cannot express complex visual structure,
and its classifier's micro F1 of about 0.33 was the evidence. M4 stops optimising
the label and replaces the representation:

``model``
    :class:`VisualGrammar` — functional regions with position, size, density and
    dominance; discrete relationships; and an attention flow.
``extractor``
    Observation → grammar. No text is read; region function comes from role,
    geometry, and layer.
``relation``
    The relation layer: ``headline_above_subject``, ``subject_center_focus``,
    ``cta_bottom_anchor`` and the rest, derived from geometry and layering.
``similarity_v2``
    :class:`SimilarityVector` — four independent dimensions, **never collapsed
    into one score**. Task-specific profiles read it for template discovery or
    creator style.
``invariants``
    Mined feature frequencies per cluster. Nothing is specified by hand.
``strategy``
    :class:`CreatorStrategyPattern` derived from grammars and invariants, with no
    dependence on a cluster's layout label.
``constraints``
    :class:`VisualConstraint` — the generation-constraint interface for M5.
    Design only: it generates nothing.
``evaluation``
    Region accuracy, relation precision/recall, discovery stability, and strategy
    agreement reported separately.
"""

from .constraints import (
    CONSTRAINT_FAMILIES,
    REQUIRED_FREQUENCY,
    STRENGTHS,
    Constraint,
    ConstraintError,
    VisualConstraint,
    constraints_from_strategy,
    render_constraints,
)
from .evaluation import (
    EvaluationBundle,
    RegionAccuracy,
    RelationMetrics,
    StabilityMetrics,
    StrategyMetrics,
    region_accuracy,
    relation_metrics,
    stability_metrics,
    strategy_metrics,
)
from .extractor import (
    ROLE_TO_GRAMMAR_TYPE,
    GrammarExtractionResult,
    GrammarExtractor,
    extract_grammar,
)
from .invariants import (
    DEFAULT_INVARIANT_THRESHOLD,
    FEATURE_FAMILIES,
    Invariant,
    InvariantError,
    InvariantExtractor,
    InvariantSet,
    invariant_features,
    summarise_invariants,
)
from .model import (
    ATTENTION_STAGES,
    COLUMN_BANDS,
    DENSITY_LEVELS,
    DOMINANCE_RANKS,
    GRAMMAR_VERSION,
    POSITION_BANDS,
    REGION_TYPES,
    RELATION_TYPES,
    AttentionFlow,
    GrammarError,
    GrammarRegion,
    GrammarRelation,
    VisualGrammar,
    column_band_of,
    position_band_of,
)
from .relation import RelationExtractor
from .similarity_v2 import (
    BALANCED_PROFILE,
    CREATOR_STYLE_PROFILE,
    PROFILES,
    SIMILARITY_DIMENSIONS,
    TEMPLATE_PROFILE,
    DimensionReading,
    SimilarityError,
    SimilarityProfile,
    SimilarityVector,
    profile_scores,
    vector_matrix,
    vector_similarity,
)
from .strategy import (
    ATTENTION_STRATEGIES,
    COMPOSITION_MOVES,
    DEFAULT_STRATEGY_SUPPORT,
    HIERARCHY_STAGES,
    CreatorStrategyPattern,
    StrategyError,
    distill_strategy,
    render_strategies,
)

__all__ = [
    "ATTENTION_STAGES",
    "ATTENTION_STRATEGIES",
    "BALANCED_PROFILE",
    "COLUMN_BANDS",
    "COMPOSITION_MOVES",
    "CONSTRAINT_FAMILIES",
    "CREATOR_STYLE_PROFILE",
    "DEFAULT_INVARIANT_THRESHOLD",
    "DEFAULT_STRATEGY_SUPPORT",
    "DENSITY_LEVELS",
    "DOMINANCE_RANKS",
    "FEATURE_FAMILIES",
    "GRAMMAR_VERSION",
    "HIERARCHY_STAGES",
    "POSITION_BANDS",
    "PROFILES",
    "REGION_TYPES",
    "RELATION_TYPES",
    "REQUIRED_FREQUENCY",
    "ROLE_TO_GRAMMAR_TYPE",
    "SIMILARITY_DIMENSIONS",
    "STRENGTHS",
    "TEMPLATE_PROFILE",
    "AttentionFlow",
    "Constraint",
    "ConstraintError",
    "CreatorStrategyPattern",
    "DimensionReading",
    "EvaluationBundle",
    "GrammarError",
    "GrammarExtractionResult",
    "GrammarExtractor",
    "GrammarRegion",
    "GrammarRelation",
    "Invariant",
    "InvariantError",
    "InvariantExtractor",
    "InvariantSet",
    "RegionAccuracy",
    "RelationExtractor",
    "RelationMetrics",
    "SimilarityError",
    "SimilarityProfile",
    "SimilarityVector",
    "StabilityMetrics",
    "StrategyError",
    "StrategyMetrics",
    "VisualConstraint",
    "VisualGrammar",
    "column_band_of",
    "constraints_from_strategy",
    "distill_strategy",
    "extract_grammar",
    "invariant_features",
    "position_band_of",
    "profile_scores",
    "region_accuracy",
    "relation_metrics",
    "render_constraints",
    "render_strategies",
    "stability_metrics",
    "strategy_metrics",
    "summarise_invariants",
    "vector_matrix",
    "vector_similarity",
]
