"""Skill Bundle → Creator Instance mapping layer (Phase C0.4-A).

C0.2 projects a Creator Instance from assets. C0.3 composes a Skill Bundle from the
same assets. Until now nothing connected them::

    SkillBundle
        |
        v  creator_mapping
        |
    creator_instance artifact

This layer is a **configuration bridge and nothing else**. It reads the skill
registry, resolves each skill's bound asset through the C0.2 asset registry,
applies a declared field rule per target path, and emits a contract-valid
instance. It does not touch the runtime, generate content, call a model, or reach
the network.

Two rules hold the layer together:

* **A skill never copies a field.** A skill declares a capability and names an
  asset; every instance field is derived from that asset and cites the rule that
  derived it.
* **An absent capability is declared, never enabled.** Generation and publishing
  are unimplemented in this repository, so mapping emits them disabled with a
  machine-readable reason, and :mod:`creator_mapping.validation` rejects an
  instance that claims otherwise.

Modules
-------

``rules``
    The mapping contract: skill type → module, and one :class:`FieldRule` per
    target field, each with a stable ``RULE_*`` id.
``resolver``
    Resolves a bundle's skills to their bound assets via the C0.2 registry. An
    unavailable asset resolves to a declared absence, not an error.
``mapper``
    :func:`map_bundle_to_instance` and :func:`bundle_instance_diff`.
``provenance``
    One :class:`FieldMapping` per field: skill, asset, version, rule.
``validation``
    Four layers: contract, skills, mapping completeness/honesty, provenance.
``errors``
    Mapping error types, all extending the contract error.
"""

from .errors import (
    MappingAssetError,
    MappingCompletenessError,
    MappingError,
    MappingHonestyError,
    MappingProvenanceError,
    MappingRuleError,
)
from .mapper import (
    CONTRACT_DOMAINS,
    CONTRACT_LANGUAGES,
    CONTRACT_PLATFORMS,
    GENERATION_INPUTS,
    MISSING_IDENTITY_NAME,
    PLATFORM_ASPECT_RATIOS,
    BundleInstanceMapper,
    MappedInstance,
    ModuleMapping,
    bundle_instance_diff,
    map_bundle_to_instance,
    write_mapped_instance,
)
from .provenance import (
    DEFAULT_TIMESTAMP,
    NO_ASSET,
    REQUIRED_MAPPING_KEYS,
    FieldMapping,
    MappingProvenanceBuilder,
    assert_fields_mapped,
    assert_no_unknown_rules,
)
from .resolver import (
    DERIVABLE_SOURCE_KINDS,
    LOCATION_SOURCE_KINDS,
    BundleAssetResolver,
    BundleAssets,
    ResolvedAsset,
)
from .rules import (
    CAPABILITY_MODULES,
    FIELD_MODES,
    FIELD_RULES,
    MAPPED_MODULES,
    MODULE_SKILL_RULES,
    REQUIRED_PATHS,
    SKILL_MODULE_RULES,
    FieldRule,
    rule_by_id,
    rule_for_path,
    rule_ids,
    rules_for_module,
    unavailable_rules,
)
from .validation import (
    MappingValidationReport,
    assert_every_field_traceable,
    describe_rules,
    validate_bundle_skills,
    validate_contract_layer,
    validate_mapping,
    validate_mapping_provenance,
    validate_mapping_result,
    validate_skills,
)

__all__ = [
    "BundleAssetResolver",
    "BundleAssets",
    "BundleInstanceMapper",
    "CAPABILITY_MODULES",
    "CONTRACT_DOMAINS",
    "CONTRACT_LANGUAGES",
    "CONTRACT_PLATFORMS",
    "DEFAULT_TIMESTAMP",
    "DERIVABLE_SOURCE_KINDS",
    "FIELD_MODES",
    "FIELD_RULES",
    "FieldMapping",
    "FieldRule",
    "GENERATION_INPUTS",
    "LOCATION_SOURCE_KINDS",
    "MAPPED_MODULES",
    "MISSING_IDENTITY_NAME",
    "MODULE_SKILL_RULES",
    "MappedInstance",
    "MappingAssetError",
    "MappingCompletenessError",
    "MappingError",
    "MappingHonestyError",
    "MappingProvenanceBuilder",
    "MappingProvenanceError",
    "MappingRuleError",
    "MappingValidationReport",
    "ModuleMapping",
    "NO_ASSET",
    "PLATFORM_ASPECT_RATIOS",
    "REQUIRED_MAPPING_KEYS",
    "REQUIRED_PATHS",
    "ResolvedAsset",
    "SKILL_MODULE_RULES",
    "assert_every_field_traceable",
    "assert_fields_mapped",
    "assert_no_unknown_rules",
    "bundle_instance_diff",
    "describe_rules",
    "map_bundle_to_instance",
    "rule_by_id",
    "rule_for_path",
    "rule_ids",
    "rules_for_module",
    "unavailable_rules",
    "validate_bundle_skills",
    "validate_contract_layer",
    "validate_mapping",
    "validate_mapping_provenance",
    "validate_mapping_result",
    "validate_skills",
    "write_mapped_instance",
]
