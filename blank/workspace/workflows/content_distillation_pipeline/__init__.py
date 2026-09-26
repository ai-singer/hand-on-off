"""Reference content distillation and quality workflow."""

from .generation_interface import GenerationAdapter, GenerationRequest
from .pipeline import ContentDistillationPipeline, PipelineResult

__all__ = [
    "ContentDistillationPipeline",
    "GenerationAdapter",
    "GenerationRequest",
    "PipelineResult",
]
