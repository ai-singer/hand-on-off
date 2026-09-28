"""Multi-role source classification for multimodal distillation (Phase M1).

The existing text-centric classifier returns exactly one ``MaterialRole`` per
source. That is correct for text and wrong for multimodality: a single earnings
screenshot is simultaneously a knowledge source, a visual style source, and a
layout source. This module therefore replaces the single label with a *set* of
roles over a declared modality set, and refuses to guess:

- every non-visual role must be backed by a modality the source declares;
- a ``visual`` modality declaration requires at least one visual-family role;
- a ``textual`` modality declaration requires at least one text-family role.

Text signals extracted from an image or video are transcription, not visual
distillation, so :func:`structure_from_metadata` records that provenance
explicitly instead of letting it masquerade as visual evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .taxonomy import MODALITIES, MultimodalContractError

#: Roles that are only meaningful when the source declares a visual modality.
VISUAL_ROLES: tuple[str, ...] = (
    "visual_style_source",
    "layout_source",
    "composition_source",
    "color_source",
    "typography_source",
    "subject_source",
    "chart_source",
    "cover_source",
    "sequence_source",
)

#: Roles meaningful for a textual modality.
TEXT_ROLES: tuple[str, ...] = ("knowledge_source", "hook_source")

#: Source types whose metadata may declare a visual modality.
VISUAL_CAPABLE_SOURCE_TYPES: tuple[str, ...] = ("image", "video")

MULTI_ROLE_STATEMENT = (
    "A source carries a set of roles, not one label. Visual roles require a "
    "declared visual modality; text roles require a declared textual modality."
)


@dataclass(frozen=True, slots=True)
class SourceStructure:
    """Declared modalities and multi-role membership for one source."""

    source_id: str
    source_type: str
    modalities: tuple[str, ...]
    roles: tuple[str, ...]
    text_is_transcribed: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.source_type not in {"video", "document", "data", "image"}:
            raise MultimodalContractError(
                f"unknown source_type {self.source_type!r} for {self.source_id!r}"
            )
        if not self.modalities:
            raise MultimodalContractError(
                f"source {self.source_id!r} must declare at least one modality"
            )
        unknown_modalities = [m for m in self.modalities if m not in MODALITIES]
        if unknown_modalities:
            raise MultimodalContractError(
                f"source {self.source_id!r} declares unknown modalities: "
                + ", ".join(sorted(unknown_modalities))
            )
        if not self.roles:
            raise MultimodalContractError(
                f"source {self.source_id!r} must carry at least one role"
            )

        visual_declared = "visual" in self.modalities
        textual_declared = "textual" in self.modalities

        visual_roles = [r for r in self.roles if r in VISUAL_ROLES]
        if visual_roles and not visual_declared:
            raise MultimodalContractError(
                f"source {self.source_id!r} claims visual roles "
                f"({', '.join(sorted(visual_roles))}) without declaring a visual modality"
            )
        if visual_declared and not visual_roles:
            raise MultimodalContractError(
                f"source {self.source_id!r} declares a visual modality but carries no "
                "visual role"
            )

        text_roles = [r for r in self.roles if r in TEXT_ROLES]
        if text_roles and not textual_declared:
            raise MultimodalContractError(
                f"source {self.source_id!r} claims text roles "
                f"({', '.join(sorted(text_roles))}) without declaring a textual modality"
            )

        if textual_declared and self.source_type in VISUAL_CAPABLE_SOURCE_TYPES:
            if not self.text_is_transcribed:
                raise MultimodalContractError(
                    f"source {self.source_id!r} is a {self.source_type} with a textual "
                    "modality; its text is transcription and must be marked with "
                    "text_is_transcribed=True so it is not mistaken for visual structure"
                )

    def as_envelope_entry(self) -> dict[str, Any]:
        """Render the envelope record stored in ``multimodal_envelope``."""

        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "modalities": list(self.modalities),
            "roles": list(self.roles),
        }


def structure_from_metadata(
    source_id: str,
    source_type: str,
    metadata: Mapping[str, Any] | None = None,
) -> SourceStructure:
    """Derive a multi-role structure from source metadata.

    Expected keys: ``modalities`` (sequence), ``multimodal_roles`` (sequence),
    and ``text_is_transcribed`` (bool).

    An image or video defaults to a **visual** modality only. Declaring a textual
    modality on those source types requires ``text_is_transcribed=True``, because
    text in an image or video can only have been transcribed or OCR'd and that
    provenance must be explicit.
    """

    meta = dict(metadata or {})
    modalities = tuple(meta.get("modalities", ()))
    roles = tuple(meta.get("multimodal_roles", ()))

    if not modalities:
        if source_type in VISUAL_CAPABLE_SOURCE_TYPES:
            # An image or video is first of all a visual source. A textual
            # modality must be declared explicitly, because for these source
            # types text can only have been transcribed, and that provenance is
            # exactly what stops transcription being mistaken for structure.
            modalities = ("visual",)
        elif source_type == "data":
            modalities = ("structured", "textual")
        else:
            modalities = ("textual",)

    if not roles:
        if "visual" in modalities:
            roles = ("visual_style_source",)
        elif "structured" in modalities:
            roles = ("knowledge_source",)
        else:
            roles = ("knowledge_source",)

    transcribed = meta.get("text_is_transcribed")
    if transcribed is None:
        # Only a document's own text is native. For image and video, text is
        # transcription by construction, so the flag defaults to True there.
        transcribed = (
            source_type in VISUAL_CAPABLE_SOURCE_TYPES and "textual" in modalities
        )

    return SourceStructure(
        source_id=source_id,
        source_type=source_type,
        modalities=modalities,
        roles=roles,
        text_is_transcribed=bool(transcribed),
    )


def roles_of(structures: Sequence[SourceStructure], source_id: str) -> tuple[str, ...]:
    """Return the declared roles for one source, or raise if it is unknown."""

    for structure in structures:
        if structure.source_id == source_id:
            return structure.roles
    raise MultimodalContractError(f"no source structure declared for {source_id!r}")


def sources_holding_role(
    structures: Sequence[SourceStructure],
    role: str,
) -> tuple[str, ...]:
    """Return every source id carrying ``role`` — the basis of multi-role use."""

    return tuple(s.source_id for s in structures if role in s.roles)
