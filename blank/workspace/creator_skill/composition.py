"""The composition engine: a CreatorRequest in, a verified SkillBundle out.

Composition is deliberately simple and fully explainable. For each required skill
type it:

1. filters skills by **compatibility** (a finance persona is not used for sports);
2. filters by **availability** (an unimplemented skill is never silently bundled);
3. scores the survivors by confidence and on-type fit;
4. selects the best and **records why**, plus what it rejected.

Nothing is guessed. Every selection carries a reason string, and the result
carries the full rejected set so a caller can see what lost and by how much.

The output bundle is verified before it is returned: it cannot reference a skill
that is not registered, it cannot omit a required type, and its dependency graph
must be acyclic with no active conflict edges.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .errors import SkillCompositionError
from .model import (
    CompositionResult,
    CreatorRequest,
    CreatorSkill,
    SkillBundle,
    SkillSelection,
)
from .provenance import DEFAULT_TIMESTAMP, bundle_provenance
from .registry import SkillRegistry
from .taxonomy import (
    OPTIONAL_SKILL_TYPES,
    REQUIRED_SKILL_TYPES,
    SKILL_TYPE_ORDER,
    is_known_skill_type,
)

#: Score bonus applied when a skill explicitly declares the requested value.
DOMAIN_MATCH_BONUS = 0.30
PLATFORM_MATCH_BONUS = 0.30
STYLE_MATCH_BONUS = 0.20

#: Score applied when a skill declares a value set that excludes the request.
INCOMPATIBLE_PENALTY = -1.0

#: A skill declaring no compatibility for a dimension is a wildcard, not a match.
WILDCARD_SCORE = 0.0

#: Skill types that exist but are not part of a standard creator bundle.
EXTRA_SKILL_TYPES: tuple[str, ...] = ("distillation",)


@dataclass(frozen=True, slots=True)
class SkillScore:
    """One skill's fitness for a request, with the arithmetic exposed."""

    skill_id: str
    skill_type: str
    total: float
    compatible: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "total": float(self.total),
            "compatible": self.compatible,
            "reasons": list(self.reasons),
        }


def score_skill(skill: CreatorSkill, request: CreatorRequest) -> SkillScore:
    """Score one skill against a request, explaining each contribution."""

    reasons: list[str] = []
    total = float(skill.provenance.confidence)

    if not skill.compatibility.matches_domain(request.domain):
        return SkillScore(
            skill_id=skill.skill_id,
            skill_type=skill.skill_type,
            total=INCOMPATIBLE_PENALTY,
            compatible=False,
            reasons=(f"domain {request.domain!r} not in {list(skill.compatibility.domains)}",),
        )

    if skill.compatibility.domains and request.domain in skill.compatibility.domains:
        total += DOMAIN_MATCH_BONUS
        reasons.append(f"matched domain {request.domain}")
    else:
        reasons.append("domain-agnostic")

    if not skill.compatibility.matches_platform(request.platform):
        return SkillScore(
            skill_id=skill.skill_id,
            skill_type=skill.skill_type,
            total=INCOMPATIBLE_PENALTY,
            compatible=False,
            reasons=(
                f"platform {request.platform!r} not in "
                f"{list(skill.compatibility.platforms)}",
            ),
        )
    if skill.compatibility.platforms and request.platform in skill.compatibility.platforms:
        total += PLATFORM_MATCH_BONUS
        reasons.append(f"matched platform {request.platform}")
    else:
        reasons.append("platform-agnostic")

    if not skill.compatibility.matches_style(request.style):
        return SkillScore(
            skill_id=skill.skill_id,
            skill_type=skill.skill_type,
            total=INCOMPATIBLE_PENALTY,
            compatible=False,
            reasons=(
                f"style {request.style!r} not in {list(skill.compatibility.styles)}",
            ),
        )
    if skill.compatibility.styles and request.style in skill.compatibility.styles:
        total += STYLE_MATCH_BONUS
        reasons.append(f"matched style {request.style}")
    else:
        reasons.append("style-agnostic")

    reasons.append(f"confidence {skill.provenance.confidence:.2f}")
    return SkillScore(
        skill_id=skill.skill_id,
        skill_type=skill.skill_type,
        total=round(total, 6),
        compatible=True,
        reasons=tuple(reasons),
    )


