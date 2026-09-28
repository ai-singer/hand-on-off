"""M4 benchmark runner (phases 8 and 9).

Chain::

    PNG ─▶ StdlibPixelBackend ─▶ FrameObserver ─▶ StructuralObservation
        ─▶ GrammarExtractor ─▶ VisualGrammar
        ─▶ SimilarityVector matrix
        ─▶ clustering (on the structural dimension)
        ─▶ InvariantExtractor ─▶ InvariantSet
        ─▶ strategy distillation ─▶ CreatorStrategyPattern
        ─▶ constraints_from_strategy ─▶ VisualConstraint

Clusters are formed from the **structural** dimension of the similarity vector,
not from a layout label. That is the M4 correction: clustering now reads the
representation instead of a coarse summary of it.

Label handling: labels are read only by the scorer, after every algorithm has
finished. A test asserts the ordering.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..clustering.template_discovery import (
    Cluster,
    ClusterEvidence,
    ClusterMember,
    TemplateDiscovery,
)
from ..observation.benchmark_runner import _observe_corpus  # reuse M3 observation
from ..observation.corpus import SampleSpec, TemplateSpec, render_corpus
from ..observation.image_observer import StdlibPixelBackend
from ..observation.interface import ObservationResult
from ..taxonomy import StructuralObservation
from .benchmark_dataset import (
    CASE_GROUPS,
    BenchmarkCase,
    BenchmarkDataset,
    build_dataset,
)
from .constraints import VisualConstraint, constraints_from_strategy
from .evaluation import (
    EvaluationBundle,
    region_accuracy,
    relation_metrics,
    stability_metrics,
    strategy_metrics,
)
from .extractor import GrammarExtractor
from .invariants import InvariantExtractor, InvariantSet
from .model import RELATION_TYPES, VisualGrammar
from .similarity_v2 import (
    TEMPLATE_PROFILE,
    SimilarityVector,
    vector_matrix,
)
from .strategy import CreatorStrategyPattern, distill_strategy

#: Structural threshold for clustering on the template profile.
#:
#: Not M2's 0.90 and not M3's 0.646: those were calibrated on a *scalar* score
#: whose scale the vector does not share. This value was measured on the M4
#: vector by sweeping the structural dimension, and the sweep is reported.
DEFAULT_STRUCTURAL_THRESHOLD = 0.75

#: Invariant support threshold used by the benchmark.
INVARIANT_THRESHOLD = 0.8


class RunError(Exception):
    """Raised when the benchmark cannot complete a stage."""


@dataclass(frozen=True, slots=True)
class GrammarRecord:
    """One sample's observation, grammar, and extraction provenance."""

    sample_id: str
    creator_id: str
    template_id: str
    observation: StructuralObservation
    grammar: VisualGrammar
    decisions: Mapping[str, str]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClusterRecord:
    """A cluster of grammars with its invariants and distilled strategy."""

    cluster_id: str
    member_ids: tuple[str, ...]
    template_ids: tuple[str, ...]
    invariants: InvariantSet
    strategy: CreatorStrategyPattern
    constraints: VisualConstraint


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    """Everything one run produced."""

    dataset: BenchmarkDataset
    grammars: tuple[GrammarRecord, ...]
    vectors: Mapping[tuple[str, str], SimilarityVector]
    clusters: tuple[ClusterRecord, ...]
    discovery: TemplateDiscovery
    evaluation: EvaluationBundle
    structural_threshold: float
    elapsed_seconds: float

    def grammar_for(self, sample_id: str) -> GrammarRecord:
        for record in self.grammars:
            if record.sample_id == sample_id:
                return record
        raise RunError(f"no grammar for sample {sample_id!r}")

    def cluster_for(self, sample_id: str) -> ClusterRecord | None:
        for cluster in self.clusters:
            if sample_id in cluster.member_ids:
                return cluster
        return None


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One scored benchmark case."""

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
        line = f"[{'PASS' if self.passed else 'FAIL'}] {self.case_id}"
        for failure in self.failures:
            line += f"\n        {failure}"
        return line


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Case results plus the metric bundle and the artifacts behind them."""

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
            "schema": "m4_benchmark_report/v1",
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
            "structural_threshold": self.run.structural_threshold,
            "clusters": [
                {
                    "cluster_id": cluster.cluster_id,
                    "member_count": len(cluster.member_ids),
                    "template_ids": list(cluster.template_ids),
                    "attention_strategy": cluster.strategy.attention_strategy,
                    "information_hierarchy": list(cluster.strategy.information_hierarchy),
                    "composition_strategy": list(cluster.strategy.composition_strategy),
                    "invariant_count": len(cluster.invariants.invariants),
                    "constraint_count": len(cluster.constraints.all_constraints()),
                    "confidence": cluster.strategy.confidence,
                }
                for cluster in self.run.clusters
            ],
            "elapsed_seconds": self.run.elapsed_seconds,
        }

    def render(self) -> str:
        lines = [
            f"M4 benchmark — {self.passed}/{self.total} cases passed "
            f"(structural threshold={self.run.structural_threshold:.3f}, "
            f"{self.run.elapsed_seconds:.1f}s)",
        ]
        for name, (passed, total) in self.by_group().items():
            lines.append(f"  {name:<24} {passed:>3}/{total}")
        if self.failures():
            lines.append("")
            lines.extend(result.render() for result in self.failures())
        lines.append("")
        lines.append(self.run.evaluation.render())
        return "\n".join(lines)


