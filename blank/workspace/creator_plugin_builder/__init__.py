"""Creator Skill Library infrastructure (Phase C0.5).

The deliverable of this phase is not a Creator Instance. It is a **Skill Library**: a
set of skills uploaded once that then serves every creator anyone asks for.

```text
                Lobster Shared Skill Library
                            |
        ┌───────────────────┴───────────────────┐
        |                                       |
  Universal Creator Skills                Meta Skills
  (how to do it, domain-free)        (how to build domain plugins)
        |                                       |
        |                            domain-plugin-builder
        |                            domain-plugin-validator
        |                            skill-composer
        |                                       |
        └───────────────────┬───────────────────┘
                            |
                            v
                  Generated Domain Plugins
              (produced at run time by the builder;
               NOT part of the base library)
```

So a user can say *"I want a finance creator"*, the library's
``domain-plugin-builder`` skill produces ``domain_finance_plugin``, and Lobster
configures the agent from it. **Ten universal skills plus N domain plugins equals
unlimited creator configurations** — instead of a hundred domains meaning a hundred
parallel skill sets.

Modules
-------

``model``
    :class:`DomainPlugin`, :class:`RuleBinding`, :class:`DistillationStage` and the
    error types. Also the two library boundaries and the unified distillation
    protocol.
``library``
    The library's own declarations: the universal Creator Skills and the three meta
    skills, as data a builder can bind to and a validator can scan.
``schema``
    The domain plugin JSON Schema, generated from the model's vocabularies.
``registry``
    The domain catalog — finance, sports, technology — and the registry over it.
``builder``
    :func:`build_domain_plugin` and :func:`load_domain_request`:
    ``domain_request.yaml`` in, a domain plugin out.
``validator``
    The six checks, including the one this phase exists for: a universal skill may
    not carry domain knowledge.
``provenance``
    ``domain_request → domain_catalog → asset → rule``, per rule.

What this package is not
------------------------

It is not a runtime and not a deployment layer. It runs no agent, executes no
workflow, calls no model, generates no content, and never contacts Lobster. It does
not build a Creator Instance: instances are composed by the layers below, and that is
deliberately not this phase's product.

This package imports nothing from ``runtime``, ``production``, ``workflows``,
``risk_evaluation``, ``multimodal_creator``, ``distillation_core``, or ``plugins``.
"""

from __future__ import annotations

from .builder import (
    DEFAULT_PLUGIN_DIR,
    GENERATED_BY,
    PERSONA_ASSET,
    PLUGIN_SUFFIX,
    PROVENANCE_SUFFIX,
    BuildResult,
    build_domain_plugin,
    build_domain_plugins,
    describe_domain,
    domain_request_from_document,
    load_domain_request,
    plugin_path,
    request_digest,
    resolve_workspace_root,
    write_domain_plugin,
)
from .library import (
    LIBRARY_VERSION,
    META_SKILL_INPUTS,
    META_SKILL_SUMMARIES,
    UNIVERSAL_SKILL_SUMMARIES,
    SkillDeclaration,
    all_declarations,
    declaration,
    library_document,
    meta_declarations,
    skill_composition,
    skill_declarations,
    universal_declarations,
)
from .model import (
    ABSENCE_MARKER,
    DEFAULT_TIMESTAMP,
    DOMAIN_MARKERS,
    ERROR_CODES,
    FORBIDDEN_MODULES,
    META_SKILLS,
    NOT_RECORDED,
    PLUGIN_CORE_SKILLS,
    PLUGIN_FORMAT_VERSION,
    PLUGIN_SLOTS,
    PROMPT_KEYS,
    PROMPT_PHRASES,
    PROTOCOL_STAGES,
    RUNTIME_KEYS,
    RUNTIME_SUFFIXES,
    UNIVERSAL_SKILLS,
    DistillationStage,
    DomainIdentity,
    DomainNotFoundError,
    DomainPlugin,
    DomainRequest,
    DomainRequestError,
    PluginBuilderError,
    PluginCapabilityError,
    PluginIsolationError,
    PluginLayerError,
    PluginLibraryError,
    PluginProvenance,
    PluginProvenanceError,
    PluginProtocolError,
    PluginRegistryError,
    PluginRuleError,
    PluginSchemaError,
    RuleBinding,
    RuleStatus,
)
from .provenance import (
    CHAIN_SOURCES,
    PROVENANCE_CHAIN,
    asset_usage,
    provenance_document,
    rule_chains,
    skill_usage,
    untraced_rules,
)
from .registry import (
    CATALOG_VERSION,
    DECLARED_ASSETS,
    DECLARED_SKILLS,
    DEFAULT_DOMAIN_CATALOG,
    DEFAULT_REQUIREMENTS,
    GENERAL_RISK_REFERENCE,
    GENERAL_STRUCTURE_TEMPLATES,
    GENERAL_TEXT_RULES,
    GENERAL_VISUAL_PROFILE,
    TAXONOMY_REASON,
    DomainEntry,
    DomainRegistry,
    catalog_document,
    catalog_domains,
    default_registry,
    protocol_document,
)
from .schema import (
    REQUIRED_KEYS,
    ROOT_NAME,
    RULE_STATUSES,
    SCHEMA_FILENAME,
    build_schema,
    load_schema,
    schema_keys,
    schema_path,
    validate_schema_document,
    write_schema,
)
from .validator import (
    LayerReport,
    PluginValidationReport,
    audit_layers,
    contains_domain_marker,
    describe_validation,
    validate_isolation,
    validate_layers,
    validate_plugin,
    validate_plugins,
    validate_protocol,
    validate_provenance,
    validate_schema,
    validate_usability,
)

