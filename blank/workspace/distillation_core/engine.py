"""Orchestrates common extraction and plugin contribution into one artifact."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Iterable

from core.models import RawSource
from core.schema_validation import validate_unified_artifact
from evaluation.evaluator import evaluate_distillation_artifact
from plugin_interface.base import CreatorDistillationPlugin

from .extractor import CommonExtractor


_ENHANCEABLE_FIELDS = {
    "topic_candidate",
    "content_template",
    "knowledge_unit",
    "style_pattern",
}


class DistillationEngine:
    """Produce exactly one validated artifact from raw inputs.

    Common extraction and domain enhancement are implementation participants in
    this invocation, not independently persisted distillation stages.
    """

    def __init__(
        self,
        plugin: CreatorDistillationPlugin,
        *,
        schema_path: str | Path | None = None,
        extractor: CommonExtractor | None = None,
    ) -> None:
        self._plugin = plugin
        self._extractor = extractor or CommonExtractor()
        self._schema_path = Path(schema_path or _default_schema_path())

    def distill(self, raw_sources: Iterable[RawSource]) -> dict:
        sources = tuple(raw_sources)
        if not sources:
            raise ValueError("at least one RawSource is required")
        source_ids = [source.source_id for source in sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("RawSource.source_id values must be unique")

        common_signals = self._extractor.extract(sources)
        contribution = self._plugin.enhance(sources, deepcopy(common_signals))
        unknown = set(contribution.field_enhancements) - _ENHANCEABLE_FIELDS
        if unknown:
            raise ValueError(
                "plugin returned unknown enhancement fields: "
                + ", ".join(sorted(unknown))
            )

        merged = deepcopy(common_signals)
        for field_name, additions in contribution.field_enhancements.items():
            merged[field_name].extend(deepcopy(list(additions)))

        base_evaluation = evaluate_distillation_artifact(merged, sources)
        artifact = {
            "artifact_version": "1.0.0",
            "plugin": self._plugin.identity.as_dict(),
            **merged,
            "domain_extension": deepcopy(dict(contribution.domain_extension)),
            "risk_constraints": deepcopy(list(contribution.risk_constraints)),
            "evaluation_result": {
                "common": base_evaluation,
                "domain": deepcopy(dict(contribution.evaluation_result)),
            },
        }
        validate_unified_artifact(artifact, self._schema_path)
        return artifact


def _default_schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "unified_distillation_artifact.json"