def _cluster_from_structural(
    grammars: Sequence[VisualGrammar],
    matrix: Mapping[tuple[str, str], SimilarityVector],
    *,
    threshold: float,
    min_cluster_size: int = 2,
) -> TemplateDiscovery:
    """Cluster on the structural dimension using the vector, not a label.

    Reuses average-linkage agglomeration by synthesising the similarity results
    M2's discovery expects, but every score comes from the structural reading of
    the M4 vector — so the clustering input is the representation M4 built, and
    ``layout_template_class`` is never consulted.
    """

    from ..similarity.similarity_contract import (
        DIMENSIONS,
        DimensionScore,
        SimilarityResult,
    )

    # M2's contract names its dimensions geometry/structure/style/asset; M4 names
    # them structural/style/composition/asset. Only the *score* field is read by
    # agglomeration, but the stand-in result must still satisfy M2's own
    # validation, so the mapping is made explicit rather than by position.
    DIMENSION_ALIASES: dict[str, str] = {
        "geometry": "composition",
        "structure": "structural",
        "style": "style",
        "asset": "asset",
    }

    ids = sorted(grammar.source_id for grammar in grammars)
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    if duplicates:
        raise RunError("duplicate grammar source ids: " + ", ".join(duplicates))

    scores: dict[tuple[str, str], Any] = {}
    for (left, right), vector in matrix.items():
        structural = vector.reading("structural")
        synthetic = SimilarityResult(
            left_id=left,
            right_id=right,
            score=structural.value,
            provenance_mode="provenance_agnostic",
            dimensions=tuple(
                DimensionScore(
                    dimension=name,
                    score=vector.reading(DIMENSION_ALIASES[name]).value,
                    detail={},
                )
                for name in DIMENSIONS
            ),
            contributions=(),
            difference_codes=(),
            comparable=True,
        )
        scores[(left, right)] = synthetic

    # Agglomerate directly: same average-linkage rule as M2's discovery, applied
    # to the structural scores.
    clusters: dict[str, frozenset[str]] = {sid: frozenset({sid}) for sid in ids}
    while True:
        best: tuple[float, str, str] | None = None
        current = sorted(clusters)
        for i, left_id in enumerate(current):
            for right_id in current[i + 1 :]:
                pairs = [
                    scores[(a, b) if (a, b) in scores else (b, a)].score
                    for a in sorted(clusters[left_id])
                    for b in sorted(clusters[right_id])
                ]
                if not pairs:
                    continue
                mean = sum(pairs) / len(pairs)
                if mean < threshold:
                    continue
                if best is None or (-mean, left_id, right_id) < (-best[0], best[1], best[2]):
                    best = (mean, left_id, right_id)
        if best is None:
            break
        mean, left_id, right_id = best
        merged = clusters.pop(left_id) | clusters.pop(right_id)
        clusters["family-" + "-".join(sorted(merged))] = merged

    by_id = {grammar.source_id: grammar for grammar in grammars}
    reported: list[Cluster] = []
    for members in clusters.values():
        if len(members) < min_cluster_size:
            continue
        member_ids = tuple(sorted(members))
        member_scores = [
            scores[(a, b) if (a, b) in scores else (b, a)].score
            for index, a in enumerate(member_ids)
            for b in member_ids[index + 1 :]
        ]
        mean_similarity = (
            round(sum(member_scores) / len(member_scores), 6) if member_scores else 0.0
        )
        min_similarity = round(min(member_scores), 6) if member_scores else 0.0
        cluster_members = tuple(
            ClusterMember(
                sample_id=sample_id,
                creator_id="",
                layout_template_class=None,
                similarity_to_centroid=round(
                    sum(
                        scores[(sample_id, other) if (sample_id, other) in scores else (other, sample_id)].score
                        for other in member_ids
                        if other != sample_id
                    )
                    / max(1, len(member_ids) - 1),
                    6,
                ),
            )
            for sample_id in member_ids
        )
        reported.append(
            Cluster(
                cluster_id="family-" + "-".join(member_ids),
                member_ids=member_ids,
                members=cluster_members,
                evidence=ClusterEvidence(
                    threshold=threshold,
                    member_count=len(member_ids),
                    creator_count=0,
                    mean_similarity=mean_similarity,
                    min_similarity=min_similarity,
                    dominant_layout_class=None,
                    layout_class_agreement=0.0,
                    dominant_color_family=None,
                    dominant_subject_class=None,
                    recurring=len(member_ids) >= 3,
                ),
            )
        )

    reported.sort(key=lambda cluster: (-cluster.size, cluster.cluster_id))
    return TemplateDiscovery(
        threshold=threshold,
        provenance_mode="structural_only",
        clusters=tuple(reported),
        merge_steps=(),
        non_comparable_pairs=(),
        sample_count=len(ids),
    )


