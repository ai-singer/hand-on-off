"""M3 benchmark runner: renders, observes, clusters, distils, evaluates.

Full chain exercised end to end on real image bytes::

    render PNG ─▶ StdlibPixelBackend ─▶ FrameObserver ─▶ ObservationResult
              ─▶ VisualSample ─▶ similarity ─▶ discovery ─▶ patterns
              ─▶ evaluation against independent labels

Label handling is the load-bearing design point. Labels are read **only** by the
evaluator, after clustering and distillation have already finished. Creator ids
are needed earlier — a real observer cannot see who made an image, so provenance
must come from ground truth — but creator identity is a fact about the source,
not a statement about which family it belongs to. No template id, no family
label, and no expected cluster ever reaches the observation, similarity,
clustering, or distillation code.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..clustering.template_discovery import TemplateDiscovery, discover_templates
from ..extraction.visual_sample import VisualSample
from ..pattern.distillation import CreatorVisualPattern, distill_patterns
from ..similarity.similarity_contract import SimilarityResult, pairwise_similarity
from .benchmark_dataset import CASE_GROUPS, BenchmarkDataset, build_dataset
from .calibration import CalibrationReport, calibrate
from .corpus import render_corpus
from .evaluation import (
    EvaluationBundle,
    clustering_metrics,
    detection_metrics,
    pattern_metrics,
)
from .frame_observer import FrameObserver, VideoSequenceObserver
from .image_observer import StdlibPixelBackend
from .interface import ObservationResult, VisualSource
from .observation_result import ObservationSet, ObservationSetBuilder


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Outcome of one benchmark case."""

    case_id: str
    group: str
    kind: str
    passed: bool
    failures: tuple[str, ...] = ()
    observed: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "kind": self.kind,
            "passed": self.passed,
            "failures": list(self.failures),
            "observed": dict(self.observed),
        }

    def render(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        line = f"[{status}] {self.case_id}"
        for failure in self.failures:
            line += f"\n        {failure}"
        return line


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    """Everything a run produces, kept for inspection and reporting."""

    dataset: BenchmarkDataset
    observation_set: ObservationSet
    samples: tuple[VisualSample, ...]
    discovery: TemplateDiscovery
    patterns: tuple[CreatorVisualPattern, ...]
    similarity: Mapping[tuple[str, str], SimilarityResult]
    calibration: CalibrationReport
    evaluation: EvaluationBundle
    threshold: float
    elapsed_seconds: float

    def sample_by_id(self, sample_id: str) -> VisualSample:
        for sample in self.samples:
            if sample.sample_id == sample_id:
                return sample
        raise KeyError(sample_id)

    def membership(self) -> dict[str, str]:
        membership: dict[str, str] = {}
        for cluster in self.discovery.clusters:
            for member_id in cluster.member_ids:
                membership[member_id] = cluster.cluster_id
        return membership


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Case results plus the metrics bundle."""

    case_results: tuple[CaseResult, ...]
    run: RunArtifacts

    @property
    def total(self) -> int:
        return len(self.case_results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.case_results if result.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def failures(self) -> tuple[CaseResult, ...]:
        return tuple(result for result in self.case_results if not result.passed)

    def by_group(self) -> dict[str, tuple[int, int]]:
        groups: dict[str, list[int]] = {name: [0, 0] for name in CASE_GROUPS}
        for result in self.case_results:
            entry = groups.setdefault(result.group, [0, 0])
            entry[0] += 1 if result.passed else 0
            entry[1] += 1
        return {name: (values[0], values[1]) for name, values in sorted(groups.items())}

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "m3_benchmark_report/v1",
            "case_count": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "ok": self.ok,
            "by_group": {
                name: {"passed": passed, "total": total}
                for name, (passed, total) in self.by_group().items()
            },
            "cases": [result.as_dict() for result in self.case_results],
            "evaluation": self.run.evaluation.as_dict(),
            "calibration": self.run.calibration.as_dict(),
            "discovery": {
                "threshold": self.run.discovery.threshold,
                "provenance_mode": self.run.discovery.provenance_mode,
                "cluster_count": len(self.run.discovery.clusters),
                "template_count": len(self.run.discovery.templates()),
                "clusters": [
                    {
                        "cluster_id": cluster.cluster_id,
                        "member_ids": list(cluster.member_ids),
                        "mean_similarity": cluster.evidence.mean_similarity,
                        "min_similarity": cluster.evidence.min_similarity,
                        "creator_count": cluster.evidence.creator_count,
                        "dominant_layout_class": cluster.evidence.dominant_layout_class,
                        "recurring": cluster.evidence.recurring,
                    }
                    for cluster in self.run.discovery.clusters
                ],
            },
            "patterns": [pattern.as_dict() for pattern in self.run.patterns],
            "elapsed_seconds": self.run.elapsed_seconds,
        }

    def render(self) -> str:
        lines = [
            f"M3 benchmark — {self.passed}/{self.total} cases passed "
            f"(threshold={self.run.threshold:.3f}, {self.run.elapsed_seconds:.1f}s)",
        ]
        for name, (passed, total) in self.by_group().items():
            lines.append(f"  {name:<32} {passed:>2}/{total}")
        if self.failures():
            lines.append("")
            lines.extend(result.render() for result in self.failures())
        lines.append("")
        lines.append(self.run.evaluation.render())
        return "\n".join(lines)


def _observe_corpus(
    dataset: BenchmarkDataset,
    *,
    directory: Path,
    backend: StdlibPixelBackend,
) -> tuple[ObservationSet, tuple[VisualSample, ...]]:
    """Render the dataset and run the real observation chain over it.

    Rendering and observation are cached in ``directory`` when
    ``M3_BENCHMARK_CACHE=1`` is set in the environment. The chain is fully
    deterministic, so a cached run is the same run — this only avoids paying
    ~150 seconds of PNG encoding and pixel analysis on every threshold sweep.
    """

    import os

    use_cache = os.environ.get("M3_BENCHMARK_CACHE") == "1"
    cache_path = directory / "observations.json"

    if use_cache and cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("sample_count") == len(dataset.samples):
            return _observations_from_cache(cached, dataset)

    written = render_corpus(
        directory,
        samples=list(dataset.samples),
        templates=dict(dataset.templates),
        width=dataset.width,
        height=dataset.height,
    )
    observer = FrameObserver(backend)
    results: list[ObservationResult] = [
        observer.observe(VisualSource(sample_id, "image", path))
        for sample_id, path in written
    ]

    builder = ObservationSetBuilder()
    # Only creator identity is taken from labels here; no template or family
    # information is read, because an observer cannot see provenance anyway and
    # family membership must never reach this stage.
    provenance = {
        sample_id: {
            "creator_id": dataset.labels[sample_id]["creator_id"],
            "batch_id": dataset.labels[sample_id]["batch_id"],
        }
        for sample_id, _path in written
    }
    observation_set = builder.build(results, labels=provenance)
    samples = builder.to_visual_samples(observation_set)

    if use_cache:
        cache_path.write_text(
            json.dumps(
                {
                    "sample_count": len(dataset.samples),
                    "results": [result.as_dict() for result in results],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return observation_set, samples


def _observations_from_cache(
    cached: Mapping[str, Any], dataset: BenchmarkDataset
) -> tuple[ObservationSet, tuple[VisualSample, ...]]:
    """Rebuild observations from a cached run."""

    from ..taxonomy import StructuralObservation, MultimodalContractError

    results: list[ObservationResult] = []
    for entry in cached["results"]:
        body = entry["observation"]
        source = VisualSource(
            source_id=entry["source"]["source_id"],
            source_type=entry["source"]["source_type"],
            asset_reference=entry["source"]["asset_reference"],
            metadata=entry["source"].get("metadata", {}),
        )
        observation = StructuralObservation(
            observation_id=entry["observation_id"],
            medium=body["medium"],
            source_id=body["source_id"],
            roles=tuple(body["roles"]),
            evidence_kinds=tuple(body["evidence_kinds"]),
            regions=tuple(dict(region) for region in body["regions"]),
            layout_template_class=body["layout_template_class"],
            alignment=body["alignment"],
            density=body["density"],
            palette_relation=body["palette_relation"],
            type_scale_relation=body["type_scale_relation"],
            subject_class=body["subject_class"],
            chart_class=body["chart_class"],
            placement=body["placement"],
            confidence=body["confidence"] if "confidence" in body else entry["confidence"],
        )
        evidence = {}
        for name, record in entry["evidence"].items():
            from .interface import EvidenceRecord

            try:
                evidence[name] = EvidenceRecord(
                    family=record["family"],
                    sources=tuple(record["sources"]),
                    strength=record["strength"],
                    detail=record.get("detail", {}),
                )
            except MultimodalContractError:
                continue
        try:
            results.append(
                ObservationResult(
                    observation=observation,
                    source=source,
                    backend_id=entry["backend_id"],
                    evidence_source=entry["evidence_source"],
                    evidence=evidence,
                    confidence=entry["confidence"],
                    warnings=tuple(entry.get("warnings", ())),
                    backend_failures=tuple(entry.get("backend_failures", ())),
                )
            )
        except MultimodalContractError:
            continue

    builder = ObservationSetBuilder()
    provenance = {
        result.source_id: {
            "creator_id": dataset.labels[result.source_id]["creator_id"],
            "batch_id": dataset.labels[result.source_id]["batch_id"],
        }
        for result in results
        if result.source_id in dataset.labels
    }
    observation_set = builder.build(results, labels=provenance)
    return observation_set, builder.to_visual_samples(observation_set)


def run_benchmark(
    *,
    dataset: BenchmarkDataset | None = None,
    threshold: float,
    provenance_mode: str = "provenance_agnostic",
    workdir: str | Path | None = None,
) -> BenchmarkReport:
    """Run the full M3 validation and score it against independent labels."""

    import tempfile

    started = time.time()
    active = dataset or build_dataset()
    backend = StdlibPixelBackend()

    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(workdir) if workdir else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        observation_set, samples = _observe_corpus(
            active, directory=directory, backend=backend
        )

    # -- clustering and distillation, with no labels in scope -----------------
    # Nothing above this line has seen a template id. Nothing below it will.
    discovery = discover_templates(
        samples, threshold=threshold, provenance_mode=provenance_mode
    )
    patterns = distill_patterns(discovery, samples)

    # -- similarity matrix, for calibration and case scoring ------------------
    by_id = {sample.sample_id: sample for sample in samples}
    ids = sorted(by_id)
    similarity: dict[tuple[str, str], SimilarityResult] = {}
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            similarity[(left, right)] = pairwise_similarity(by_id[left], by_id[right])

    evaluation_labels = {
        sample_id: {
            "template_id": active.labels[sample_id]["template_id"],
            "creator_id": active.labels[sample_id]["creator_id"],
            "layout_family": active.labels[sample_id]["layout_family"],
            "expected_layout_class": active.labels[sample_id]["expected_layout_class"],
        }
        for sample_id in ids
    }

    # -- evaluation (the only place family labels are read) -------------------
    predictions = {
        sample.sample_id: sample.layout_template_class for sample in samples
    }
    ground_truth_layout = {
        sample_id: evaluation_labels[sample_id]["expected_layout_class"]
        for sample_id in ids
    }
    ground_truth_family = {
        sample_id: evaluation_labels[sample_id]["layout_family"] for sample_id in ids
    }
    detection = detection_metrics(predictions, ground_truth_layout)
    clustering = clustering_metrics(
        {sid: cluster.cluster_id for cluster in discovery.clusters for sid in cluster.member_ids},
        ground_truth_family,
        recurring_cluster_ids=[c.cluster_id for c in discovery.templates()],
    )
    pattern = pattern_metrics(patterns, ground_truth_family)

    calibration_labels = {
        sample_id: {
            "template_id": evaluation_labels[sample_id]["layout_family"],
            "creator_id": evaluation_labels[sample_id]["creator_id"],
        }
        for sample_id in ids
    }
    calibration = calibrate(
        ((left, right, result) for (left, right), result in sorted(similarity.items())),
        labels=calibration_labels,
        dataset_id="m3-benchmark",
        backend_id=observation_set.backend_id,
    )

    evaluation = EvaluationBundle(
        detection=detection, clustering=clustering, pattern=pattern
    )

    run = RunArtifacts(
        dataset=active,
        observation_set=observation_set,
        samples=samples,
        discovery=discovery,
        patterns=patterns,
        similarity=similarity,
        calibration=calibration,
        evaluation=evaluation,
        threshold=threshold,
        elapsed_seconds=round(time.time() - started, 3),
    )

    case_results = _score_cases(active, run)
    return BenchmarkReport(case_results=tuple(case_results), run=run)


def _pair_result(run: RunArtifacts, left: str, right: str) -> SimilarityResult:
    key = (left, right) if (left, right) in run.similarity else (right, left)
    return run.similarity[key]


def _same_cluster(run: RunArtifacts, left: str, right: str) -> bool:
    membership = run.membership()
    if left not in membership or right not in membership:
        return False
    return membership[left] == membership[right]


def _score_cases(dataset: BenchmarkDataset, run: RunArtifacts) -> list[CaseResult]:
    """Score each case against the run's output."""

    results: list[CaseResult] = []
    sequence_observer = VideoSequenceObserver(StdlibPixelBackend())

    for case in dataset.cases:
        failures: list[str] = []
        observed: dict[str, Any] = {}

        if case.kind in {"pair_same_template", "pair_different_template", "pair_same_creator_different_template", "pair_same_sample_family"}:
            left, right = case.sample_ids
            result = _pair_result(run, left, right)
            grouped = _same_cluster(run, left, right)
            expected_same = bool(case.expected.get("same_family"))
            observed = {
                "score": result.score,
                "grouped": grouped,
                "expected_same_family": expected_same,
            }
            if grouped != expected_same:
                failures.append(
                    f"expected same_family={expected_same}, got grouped={grouped} "
                    f"(score={result.score:.3f}, threshold={run.threshold:.3f})"
                )
            if case.expected.get("same_creator") and not case.expected.get("same_family"):
                # A same-creator, different-template pair must be both ungrouped
                # *and* clearly below threshold, not merely on the wrong side of it.
                if result.score >= run.threshold:
                    failures.append(
                        f"same-creator different-template pair scored "
                        f"{result.score:.3f} at or above threshold"
                    )

        elif case.kind == "pattern_contains":
            template_id = case.expected["template_id"]
            member_ids = set(case.sample_ids)
            matching = [
                pattern
                for pattern in run.patterns
                if member_ids & set(pattern.member_ids)
            ]
            observed = {
                "patterns_matched": [pattern.pattern_id for pattern in matching],
                "template_id": template_id,
            }
            if not matching:
                failures.append(
                    f"no distilled pattern covers any member of {template_id}"
                )
            else:
                moves: set[str] = set()
                stages: set[str] = set()
                for pattern in matching:
                    moves.update(pattern.layout_strategy)
                    stages.update(pattern.hierarchy)
                required_moves = case.expected.get("required_moves_any") or []
                if required_moves and not any(
                    any(move.startswith(required) for move in moves)
                    for required in required_moves
                ):
                    failures.append(
                        f"none of {required_moves} present in strategy {sorted(moves)}"
                    )
                required_stages = case.expected.get("required_stages") or []
                for stage in required_stages:
                    if stage not in stages:
                        failures.append(
                            f"required hierarchy stage {stage!r} missing from "
                            f"{sorted(stages)}"
                        )

        elif case.kind == "sequence_consistency":
            cases = [
                next(result for result in run.observation_set.results if result.source_id == sid)
                for sid in case.sample_ids
            ]
            layouts = {result.observation.layout_template_class for result in cases}
            observed = {
                "layouts": sorted(str(layout) for layout in layouts),
                "sequence_length": len(cases),
            }
            if len(layouts) > 1:
                failures.append(
                    f"frames of one sequence observed inconsistently: {sorted(str(x) for x in layouts)}"
                )
            for result in cases:
                if not result.is_complete():
                    failures.append(
                        f"frame {result.source_id} observation is incomplete: "
                        f"{list(result.missing_families())}"
                    )

        else:
            failures.append(f"unknown case kind {case.kind!r}")

        results.append(
            CaseResult(
                case_id=case.case_id,
                group=case.group,
                kind=case.kind,
                passed=not failures,
                failures=tuple(failures),
                observed=observed,
            )
        )

    return results


def write_report(report: BenchmarkReport, path: str | Path) -> Path:
    """Persist the benchmark report as JSON."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "BenchmarkReport",
    "CaseResult",
    "RunArtifacts",
    "run_benchmark",
    "write_report",
]
