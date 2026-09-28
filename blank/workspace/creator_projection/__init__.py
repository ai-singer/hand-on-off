"""Creator Instance Projection layer (Phase C0.2).

Turns existing Creator assets into a Creator Instance that conforms to the C0.1
contract::

    Existing Assets  ->  Projection  ->  Creator Instance Artifact

This layer does **not** create a creator, generate content, or run an agent. It
performs structural conversion from declared assets into the contract's eight
modules, and it is explicit about what does not exist.

Modules
-------

``assets.yaml``
    The asset registry. Every projection input comes from here; no path is
    hard-coded in Python.
``asset_registry``
    Validated access to the registry, plus typed reads.
``yaml_subset``
    The dependency-free YAML-subset reader shared by the registry and the M5
    profile.
``markdown_parser``
    Markdown -> ordered sections, preserving original text. Structure only: no
    summarising, no rewriting, no persona generation.
``mapper``
    Asset -> contract module mappers, plus :func:`project_instance` and
    :func:`write_instance`.
``provenance``
    Field-level provenance. Any field that cannot be traced fails validation.
``validation``
    Projection checks on top of the contract checks, including the guard against
    claiming a capability that does not exist.
``errors``
    Projection error types, all extending the contract error.
"""

from .asset_registry import (
    ASSET_STATUSES,
    ASSET_TYPES,
    REGISTRY_FILENAME,
    Asset,
    AssetRegistry,
)
from .errors import (
    ProjectionAssetError,
    ProjectionAssetUnavailableError,
    ProjectionCapabilityError,
    ProjectionError,
    ProjectionParseError,
    ProjectionProvenanceError,
)
from .mapper import (
    CONTRACT_DOMAINS,
    CONTRACT_PLATFORMS,
    GENERATION_ABSENT_REASON,
    GENERATION_INPUTS,
    PUBLISHING_ABSENT_REASON,
    SOURCED_MODULES,
    ModuleProjection,
    ProjectionNote,
    ProjectionResult,
    project_generation,
    project_identity,
    project_instance,
    project_publishing,
    project_risk_policy,
    project_source,
    project_text_rules,
    project_visual_rules,
    write_instance,
)
from .markdown_parser import (
    MarkdownDocument,
    MarkdownSection,
    parse_frontmatter,
    parse_markdown,
    section_titles,
    sections_as_dicts,
)
from .provenance import (
    DECLARATION_CONFIDENCE,
    DEFAULT_TIMESTAMP,
    PROJECTION_METHODS,
    REQUIRED_PROVENANCE_KEYS,
    SUBSTITUTION_CONFIDENCE,
    FieldProvenance,
    ProvenanceBuilder,
    assert_fields_traceable,
    utc_now,
)
from .validation import (
    GENERATION_TOKENS,
    assert_no_generation_capability,
    assert_no_phantom_capability,
    assert_no_runtime_code,
    assert_projection_provenance,
    assert_provenance_keys_complete,
    assert_registry_consistency,
    validate_projection,
)
from .yaml_subset import parse_yaml_subset

__all__ = [
    "ASSET_STATUSES",
    "ASSET_TYPES",
    "Asset",
    "AssetRegistry",
    "CONTRACT_DOMAINS",
    "CONTRACT_PLATFORMS",
    "DECLARATION_CONFIDENCE",
    "DEFAULT_TIMESTAMP",
    "GENERATION_ABSENT_REASON",
    "GENERATION_INPUTS",
    "GENERATION_TOKENS",
    "FieldProvenance",
    "MarkdownDocument",
    "MarkdownSection",
    "ModuleProjection",
    "PROJECTION_METHODS",
    "PUBLISHING_ABSENT_REASON",
    "ProjectionAssetError",
    "ProjectionAssetUnavailableError",
    "ProjectionCapabilityError",
    "ProjectionError",
    "ProjectionNote",
    "ProjectionParseError",
    "ProjectionProvenanceError",
    "ProjectionResult",
    "ProvenanceBuilder",
    "REGISTRY_FILENAME",
    "REQUIRED_PROVENANCE_KEYS",
    "SOURCED_MODULES",
    "SUBSTITUTION_CONFIDENCE",
    "assert_fields_traceable",
    "assert_no_generation_capability",
    "assert_no_phantom_capability",
    "assert_no_runtime_code",
    "assert_projection_provenance",
    "assert_provenance_keys_complete",
    "assert_registry_consistency",
    "parse_frontmatter",
    "parse_markdown",
    "parse_yaml_subset",
    "project_generation",
    "project_identity",
    "project_instance",
    "project_publishing",
    "project_risk_policy",
    "project_source",
    "project_text_rules",
    "project_visual_rules",
    "section_titles",
    "sections_as_dicts",
    "utc_now",
    "validate_projection",
    "write_instance",
]
