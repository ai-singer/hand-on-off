"""Provenance helpers for Creator Skills.

A skill with no source is invalid. This module builds and checks the provenance
record every skill must carry, and keeps the deterministic-timestamp convention
established by the projection layer so two runs produce identical output.

Source kinds and what they must name:

======================  =========================================================
source_kind             source_ref must be
======================  =========================================================
``template``            a workspace-relative path or a registered asset id
``distillation_artifact``a **registered asset id** (the artifact actually exists)
``projection``          a **registered asset id** used by the projection layer
``manual``              a human-readable authoring reference
======================  =========================================================
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .errors import SkillProvenanceError
from .model import PROVENANCE_SOURCES, SkillProvenance

#: Deterministic default timestamp, matching the projection layer's convention.
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

#: Confidence assigned by source kind. A hand-authored skill is not less valid,
#: but a skill derived from a real artifact is more traceable.
CONFIDENCE_BY_SOURCE: Mapping[str, float] = {
    "template": 1.0,
    "distillation_artifact": 1.0,
    "projection": 1.0,
    "manual": 0.7,
}

#: Provenance keys the schema requires.
REQUIRED_SKILL_PROVENANCE_KEYS: tuple[str, ...] = (
    "source_kind",
    "source_ref",
    "skill_version",
    "generated_at",
    "confidence",
)


def build_skill_provenance(
    *,
    source_kind: str,
    source_ref: str,
    skill_version: str,
    generated_at: str = DEFAULT_TIMESTAMP,
    confidence: float | None = None,
    note: str = "",
) -> SkillProvenance:
    """Build a skill provenance record, defaulting confidence by source kind."""

    if source_kind not in PROVENANCE_SOURCES:
        raise SkillProvenanceError(
            f"source_kind {source_kind!r} is not one of: {', '.join(PROVENANCE_SOURCES)}"
        )
    resolved = (
        float(confidence)
        if confidence is not None
        else CONFIDENCE_BY_SOURCE.get(source_kind, 0.5)
    )
    return SkillProvenance(
        source_kind=source_kind,
        source_ref=source_ref,
        skill_version=skill_version,
        generated_at=generated_at,
        confidence=resolved,
        note=note,
    )


def assert_source_registered(
    provenance: SkillProvenance,
    registered_assets: Sequence[str],
) -> None:
    """Raise when a derived source does not resolve in the asset registry."""

    if provenance.source_kind not in ("distillation_artifact", "projection"):
        return
    if provenance.source_ref not in set(registered_assets):
        raise SkillProvenanceError(
            f"skill source {provenance.source_kind}:{provenance.source_ref!r} does not "
            "resolve to a registered asset"
        )


def assert_provenance_keys_complete(provenance: Mapping[str, Any]) -> None:
    """Raise unless a provenance document carries every required key."""

    missing = [key for key in REQUIRED_SKILL_PROVENANCE_KEYS if key not in provenance]
    if missing:
        raise SkillProvenanceError(
            "skill provenance is missing: " + ", ".join(missing)
        )
    for key in ("source_kind", "source_ref", "skill_version", "generated_at"):
        if not str(provenance.get(key, "")).strip():
            raise SkillProvenanceError(f"skill provenance has an empty {key}")


def bundle_provenance(
    *,
    bundle_id: str,
    sources: Sequence[str],
    generated_at: str = DEFAULT_TIMESTAMP,
) -> SkillProvenance:
    """Build the provenance record for a composed bundle.

    A bundle derives from the skills it selects, so its source kind is
    ``projection`` and its reference is the bundle identity.
    """

    if not sources:
        raise SkillProvenanceError(f"bundle {bundle_id!r} has no source skills")
    return SkillProvenance(
        source_kind="projection",
        source_ref=bundle_id,
        skill_version="1.0.0",
        generated_at=generated_at,
        confidence=1.0,
        note=f"composed from {len(sources)} skill(s): " + ", ".join(sorted(sources)),
    )


__all__ = [
    "CONFIDENCE_BY_SOURCE",
    "DEFAULT_TIMESTAMP",
    "REQUIRED_SKILL_PROVENANCE_KEYS",
    "assert_provenance_keys_complete",
    "assert_source_registered",
    "build_skill_provenance",
    "bundle_provenance",
]
