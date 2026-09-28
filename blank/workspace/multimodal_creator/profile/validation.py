"""Profile validation (Phase M5, Task 3).

Three classes of check, each targeting one of the brief's negative cases.

**Schema** — shape, from the generated schema. Strict at every level, so a key
that is not part of the profile cannot exist.

**Provenance** — every family must carry a source naming an M4 artifact, a
derivation, and a confidence. A field with no source is rejected, because an
unsourced config value is indistinguishable from a guess.

**Prohibitions** — the three negative cases the brief names:

1. *hand-written rules with no M4 origin* — a rule that cannot be traced to a
   source pattern is rejected (:meth:`assert_rules_are_sourced`);
2. *generation logic mixed in* — any prompt, model, or renderer key is rejected
   outright, and the check runs on the raw document too, so a forbidden key is
   caught by name rather than merely by shape (:func:`assert_no_generation_logic`);
3. *creator-specific override of universal structure* — a profile may not
   redefine a term the M1 universal layer owns
   (:func:`assert_no_universal_override`).

Check 3 matters because M5 sits downstream of a plugin-facing layer. A profile is
*creator-specific configuration*, and the temptation is to let it redefine what
``layout_pattern`` means for that creator. The M1 contract forbids that split, so
M5 forbids it too.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..grammar.model import RELATION_TYPES as M4_RELATION_TYPES
from ..taxonomy import (
    LAYOUT_TEMPLATE_CLASSES,
    REGION_ROLES,
)
from .model import (
    PROFILE_VERSION,
    PROVENANCE_FAMILIES,
    ProfileError,
    VisualCreatorProfile,
)
from .schema import FORBIDDEN_KEYS, validate_schema_document


class ValidationError(ProfileError):
    """Raised when a profile fails a validation rule."""


def _walk_keys(document: Any, path: str = "") -> list[tuple[str, str]]:
    """Every ``(path, key)`` pair in a nested document."""

    found: list[tuple[str, str]] = []
    if isinstance(document, Mapping):
        for key, value in document.items():
            here = f"{path}.{key}" if path else str(key)
            found.append((here, str(key)))
            found.extend(_walk_keys(value, here))
    elif isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
        for index, item in enumerate(document):
            found.extend(_walk_keys(item, f"{path}[{index}]"))
    return found


def assert_no_generation_logic(document: Mapping[str, Any]) -> None:
    """Reject any generation, model, asset, or deployment key.

    Runs on the raw document rather than the model, so a key that the model could
    never hold is still reported by its own name. That gives a caller a useful
    error instead of an opaque schema failure.
    """

    offenders = sorted(
        {
            f"{path} ({key})"
            for path, key in _walk_keys(document)
            if key.lower() in FORBIDDEN_KEYS
        }
    )
    if offenders:
        raise ValidationError(
            "profile contains keys that are not permitted in a configuration asset: "
            + ", ".join(offenders)
            + ". M5 produces configuration only; generation, model, asset, and "
            "deployment settings are out of scope by design."
        )


def assert_no_universal_override(
    document: Mapping[str, Any],
    *,
    universal_vocabulary: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Reject any attempt to redefine a universal structure term.

    The universal vocabulary — M1's region roles and layout template classes, and
    the grammar relation vocabulary M4 owns — is not the profile layer's to
    change. A creator profile may describe *which* of those a creator uses; it
    may not change what they mean.
    """

    vocabulary = dict(
        universal_vocabulary
        or {
            "region_role": REGION_ROLES,
            "layout_template_class": LAYOUT_TEMPLATE_CLASSES,
            "relation_type": M4_RELATION_TYPES,
        }
    )

    # A profile has no field for a vocabulary definition, so the check is for the
    # key names such a definition would use.
    redefinition_keys = {
        "region_roles",
        "region_role_vocabulary",
        "layout_template_classes",
        "layout_template_class_vocabulary",
        "relation_types",
        "relation_vocabulary",
        "vocabulary",
        "redefine",
        "overrides",
        "layer",
    }
    offenders = sorted(
        {
            f"{path} ({key})"
            for path, key in _walk_keys(document)
            if key.lower() in redefinition_keys
        }
    )
    if offenders:
        raise ValidationError(
            "profile attempts to redefine universal structure, which the M1 contract "
            "reserves: " + ", ".join(offenders)
        )

    # Also reject a value that claims to replace the universal layer.
    for path, key in _walk_keys(document):
        if key.lower() in {"definition", "means", "redefines"}:
            raise ValidationError(
                f"{path} defines {key!r}; a creator profile describes usage, not meaning"
            )


def assert_provenance_complete(profile: VisualCreatorProfile) -> None:
    """Every family must carry a usable provenance record."""

    missing = [
        family for family in PROVENANCE_FAMILIES if family not in profile.provenance
    ]
    if missing:
        raise ValidationError(
            "provenance is missing for: " + ", ".join(missing)
        )
    for family, record in profile.provenance.items():
        if not record.artifact_id.strip():
            raise ValidationError(f"provenance for {family!r} names no artifact")
        if record.source_phase != "M4":
            raise ValidationError(
                f"provenance for {family!r} comes from {record.source_phase!r}, "
                "but M5 derives only from M4"
            )
        if record.confidence <= 0.0:
            raise ValidationError(
                f"provenance for {family!r} has zero confidence; a field with no "
                "evidence behind it must not be presented as derived"
            )


