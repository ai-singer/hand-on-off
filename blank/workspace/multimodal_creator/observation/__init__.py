"""Observation layer for real visual input (Phase M3).

Replaces M2's declarative mock observer with a **real observation adapter** while
keeping the M1 :class:`StructuralObservation` as the only intermediate
representation. Similarity, clustering, and pattern distillation are unchanged
and unaware that anything shifted — the payoff of building the contract first.

Contents
--------

``interface``
    :class:`VisualSource`, :class:`ObservationResult`, :class:`VisionBackend`,
    and the evidence-completeness rules.
``image_observer``
    :class:`StdlibPixelBackend` — real pixel analysis on decoded image bytes.
``manual_backend``
    Manual annotation and M2 mock-descriptor backends, proving the seam.
``frame_observer``
    Backend output → evidence-complete observation; video sequences.
``observation_result``
    Observation sets and reconstruction into M2-compatible samples.
``calibration``
    Similarity measurement and threshold selection over four quadrants.
``benchmark_dataset`` / ``benchmark_runner``
    54 labeled cases over real rendered images, scored independently.
``evaluation``
    Detection, clustering, and pattern metrics.
``corpus`` / ``pixel``
    The synthetic corpus and the dependency-free pixel primitives.
"""

from .calibration import (
    M2_SYNTHETIC_THRESHOLD,
    QUADRANTS,
    CalibrationError,
    CalibrationReport,
    QuadrantStats,
    ThresholdCandidate,
    calibrate,
    calibrate_from_samples,
    write_calibration,
)
from .frame_observer import FrameObserver, VideoSequenceObserver
from .image_observer import (
    RegionEvidence,
    StdlibPixelBackend,
)
from .interface import (
    EVIDENCE_FAMILIES,
    EVIDENCE_SOURCES,
    EvidenceRecord,
    ObservationResult,
    ObserverError,
    VisionBackend,
    VisualSource,
)
from .manual_backend import ManualAnnotationBackend, MockDescriptorBackend
from .observation_result import ObservationSet, ObservationSetBuilder

__all__ = [
    "EVIDENCE_FAMILIES",
    "EVIDENCE_SOURCES",
    "M2_SYNTHETIC_THRESHOLD",
    "QUADRANTS",
    "CalibrationError",
    "CalibrationReport",
    "EvidenceRecord",
    "FrameObserver",
    "ManualAnnotationBackend",
    "MockDescriptorBackend",
    "ObservationResult",
    "ObservationSet",
    "ObservationSetBuilder",
    "ObserverError",
    "QuadrantStats",
    "RegionEvidence",
    "StdlibPixelBackend",
    "ThresholdCandidate",
    "VideoSequenceObserver",
    "VisionBackend",
    "VisualSource",
    "calibrate",
    "calibrate_from_samples",
    "write_calibration",
]
