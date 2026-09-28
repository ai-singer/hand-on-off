"""Multimodal signal extraction prototype (Phase M2).

This subpackage answers the M1 open question "who produces structural
observations?". It supplies three producers, all of which are deliberately
**non-perceptual**:

``visual_sample``
    A declarative description of what a controlled sample contains.
``mock_vision_extractor``
    A deterministic function from a :class:`VisualSample` to an M1
    :class:`StructuralObservation`. No model, no randomness, no pixel access.
``observation_producer``
    Accepts hand annotations, mock extraction, or a mixture, and returns
    M1-valid observations plus cross-modal alignment candidates.

The distinction that matters: these producers implement *structural reasoning
over declared facts*. They do not see images. That is what makes M2 a
verification of protocol and algorithm rather than a verification of perception.
"""

from .cross_modal_candidates import (
    GEOMETRIC_RELATIONS,
    CrossModalCandidate,
    candidates_from_observation,
    candidates_from_sample,
    geometric_relation,
)
from .mock_vision_extractor import (
    MockVisionExtractor,
    contrast_role_for,
    derive_evidence_kinds,
)
from .observation_producer import (
    ObservationBatch,
    ObservationProducer,
    annotation_to_observation,
)
from .visual_sample import (
    MockExtractionError,
    RegionSpec,
    SampleProvenance,
    SubjectSpec,
    TextStyleSpec,
    VisualSample,
    region_to_dict,
)

__all__ = [
    "GEOMETRIC_RELATIONS",
    "CrossModalCandidate",
    "MockExtractionError",
    "MockVisionExtractor",
    "ObservationBatch",
    "ObservationProducer",
    "RegionSpec",
    "SampleProvenance",
    "SubjectSpec",
    "TextStyleSpec",
    "VisualSample",
    "annotation_to_observation",
    "candidates_from_observation",
    "candidates_from_sample",
    "contrast_role_for",
    "derive_evidence_kinds",
    "geometric_relation",
    "region_to_dict",
]
