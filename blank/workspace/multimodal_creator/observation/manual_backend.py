"""Alternative vision backends: manual annotation and the M2 mock descriptor.

Two backends that are **not** perceptual, provided so the M3 observer contract
can be shown to hold independently of any particular implementation, and so the
pipeline is testable without files on disk.

Neither is a fallback for the real pixel backend. They exist to prove the seam:
the observation producer cannot tell which backend it is given.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..extraction.mock_vision_extractor import MockVisionExtractor
from ..extraction.visual_sample import VisualSample
from .interface import ObserverError, VisualSource

#: Keys a manual annotation may carry. Notably absent: any text content field.
#: An annotation that could supply text would invite an OCR shortcut, so the
#: format has no way to express one.
ANNOTATION_KEYS: tuple[str, ...] = (
    "regions",
    "palette_relation",
    "contrast_role",
    "density",
    "type_scale_relation",
    "hierarchy_levels",
    "alignment",
    "subject_class",
    "chart_class",
    "cover_role",
    "placement",
)


class ManualAnnotationBackend:
    """Reads a structural annotation supplied alongside the asset.

    The annotation is JSON: either a path in ``source.metadata['annotation_path']``
    or an inline mapping in ``source.metadata['annotation']``. It describes
    structure only; there is no field for text content, which makes an OCR
    shortcut unrepresentable rather than merely discouraged.
    """

    backend_id = "manual_annotation_v1"
    evidence_source = "manual_annotation"

    def __init__(self) -> None:
        self._cache: dict[str, Mapping[str, Any]] = {}

    def annotation_for(self, source: VisualSource) -> Mapping[str, Any]:
        key = str(source.asset_reference)
        if key in self._cache:
            return self._cache[key]

        inline = source.metadata.get("annotation")
        if inline is not None:
            if not isinstance(inline, Mapping):
                raise ObserverError(
                    f"annotation for {source.source_id!r} must be a mapping"
                )
            self._cache[key] = inline
            return inline

        path_value = source.metadata.get("annotation_path")
        if not path_value:
            raise ObserverError(
                f"source {source.source_id!r} carries neither metadata['annotation'] "
                "nor metadata['annotation_path']; the manual backend has nothing to read"
            )
        path = Path(str(path_value))
        if not path.is_file():
            raise ObserverError(f"annotation file does not exist: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ObserverError(f"annotation is not valid JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ObserverError("annotation root must be an object")
        self._cache[key] = payload
        return payload

    def _require(self, annotation: Mapping[str, Any], key: str, source: VisualSource) -> Any:
        if key not in annotation:
            raise ObserverError(
                f"annotation for {source.source_id!r} is missing required key {key!r}"
            )
        return annotation[key]

    def detect_regions(self, source: VisualSource) -> Sequence[Mapping[str, Any]]:
        annotation = self.annotation_for(source)
        regions = self._require(annotation, "regions", source)
        if not isinstance(regions, Sequence) or not regions:
            raise ObserverError(
                f"annotation for {source.source_id!r} must declare a non-empty region list"
            )
        for index, region in enumerate(regions):
            if not isinstance(region, Mapping):
                raise ObserverError(f"region {index} is not an object")
            for key in ("region_id", "role", "box", "layer_order"):
                if key not in region:
                    raise ObserverError(f"region {index} is missing {key!r}")
        return regions

    def detect_visual_roles(self, source: VisualSource) -> Mapping[str, Any]:
        annotation = self.annotation_for(source)
        return {
            "palette_relation": annotation.get("palette_relation", "mixed"),
            "contrast_role": annotation.get("contrast_role", "neutral"),
            "density": annotation.get("density", "balanced"),
        }

    def detect_style_features(self, source: VisualSource) -> Mapping[str, Any]:
        annotation = self.annotation_for(source)
        return {
            "type_scale_relation": annotation.get("type_scale_relation"),
            "hierarchy_levels": annotation.get("hierarchy_levels"),
            "alignment": annotation.get("alignment"),
        }

    def detect_text_visual_alignment(
        self, source: VisualSource
    ) -> Sequence[Mapping[str, Any]]:
        """Derive relations from the annotated geometry, never from text."""

        from ..extraction.cross_modal_candidates import (
            candidates_from_observation,
        )
        from ..taxonomy import StructuralObservation

        regions = self.detect_regions(source)
        observation = StructuralObservation(
            observation_id=f"{source.source_id}:annotation",
            medium="video" if source.source_type == "video_frame" else "image",
            source_id=source.source_id,
            roles=("visual_style_source", "layout_source"),
            evidence_kinds=("region_layout", "region_geometry"),
            regions=tuple(dict(region) for region in regions),
        )
        return [
            {
                "text_region_id": candidate.text_region_id,
                "text_role": candidate.text_role,
                "visual_region_id": candidate.visual_region_id,
                "visual_role": candidate.visual_role,
                "geometric_relation": candidate.geometric_relation,
                "rationale": candidate.rationale,
            }
            for candidate in candidates_from_observation(observation)
        ]


class MockDescriptorBackend:
    """Adapts M2's declarative :class:`VisualSample` to the backend interface.

    The sample is supplied through ``source.metadata['sample']``. This backend
    performs no observation at all — it re-states what the caller declared — and
    is labelled ``mock_backend`` so a result produced this way can never be
    mistaken for a real observation.
    """

    backend_id = "mock_descriptor_v1"
    evidence_source = "mock_backend"

    def __init__(self) -> None:
        self._extractor = MockVisionExtractor()

    def _sample(self, source: VisualSource) -> VisualSample:
        sample = source.metadata.get("sample")
        if not isinstance(sample, VisualSample):
            raise ObserverError(
                f"source {source.source_id!r} metadata['sample'] must be a VisualSample"
            )
        return sample

    def _observation(self, source: VisualSource):
        return self._extractor.extract(self._sample(source))

    def detect_regions(self, source: VisualSource) -> Sequence[Mapping[str, Any]]:
        return [dict(region) for region in self._observation(source).regions]

    def detect_visual_roles(self, source: VisualSource) -> Mapping[str, Any]:
        observation = self._observation(source)
        return {
            "palette_relation": observation.palette_relation or "mixed",
            "contrast_role": "neutral",
            "density": observation.density or "balanced",
        }

    def detect_style_features(self, source: VisualSource) -> Mapping[str, Any]:
        observation = self._observation(source)
        return {
            "type_scale_relation": observation.type_scale_relation,
            "hierarchy_levels": None,
            "alignment": observation.alignment,
        }

    def detect_text_visual_alignment(
        self, source: VisualSource
    ) -> Sequence[Mapping[str, Any]]:
        from ..extraction.cross_modal_candidates import candidates_from_observation

        return [
            {
                "text_region_id": candidate.text_region_id,
                "text_role": candidate.text_role,
                "visual_region_id": candidate.visual_region_id,
                "visual_role": candidate.visual_role,
                "geometric_relation": candidate.geometric_relation,
                "rationale": candidate.rationale,
            }
            for candidate in candidates_from_observation(self._observation(source))
        ]


__all__ = ["ANNOTATION_KEYS", "ManualAnnotationBackend", "MockDescriptorBackend"]
