"""Creator Skill Factory architecture (Phase C0.3).

Classifies, composes and generates the *skills* a Creator Agent is built from::

    "create a finance xiaohongshu creator"
              |
              v
    SkillComposer  ->  SkillBundle  ->  (later) Lobster Shared Skill Library
              |                             |
        SkillRegistry                 Creator Instance loads the bundle
              |
        creator_skill.schema.json

**A skill is a declared capability, never executable code.** A skill states what a
Creator Agent *can do* and what it *needs*; it carries no prompt, no model call,
and no runtime code. That is enforced by schema shape and by semantic checks.

This phase defines the architecture only. It does not deploy anything, call
Lobster, upload a skill, generate content, or invoke a model.

Modules
-------

``model``
    :class:`CreatorSkill`, :class:`SkillBundle`, :class:`CreatorRequest`,
    :class:`SkillProvenance` and the other immutable value objects.
``taxonomy``
    The seven skill types and the composition skeleton between them.
``schema``
    The JSON Schema, generated from the model's own vocabularies.
``registry``
    :class:`SkillRegistry` - register, resolve, validate dependencies, list.
``composition``
    :class:`SkillComposer` - a request in, a verified bundle out, with reasons.
``catalog``
    The shipped thirteen-skill catalog, each bound to a registered asset.
``provenance``
    Source and version records. A skill with no source is invalid.
``validation``
    Schema, semantic, provenance and isolation checks.
``errors``
    Skill error types, all extending the contract error.
"""

from .catalog import (
    CATALOG_TIMESTAMP,
    CATALOG_VERSION,
    DEFAULT_SKILL_CATALOG,
    catalog_asset_references,
    catalog_document,
)
from .composition import (
    DOMAIN_MATCH_BONUS,
    INCOMPATIBLE_PENALTY,
    PLATFORM_MATCH_BONUS,
    STYLE_MATCH_BONUS,
    SkillComposer,
    SkillScore,
    compose,
    compose_bundle_id,
    score_skill,
)
from .errors import (
    SkillCompositionError,
    SkillDependencyError,
    SkillError,
    SkillIsolationError,
    SkillProvenanceError,
    SkillRegistryError,
    SkillSchemaError,
)
from .model import (
    DEPENDENCY_KINDS,
    PROVENANCE_SOURCES,
    SKILL_STATUSES,
    CompositionResult,
    CreatorRequest,
    CreatorSkill,
    SkillBundle,
    SkillCompatibility,
    SkillDependency,
    SkillProvenance,
    SkillSelection,
)
from .provenance import (
    CONFIDENCE_BY_SOURCE,
    REQUIRED_SKILL_PROVENANCE_KEYS,
    assert_provenance_keys_complete,
    assert_source_registered,
    build_skill_provenance,
    bundle_provenance,
)
from .registry import (
    DependencyReport,
    SkillRegistry,
    VERSION_SEPARATOR,
    skill_from_document,
)
from .schema import (
    SCHEMA_FILENAME,
    SKILL_SCHEMA_VERSION,
    build_schema,
    load_document,
    minimum_capabilities,
    schema_keys,
    validate_schema_document,
    write_schema,
)
from .taxonomy import (
    MINIMUM_CAPABILITIES,
    OPTIONAL_SKILL_TYPES,
    PLATFORM_SPECIFIC_TYPES,
    REQUIRED_SKILL_TYPES,
    SKILL_TYPES,
    SKILL_TYPE_NAMES,
    SKILL_TYPE_ORDER,
    SkillType,
    composition_order,
    is_known_skill_type,
    prior_types,
    skill_type,
    taxonomy_document,
)
from .validation import (
    SKILL_FORBIDDEN_MODULES,
    SKILL_ISOLATION_KEYS,
    SKILL_PROMPT_KEYS,
    SKILL_PROMPT_PHRASES,
    SkillValidationReport,
    assert_no_model_call,
    assert_no_prompt,
    assert_no_runtime_code,
    assert_provenance_present,
    validate_document,
    validate_isolation,
    validate_provenance,
    validate_schema,
    validate_semantics,
    validate_skill,
)

__all__ = [
    "CATALOG_TIMESTAMP",
    "CATALOG_VERSION",
    "CONFIDENCE_BY_SOURCE",
    "CompositionResult",
    "CreatorRequest",
    "CreatorSkill",
    "DEFAULT_SKILL_CATALOG",
    "DEPENDENCY_KINDS",
    "DOMAIN_MATCH_BONUS",
    "DependencyReport",
    "INCOMPATIBLE_PENALTY",
    "MINIMUM_CAPABILITIES",
    "OPTIONAL_SKILL_TYPES",
    "PLATFORM_MATCH_BONUS",
    "PLATFORM_SPECIFIC_TYPES",
    "PROVENANCE_SOURCES",
    "REQUIRED_SKILL_PROVENANCE_KEYS",
    "REQUIRED_SKILL_TYPES",
    "SCHEMA_FILENAME",
    "SKILL_FORBIDDEN_MODULES",
    "SKILL_ISOLATION_KEYS",
    "SKILL_PROMPT_KEYS",
    "SKILL_PROMPT_PHRASES",
    "SKILL_SCHEMA_VERSION",
    "SKILL_STATUSES",
    "SKILL_TYPES",
    "SKILL_TYPE_NAMES",
    "SKILL_TYPE_ORDER",
    "STYLE_MATCH_BONUS",
    "SkillBundle",
    "SkillCompatibility",
    "SkillComposer",
    "SkillCompositionError",
    "SkillDependency",
    "SkillDependencyError",
    "SkillError",
    "SkillIsolationError",
    "SkillProvenance",
    "SkillProvenanceError",
    "SkillRegistry",
    "SkillRegistryError",
    "SkillSchemaError",
    "SkillScore",
    "SkillSelection",
    "SkillType",
    "SkillValidationReport",
    "VERSION_SEPARATOR",
    "assert_no_model_call",
    "assert_no_prompt",
    "assert_no_runtime_code",
    "assert_provenance_keys_complete",
    "assert_provenance_present",
    "assert_source_registered",
    "build_schema",
    "build_skill_provenance",
    "bundle_provenance",
    "catalog_asset_references",
    "catalog_document",
    "compose",
    "compose_bundle_id",
    "composition_order",
    "is_known_skill_type",
    "load_document",
    "minimum_capabilities",
    "prior_types",
    "schema_keys",
    "score_skill",
    "skill_from_document",
    "skill_type",
    "taxonomy_document",
    "validate_document",
    "validate_isolation",
    "validate_provenance",
    "validate_schema",
    "validate_schema_document",
    "validate_semantics",
    "validate_skill",
    "write_schema",
]
