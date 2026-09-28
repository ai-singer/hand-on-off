"""Risk Coverage Expansion Framework.

A repeatable way to find out what the risk evaluator cannot see, and to queue the
answers for a human instead of applying them.

The evaluator itself is frozen. This package reads it — its lexicons, its relations,
its frames — and runs it over the Phase 8.9 independent benchmark, but it never writes
to `risk_evaluation/v3/`, `risk_evaluation/v3_1/`, `risk_evaluation/v3_independent/` or
any benchmark. `freeze.guard()` recomputes the digests and fails if a byte moved.

The six stages:

    generator  ->  analyzer  ->  registry  ->  pipeline
       |              |             |
       v              v             v
    generated     failure       pending /
    cases         analysis      rejected

`generator` is the Failure Generator: structured substitution into declared templates,
never random text and never a model call. `analyzer` is the Failure Analyzer: it
classifies each failing case into one of nine failure types and records the evidence
for the classification. `registry` is the Coverage Expansion Candidate store and the
Human Review Queue. `pipeline` wires them together and writes the artifacts.

Three things this package will not do, each enforced in code rather than promised:

**It will not modify the evaluator.** `freeze.guard()` verifies the frozen sources.
No module here writes outside its own directory.

**It will not put generated cases in a benchmark.** `model.GeneratedCase` raises if
`excludes_from_benchmark` is false, and nothing here writes to
`risk_evaluation/benchmarks/`.

**It will not accept its own candidates.** `registry.write()` writes `pending/` and
provable rejections only. `accepted/` carries a README and is written by a human.

Read `describe()` for a machine-readable summary of the whole framework.
"""

from __future__ import annotations

from . import (
    analyzer,
    freeze,
    generator,
    lexicon,
    pipeline,
    registry,
    reporter,
    synonyms,
    taxonomy,
)
from .analyzer import analyze
from .generator import generate
from .model import (
    CoverageCandidate,
    CoverageError,
    Evidence,
    FailureAnalysis,
    FailureRecord,
    GeneratedCase,
    RegressionCandidate,
    RepairCandidate,
    ReviewDecision,
)
from .pipeline import describe as framework_summary
from .pipeline import run, validate_artifacts
from .registry import build as build_candidates
from .taxonomy import (
    ANNOTATION_CONFLICT,
    ATTRIBUTION_GAP,
    AUTO_GENERATABLE,
    FAILURE_TYPES,
    FRAME_GAP,
    HUMAN_REQUIRED,
    LEXICAL_GAP,
    MORPHOLOGY_GAP,
    STANCE_GAP,
    SYNONYM_GAP,
    TAXONOMY_CONFLICT,
    UNKNOWN,
)

__all__ = [
    # modules
    "analyzer",
    "freeze",
    "generator",
    "lexicon",
    "pipeline",
    "registry",
    "reporter",
    "synonyms",
    "taxonomy",
    # stages
    "analyze",
    "generate",
    "build_candidates",
    "run",
    "validate_artifacts",
    "framework_summary",
    # model
    "CoverageCandidate",
    "CoverageError",
    "Evidence",
    "FailureAnalysis",
    "FailureRecord",
    "GeneratedCase",
    "RegressionCandidate",
    "RepairCandidate",
    "ReviewDecision",
    # taxonomy
    "FAILURE_TYPES",
    "AUTO_GENERATABLE",
    "HUMAN_REQUIRED",
    "LEXICAL_GAP",
    "SYNONYM_GAP",
    "MORPHOLOGY_GAP",
    "FRAME_GAP",
    "ATTRIBUTION_GAP",
    "STANCE_GAP",
    "TAXONOMY_CONFLICT",
    "ANNOTATION_CONFLICT",
    "UNKNOWN",
]

__version__ = "1.0.0"