def assert_rules_are_sourced(profile: VisualCreatorProfile) -> None:
    """Every rule must trace to a source pattern.

    This is the negative case the brief calls "hand-written rules with no M4
    origin". A profile whose rule set cannot be attributed to an M4 artifact is a
    hand-written config wearing a profile's shape.
    """

    if not profile.source_pattern_ids:
        raise ValidationError(
            "profile names no source pattern, so none of its rules can be traced to M4"
        )
    known = set(profile.source_pattern_ids)

    def traces_to_a_source(artifact_id: str) -> bool:
        """True when an artifact id names, or is derived from, a source pattern.

        M4's constraint ids are their pattern id with a ``constraint-`` prefix, so
        the check strips known derivational prefixes and compares the remainder
        rather than requiring an exact match on the composite id.
        """

        for part in artifact_id.split("+"):
            part = part.strip()
            if not part:
                continue
            if part in known:
                return True
            for prefix in ("constraint-", "strategy-", "vp-", "vcp-"):
                if part.startswith(prefix) and part[len(prefix) :] in known:
                    return True
        return False

    for family in ("composition_rules", "attention_strategy", "hierarchy_pattern", "constraints"):
        record = profile.provenance.get(family)
        if record is None:
            raise ValidationError(f"no provenance recorded for {family!r}")
        if not traces_to_a_source(record.artifact_id):
            raise ValidationError(
                f"{family!r} cites artifact {record.artifact_id!r}, which does not "
                f"trace to a declared source pattern {sorted(known)}"
            )


def assert_no_contradiction(profile: VisualCreatorProfile) -> None:
    """Preferred and forbidden sets must not contradict each other."""

    overlap = set(profile.composition_rules.preferred) & set(
        profile.composition_rules.forbidden
    )
    if overlap:
        raise ValidationError(
            "composition rules contradict themselves: "
            + ", ".join(sorted(overlap))
        )
    clash = set(profile.constraints.must_have) & set(profile.constraints.avoid)
    if clash:
        raise ValidationError(
            "constraints contradict themselves: " + ", ".join(sorted(clash))
        )


def assert_slots_are_contiguous(document: Mapping[str, Any]) -> None:
    """Attention slots and hierarchy tiers must be filled from the front.

    The dependency-free schema subset cannot express "contiguous from the start",
    so it is checked here on the raw document. A gap would let a reader mistake a
    missing middle tier for an absent one.
    """

    from .model import ATTENTION_SLOTS, HIERARCHY_TIERS

    for key, vocabulary in (
        ("attention_strategy", ATTENTION_SLOTS),
        ("hierarchy_pattern", HIERARCHY_TIERS),
    ):
        section = document.get(key)
        if not isinstance(section, Mapping) or not section:
            raise ValidationError(f"{key} must be a non-empty object")

        present = list(section)
        expected = list(vocabulary[: len(present)])

        # Two separate failures, reported separately: a key outside the
        # vocabulary, and a gap or reordering within it. Comparing against the
        # canonical prefix catches both, but the messages must not be conflated —
        # "unknown slot" and "gap in slots" have different fixes.
        unknown = [name for name in present if name not in vocabulary]
        if unknown:
            raise ValidationError(
                f"{key} uses names outside its vocabulary: "
                + ", ".join(map(str, unknown))
            )
        if present != expected:
            raise ValidationError(
                f"{key} must be filled contiguously from {vocabulary[0]!r} in "
                f"canonical order {expected!r}, got {present!r}"
            )


def validate_document(
    document: Mapping[str, Any],
    *,
    check_universal_override: bool = True,
) -> None:
    """Validate a raw profile document without constructing a model first.

    Runs the prohibition checks *before* schema validation so a forbidden key is
    reported by name. Order matters for the caller's experience: "profile contains
    a 'prompt' key" is actionable, "additional properties are not allowed" is not.
    """

    assert_no_generation_logic(document)
    if check_universal_override:
        assert_no_universal_override(document)
    validate_schema_document(document)
    if document.get("profile_version") != PROFILE_VERSION:
        raise ValidationError(
            f"profile_version must be {PROFILE_VERSION!r}, got "
            f"{document.get('profile_version')!r}"
        )
    assert_slots_are_contiguous(document)


def validate_profile(profile: VisualCreatorProfile) -> None:
    """Full validation of a built profile: schema, provenance, and prohibitions."""

    document = profile.as_dict()
    validate_document(document)
    assert_provenance_complete(profile)
    assert_rules_are_sourced(profile)
    assert_no_contradiction(profile)


def validation_summary(profile: VisualCreatorProfile) -> dict[str, Any]:
    """A machine-readable record of what was checked and what was found."""

    checks: dict[str, bool] = {}
    failures: dict[str, str] = {}

    for name, check in (
        ("schema", lambda: validate_document(profile.as_dict())),
        ("provenance_complete", lambda: assert_provenance_complete(profile)),
        ("rules_are_sourced", lambda: assert_rules_are_sourced(profile)),
        ("no_contradiction", lambda: assert_no_contradiction(profile)),
        ("no_generation_logic", lambda: assert_no_generation_logic(profile.as_dict())),
        ("no_universal_override", lambda: assert_no_universal_override(profile.as_dict())),
    ):
        try:
            check()
        except ProfileError as exc:
            checks[name] = False
            failures[name] = str(exc)
        else:
            checks[name] = True

    return {
        "profile_id": profile.profile_id,
        "passed": all(checks.values()),
        "checks": checks,
        "failures": failures,
        "provenance_families": sorted(profile.provenance),
        "source_pattern_ids": list(profile.source_pattern_ids),
    }


__all__ = [
    "ValidationError",
    "assert_no_contradiction",
    "assert_no_generation_logic",
    "assert_no_universal_override",
    "assert_provenance_complete",
    "assert_rules_are_sourced",
    "assert_slots_are_contiguous",
    "validate_document",
    "validate_profile",
    "validation_summary",
]
