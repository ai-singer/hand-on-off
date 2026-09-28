"""Multimodal Creator Distillation — Phase M1 contract surface.

This package is the implementation half of the Phase M1 contract. It exists so
the multimodal extension is *executable and checkable*, not merely documented:
the anti-OCR rule, the universal/plugin split, multi-role source classification,
and old-artifact compatibility are all enforced by code that offline tests call
directly.

Scope discipline (Phase M1)
---------------------------
This package performs **no** image generation, video generation, external
fetching, asset download, or model training, and it never reads pixel data. It
consumes caller-supplied structural observations and turns them into a
contract-shaped artifact. Any capability that would require perception belongs
to a later phase and must arrive as an injected observer, exactly as content
generation arrives as an injected adapter elsewhere in this framework.

Isolation
---------
Nothing here imports from or modifies ``risk_evaluation``, ``runtime``,
``production``, ``workflows``, ``security``, ``artifact``, or
``plugins.xiaolin_finance``. The only project modules consulted are the
read-only text-signal schema and the dependency-free schema validator.
"""

from .builder import (
    BASELINE_SCHEMA_NAME,
    DEFAULT_SIGNALS,
    SCHEMA_DIR,
    SIGNAL_REQUIREMENTS,
    build_cross_modal_records,
    build_layout_records,
    build_multimodal_artifact,
    build_multimodal_envelope,
    merge_creator_extension,
    merge_multimodal_artifact,
    observation_to_records,
    project_text_core,
    signal_is_supported,
)
from .geometry import (
    box_area,
    classify_density,
    grid_columns_are_declared,
    region_boxes_are_disjoint,
    validate_region,
)
from .integration import (
    INTEGRATION_VERSION,
    ArtifactIntegration,
    integrate_samples,
    validate_integrated_artifact,
)
from .observation import (
    EVIDENCE_FAMILIES,
    EVIDENCE_SOURCES,
    FrameObserver,
    ManualAnnotationBackend,
    MockDescriptorBackend,
    ObservationResult,
    ObservationSet,
    ObservationSetBuilder,
    ObserverError,
    StdlibPixelBackend,
    VisionBackend,
    VisualSource,
)
from .pattern import CreatorVisualPattern, distill_patterns
from .grammar import (
    CreatorStrategyPattern,
    InvariantExtractor,
    SimilarityVector,
    VisualConstraint,
    VisualGrammar,
    constraints_from_strategy,
    distill_strategy,
    extract_grammar,
    vector_similarity,
)
from .dataset import (
    DatasetManifest,
    ProvenanceRecord,
    Rating,
    Rater,
    compute_agreement,
    synthetic_manifest,
)
from .profile import (
    PROFILE_VERSION,
    FieldProvenance,
    PatternToProfileMapper,
    VisualCreatorProfile,
    factory_config,
    pattern_to_profile,
    to_yaml,
    validate_profile,
    write_profile_bundle,
)
from .roles import (
    MULTI_ROLE_STATEMENT,
    SourceStructure,
    roles_of,
    sources_holding_role,
    structure_from_metadata,
)
from .taxonomy import (
    ALIGNMENT_RELATIONS,
    ALL_EVIDENCE_KINDS,
    ASSET_PATTERN_TYPES,
    CROSS_MODAL_TYPES,
    DENSITIES,
    LAYER_UNIVERSAL,
    LEGACY_ROLE_SUCCESSOR,
    MULTIMODAL_CONTRACT_VERSION,
    NON_STRUCTURAL_EVIDENCE,
    PATTERN_LAYER,
    PLUGIN_MAY_NOT_REDEFINE,
    REGION_ROLES,
    SEQUENCE_ROLES,
    SIGNAL_BINDING,
    SIGNAL_FAMILY_BY_KIND,
    SOURCE_ROLES,
    STRUCTURAL_EVIDENCE,
    TEXT_SIGNALS,
    VISUAL_PATTERN_TYPES,
    MultimodalContractError,
    SignalFamily,
    StructuralObservation,
    VisualSignal,
)
from .validation import (
    MULTIMODAL_FAMILIES,
    OBSERVED_REQUIRED_FAMILIES,
    assert_creator_extension_is_interpretive,
    assert_no_ocr_substitution,
    assert_universal_layer_shape,
    layout_exists_independently,
    text_signals_are_not_visual,
    validate_multimodal_artifact,
)

__all__ = [
    "ALIGNMENT_RELATIONS",
    "ALL_EVIDENCE_KINDS",
    "ASSET_PATTERN_TYPES",
    "BASELINE_SCHEMA_NAME",
    "CROSS_MODAL_TYPES",
    "DEFAULT_SIGNALS",
    "DENSITIES",
    "EVIDENCE_FAMILIES",
    "EVIDENCE_SOURCES",
    "INTEGRATION_VERSION",
    "LAYER_UNIVERSAL",
    "LEGACY_ROLE_SUCCESSOR",
    "MULTIMODAL_CONTRACT_VERSION",
    "MULTIMODAL_FAMILIES",
    "MULTI_ROLE_STATEMENT",
    "NON_STRUCTURAL_EVIDENCE",
    "OBSERVED_REQUIRED_FAMILIES",
    "PATTERN_LAYER",
    "PLUGIN_MAY_NOT_REDEFINE",
    "REGION_ROLES",
    "SCHEMA_DIR",
    "SEQUENCE_ROLES",
    "SIGNAL_BINDING",
    "SIGNAL_FAMILY_BY_KIND",
    "SIGNAL_REQUIREMENTS",
    "SOURCE_ROLES",
    "STRUCTURAL_EVIDENCE",
    "TEXT_SIGNALS",
    "VISUAL_PATTERN_TYPES",
    "MultimodalContractError",
    "SignalFamily",
    "ArtifactIntegration",
    "CreatorStrategyPattern",
    "CreatorVisualPattern",
    "DatasetManifest",
    "FieldProvenance",
    "FrameObserver",
    "InvariantExtractor",
    "ManualAnnotationBackend",
    "MockDescriptorBackend",
    "ObservationResult",
    "ObservationSet",
    "ObservationSetBuilder",
    "ObserverError",
    "PROFILE_VERSION",
    "PatternToProfileMapper",
    "ProvenanceRecord",
    "Rating",
    "Rater",
    "SimilarityVector",
    "SourceStructure",
    "StdlibPixelBackend",
    "StructuralObservation",
    "VisionBackend",
    "VisualConstraint",
    "VisualCreatorProfile",
    "VisualGrammar",
    "VisualSignal",
    "VisualSource",
    "assert_creator_extension_is_interpretive",
    "assert_no_ocr_substitution",
    "assert_universal_layer_shape",
    "box_area",
    "build_cross_modal_records",
    "build_layout_records",
    "build_multimodal_artifact",
    "build_multimodal_envelope",
    "classify_density",
    "compute_agreement",
    "constraints_from_strategy",
    "distill_patterns",
    "distill_strategy",
    "extract_grammar",
    "factory_config",
    "grid_columns_are_declared",
    "integrate_samples",
    "layout_exists_independently",
    "merge_creator_extension",
    "merge_multimodal_artifact",
    "observation_to_records",
    "pattern_to_profile",
    "project_text_core",
    "region_boxes_are_disjoint",
    "roles_of",
    "signal_is_supported",
    "sources_holding_role",
    "structure_from_metadata",
    "synthetic_manifest",
    "text_signals_are_not_visual",
    "to_yaml",
    "validate_integrated_artifact",
    "validate_multimodal_artifact",
    "validate_profile",
    "validate_region",
    "vector_similarity",
    "write_profile_bundle",
]
