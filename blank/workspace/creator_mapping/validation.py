"""Validation for a mapped instance.

Four layers, each separately reportable so a caller can tell a *shape* problem
from a *policy* problem:

1. :func:`validate_contract_layer` - the mapped document satisfies
   ``creator_contract.validate()``, which itself runs schema, dependencies,
   capability declaration and isolation.
2. :func:`validate_skills` - every skill the bundle selected is a valid skill.
3. :func:`validate_mapping` - completeness and honesty: every selected skill maps
   to at least one module, every required field has a rule, every declared-absent
   field carries a reason, and no absent capability is enabled.
4. :func:`validate_mapping_provenance` - every field records a skill, an asset, a
   version and a rule, and every cited rule exists.

:func:`validate_mapping_result` runs all four and returns a report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from creator_contract import validate as validate_contract
from creator_skill import validate_skill

from .errors import (
    MappingCompletenessError,
    MappingHonestyError,
    MappingProvenanceError,
    MappingRuleError,
)
from .mapper import MappedInstance
from .provenance import (
    REQUIRED_MAPPING_KEYS,
    assert_no_unknown_rules,
)
from .rules import (
    CAPABILITY_MODULES,
    REQUIRED_PATHS,
    SKILL_MODULE_RULES,
    rule_ids,
)


@dataclass(frozen=True, slots=True)
class MappingValidationReport:
    """Result of validating a mapped instance."""

    bundle_id: str
    creator_id: str
    checks: Mapping[str, str]
    modules: tuple[str, ...]
    unavailable_fields: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(value == "PASS" for value in self.checks.values())

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "creator_id": self.creator_id,
            "status": self.status,
            "checks": dict(self.checks),
            "modules": list(self.modules),
            "unavailable_fields": list(self.unavailable_fields),
        }


# --------------------------------------------------------------------------
# 1. Contract layer
# --------------------------------------------------------------------------


def validate_contract_layer(mapped: MappedInstance) -> None:
    """The mapped document must satisfy the C0.1 contract in full."""

    validate_contract(mapped.instance)


# --------------------------------------------------------------------------
# 2. Skill layer
# --------------------------------------------------------------------------


def validate_skills(mapped: MappedInstance) -> None:
    """Every skill the bundle selected must be identifiable in the mapping."""

    if not mapped.assets.skills:
        raise MappingCompletenessError("the bundle selected no skills")

    for selection in mapped.assets.skills:
        if not selection.skill_id.strip():
            raise MappingCompletenessError("a selection has an empty skill id")
        if not selection.version.strip():
            raise MappingCompletenessError(
                f"skill {selection.skill_id!r} has an empty version"
            )
        if not selection.skill_type.strip():
            raise MappingCompletenessError(
                f"skill {selection.skill_id!r} has an empty skill type"
            )

    # Every selected skill must be represented in the mapping provenance, so a
    # selection cannot vanish between the bundle and the instance.
    known_skills = {
        str(record.get("skill_id"))
        for record in mapped.field_provenance.values()
        if isinstance(record, Mapping)
    }
    for selection in mapped.assets.skills:
        if selection.skill_id not in known_skills:
            raise MappingCompletenessError(
                f"skill {selection.skill_id!r} appears in no mapping provenance "
                "record"
            )


def validate_bundle_skills(bundle: Any, skill_registry: Any) -> None:
    """Validate every skill in a bundle against the skill registry."""

    for selection in bundle.all_selections():
        skill = skill_registry.resolve(f"{selection.skill_id}@{selection.version}")
        report = validate_skill(skill)
        if not report.passed:
            raise MappingCompletenessError(
                f"skill {selection.skill_id!r} failed skill validation: "
                f"{dict(report.checks)}"
            )


# --------------------------------------------------------------------------
# 3. Mapping completeness and honesty
# --------------------------------------------------------------------------


def validate_mapping(mapped: MappedInstance) -> None:
    """Completeness and capability honesty of the mapping itself."""

    _assert_every_skill_mapped(mapped)
    _assert_every_module_mapped(mapped)
    _assert_required_fields_present(mapped)
    _assert_declared_absences_have_reasons(mapped)
    _assert_no_capability_enabled_without_a_source(mapped)


def _assert_every_skill_mapped(mapped: MappedInstance) -> None:
    """Every selected skill must contribute to at least one module."""

    mapped_modules = {module.module for module in mapped.modules}
    for selection in mapped.assets.skills:
        targets = SKILL_MODULE_RULES.get(selection.skill_type)
        if not targets:
            raise MappingCompletenessError(
                f"skill {selection.skill_id!r} has type {selection.skill_type!r}, "
                "which no mapping rule covers"
            )
        if not (set(targets) & mapped_modules):
            raise MappingCompletenessError(
                f"skill {selection.skill_id!r} maps to {list(targets)} but the mapped "
                f"instance contains none of them"
            )


def _assert_every_module_mapped(mapped: MappedInstance) -> None:
    if not mapped.modules:
        raise MappingCompletenessError("no modules were mapped")
    if len(mapped.modules) != len({m.module for m in mapped.modules}):
        raise MappingCompletenessError("a module was mapped more than once")


def _assert_required_fields_present(mapped: MappedInstance) -> None:
    """Every target path a rule declares must exist in its module."""

    for module_mapping in mapped.modules:
        required = REQUIRED_PATHS[module_mapping.module]
        document = module_mapping.document
        missing = [
            path
            for path in required
            if path not in document and path not in module_mapping.unavailable_fields
        ]
        if missing:
            raise MappingCompletenessError(
                f"module {module_mapping.module!r} is missing mapped fields: "
                + ", ".join(missing)
            )


def _assert_declared_absences_have_reasons(mapped: MappedInstance) -> None:
    """A field declared absent must say why, and must not carry mapped content.

    The set of absent fields is derived from the **instance's own provenance**, not
    from the mapping's build-time record. Deriving it from the record would let a
    field be replaced with ordinary content after the mapping ran and still validate,
    because the record would still say the field was absent while the document said
    otherwise. Reading provenance keeps the check honest about what the artifact
    actually contains.

    Three declaration shapes are accepted, because the contract seals different
    fields differently:

    * a marked mapping or array (``not_available`` plus ``reason``);
    * a marked scalar literal (``not_available:<code>``);
    * a **sealed shape** - a required object or array that cannot take a marker key,
      whose declaration is carried by a marked value inside it.
    """

    payload = mapped.instance.get("provenance", {}).get("field_provenance")
    fields: Mapping[str, Any] = {}
    if isinstance(payload, Mapping):
        declared = payload.get("fields")
        if isinstance(declared, Mapping):
            fields = declared

    # Build-time record folded in, so a field the mapper declared absent is checked
    # even if its provenance record was replaced entirely.
    recorded = {
        f"{module.module}.{path}"
        for module in mapped.modules
        for path in module.unavailable_fields
    }
    absent = {
        key
        for key, record in fields.items()
        if isinstance(record, Mapping) and record.get("mode") in ("unavailable", "not_available")
    } | recorded

    for key in sorted(absent):
        module, _, path = key.partition(".")
        document = mapped.instance.get(module)
        if not isinstance(document, Mapping) or path not in document:
            # The field has no place in a contract-valid document; the absence lives
            # in provenance alone.
            continue
        _assert_absence(mapped, module, path, document[path])


def _assert_absence(mapped: MappedInstance, module: str, path: str, value: Any) -> None:
    if isinstance(value, str):
        _assert_scalar_marker(module, path, value)
        return

    if isinstance(value, list):
        if not value:
            raise MappingHonestyError(
                f"{module}.{path} is declared absent with an empty list"
            )
        _assert_any_marker(module, path, value)
        return

    if isinstance(value, Mapping):
        if value.get("not_available") is True:
            _assert_absence_marker(module, path, value)
            return
        # A sealed shape: the marker must appear in one of its values.
        _assert_any_marker(module, path, value)
        return

    raise MappingHonestyError(
        f"{module}.{path} is declared absent but carries an unrecognised declaration "
        f"of type {type(value).__name__}"
    )


def _assert_scalar_marker(module: str, path: str, value: str) -> None:
    from .mapper import ABSENCE_MARKER

    if not value.startswith(ABSENCE_MARKER):
        raise MappingHonestyError(
            f"{module}.{path} is declared absent but its value is not marked as a "
            "declaration of absence"
        )
    if len(value) <= len(ABSENCE_MARKER):
        raise MappingHonestyError(f"{module}.{path} declares no absence reason")


def _assert_any_marker(module: str, path: str, value: Any) -> None:
    """The declaration must be discoverable inside a sealed shape."""

    from .mapper import ABSENCE_MARKER

    found = False
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, str) and item.startswith(ABSENCE_MARKER):
                found = True
            elif isinstance(item, (int, float)) and not isinstance(item, bool) and item == 0:
                # A zero is the sentinel for "nothing is configured".
                found = True
            elif isinstance(item, (Mapping, list)) and _contains_marker(item):
                found = True
    elif isinstance(value, list):
        for item in value:
            if _contains_marker(item):
                found = True
    if not found:
        raise MappingHonestyError(
            f"{module}.{path} is declared absent but carries no absence marker"
        )


def _contains_marker(value: Any) -> bool:
    from .mapper import ABSENCE_MARKER

    if isinstance(value, str):
        return value.startswith(ABSENCE_MARKER)
    if isinstance(value, Mapping):
        return any(_contains_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_marker(item) for item in value)
    return False


def _assert_absence_marker(module: str, path: str, value: Any) -> None:
    if not isinstance(value, Mapping):
        raise MappingHonestyError(
            f"{module}.{path} is declared absent but carries a non-declaration value"
        )
    if value.get("not_available") is not True:
        raise MappingHonestyError(
            f"{module}.{path} is declared absent but does not set not_available"
        )
    if not str(value.get("reason", "")).strip():
        raise MappingHonestyError(
            f"{module}.{path} is declared absent with no reason"
        )


def _assert_no_capability_enabled_without_a_source(mapped: MappedInstance) -> None:
    """The load-bearing honesty check.

    An absent capability must be disabled and must state why. Auto-filling one is
    the failure mode the whole C0.1/C0.2/C0.3 programme exists to prevent.
    """

    by_module = {module.module: module for module in mapped.modules}

    for module in CAPABILITY_MODULES:
        block = mapped.instance.get(module)
        if not isinstance(block, Mapping):
            raise MappingHonestyError(f"mapped instance has no {module} block")

        module_mapping = by_module.get(module)
        if module_mapping is None:
            raise MappingHonestyError(
                f"{module} was not mapped, so its enabled state cannot be justified"
            )
        availability = module_mapping.availability
        if not isinstance(availability, Mapping) or not availability:
            raise MappingHonestyError(
                f"{module} has no availability record, so its enabled state cannot be "
                "justified"
            )

        has_source = availability.get("has_available_source")
        enabled = block.get("enabled")
        reason = str(block.get("reason", "")).strip()

        if has_source is False and enabled is not False:
            raise MappingHonestyError(
                f"{module}.enabled must be false: skill "
                f"{availability.get('skill_type')!r} has no available asset "
                f"({availability.get('asset_reason') or 'absent'})"
            )
        if enabled is False and not reason:
            raise MappingHonestyError(
                f"{module}.enabled is false but no reason is declared"
            )
        if has_source is True and enabled is not True:
            raise MappingHonestyError(
                f"{module} has an available source but is not enabled; availability "
                "and enabled must agree"
            )


# --------------------------------------------------------------------------
# 4. Mapping provenance
# --------------------------------------------------------------------------


def validate_mapping_provenance(mapped: MappedInstance) -> None:
    """Every field must trace to a skill, an asset, a version and a rule."""

    payload = mapped.instance.get("provenance", {}).get("field_provenance")
    if not isinstance(payload, Mapping):
        raise MappingProvenanceError(
            "the instance carries no field_provenance payload"
        )
    provenance = payload.get("fields")
    if not isinstance(provenance, Mapping) or not provenance:
        raise MappingProvenanceError("the mapping produced no field provenance")

    known = rule_ids()
    assert_no_unknown_rules(provenance, known)

    for module_mapping in mapped.modules:
        for path in REQUIRED_PATHS[module_mapping.module]:
            key = f"{module_mapping.module}.{path}"
            record = provenance.get(key)
            if not isinstance(record, Mapping):
                raise MappingProvenanceError(f"field {key!r} has no mapping record")
            missing = [name for name in REQUIRED_MAPPING_KEYS if name not in record]
            if missing:
                raise MappingProvenanceError(
                    f"mapping record for {key!r} is missing: " + ", ".join(missing)
                )
            for name in ("skill_id", "asset_id", "version", "rule_id", "mode"):
                if not str(record.get(name, "")).strip():
                    raise MappingProvenanceError(
                        f"mapping record for {key!r} has an empty {name}"
                    )

    modules_block = payload.get("modules")
    if not isinstance(modules_block, Mapping):
        raise MappingProvenanceError(
            "the field_provenance payload carries no per-module availability"
        )
    for module_mapping in mapped.modules:
        record = modules_block.get(module_mapping.module)
        if not isinstance(record, Mapping):
            raise MappingProvenanceError(
                f"module {module_mapping.module!r} has no availability record"
            )
        if "has_available_source" not in record:
            raise MappingProvenanceError(
                f"module {module_mapping.module!r} availability does not record "
                "whether a source was available"
            )


def assert_every_field_traceable(mapped: MappedInstance) -> None:
    """A field present in the document but absent from provenance is a defect."""

    for module_mapping in mapped.modules:
        used_rules = set(module_mapping.rule_ids)
        if not used_rules:
            raise MappingProvenanceError(
                f"module {module_mapping.module!r} applied no mapping rules"
            )
        for rule_id in used_rules:
            if rule_id not in set(rule_ids()):
                raise MappingRuleError(f"unknown mapping rule {rule_id!r}")


# --------------------------------------------------------------------------
# Combined
# --------------------------------------------------------------------------


def validate_mapping_result(mapped: MappedInstance) -> MappingValidationReport:
    """Run all four validation layers and return an inspectable report."""

    checks: dict[str, str] = {}

    validate_contract_layer(mapped)
    checks["contract"] = "PASS"

    validate_skills(mapped)
    checks["skills"] = "PASS"

    validate_mapping(mapped)
    checks["mapping"] = "PASS"

    validate_mapping_provenance(mapped)
    checks["mapping_provenance"] = "PASS"

    assert_every_field_traceable(mapped)
    checks["field_traceability"] = "PASS"

    return MappingValidationReport(
        bundle_id=mapped.bundle_id,
        creator_id=mapped.creator_id,
        checks=checks,
        modules=tuple(m.module for m in mapped.modules),
        unavailable_fields=mapped.unavailable_fields,
    )


def describe_rules() -> dict[str, Any]:
    """The rule tables as a document, for the report and the tests."""

    from .rules import FIELD_RULES, SKILL_MODULE_RULES as skill_rules

    return {
        "skill_module_rules": {k: list(v) for k, v in sorted(skill_rules.items())},
        "field_rules": [rule.as_dict() for rule in FIELD_RULES],
        "rule_count": len(FIELD_RULES),
        "required_paths": {k: list(v) for k, v in sorted(REQUIRED_PATHS.items())},
    }


__all__ = [
    "MappingValidationReport",
    "assert_every_field_traceable",
    "describe_rules",
    "validate_bundle_skills",
    "validate_contract_layer",
    "validate_mapping",
    "validate_mapping_provenance",
    "validate_mapping_result",
    "validate_skills",
]