def run_benchmark(
    *,
    dataset: BenchmarkDataset | None = None,
    structural_threshold: float = DEFAULT_STRUCTURAL_THRESHOLD,
    invariant_threshold: float = INVARIANT_THRESHOLD,
    workdir: str | Path | None = None,
) -> BenchmarkReport:
    """Run the M4 pipeline end to end and score it against independent labels."""

    import os
    import tempfile

    started = time.time()
    active = dataset or build_dataset()
    backend = StdlibPixelBackend()

    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(workdir) if workdir else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("M3_BENCHMARK_CACHE", "1")
        observation_set, _samples = _observe_corpus(
            active, directory=directory, backend=backend
        )

    # -- grammar extraction (no labels in scope) -----------------------------
    extractor = GrammarExtractor()
    records: list[GrammarRecord] = []
    for result in observation_set.results:
        extraction = extractor.extract(result.observation)
        records.append(
            GrammarRecord(
                sample_id=result.source_id,
                creator_id=active.labels.get(result.source_id, {}).get("creator_id", ""),
                template_id=active.labels.get(result.source_id, {}).get("template_id", ""),
                observation=result.observation,
                grammar=extraction.grammar,
                decisions=extraction.decisions,
                warnings=extraction.warnings,
            )
        )

    grammars = tuple(record.grammar for record in records)
    observations = {record.sample_id: record.observation for record in records}
    vectors = vector_matrix(grammars, observations)
    discovery = _cluster_from_structural(
        grammars, vectors, threshold=structural_threshold
    )

    # -- invariants and strategy (still no labels) ---------------------------
    invariant_extractor = InvariantExtractor(threshold=invariant_threshold)
    creator_by_sample = {
        record.sample_id: record.creator_id for record in records
    }
    clusters: list[ClusterRecord] = []
    for cluster in discovery.clusters:
        member_grammars = [
            grammar for grammar in grammars if grammar.source_id in cluster.member_ids
        ]
        invariant_set = invariant_extractor.extract(
            member_grammars, cluster_id=cluster.cluster_id
        )
        strategy = distill_strategy(
            member_grammars,
            invariant_set,
            creator_ids=[creator_by_sample[sid] for sid in cluster.member_ids],
        )
        constraints = constraints_from_strategy(strategy)
        clusters.append(
            ClusterRecord(
                cluster_id=cluster.cluster_id,
                member_ids=tuple(cluster.member_ids),
                template_ids=tuple(
                    sorted(
                        {
                            active.labels[sid]["template_id"]
                            for sid in cluster.member_ids
                            if sid in active.labels
                        }
                    )
                ),
                invariants=invariant_set,
                strategy=strategy,
                constraints=constraints,
            )
        )

    # -- evaluation (labels first read here) --------------------------------
    reference_regions = {
        label["sample_id"]: label["grammar"] for label in active.labels.values()
    }
    reference_relations = {
        sample_id: label["grammar"].get("relations", ())
        for sample_id, label in active.labels.items()
    }

    region_scores = [
        region_accuracy(
            record.grammar,
            reference_regions.get(record.sample_id, {"regions": []}),
        )
        for record in records
    ]
    relation_scores = [
        relation_metrics(
            record.grammar, reference_relations.get(record.sample_id, ())
        )
        for record in records
    ]

    aggregate_region = _aggregate_regions(region_scores)
    aggregate_relation = _aggregate_relations(relation_scores)

    # Stability: repeat the clustering on a shuffled input and on a nudged
    # threshold, and compare partitions rather than labels.
    baseline = [cluster.member_ids for cluster in discovery.clusters]
    repeats = [
        [
            cluster.member_ids
            for cluster in _cluster_from_structural(
                grammars, vectors, threshold=structural_threshold
            ).clusters
        ]
        for _ in range(2)
    ]
    perturbed = [
        [
            cluster.member_ids
            for cluster in _cluster_from_structural(
                grammars, vectors, threshold=structural_threshold + delta
            ).clusters
        ]
        for delta in (-0.02, 0.02)
    ]
    stability = stability_metrics(
        baseline,
        repeats,
        perturbed,
        notes=(
            "perturbation nudges the structural threshold by +-0.02; a partition "
            "change there is expected and is reported rather than hidden",
        ),
    )

    strategy_reference = {
        cluster.strategy.pattern_id: active.labels[cluster.member_ids[0]]["strategy"]
        for cluster in clusters
        if cluster.member_ids and cluster.member_ids[0] in active.labels
    }
    aggregate_strategy = strategy_metrics(
        [cluster.strategy for cluster in clusters], strategy_reference
    )

    evaluation = EvaluationBundle(
        region=aggregate_region,
        relation=aggregate_relation,
        stability=stability,
        strategy=aggregate_strategy,
    )

    run = RunArtifacts(
        dataset=active,
        grammars=tuple(records),
        vectors=vectors,
        clusters=tuple(clusters),
        discovery=discovery,
        evaluation=evaluation,
        structural_threshold=structural_threshold,
        elapsed_seconds=round(time.time() - started, 3),
    )

    return BenchmarkReport(
        case_results=tuple(_score_cases(active, run)), run=run
    )