__all__ = [
    "ABSENCE_MARKER",
    "BuildResult",
    "CATALOG_VERSION",
    "CHAIN_SOURCES",
    "DECLARED_ASSETS",
    "DECLARED_SKILLS",
    "DEFAULT_DOMAIN_CATALOG",
    "DEFAULT_PLUGIN_DIR",
    "DEFAULT_REQUIREMENTS",
    "DEFAULT_TIMESTAMP",
    "DOMAIN_MARKERS",
    "DistillationStage",
    "DomainEntry",
    "DomainIdentity",
    "DomainNotFoundError",
    "DomainPlugin",
    "DomainRegistry",
    "DomainRequest",
    "DomainRequestError",
    "ERROR_CODES",
    "FORBIDDEN_MODULES",
    "GENERATED_BY",
    "GENERAL_RISK_REFERENCE",
    "GENERAL_STRUCTURE_TEMPLATES",
    "GENERAL_TEXT_RULES",
    "GENERAL_VISUAL_PROFILE",
    "LayerReport",
    "LIBRARY_VERSION",
    "META_SKILLS",
    "META_SKILL_INPUTS",
    "META_SKILL_SUMMARIES",
    "NOT_RECORDED",
    "PERSONA_ASSET",
    "PLUGIN_CORE_SKILLS",
    "PLUGIN_FORMAT_VERSION",
    "PLUGIN_SLOTS",
    "PLUGIN_SUFFIX",
    "PROMPT_KEYS",
    "PROMPT_PHRASES",
    "PROTOCOL_STAGES",
    "PROVENANCE_CHAIN",
    "PROVENANCE_SUFFIX",
    "PluginBuilderError",
    "PluginCapabilityError",
    "PluginIsolationError",
    "PluginLayerError",
    "PluginLibraryError",
    "PluginProvenance",
    "PluginProvenanceError",
    "PluginProtocolError",
    "PluginRegistryError",
    "PluginRuleError",
    "PluginSchemaError",
    "PluginValidationReport",
    "REQUIRED_KEYS",
    "ROOT_NAME",
    "RULE_STATUSES",
    "RUNTIME_KEYS",
    "RUNTIME_SUFFIXES",
    "RuleBinding",
    "RuleStatus",
    "SCHEMA_FILENAME",
    "SkillDeclaration",
    "TAXONOMY_REASON",
    "UNIVERSAL_SKILLS",
    "UNIVERSAL_SKILL_SUMMARIES",
    "all_declarations",
    "asset_usage",
    "audit_layers",
    "build_domain_plugin",
    "build_domain_plugins",
    "build_schema",
    "catalog_document",
    "catalog_domains",
    "contains_domain_marker",
    "declaration",
    "default_registry",
    "describe_domain",
    "describe_validation",
    "domain_request_from_document",
    "library_document",
    "load_domain_request",
    "load_schema",
    "meta_declarations",
    "plugin_path",
    "protocol_document",
    "provenance_document",
    "request_digest",
    "resolve_workspace_root",
    "rule_chains",
    "schema_keys",
    "schema_path",
    "skill_composition",
    "skill_declarations",
    "skill_usage",
    "universal_declarations",
    "untraced_rules",
    "validate_isolation",
    "validate_layers",
    "validate_plugin",
    "validate_plugins",
    "validate_protocol",
    "validate_provenance",
    "validate_schema",
    "validate_schema_document",
    "validate_usability",
    "write_domain_plugin",
    "write_schema",
]
