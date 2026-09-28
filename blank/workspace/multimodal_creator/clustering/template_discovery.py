"""Deterministic agglomerative template discovery.

Algorithm
---------

Average-linkage agglomerative clustering over the similarity matrix:

* start with every sample in its own cluster;
* find the pair of clusters with the highest average inter-cluster similarity
  (``average`` linkage, not ``single``: a single lucky pair should not chain two
  otherwise-unrelated groups together);
* merge them when that similarity is at or above the threshold;
* stop when no pair reaches the threshold.

Average linkage is chosen specifically because single linkage produces chaining:
with single linkage, A~B and B~C merges A and C even when A and C are nothing
alike, which would manufacture templates out of a chain of coincidences. Average
linkage requires the groups as a whole to agree.

Every merge is recorded as a :class:`MergeStep` with the similarity that
justified it, so the final clusters can be replayed and audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..extraction.visual_sample import VisualSample
from ..similarity.similarity_contract import (
    PROVENANCE_MODES,
    STRUCTURAL_RECURRENCE_MIN,
    SimilarityContractError,
    SimilarityResult,
    pairwise_similarity,
)

#: Default similarity threshold for merging two clusters.
#:
#: Chosen from the M2 synthetic benchmark, which is what a threshold is for: the
#: same-template population scores >= 0.976 under geometry jitter and the
#: different-layout population scores <= 0.83, so 0.90 sits in a wide empty band
#: between them. The value is exposed and overridable rather than buried, and it
#: is not a universal constant — it is calibrated to this prototype's samples.
DEFAULT_SIMILARITY_THRESHOLD = 0.90

#: A cluster smaller than this is a pair, not a recurring template.
MIN_CLUSTER_SIZE = 2

#: Minimum members before a cluster may be described as *structurally recurring*
#: rather than merely *grouped*. Uses the M1/M2 shared constant.
RECURRENCE_MIN = STRUCTURAL_RECURRENCE_MIN


class TemplateClusterError(SimilarityContractError):
    """Raised when discovery is asked for something undefined."""


@dataclass(frozen=True, slots=True)
class ClusterMember:
    """One sample inside a cluster, with its creator provenance."""

    sample_id: str
    creator_id: str
    layout_template_class: str | None
    similarity_to_centroid: float


@dataclass(frozen=True, slots=True)
class MergeStep:
    """One merge, recorded so the clustering can be replayed."""

    step: int
    left_cluster_id: str
    right_cluster_id: str
    merged_cluster_id: str
    average_similarity: float
    justifying_pairs: tuple[tuple[str, str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ClusterEvidence:
    """The structural grounds on which a cluster was formed."""

    threshold: float
    member_count: int
    creator_count: int
    mean_similarity: float
    min_similarity: float
    dominant_layout_class: str | None
    layout_class_agreement: float
    dominant_color_family: str | None
    dominant_subject_class: str | None
    recurring: bool
    merge_steps: tuple[MergeStep, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "member_count": self.member_count,
            "creator_count": self.creator_count,
            "mean_similarity": self.mean_similarity,
            "min_similarity": self.min_similarity,
            "dominant_layout_class": self.dominant_layout_class,
            "layout_class_agreement": self.layout_class_agreement,
            "dominant_color_family": self.dominant_color_family,
            "dominant_subject_class": self.dominant_subject_class,
            "recurring": self.recurring,
            "merge_steps": [
                {
                    "step": step.step,
                    "left": step.left_cluster_id,
                    "right": step.right_cluster_id,
                    "merged": step.merged_cluster_id,
                    "average_similarity": step.average_similarity,
                    "justifying_pairs": [list(pair) for pair in step.justifying_pairs],
                }
                for step in self.merge_steps
            ],
        }


@dataclass(frozen=True, slots=True)
class Cluster:
    """A discovered visual family."""

    cluster_id: str
    member_ids: tuple[str, ...]
    members: tuple[ClusterMember, ...]
    evidence: ClusterEvidence

    @property
    def size(self) -> int:
        return len(self.member_ids)

    def is_template(self) -> bool:
        """True when the cluster is large enough to be called a recurring family."""

        return self.evidence.recurring

    def as_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "member_ids": list(self.member_ids),
            "members": [
                {
                    "sample_id": member.sample_id,
                    "creator_id": member.creator_id,
                    "layout_template_class": member.layout_template_class,
                    "similarity_to_centroid": member.similarity_to_centroid,
                }
                for member in self.members
            ],
            "evidence": self.evidence.as_dict(),
        }

    def summarise(self) -> str:
        evidence = self.evidence
        return (
            f"{self.cluster_id}: {self.size} members "
            f"({evidence.creator_count} creators), "
            f"layout={evidence.dominant_layout_class!r}, "
            f"mean={evidence.mean_similarity:.3f}, min={evidence.min_similarity:.3f}, "
            f"recurring={evidence.recurring}"
        )


@dataclass(frozen=True, slots=True)
class TemplateDiscovery:
    """The full discovery result."""

    threshold: float
    provenance_mode: str
    clusters: tuple[Cluster, ...]
    merge_steps: tuple[MergeStep, ...]
    non_comparable_pairs: tuple[tuple[str, str], ...] = ()
    sample_count: int = 0

    def templates(self) -> tuple[Cluster, ...]:
        """Only the clusters large enough to be called recurring templates."""

        return tuple(cluster for cluster in self.clusters if cluster.is_template())

    def cluster_for(self, sample_id: str) -> Cluster:
        for cluster in self.clusters:
            if sample_id in cluster.member_ids:
                return cluster
        raise TemplateClusterError(f"sample {sample_id!r} is not in any cluster")

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "provenance_mode": self.provenance_mode,
            "sample_count": self.sample_count,
            "cluster_count": len(self.clusters),
            "template_count": len(self.templates()),
            "non_comparable_pairs": [list(pair) for pair in self.non_comparable_pairs],
            "clusters": [cluster.as_dict() for cluster in self.clusters],
        }

    def summarise(self) -> str:
        lines = [
            f"template discovery: {self.sample_count} samples, "
            f"threshold={self.threshold}, mode={self.provenance_mode}",
        ]
        for cluster in self.clusters:
            lines.append("  " + cluster.summarise())
        return "\n".join(lines)


def dominant_layout_class(samples: Sequence[VisualSample]) -> tuple[str | None, float]:
    """Most common declared layout class, and the fraction of members sharing it.

    Ties are broken lexicographically so the answer never depends on input order.
    """

    declared = [
        sample.layout_template_class
        for sample in samples
        if sample.layout_template_class is not None
    ]
    if not declared:
        return None, 0.0
    counts: dict[str, int] = {}
    for value in declared:
        counts[value] = counts.get(value, 0) + 1
    best = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return best, round(counts[best] / len(samples), 6)


def _dominant_value(values: Iterable[str | None]) -> str | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    counts: dict[str, int] = {}
    for value in present:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _cluster_id_for(member_ids: Sequence[str]) -> str:
    """A stable identifier derived from membership, not from discovery order.

    Two runs over the same members therefore produce the same id, and relabelling
    is impossible: the id cannot drift while the members stay the same.
    """

    return "family-" + "-".join(sorted(member_ids))


def _average_linkage(
    left: frozenset[str],
    right: frozenset[str],
    similarities: Mapping[tuple[str, str], SimilarityResult],
) -> tuple[float, tuple[tuple[str, str, float], ...]]:
    """Mean similarity across every cross-cluster pair, with the pairs recorded."""

    pairs: list[tuple[str, str, float]] = []
    for a in sorted(left):
        for b in sorted(right):
            key = (a, b) if (a, b) in similarities else (b, a)
            result = similarities[key]
            pairs.append((a, b, result.score))
    if not pairs:
        return 0.0, ()
    mean = sum(score for _a, _b, score in pairs) / len(pairs)
    return round(mean, 6), tuple(pairs)


def _mean_similarity_to_others(
    sample_id: str,
    member_ids: Sequence[str],
    similarities: Mapping[tuple[str, str], SimilarityResult],
) -> float:
    """Mean similarity from one member to the rest of its cluster.

    Reported as ``similarity_to_centroid``, but computed as mean pairwise
    similarity to the other members: there is no vector centroid here, because
    this is not an embedding space. The report calls this out explicitly rather
    than implying a geometric centre that does not exist.
    """

    others = [other for other in member_ids if other != sample_id]
    if not others:
        return 1.0
    scores: list[float] = []
    for other in others:
        key = (sample_id, other) if (sample_id, other) in similarities else (other, sample_id)
        scores.append(similarities[key].score)
    return round(sum(scores) / len(scores), 6)


def discover_templates(
    samples: Sequence[VisualSample],
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    provenance_mode: str = "provenance_agnostic",
    min_cluster_size: int = MIN_CLUSTER_SIZE,
) -> TemplateDiscovery:
    """Discover visual families without ever being told the answer.

    ``provenance_mode="cross_provenance"`` is the mode that makes a discovered
    family meaningful: pairs from the same creator are marked non-comparable, so
    a cluster can only form from agreement *between* creators.
    """

    if provenance_mode not in PROVENANCE_MODES:
        raise TemplateClusterError(
            f"unknown provenance_mode {provenance_mode!r}; expected one of "
            f"{list(PROVENANCE_MODES)!r}"
        )
    if not 0.0 <= threshold <= 1.0:
        raise TemplateClusterError(f"threshold must be within 0..1, got {threshold!r}")
    if min_cluster_size < 1:
        raise TemplateClusterError("min_cluster_size must be at least 1")

    ordered = sorted(samples, key=lambda sample: sample.sample_id)
    if not ordered:
        raise TemplateClusterError("at least one sample is required")
    ids = [sample.sample_id for sample in ordered]
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    if duplicates:
        raise TemplateClusterError("duplicate sample ids: " + ", ".join(duplicates))
    by_id = {sample.sample_id: sample for sample in ordered}

    # Pairwise similarities, computed once, keyed in sorted order.
    similarities: dict[tuple[str, str], SimilarityResult] = {}
    non_comparable: list[tuple[str, str]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            key = (left.sample_id, right.sample_id)
            result = pairwise_similarity(left, right, provenance_mode=provenance_mode)
            similarities[key] = result
            if not result.comparable:
                non_comparable.append(key)

    # Agglomerate.
    clusters: dict[str, frozenset[str]] = {sid: frozenset({sid}) for sid in ids}
    merge_steps: list[MergeStep] = []
    step_index = 0

    while True:
        best: tuple[float, str, str, tuple[tuple[str, str, float], ...]] | None = None
        current_ids = sorted(clusters)
        for i, left_id in enumerate(current_ids):
            for right_id in current_ids[i + 1 :]:
                mean, pairs = _average_linkage(
                    clusters[left_id], clusters[right_id], similarities
                )
                if mean < threshold:
                    continue
                # Deterministic tie-break on the cluster identifiers.
                candidate = (mean, left_id, right_id, pairs)
                if best is None or (-mean, left_id, right_id) < (
                    -best[0],
                    best[1],
                    best[2],
                ):
                    best = candidate
        if best is None:
            break

        mean, left_id, right_id, pairs = best
        merged_members = clusters[left_id] | clusters[right_id]
        merged_id = _cluster_id_for(sorted(merged_members))
        step_index += 1
        merge_steps.append(
            MergeStep(
                step=step_index,
                left_cluster_id=left_id,
                right_cluster_id=right_id,
                merged_cluster_id=merged_id,
                average_similarity=mean,
                justifying_pairs=pairs,
            )
        )
        del clusters[left_id]
        del clusters[right_id]
        clusters[merged_id] = merged_members

    # Build reported clusters, largest first with deterministic tie-breaks.
    reported: list[Cluster] = []
    for members in clusters.values():
        if len(members) < min_cluster_size:
            continue
        member_ids = tuple(sorted(members))
        member_samples = [by_id[sid] for sid in member_ids]

        member_scores: list[float] = []
        for left_index, left in enumerate(member_ids):
            for right in member_ids[left_index + 1 :]:
                key = (left, right) if (left, right) in similarities else (right, left)
                member_scores.append(similarities[key].score)
        mean_similarity = (
            round(sum(member_scores) / len(member_scores), 6) if member_scores else 0.0
        )
        min_similarity = round(min(member_scores), 6) if member_scores else 0.0

        layout, agreement = dominant_layout_class(member_samples)
        creators = {sample.provenance.creator_id for sample in member_samples}
        members = tuple(
            ClusterMember(
                sample_id=sample.sample_id,
                creator_id=sample.provenance.creator_id,
                layout_template_class=sample.layout_template_class,
                similarity_to_centroid=_mean_similarity_to_others(
                    sample.sample_id, member_ids, similarities
                ),
            )
            for sample in member_samples
        )
        evidence = ClusterEvidence(
            threshold=threshold,
            member_count=len(member_ids),
            creator_count=len(creators),
            mean_similarity=mean_similarity,
            min_similarity=min_similarity,
            dominant_layout_class=layout,
            layout_class_agreement=agreement,
            dominant_color_family=_dominant_value(
                sample.color_family for sample in member_samples
            ),
            dominant_subject_class=_dominant_value(
                sample.subject.subject_class for sample in member_samples
            ),
            recurring=len(member_ids) >= RECURRENCE_MIN,
            merge_steps=tuple(
                step
                for step in merge_steps
                if step.merged_cluster_id == _cluster_id_for(member_ids)
                or set(_ids_of(step)) <= set(member_ids)
            ),
        )
        reported.append(
            Cluster(
                cluster_id=_cluster_id_for(member_ids),
                member_ids=member_ids,
                members=members,
                evidence=evidence,
            )
        )

    reported.sort(key=lambda cluster: (-cluster.size, cluster.cluster_id))
    return TemplateDiscovery(
        threshold=threshold,
        provenance_mode=provenance_mode,
        clusters=tuple(reported),
        merge_steps=tuple(merge_steps),
        non_comparable_pairs=tuple(non_comparable),
        sample_count=len(ordered),
    )


def _ids_of(step: MergeStep) -> tuple[str, ...]:
    """Member ids implied by a merge step's cluster identifiers."""

    ids: set[str] = set()
    for label in (step.left_cluster_id, step.right_cluster_id):
        ids.update(label.split("-")[1:] if label.startswith("family-") else [label])
    return tuple(sorted(ids))


def self_score(
    sample_id: str,
    member_ids: Sequence[str],
    similarities: Mapping[tuple[str, str], SimilarityResult],
) -> float:
    """Deprecated alias for the internal mean-similarity helper."""

    return _mean_similarity_to_others(sample_id, member_ids, similarities)


__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD",
    "MIN_CLUSTER_SIZE",
    "RECURRENCE_MIN",
    "Cluster",
    "ClusterEvidence",
    "ClusterMember",
    "MergeStep",
    "TemplateClusterError",
    "TemplateDiscovery",
    "discover_templates",
    "dominant_layout_class",
]