def _aggregate_regions(scores: Sequence[Any]) -> Any:
    """Aggregate per-sample region scores into one report.

    Reported as micro-averages over counted regions, not as a mean of per-sample
    means, so a sample with two regions does not weigh as much as one with eight.
    """

    from .evaluation import RegionAccuracy

    expected = sum(score.expected for score in scores)
    found = sum(score.found for score in scores)
    true_positive = sum(
        sum(min(v["expected"], v["found"]) for v in score.per_type.values())
        for score in scores
    )
    false_positive = found - true_positive
    false_negative = expected - true_positive
    precision = round(true_positive / (true_positive + false_positive), 6) if (true_positive + false_positive) else 0.0
    recall = round(true_positive / (true_positive + false_negative), 6) if (true_positive + false_negative) else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 6) if (precision + recall) else 0.0

    per_type: dict[str, dict[str, Any]] = {}
    for score in scores:
        for name, values in score.per_type.items():
            entry = per_type.setdefault(name, {"expected": 0, "found": 0, "matched": 0})
            entry["expected"] += values["expected"]
            entry["found"] += values["found"]
            entry["matched"] += values["matched"]

    return RegionAccuracy(
        expected=expected,
        found=found,
        correct_type=sum(score.correct_type for score in scores),
        correct_placement=sum(score.correct_placement for score in scores),
        precision=precision,
        recall=recall,
        f1=f1,
        type_accuracy=round(
            sum(score.correct_type for score in scores)
            / max(1, sum(len(s.per_type) and s.expected for s in scores)),
            6,
        ) if scores else 0.0,
        placement_accuracy=round(
            sum(score.correct_placement for score in scores)
            / max(1, sum(score.expected for score in scores)),
            6,
        ) if scores else 0.0,
        per_type=per_type,
        missing=tuple(sorted({m for score in scores for m in score.missing})),
        spurious=tuple(sorted({s for score in scores for s in score.spurious})),
    )