class SkillComposer:
    """Compose a verified SkillBundle from a CreatorRequest."""

    def __init__(self, registry: SkillRegistry, *, timestamp: str = DEFAULT_TIMESTAMP) -> None:
        if not isinstance(registry, SkillRegistry):
            raise SkillCompositionError("SkillComposer requires a SkillRegistry")
        self._registry = registry
        self._timestamp = timestamp

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    # -- composition ------------------------------------------------------

    def compose(self, request: CreatorRequest) -> CompositionResult:
        """Compose a bundle for a request, or raise if it cannot be satisfied."""

        if not isinstance(request, CreatorRequest):
            raise SkillCompositionError("compose requires a CreatorRequest")

        required = request.required_skill_types or REQUIRED_SKILL_TYPES
        for skill_type in required:
            if not is_known_skill_type(skill_type):
                raise SkillCompositionError(f"unknown required skill type {skill_type!r}")

        selections: list[SkillSelection] = []
        reasons: dict[str, str] = {}
        rejected: dict[str, tuple[str, ...]] = {}
        unsatisfied: list[str] = []
        notes: list[str] = []

        for skill_type in SKILL_TYPE_ORDER:
            if skill_type not in required:
                continue
            chosen, alternatives, explanation, unmet = self._select(skill_type, request)
            if chosen is None:
                unsatisfied.append(skill_type)
                reasons[skill_type] = explanation
                rejected[skill_type] = alternatives
                continue
            selections.append(chosen)
            reasons[skill_type] = explanation
            rejected[skill_type] = alternatives

        # Optional extras: additional skills of an already-satisfied type, such as
        # a visual-style distillation alongside text distillation. They are kept
        # separate from the one-per-type spine.
        extras: list[SkillSelection] = []
        for extra_id in request.declared_capabilities:
            if not self._registry.has(extra_id):
                notes.append(f"declared capability {extra_id!r} is not registered")
                continue
            extra = self._registry.resolve(extra_id)
            if extra.skill_id in {s.skill_id for s in selections}:
                continue
            score = score_skill(extra, request)
            if not score.compatible:
                notes.append(
                    f"declared capability {extra_id!r} is incompatible with the request"
                )
                continue
            if not extra.available:
                notes.append(
                    f"declared capability {extra_id!r} is declared but not available "
                    f"({extra.reason})"
                )
                continue
            extras.append(
                SkillSelection(
                    skill_type=extra.skill_type,
                    skill_id=extra.skill_id,
                    version=extra.version,
                    reason=f"{extra.skill_id}: optional extra requested by the caller",
                    score=score.total,
                    status=extra.status,
                )
            )
            reasons[f"{extra.skill_type}:{extra.skill_id}"] = (
                f"{extra.skill_id}: requested as an optional extra; "
                + "; ".join(score.reasons)
            )

        # Record the gap *before* the bundle is built: SkillBundle is frozen, so a
        # note appended afterwards would never reach it.
        if unsatisfied:
            notes.append(
                "partial bundle: unresolved skill types " + ", ".join(unsatisfied)
            )

        bundle = self._build_bundle(
            request, tuple(selections), tuple(extras), reasons, rejected, notes
        )

        if unsatisfied and not request.allow_unavailable:
            raise SkillCompositionError(
                "cannot compose a complete bundle; no skill satisfied: "
                + ", ".join(unsatisfied)
                + " (pass allow_unavailable=True to compose a partial bundle)"
            )

        return CompositionResult(
            bundle=bundle,
            reasons=dict(reasons),
            rejected=dict(rejected),
            unsatisfied=tuple(unsatisfied),
        )

    def compose_document(self, request: CreatorRequest) -> dict[str, Any]:
        """Compose and return the result as a plain document."""

        return self.compose(request).as_dict()

    # -- selection --------------------------------------------------------

    def _select(
        self, skill_type: str, request: CreatorRequest
    ) -> tuple[SkillSelection | None, tuple[str, ...], str, bool]:
        """Select the best skill of one type.

        Returns ``(selection, rejected_ids, explanation, unmet)``.
        """

        candidates = [
            skill for skill in self._registry.by_type(skill_type) if skill.reusable
        ]
        if not candidates:
            return None, (), f"no {skill_type} skill is registered", True

        scored = [(skill, score_skill(skill, request)) for skill in candidates]
        compatible = [(skill, score) for skill, score in scored if score.compatible]
        incompatible = [skill.skill_id for skill, score in scored if not score.compatible]

        if not compatible:
            return (
                None,
                tuple(sorted(incompatible)),
                f"no {skill_type} skill is compatible with domain={request.domain!r} "
                f"platform={request.platform!r} style={request.style!r}",
                True,
            )

        available = [(skill, score) for skill, score in compatible if skill.available]
        unavailable = [skill.skill_id for skill, score in compatible if not skill.available]

        if not available and not request.allow_unavailable:
            return (
                None,
                tuple(sorted(unavailable)),
                f"every compatible {skill_type} skill is unavailable: "
                + ", ".join(sorted(unavailable)),
                True,
            )

        # Prefer an available skill; fall back to a declared one so the bundle
        # names the capability and records that it is not yet implemented.
        pool = available if available else compatible
        pool.sort(key=lambda item: (-item[1].total, item[0].skill_id))
        skill, score = pool[0]

        losers = [
            other.skill_id for other, _ in pool[1:]
        ] + incompatible + (unavailable if available else [])

        explanation = (
            f"{skill.skill_id}: " + "; ".join(score.reasons)
        )
        if not skill.available:
            explanation += f" (declared, not available: {skill.reason})"

        return (
            SkillSelection(
                skill_type=skill.skill_type,
                skill_id=skill.skill_id,
                version=skill.version,
                reason=explanation,
                score=score.total,
                status=skill.status,
            ),
            tuple(sorted(set(losers))),
            explanation,
            False,
        )

    # -- bundle -----------------------------------------------------------

    def _build_bundle(
        self,
        request: CreatorRequest,
        selections: Sequence[SkillSelection],
        extras: Sequence[SkillSelection],
        reasons: Mapping[str, str],
        rejected: Mapping[str, tuple[str, ...]],
        notes: list[str],
    ) -> SkillBundle:
        bundle_id = compose_bundle_id(request, selections)
        sources = [s.skill_id for s in (*selections, *extras)]
        provenance = bundle_provenance(
            bundle_id=bundle_id, sources=sources, generated_at=self._timestamp
        )
        return SkillBundle(
            bundle_id=bundle_id,
            request=request,
            selections=tuple(selections),
            extras=tuple(extras),
            provenance=provenance,
            notes=tuple(notes),
            alternatives={key: tuple(value) for key, value in rejected.items()},
        )

    # -- verification -----------------------------------------------------

    def verify(self, bundle: SkillBundle) -> dict[str, str]:
        """Verify a bundle against the registry, raising on any failure.

        Checks:
            * every selected skill id resolves in the registry;
            * the selected version matches the registered version;
            * every required skill type is present;
            * no two selections share a skill type;
            * dependency edges between selections are satisfied;
            * no selected pair declares a conflict;
            * the selected subgraph is acyclic.
        """

        checks: dict[str, str] = {}

        for selection in bundle.all_selections():
            skill = self._registry.resolve(f"{selection.skill_id}@{selection.version}")
            if skill.skill_id != selection.skill_id:
                raise SkillCompositionError(
                    f"bundle references {selection.skill_id!r} which resolved to "
                    f"{skill.skill_id!r}"
                )
        checks["skills_exist"] = "PASS"

        types = [s.skill_type for s in bundle.selections]
        if len(types) != len(set(types)):
            raise SkillCompositionError("bundle selects the same skill type twice")
        checks["types_unique"] = "PASS"

        missing = [t for t in REQUIRED_SKILL_TYPES if t not in set(types)]
        if missing and not bundle.request.allow_unavailable:
            raise SkillCompositionError(
                "bundle omits required skill types: "
                + ", ".join(missing)
                + " (request had allow_unavailable=False)"
            )
        if missing and not bundle.notes:
            # A gap must be *declared*. An incomplete bundle with no note is
            # indistinguishable from a bug, so it is rejected rather than passed
            # through as a silent partial result.
            raise SkillCompositionError(
                "bundle omits required skill types: "
                + ", ".join(missing)
                + " and declares no gap note"
            )
        checks["required_types"] = "PARTIAL" if missing else "PASS"

        selected = set(bundle.skill_ids())
        by_type = {s.skill_type: s for s in bundle.selections}
        by_id = {s.skill_id: s for s in bundle.all_selections()}

        for selection in bundle.all_selections():
            skill = self._registry.resolve(f"{selection.skill_id}@{selection.version}")
            for dependency in skill.dependencies:
                if dependency.kind == "conflict":
                    if dependency.target in selected:
                        raise SkillCompositionError(
                            f"bundle contains a conflict: {skill.skill_id!r} conflicts "
                            f"with {dependency.target!r}"
                        )
                    continue
                if dependency.kind != "require":
                    continue
                if dependency.target in by_id:
                    continue
                target_skill = self._registry.resolve(dependency.target)
                if (
                    target_skill.skill_type in by_type
                    and by_type[target_skill.skill_type].skill_id != dependency.target
                ):
                    raise SkillCompositionError(
                        f"bundle selected {by_type[target_skill.skill_type].skill_id!r} "
                        f"for type {target_skill.skill_type!r} but "
                        f"{skill.skill_id!r} requires {dependency.target!r}"
                    )
                if target_skill.skill_type in by_type:
                    continue
                raise SkillCompositionError(
                    f"bundle is missing required skill {dependency.target!r} "
                    f"needed by {skill.skill_id!r}"
                )
        checks["dependencies"] = "PASS"

        self._assert_acyclic(selected)
        checks["acyclic"] = "PASS"

        return checks

    def verify_document(self, bundle: SkillBundle) -> dict[str, Any]:
        """Verify and return an inspectable document."""

        return {
            "bundle_id": bundle.bundle_id,
            "status": "PASS",
            "checks": self.verify(bundle),
        }

    def _assert_acyclic(self, selected: set[str]) -> None:
        edges: dict[str, set[str]] = {}
        for skill_id in selected:
            skill = self._registry.resolve(skill_id)
            edges[skill_id] = {d for d in skill.requires() if d in selected}
        remaining = dict(edges)
        resolved: set[str] = set()
        while remaining:
            ready = [k for k, deps in remaining.items() if not (deps - resolved)]
            if not ready:
                raise SkillCompositionError(
                    "dependency cycle among selected skills: "
                    + ", ".join(sorted(remaining))
                )
            for skill_id in ready:
                resolved.add(skill_id)
                del remaining[skill_id]


