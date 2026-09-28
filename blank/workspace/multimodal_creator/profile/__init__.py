"""Visual Creator Profile layer (Phase M5).

The engineering bridge from M4's visual distillation output to a configuration
asset a Creator Instance Factory can consume::

    M4  CreatorStrategyPattern + VisualGrammar + VisualConstraint
             │
             ▼
    M5  VisualCreatorProfile
             │  profile JSON (complete, traceable)
             └─ visual_profile.yaml (flattened, factory-facing)

This layer adds **no** visual understanding. Every field is derived from an M4
artifact, and every field records which artifact it came from. It contains no
generation logic: prompts, model references, image data, and deployment settings
are rejected by the schema's shape *and* by name.

Modules
-------

``model``
    :class:`VisualCreatorProfile` and its five parts, plus
    :class:`FieldProvenance`.
``schema``
    The JSON Schema, generated from the model's own vocabularies so the two
    cannot drift.
``pattern_to_profile``
    The derivation. No template, no creator name, no colour, no prompt.
``validation``
    Schema, provenance completeness, and the three prohibitions the phase brief
    names: unsourced rules, mixed-in generation logic, and creator-specific
    override of universal structure.
``serialization``
    JSON and the dependency-free ``visual_profile.yaml`` emitter, plus the
    factory-facing config.
"""

from .model import (
    ATTENTION_SLOTS,
    COMPLEXITY_LEVELS,
    DERIVATIONS,
    HIERARCHY_TIERS,
    PROFILE_VERSION,
    PROVENANCE_FAMILIES,
    SOURCE_PHASES,
    VISUAL_LANGUAGES,
    AttentionStrategy,
    CompositionRules,
    ConstraintLayer,
    FieldProvenance,
    HierarchyPattern,
    ProfileError,
    VisualCreatorProfile,
    VisualIdentity,
)
from .pattern_to_profile import (
    LANGUAGE_BY_ATTENTION,
    MappingError,
    MappingEvidence,
    PatternToProfileMapper,
    pattern_to_profile,
)
from .schema import (
    FORBIDDEN_KEYS,
    SCHEMA_FILENAME,
    build_schema,
    schema_keys,
    validate_schema_document,
    write_schema,
)
from .serialization import (
    YAML_FILENAME,
    SerializationError,
    WrittenProfile,
    factory_config,
    from_dict,
    from_json,
    parse_emitted_yaml,
    read_json,
    to_json,
    to_yaml,
    write_json,
    write_profile_bundle,
    write_yaml,
)
from .validation import (
    ValidationError,
    assert_no_contradiction,
    assert_no_generation_logic,
    assert_no_universal_override,
    assert_provenance_complete,
    assert_rules_are_sourced,
    assert_slots_are_contiguous,
    validate_document,
    validate_profile,
    validation_summary,
)

__all__ = [
    "ATTENTION_SLOTS",
    "COMPLEXITY_LEVELS",
    "DERIVATIONS",
    "FORBIDDEN_KEYS",
    "HIERARCHY_TIERS",
    "LANGUAGE_BY_ATTENTION",
    "PROFILE_VERSION",
    "PROVENANCE_FAMILIES",
    "SCHEMA_FILENAME",
    "SOURCE_PHASES",
    "VISUAL_LANGUAGES",
    "YAML_FILENAME",
    "AttentionStrategy",
    "CompositionRules",
    "ConstraintLayer",
    "FieldProvenance",
    "HierarchyPattern",
    "MappingError",
    "MappingEvidence",
    "PatternToProfileMapper",
    "ProfileError",
    "SerializationError",
    "ValidationError",
    "VisualCreatorProfile",
    "VisualIdentity",
    "WrittenProfile",
    "assert_no_contradiction",
    "assert_no_generation_logic",
    "assert_no_universal_override",
    "assert_provenance_complete",
    "assert_rules_are_sourced",
    "assert_slots_are_contiguous",
    "build_schema",
    "factory_config",
    "from_dict",
    "from_json",
    "parse_emitted_yaml",
    "pattern_to_profile",
    "read_json",
    "schema_keys",
    "to_json",
    "to_yaml",
    "validate_document",
    "validate_profile",
    "validate_schema_document",
    "validation_summary",
    "write_json",
    "write_profile_bundle",
    "write_schema",
    "write_yaml",
]
