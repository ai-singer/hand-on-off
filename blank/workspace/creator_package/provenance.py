"""Provenance: the chain from an asset, through a skill, to an instance field.

The requirement this module satisfies is specific: **every output field must be
traceable to its origin** — ``asset_id``, ``skill_id``, ``instance_field``,
``mapping_rule``. Four of those five come from the instance artifact's own field
records. The fifth, ``skill_id``, is the one the artifact does *not* carry: a
C0.4-A field record names the asset and the rule, but not the skill it came from,
even though the mapping read one.

That gap is closed by attribution, never by invention. The package knows which
skills the bundle selected and, from ``creator_mapping.SKILL_MODULE_RULES``, which
module each skill type produces. A field's skill is therefore the selected skill
whose type maps to the field's module. Where several selected skills share a
module, every one of them is recorded and the attribution is marked
``attributed: true`` with the candidate list — so a reader sees a set, not a
fabricated single answer.

Where nothing can be attributed, the field is reported `untraced` rather than
given a plausible-looking skill id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from creator_mapping import SKILL_MODULE_RULES

from .errors import PackageProvenanceError

#: Keys a field trace must carry to count as complete.
REQUIRED_FIELD_KEYS: tuple[str, ...] = (
    "instance_field",
    "module",
    "asset_id",
    "mapping_rule",
    "mode",
    "version",
)

#: Placeholder used where an artifact records no asset for a field.
NO_ASSET = "(none)"


def skill_types_for_module(module: str) -> tuple[str, ...]:
    """Every skill type whose mapping rules write into ``module``."""

    return tuple(
        sorted(
            skill_type
            for skill_type, modules in SKILL_MODULE_RULES.items()
            if module in modules
        )
    )


def modules_for_skill_type(skill_type: str) -> tuple[str, ...]:
    """Every module one skill type writes into."""

    return tuple(SKILL_MODULE_RULES.get(skill_type, ()))


@dataclass(frozen=True, slots=True)
class SkillTrace:
    """What one packaged skill contributed, and to which instance fields.

    ``attributed`` is the honest flag. A skill whose module it wrote is known
    contributes exactly its own fields (``attributed`` is false: the module *is* the
    answer). A skill sharing a module with another skill contributes a candidate set
    (``attributed`` is true, and ``candidates`` names the alternative skills).
    """

    skill_id: str
    skill_type: str
    version: str
    slot: str
    status: str
    available: bool
    reason: str = ""
    modules: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()
    attributed: bool = False
    candidates: tuple[str, ...] = ()

    @property
    def field_count(self) -> int:
        return len(self.fields)

    @property
    def complete(self) -> bool:
        """Whether this skill's own chain is whole.

        A skill is traced when it names itself, its version and its directory slot.
        Whether it *contributed* fields is a different fact — a declared capability
        legitimately contributes none — so an empty field list is not incompleteness.
        """

        return bool(self.skill_id and self.version and self.slot)

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "version": self.version,
            "slot": self.slot,
            "status": self.status,
            "available": self.available,
            "modules": list(self.modules),
            "field_count": self.field_count,
            "fields": list(self.fields),
            "assets": list(self.assets),
            "mapping_rules": list(self.rules),
            "modes": list(self.modes),
            "attributed": self.attributed,
        }
        if self.reason:
            record["reason"] = self.reason
        if self.candidates:
            record["candidates"] = list(self.candidates)
        return record


@dataclass(frozen=True, slots=True)
class FieldTrace:
    """One instance field and the whole chain that produced it."""

    instance_field: str
    module: str
    field_name: str
    asset_id: str
    mapping_rule: str
    mode: str
    version: str
    skill_id: str
    skill_type: str
    attributed: bool = False
    candidates: tuple[str, ...] = ()

    @property
    def has_asset(self) -> bool:
        return self.asset_id not in ("", NO_ASSET)

    @property
    def complete(self) -> bool:
        """Whether every required part of the chain is present."""

        return all(
            (
                self.instance_field,
                self.module,
                self.mapping_rule,
                self.mode,
                self.version,
                self.skill_id,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "instance_field": self.instance_field,
            "module": self.module,
            "field_name": self.field_name,
            "asset_id": self.asset_id,
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "mapping_rule": self.mapping_rule,
            "mode": self.mode,
            "version": self.version,
            "attributed": self.attributed,
        }
        if self.candidates:
            record["candidates"] = list(self.candidates)
        return record


@dataclass(frozen=True, slots=True)
class PackageProvenance:
    """The whole chain, in one document, ready to be written to the package."""

    creator_id: str
    bundle_id: str
    bundle_digest: str
    instance_hash: str
    instance_source: str
    generated_by: str
    generated_at: str
    skills: tuple[SkillTrace, ...] = ()
    fields: tuple[FieldTrace, ...] = ()
    assets: tuple[str, ...] = ()
    modules: Mapping[str, Any] = field(default_factory=dict)

    @property
    def field_count(self) -> int:
        return len(self.fields)

    def untraced_fields(self) -> tuple[str, ...]:
        """Fields whose chain is incomplete. Empty is the only acceptable answer."""

        return tuple(sorted(f.instance_field for f in self.fields if not f.complete))

    def fields_with_no_asset(self) -> tuple[str, ...]:
        """Fields that cite no asset — declared-absent fields, legitimately."""

        return tuple(sorted(f.instance_field for f in self.fields if not f.has_asset))

    def attributed_fields(self) -> tuple[str, ...]:
        """Fields whose skill came from a shared module rather than a unique one."""

        return tuple(sorted(f.instance_field for f in self.fields if f.attributed))

    def skill(self, skill_id: str) -> SkillTrace:
        for trace in self.skills:
            if trace.skill_id == skill_id:
                return trace
        raise PackageProvenanceError(
            f"package provenance has no trace for skill {skill_id!r}",
            detail="traced skills: " + ", ".join(t.skill_id for t in self.skills),
        )

    def assets_of_skill(self, skill_id: str) -> tuple[str, ...]:
        return self.skill(skill_id).assets

    def as_dict(self) -> dict[str, Any]:
        return {
            "creator_id": self.creator_id,
            "created_from_bundle": {
                "bundle_id": self.bundle_id,
                "bundle_digest": self.bundle_digest,
            },
            "created_from_instance": {
                "instance_hash": self.instance_hash,
                "source": self.instance_source,
            },
            "generated_by": self.generated_by,
            "generated_at": self.generated_at,
            "chain": ["asset", "skill", "instance_field"],
            "summary": {
                "skill_count": len(self.skills),
                "field_count": self.field_count,
                "asset_count": len(self.assets),
                "untraced_field_count": len(self.untraced_fields()),
                "fields_without_asset_count": len(self.fields_with_no_asset()),
                "attributed_field_count": len(self.attributed_fields()),
            },
            "assets": list(self.assets),
            "skills": [trace.as_dict() for trace in self.skills],
            "modules": {
                str(key): value for key, value in sorted(self.modules.items())
            },
            "fields": [trace.as_dict() for trace in self.fields],
        }


def attribute_fields(
    *,
    field_records: Mapping[str, Any],
    selected: Sequence[Mapping[str, Any]],
) -> tuple[FieldTrace, ...]:
    """Turn an instance's own field records into fully attributed traces.

    ``field_records`` is the artifact's ``field_provenance.fields`` map: one record
    per instance field, each naming the asset, rule, mode and version it was mapped
    with. ``selected`` is the bundle's selections, each naming a skill id and type.

    A field's module decides which skill types could have produced it; the selected
    skill of that type is the answer. Where several selected skills share the module,
    the field is marked attributed with the whole candidate set.
    """

    by_module: dict[str, list[Mapping[str, Any]]] = {}
    for selection in selected:
        skill_type = str(selection.get("skill_type", ""))
        for module in modules_for_skill_type(skill_type):
            by_module.setdefault(module, []).append(selection)

    traces: list[FieldTrace] = []
    for key in sorted(field_records):
        record = field_records[key]
        if not isinstance(record, Mapping):
            raise PackageProvenanceError(
                f"instance field record {key!r} is not an object"
            )
        instance_field = str(key)
        module, _, field_name = instance_field.partition(".")
        candidates = by_module.get(module, [])

        missing = [
            name
            for name in ("asset_id", "rule_id", "mode", "version")
            if name not in record
        ]
        if missing:
            raise PackageProvenanceError(
                f"instance field record {instance_field!r} is missing: "
                + ", ".join(missing),
                detail="a chain with a gap is reported, never filled",
            )

        if len(candidates) == 1:
            skill_id = str(candidates[0].get("skill_id", ""))
            skill_type = str(candidates[0].get("skill_type", ""))
            names: tuple[str, ...] = ()
            attributed = False
        elif candidates:
            first = candidates[0]
            skill_id = str(first.get("skill_id", ""))
            skill_type = str(first.get("skill_type", ""))
            names = tuple(
                sorted(str(c.get("skill_id", "")) for c in candidates[1:])
            )
            attributed = True
        else:
            skill_id = ""
            skill_type = ""
            names = ()
            attributed = True

        traces.append(
            FieldTrace(
                instance_field=instance_field,
                module=module,
                field_name=field_name,
                asset_id=str(record["asset_id"]),
                mapping_rule=str(record["rule_id"]),
                mode=str(record["mode"]),
                version=str(record["version"]),
                skill_id=skill_id,
                skill_type=skill_type,
                attributed=attributed,
                candidates=names,
            )
        )
    return tuple(traces)


def build_skill_traces(
    *,
    selected: Sequence[Mapping[str, Any]],
    fields: Sequence[FieldTrace],
    slot_of: Any,
    version_of: Any = None,
) -> tuple[SkillTrace, ...]:
    """One :class:`SkillTrace` per selected skill, from already-attributed fields.

    ``slot_of`` resolves a ``(skill_type, outputs)`` pair to its package directory;
    ``version_of`` optionally overrides the version a skill is recorded at.
    """

    traces: list[SkillTrace] = []
    for selection in selected:
        skill_id = str(selection.get("skill_id", ""))
        skill_type = str(selection.get("skill_type", ""))
        outputs = tuple(selection.get("outputs", ()) or ())
        slot = slot_of(skill_type, outputs)
        version = (
            str(selection.get("version", ""))
            if version_of is None
            else str(version_of(skill_id, selection))
        )

        mine = [f for f in fields if f.skill_id == skill_id]
        if not mine and not any(
            f.attributed and skill_id in f.candidates for f in fields
        ):
            # A skill whose module no field cites — a declared capability whose
            # skill contributed nothing, which is exactly generation and publishing.
            mine = [
                f
                for f in fields
                if f.module in modules_for_skill_type(skill_type)
                and f.skill_type == skill_type
            ]

        assets: list[str] = []
        rules: list[str] = []
        modes: list[str] = []
        for trace in mine:
            if trace.has_asset and trace.asset_id not in assets:
                assets.append(trace.asset_id)
            if trace.mapping_rule not in rules:
                rules.append(trace.mapping_rule)
            if trace.mode not in modes:
                modes.append(trace.mode)

        traces.append(
            SkillTrace(
                skill_id=skill_id,
                skill_type=skill_type,
                version=version,
                slot=slot,
                status=str(selection.get("status", "available")),
                available=str(selection.get("status", "available")) == "available",
                reason=str(selection.get("reason", "")),
                modules=modules_for_skill_type(skill_type),
                fields=tuple(sorted(t.instance_field for t in mine)),
                assets=tuple(sorted(assets)),
                rules=tuple(sorted(rules)),
                modes=tuple(sorted(modes)),
            )
        )
    return tuple(sorted(traces, key=lambda t: (t.slot, t.skill_id)))


def skill_manifest_entry(
    skill: Any,
    *,
    slot: str,
    member_paths: Mapping[str, str],
    provenance_member: str,
) -> dict[str, Any]:
    """The manifest's record of one packaged skill.

    Carries what a consumer needs to find and trust the skill: where it lives, what
    it is, whether the capability actually exists, and where its chain is recorded.
    """

    document = skill.as_dict() if hasattr(skill, "as_dict") else dict(skill)
    status = str(document.get("status", "available"))
    entry: dict[str, Any] = {
        "skill_id": str(document["skill_id"]),
        "skill_type": str(document["skill_type"]),
        "version": str(document["version"]),
        "slot": slot,
        "status": status,
        "available": status == "available",
        "path": member_paths["skill.json"],
        "documentation": member_paths["SKILL.md"],
        "provenance_reference": f"{provenance_member}#/skills/",
        "capabilities": list(document.get("capabilities", ())),
        "outputs": list(document.get("outputs", ())),
        "source_kind": str(document["provenance"]["source_kind"]),
        "source_asset": str(document["provenance"]["source_ref"]),
    }
    if status != "available":
        entry["reason"] = str(document.get("reason", "")) or "no reason recorded"
    return entry


__all__ = [
    "NO_ASSET",
    "REQUIRED_FIELD_KEYS",
    "FieldTrace",
    "PackageProvenance",
    "SkillTrace",
    "attribute_fields",
    "build_skill_traces",
    "modules_for_skill_type",
    "skill_manifest_entry",
    "skill_types_for_module",
]