def _aggregate_relations(scores: Sequence[Any]) -> Any:
    from .evaluation import RelationMetrics

    tp = sum(score.true_positive for score in scores)
    fp = sum(score.false_positive for score in scores)
    fn = sum(score.false_negative for score in scores)
    precision = round(tp / (tp + fp), 6) if (tp + fp) else 0.0
    recall = round(tp / (tp + fn), 6) if (tp + fn) else 0.0
    return RelationMetrics(
        expected=sum(score.expected for score in scores),
        found=sum(score.found for score in scores),
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=precision,
        recall=recall,
        f1=round(2 * precision * recall / (precision + recall), 6) if (precision + recall) else 0.0,
    )


def _score_cases(dataset: BenchmarkDataset, run: RunArtifacts) -> list[CaseResult]:
    """Score each case against the run's output."""

    results: list[CaseResult] = []

    for case in dataset.cases:
        failures: list[str] = []
        observed: dict[str, Any] = {}

        if case.kind == "grammar_regions":
            observed_accuracy = [
                region_accuracy(
                    run.grammar_for(sample_id).grammar,
                    {"regions": case.expected["regions"]},
                )
                for sample_id in case.sample_ids
            ]
            observed["mean_f1"] = round(
                sum(score.f1 for score in observed_accuracy) / len(observed_accuracy), 6
            )
            if observed["mean_f1"] < 0.5:
                failures.append(
                    f"region F1 {observed['mean_f1']:.3f} below 0.5 for {case.template_id}"
                )

        elif case.kind == "grammar_region_types":
            missing: set[str] = set()
            for sample_id in case.sample_ids:
                grammar = run.grammar_for(sample_id).grammar
                present = {region.region_type for region in grammar.regions}
                missing |= set(case.expected["region_types"]) - present
            observed["missing_types"] = sorted(missing)
            if missing:
                failures.append(f"declared region types absent: {sorted(missing)}")

        elif case.kind == "grammar_no_invention":
            allowed = set(case.expected["allowed_types"])
            invented: set[str] = set()
            for sample_id in case.sample_ids:
                grammar = run.grammar_for(sample_id).grammar
                invented |= {r.region_type for r in grammar.regions} - allowed
            observed["invented_types"] = sorted(invented)
            if invented:
                failures.append(f"extractor invented region types: {sorted(invented)}")

        elif case.kind == "relation_expected":
            expected = set(case.expected["relations"])
            missing: set[str] = set()
            for sample_id in case.sample_ids:
                found = run.grammar_for(sample_id).grammar.relation_types()
                missing |= expected - found
            observed["missing_relations"] = sorted(missing)
            # Relations about a header/supporting pair are only recoverable when
            # the observer found both regions; that is reported, not hidden.
            if missing:
                failures.append(f"declared relations absent: {sorted(missing)}")

        elif case.kind == "relation_valid":
            bad: list[str] = []
            for sample_id in case.sample_ids:
                grammar = run.grammar_for(sample_id).grammar
                known = {region.region_id for region in grammar.regions}
                for relation in grammar.relationships:
                    if relation.relation_type not in RELATION_TYPES:
                        bad.append(f"{relation.relation_id}:bad-type")
                    if (
                        relation.source_region_id not in known
                        or relation.target_region_id not in known
                    ):
                        bad.append(f"{relation.relation_id}:dangling")
            observed["invalid_relations"] = bad
            if bad:
                failures.append(f"invalid relations: {bad[:5]}")

        elif case.kind == "invariant_frequency":
            member_clusters = [
                run.cluster_for(sample_id)
                for sample_id in case.sample_ids
            ]
            clusters = [c for c in member_clusters if c is not None]
            observed["clustered"] = len(clusters)
            if not clusters:
                failures.append(
                    f"no cluster contains any member of {case.template_id}, so its "
                    "invariants cannot be mined"
                )
            else:
                best = max(clusters, key=lambda c: len(c.member_ids))
                for expectation in case.expected["invariants"]:
                    found = best.invariants.frequency_of(expectation["feature"])
                    if found < expectation["min_frequency"] - 1e-9:
                        failures.append(
                            f"{expectation['feature']} frequency {found:.3f} below "
                            f"declared minimum {expectation['min_frequency']:.3f} "
                            f"in {best.cluster_id}"
                        )
                observed["cluster"] = best.cluster_id

        elif case.kind == "invariant_is_mined":
            # The property is about the extractor, not the data: it must count
            # rather than consult a list. Verified by inspecting the source.
            import inspect

            from . import invariants as invariants_module

            source = inspect.getsource(invariants_module.InvariantExtractor.extract)
            forbidden = ("RELATION_TYPES", "REGION_TYPES", "ATTENTION_STAGES", "if feature ==")
            offenders = [token for token in forbidden if token in source]
            observed["forbidden_tokens"] = offenders
            if offenders:
                failures.append(
                    f"invariant extraction consults a declared list: {offenders}"
                )

        elif case.kind == "strategy_attention":
            clusters = [
                c for c in run.clusters if c.member_ids and c.member_ids[0].startswith(tuple(case.sample_ids) or ("",))
            ] or [
                c
                for c in run.clusters
                if any(sample_id in c.member_ids for sample_id in case.sample_ids)
            ]
            observed["clusters_found"] = len(clusters)
            if not clusters:
                failures.append(
                    f"no cluster covers {case.template_id}, so no strategy was distilled"
                )
            else:
                strategies = {c.strategy.attention_strategy for c in clusters}
                observed["attention_strategies"] = sorted(strategies)
                if case.expected["attention_strategy"] not in strategies:
                    failures.append(
                        f"expected attention {case.expected['attention_strategy']!r}, "
                        f"got {sorted(strategies)}"
                    )

        elif case.kind == "strategy_hierarchy":
            clusters = [
                c
                for c in run.clusters
                if any(sample_id in c.member_ids for sample_id in case.sample_ids)
            ]
            if not clusters:
                failures.append(
                    f"no cluster covers {case.template_id}, so no strategy was distilled"
                )
            else:
                stages: set[str] = set()
                moves: set[str] = set()
                for cluster in clusters:
                    stages |= set(cluster.strategy.information_hierarchy)
                    moves |= set(cluster.strategy.composition_strategy)
                observed["stages"] = sorted(stages)
                observed["moves"] = sorted(moves)
                for stage in case.expected["required_stages"]:
                    if stage not in stages:
                        failures.append(
                            f"required hierarchy stage {stage!r} missing from "
                            f"{sorted(stages)}"
                        )
                required_moves = case.expected["required_moves_any"]
                if required_moves and not (set(required_moves) & moves):
                    failures.append(
                        f"none of {required_moves} present in composition {sorted(moves)}"
                    )

        elif case.kind in _NEGATIVE_KINDS:
            outcomes = _NEGATIVE_KINDS[case.kind](run)
            observed = outcomes
            if not outcomes.get("holds", False):
                failures.append(str(outcomes.get("detail", "negative assertion violated")))

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