def compose_bundle_id(
    request: CreatorRequest, selections: Sequence[SkillSelection]
) -> str:
    """Derive a deterministic bundle id from the request and the selection.

    Deterministic on purpose: composing the same request against the same registry
    twice must produce the same id, so a re-run is diffable.
    """

    payload = "|".join(
        [
            request.creator_id or "unnamed",
            request.domain,
            request.platform,
            request.style,
            *(
                f"{s.skill_type}:{s.skill_id}@{s.version}"
                for s in sorted(selections, key=lambda s: s.skill_type)
            ),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"bundle-{digest}"


def compose(
    request: CreatorRequest,
    *,
    registry: SkillRegistry | None = None,
    timestamp: str = DEFAULT_TIMESTAMP,
) -> CompositionResult:
    """Compose a bundle using the default registry unless one is supplied."""

    active = registry or SkillRegistry.default()
    return SkillComposer(active, timestamp=timestamp).compose(request)


__all__ = [
    "DOMAIN_MATCH_BONUS",
    "EXTRA_SKILL_TYPES",
    "INCOMPATIBLE_PENALTY",
    "PLATFORM_MATCH_BONUS",
    "STYLE_MATCH_BONUS",
    "SkillComposer",
    "SkillScore",
    "WILDCARD_SCORE",
    "compose",
    "compose_bundle_id",
    "score_skill",
]
