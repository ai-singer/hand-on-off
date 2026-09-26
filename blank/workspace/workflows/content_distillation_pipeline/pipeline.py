"""Reference orchestration for source-to-quality-gate processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.models import RawSource
from distillation_core import DistillationEngine
from evaluation import QualityGateController, evaluate_pipeline_output

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
        quality_gate_controller: QualityGateController | None = None,
    ) -> None:
        self._engine = engine
        self._generation_adapter = generation_adapter
        self._quality_gate_controller = (
            quality_gate_controller or QualityGateController()
        )

    def run(
        self,
        raw_sources: Iterable[RawSource],
        *,
        format_name: str = "content_plan",
        generation_constraints: dict[str, Any] | None = None,
    ) -> PipelineResult:
        artifact = self._engine.distill(raw_sources)
        quality_report = evaluate_pipeline_output(artifact, None)
        gate_result = self._quality_gate_controller.decide(quality_report)
        generation = self._quality_gate_controller.execute_generation(
            gate_result,
            self._generation_adapter,
            GenerationRequest(
                artifact=artifact,
                format_name=format_name,
                constraints=generation_constraints or {},
            ),
        )
        final_quality_report = dict(gate_result.quality_report)
        final_quality_report["generation_adapter_invoked"] = generation.invoked
        return PipelineResult(
            artifact=artifact,
            generated_output=generation.output,
            quality_report=final_quality_report,
        )