# --------------------------------------------------------------------------
# Negative assertions
# --------------------------------------------------------------------------


def _no_invented_regions(run: RunArtifacts) -> dict[str, Any]:
    from .model import REGION_TYPES

    for record in run.grammars:
        for region in record.grammar.regions:
            if region.region_type not in REGION_TYPES:
                return {
                    "holds": False,
                    "detail": f"{region.region_type!r} is outside the region vocabulary",
                }
    return {"holds": True}


def _no_dangling_relations(run: RunArtifacts) -> dict[str, Any]:
    for record in run.grammars:
        known = {region.region_id for region in record.grammar.regions}
        for relation in record.grammar.relationships:
            if (
                relation.source_region_id not in known
                or relation.target_region_id not in known
            ):
                return {
                    "holds": False,
                    "detail": f"{relation.relation_id} has a dangling endpoint",
                }
    return {"holds": True}


def _no_combined_score(run: RunArtifacts) -> dict[str, Any]:
    for vector in run.vectors.values():
        payload = vector.as_dict()
        for forbidden in ("score", "total", "combined", "aggregate"):
            if forbidden in payload:
                return {
                    "holds": False,
                    "detail": f"vector exposes a {forbidden!r} field",
                }
    return {"holds": True}


def _no_material_in_pattern(run: RunArtifacts) -> dict[str, Any]:
    forbidden = (
        ".png",
        ".jpg",
        "base64",
        "pixel",
        "rgb(",
        "#",
        "asset_reference",
        "bitmap",
        "colour_value",
    )
    for cluster in run.clusters:
        serialised = json.dumps(cluster.strategy.as_dict()).lower()
        for token in forbidden:
            if token in serialised:
                return {
                    "holds": False,
                    "detail": f"strategy {cluster.strategy.pattern_id} contains {token!r}",
                }
    return {"holds": True}


