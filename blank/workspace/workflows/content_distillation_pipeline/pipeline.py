"""Reference orchestration for source-to-quality-gate processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.models import RawSource
from distillation_core import DistillationEngine
from evaluation import evaluate_pipeline_output

from .generation_interface import GenerationAdapter, GenerationRequest


@dataclass(frozen=True, slots=True)
class PipelineResult:
    artifact: dict[str, Any]
    generated_output: Any | None
    quality_report: dict[str, Any]


class ContentDistillationPipeline:
    """Run one distillation, an optional generator, and the quality gate."""

    def __init__(
        self,
        engine: DistillationEngine,
        generation_adapter: GenerationAdapter | None = None,
    ) -> None:
        self._engine = engine
        self._generation_adapter = generation_adapter

    def run(
        self,
        raw_sources: Iterable[RawSource],
        *,
        format_name: str = "content_plan",
        generation_constraints: dict[str, Any] | None = None,
    ) -> PipelineResult:
        artifact = self._engine.distill(raw_sources)
        generated_output = None
        if self._generation_adapter is not None:
            generated_output = self._generation_adapter.generate(
                GenerationRequest(
                    artifact=artifact,
                    format_name=format_name,
                    constraints=generation_constraints or {},
                )
            )
        quality_report = evaluate_pipeline_output(artifact, generated_output)
        return PipelineResult(
            artifact=artifact,
            generated_output=generated_output,
            quality_report=quality_report,
        )
