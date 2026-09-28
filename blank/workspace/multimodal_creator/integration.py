"""Observation → Pattern → Artifact integration (Phase M2, task 4).

This module closes the loop: declared samples become M1 observations
(:mod:`multimodal_creator.extraction`), observations are grouped into visual
families by the similarity and clustering contracts, and the families plus
observations are merged into one **M1-valid multimodal artifact**.

It is the end-to-end proof the phase asks for — *"visual information can enter
the current Creator artifact pipeline"* — and it holds three boundaries while
doing it:

**Universal / plugin.** Every structural record is emitted with
``layer="universal"`` and ``origin="common"``. A Creator plugin's contribution
is confined to ``creator_extension`` and must state that it does not redefine
the universal vocabulary.

**Anti-OCR.** Nothing here reads text. Cross-modal relations come from region
geometry, so every cross-modal record carries structural evidence by
construction.

**Additive.** The base artifact's text core is never rewritten. Integration adds
the four multimodal families and re-runs the M1 compatibility projection, so the
result is still a legal text-only artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .builder import (
    build_multimodal_artifact,
    merge_creator_extension,
    merge_multimodal_artifact,
    project_text_core,
)
from .clustering.template_discovery import (
    DEFAULT_SIMILARITY_THRESHOLD,
    TemplateDiscovery,
    discover_templates,
)
from .extraction.cross_modal_candidates import candidates_from_sample
from .extraction.observation_producer import ObservationProducer
from .extraction.visual_sample import VisualSample
from .roles import SourceStructure, structure_from_metadata
from .validation import DEFAULT_SCHEMA_PATH, validate_multimodal_artifact

#: Phase M2 artifact contract version, distinct from the M1 contract version.
INTEGRATION_VERSION = "m2.0.0"

#: Default text signal a cross-modal relation is anchored to. ``knowledge_unit``
#: is used when the base artifact carries no topic candidates, because a
#: cross-modal record must always name a real text signal.
_DEFAULT_TEXT_SIGNAL = "knowledge_unit"


@dataclass(frozen=True, slots=True)
class ArtifactIntegration:
    """The integrated result, with every intermediate kept for inspection.

    ``discovery`` is held here rather than inside the artifact on purpose. The
    M1 schema declares ``additionalProperties: false`` and the brief forbids
    editing it, so a discovery sidecar inside the artifact would either violate
    the contract or force a schema edit. Keeping it beside the artifact preserves
    both, and keeps the artifact a pure M1 document.
    """

    artifact: dict[str, Any]
    discovery: TemplateDiscovery
    observations_count: int
    cross_modal_records: int
    text_core_projection: dict[str, Any]
    plugin: str | None = None

    def family_summary(self) -> dict[str, int]:
        return {
            "visual_patterns": len(self.artifact.get("visual_patterns", ())),
            "layout_patterns": len(self.artifact.get("layout_patterns", ())),
            "asset_patterns": len(self.artifact.get("asset_patterns", ())),
            "cross_modal_patterns": len(self.artifact.get("cross_modal_patterns", ())),
        }

    def as_dict(self) -> dict[str, Any]:
        """Full machine-readable result: artifact plus discovery evidence."""

        return {
            "contract_version": INTEGRATION_VERSION,
            "artifact": self.artifact,
            "discovery": self.discovery.as_dict(),
            "observations_count": self.observations_count,
            "cross_modal_records": self.cross_modal_records,
            "text_core_projection": self.text_core_projection,
            "plugin": self.plugin,
        }

    def summarise(self) -> str:
        counts = self.family_summary()
        lines = [
            f"multimodal artifact integration ({INTEGRATION_VERSION})",
            f"  observations: {self.observations_count}",
            f"  discovered clusters: {len(self.discovery.clusters)} "
            f"(recurring: {len(self.discovery.templates())})",
            "  families: " + ", ".join(f"{name}={count}" for name, count in counts.items()),
            f"  text core preserved: {sorted(self.text_core_projection)}",
        ]
        return "\n".join(lines)


def _text_signal_for(base_artifact: Mapping[str, Any]) -> tuple[str, str]:
    """Choose the text signal and role a cross-modal link should anchor to.

    Preference order matches how strongly the text core already commits to a
    framing: an explicit topic candidate first, then a content template, then a
    knowledge unit. The choice is structural (which field is populated), never
    semantic (what the text says).
    """

    if base_artifact.get("topic_candidate"):
        return "topic_candidate", "title"
    if base_artifact.get("content_template"):
        return "content_template", "body"
    return _DEFAULT_TEXT_SIGNAL, "body"


def _member_anchor_ids(
    clusters: Sequence[Any],
    per_member: Mapping[str, list[tuple[str, str]]],
) -> tuple[list[tuple[str, str]], list[list[tuple[str, str]]]]:
    """Build cluster-level and member-level anchor id lists.

    ``per_member`` maps a sample id to its ``(family, pattern_id)`` pairs. A
    cluster's anchor list is the deduplicated union of its members' anchors, so
    the cluster record points at the structures that produced it.
    """

    cluster_anchors: list[tuple[str, str]] = []
    member_anchors: list[list[tuple[str, str]]] = []
    for cluster in clusters:
        seen: dict[tuple[str, str], None] = {}
        members: list[list[tuple[str, str]]] = []
        for member_id in cluster.member_ids:
            anchors = per_member.get(member_id, [])
            members.append(anchors)
            for anchor in anchors:
                seen.setdefault(anchor, None)
        cluster_anchors.append(list(seen))
        member_anchors.append(members)
    return cluster_anchors, member_anchors


def integrate_samples(
    base_artifact: Mapping[str, Any],
    samples: Sequence[VisualSample],
    *,
    producer: ObservationProducer | None = None,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    provenance_mode: str = "cross_provenance",
    plugin: str | None = None,
    domain_vocabulary: Mapping[str, Sequence[str]] | None = None,
    pattern_bindings: Sequence[Mapping[str, Any]] = (),
) -> ArtifactIntegration:
    """Run extraction, discovery, and artifact integration over declared samples.

    ``provenance_mode`` defaults to ``cross_provenance`` so a discovered family
    must be agreed between creators. Passing ``provenance_agnostic`` widens the
    comparison but weakens what a family means, which the report should say.
    """

    if not samples:
        raise ValueError("at least one sample is required")

    active_producer = producer or ObservationProducer(mode="mock_extracted")
    batch = active_producer.produce(samples)
    discovery = discover_templates(
        samples, threshold=threshold, provenance_mode=provenance_mode
    )

    # -- Source structures: multi-role, one entry per sample -----------------
    structures = [
        structure_from_metadata(
            observation.source_id,
            "image" if observation.medium == "image" else "video",
            {
                "modalities": (
                    ("visual", "textual")
                    if any(
                        region.get("role")
                        in {"title", "subtitle", "body", "caption", "label", "annotation"}
                        for region in observation.regions
                    )
                    else ("visual",)
                )
                + (("temporal",) if observation.medium == "video" else ()),
                "multimodal_roles": list(observation.roles),
                # Text in an image or video frame only ever arrives by
                # transcription, so the flag is set explicitly rather than
                # defaulted, keeping the anti-OCR provenance visible.
                "text_is_transcribed": True,
            },
        )
        for observation in batch.observations
    ]

    # -- Cross-modal: geometry-derived, never text-derived -------------------
    text_signal, text_role = _text_signal_for(base_artifact)
    by_id = {sample.sample_id: sample for sample in samples}
    cross_modal_entries: list[dict[str, Any]] = []
    for observation in batch.observations:
        for candidate in candidates_from_sample(by_id[observation.source_id]):
            cross_modal_entries.append(
                {
                    "text_signal": text_signal,
                    "text_role": candidate.text_role or text_role,
                    "relation": candidate.relation,
                    "visual_family": "layout_patterns",
                    "visual_pattern_id": observation.source_id,
                    "visual_evidence": ["region_layout", "region_geometry"],
                    "source_ids": [candidate.source_id],
                    "builder": (
                        "hook_visual_alignment"
                        if candidate.text_role == "hook"
                        else "text_visual_alignment"
                    ),
                    "confidence": candidate.confidence,
                }
            )

    artifact = build_multimodal_artifact(
        base_artifact,
        structures=structures,
        observations=batch.observations,
        cross_modal=cross_modal_entries,
        visual_capability="observed" if batch.observations else "contract_only",
    )

    if plugin is not None:
        bindings = list(pattern_bindings)
        if not bindings:
            # Default interpretation: name what each discovered family means in
            # the domain without touching any universal vocabulary.
            for cluster in discovery.templates():
                bindings.append(
                    {
                        "pattern_id": cluster.cluster_id,
                        "family": "visual_patterns",
                        "domain_meaning": (
                            f"Recurring visual family with layout "
                            f"{cluster.evidence.dominant_layout_class!r} observed across "
                            f"{cluster.evidence.creator_count} creators."
                        ),
                        "attention_hints": [
                            f"mean internal similarity {cluster.evidence.mean_similarity}"
                        ],
                    }
                )
        artifact = merge_creator_extension(
            artifact,
            plugin=plugin,
            domain_vocabulary=dict(domain_vocabulary or {}),
            pattern_bindings=bindings,
        )

    validate_multimodal_artifact(artifact)
    merged = merge_multimodal_artifact(base_artifact, artifact)

    return ArtifactIntegration(
        artifact=merged,
        discovery=discovery,
        observations_count=len(batch.observations),
        cross_modal_records=len(cross_modal_entries),
        text_core_projection=project_text_core(merged),
        plugin=plugin,
    )


def validate_integrated_artifact(integration: ArtifactIntegration) -> None:
    """Validate an integrated artifact against the M1 contract.

    The artifact is expected to be a pure M1 document: discovery results live on
    :class:`ArtifactIntegration`, not inside the artifact, precisely so this
    validation is meaningful rather than something a sidecar could weaken. Any
    key outside the schema is reported rather than ignored.
    """

    declared = _schema_keys()
    extra = set(integration.artifact) - declared
    if extra:
        raise ValueError(
            "integrated artifact carries keys outside the M1 schema: "
            + ", ".join(sorted(extra))
        )
    validate_multimodal_artifact(integration.artifact)


def _schema_keys() -> frozenset[str]:
    """Top-level keys declared by the M1 multimodal schema."""

    schema = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    return frozenset(schema.get("properties", {}))


__all__ = [
    "INTEGRATION_VERSION",
    "ArtifactIntegration",
    "integrate_samples",
    "validate_integrated_artifact",
]