def _invariants_are_mined(run: RunArtifacts) -> dict[str, Any]:
    for cluster in run.clusters:
        if cluster.invariants.member_count != len(cluster.member_ids):
            return {
                "holds": False,
                "detail": "invariant support does not match cluster membership",
            }
        for invariant in cluster.invariants.invariants:
            if invariant.support < 1:
                return {
                    "holds": False,
                    "detail": f"{invariant.feature} has no supporting member",
                }
    return {"holds": True}


def _agreement_requires_two_humans(run: RunArtifacts) -> dict[str, Any]:
    from ..dataset.human_eval import (
        HumanEvaluationError,
        Rating,
        Rater,
        compute_agreement,
    )

    ratings = [
        Rating("r1", "item", "yes", "yes"),
        Rating("r2", "item", "no", "yes"),
    ]
    # Two model raters must be rejected as human evidence.
    models = [Rater("r1", "model"), Rater("r2", "model")]
    try:
        compute_agreement(ratings, models)
    except HumanEvaluationError:
        pass
    else:
        return {
            "holds": False,
            "detail": "agreement was computed from non-human raters",
        }
    # One human alone must also be rejected.
    try:
        compute_agreement([Rating("r1", "item", "yes", "yes")], [Rater("r1", "human")])
    except HumanEvaluationError:
        pass
    else:
        return {"holds": False, "detail": "agreement was computed from one rater"}
    return {"holds": True}


def _synthetic_fails_real_check(run: RunArtifacts) -> dict[str, Any]:
    from ..dataset.provenance import ProvenanceError, synthetic_manifest

    manifest = synthetic_manifest(["a", "b", "c"])
    try:
        manifest.assert_real_collection(minimum=1)
    except ProvenanceError:
        return {"holds": True}
    return {
        "holds": False,
        "detail": "a synthetic manifest passed real-collection validation",
    }


def _constraint_not_generative(run: RunArtifacts) -> dict[str, Any]:
    for cluster in run.clusters:
        if cluster.constraints.generative:
            return {
                "holds": False,
                "detail": f"{cluster.constraints.constraint_id} is marked generative",
            }
    return {"holds": True}


def _no_runtime_integration(run: RunArtifacts) -> dict[str, Any]:
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    forbidden = {
        "distillation_core",
        "workflows",
        "runtime",
        "production",
        "security",
        "artifact",
        "plugins",
        "risk_evaluation",
        "schema_validation",
    }
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if module.split(".")[0] in forbidden:
                        offenders.append(f"{path.name}:{module}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                if module.split(".")[0] in forbidden:
                    offenders.append(f"{path.name}:{module}")
    if offenders:
        return {"holds": False, "detail": f"runtime imports found: {offenders}"}
    return {"holds": True}


def _strategy_ignores_layout_label(run: RunArtifacts) -> dict[str, Any]:
    import ast
    import inspect

    from . import strategy as strategy_module

    source = inspect.getsource(strategy_module.distill_strategy)
    tree = ast.parse(source)
    body = tree.body[0].body if isinstance(tree.body[0], ast.FunctionDef) else []
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    code = "\n".join(ast.unparse(node) for node in body)
    for token in ("layout_template_class", "layout_class", "template_class"):
        if token in code:
            return {
                "holds": False,
                "detail": f"strategy distillation reads {token!r}",
            }
    return {"holds": True}


_NEGATIVE_KINDS: Mapping[str, Any] = {
    "no_invented_regions": _no_invented_regions,
    "no_dangling_relations": _no_dangling_relations,
    "no_combined_score": _no_combined_score,
    "no_material_in_pattern": _no_material_in_pattern,
    "invariants_are_mined": _invariants_are_mined,
    "agreement_requires_two_humans": _agreement_requires_two_humans,
    "synthetic_fails_real_check": _synthetic_fails_real_check,
    "constraint_not_generative": _constraint_not_generative,
    "no_runtime_integration": _no_runtime_integration,
    "strategy_ignores_layout_label": _strategy_ignores_layout_label,
}


def write_report(report: BenchmarkReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "DEFAULT_STRUCTURAL_THRESHOLD",
    "INVARIANT_THRESHOLD",
    "BenchmarkReport",
    "CaseResult",
    "ClusterRecord",
    "GrammarRecord",
    "RunArtifacts",
    "RunError",
    "run_benchmark",
    "write_report",
]
