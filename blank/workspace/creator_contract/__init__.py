"""Creator Instance Contract layer.

An instance is *configuration*, never runtime. This package freezes what one
Creator Agent instance is made of, validates that composition, and provides a
projection from the existing blank template.

Layers
------

``errors``
    :class:`CreatorContractError`, a subclass of the project's existing
    :class:`core.errors.ArtifactValidationError` so callers that already catch
    artifact errors keep working.
``artifacts``
    The eight module filenames, path helpers, canonical JSON serialisation, and
    a dependency-free emitter/parser for the JSON-subset document form.
``validation``
    Three checks: ``validate_schema`` (shape), ``validate_dependencies``
    (cross-module references), ``validate_isolation`` (an instance may not
    contain code, model calls, crawling, or publishing).
``authoring``
    Builders producing a minimal valid instance, so tests and later phases do
    not hand-roll documents.
``template_projection``
    Projects the blank template's own configuration into the contract, so the
    contract is proven against real content rather than invented.

This package opens no network connection and imports nothing from ``runtime``,
``production``, ``risk_evaluation``, ``workflows``, or ``multimodal_creator``.
"""

from .artifacts import (
    ARTIFACT_CONTRACT_VERSION,
    MODULE_FILES,
    MODULE_NAMES,
    YAML_FILENAME,
    canonical_json,
    contract_schema_path,
    default_instance_dir,
    emit_document,
    instance_dir,
    module_filename,
    module_path,
    parse_document,
    read_instance,
    write_instance,
)
from .authoring import (
    build_blank_instance,
    build_generation,
    build_identity,
    build_provenance,
    build_publishing,
    build_risk_policy,
    build_source,
    build_text_rules,
    build_visual_rules,
    minimal_instance,
)
from .errors import (
    CreatorContractDependencyError,
    CreatorContractError,
    CreatorContractIsolationError,
    CreatorContractSchemaError,
)
from .validation import (
    CONTRACT_VERSION,
    ISOLATION_FORBIDDEN_KEYS,
    PROMPT_FORBIDDEN_KEYS,
    ISOLATION_FORBIDDEN_MODULES,
    IsolationReport,
    assert_no_generation_prompt,
    assert_no_runtime_code,
    assert_provenance_complete,
    assert_risk_policy_not_empty,
    assert_visual_rules_reference_only,
    load_contract_schema,
    validate,
    validate_dependencies,
    validate_isolation,
    validate_schema,
)
from .template_projection import (
    ProjectionReport,
    project_blank_template,
    resolve_repository_template_root,
    resolve_template_root,
    write_projected_instance,
)

__all__ = [
    "ARTIFACT_CONTRACT_VERSION",
    "CONTRACT_VERSION",
    "ISOLATION_FORBIDDEN_KEYS",
    "ISOLATION_FORBIDDEN_MODULES",
    "MODULE_FILES",
    "MODULE_NAMES",
    "PROMPT_FORBIDDEN_KEYS",
    "CreatorContractDependencyError",
    "CreatorContractError",
    "CreatorContractIsolationError",
    "CreatorContractSchemaError",
    "IsolationReport",
    "ProjectionReport",
    "YAML_FILENAME",
    "assert_no_generation_prompt",
    "assert_no_runtime_code",
    "assert_provenance_complete",
    "assert_risk_policy_not_empty",
    "assert_visual_rules_reference_only",
    "build_blank_instance",
    "build_generation",
    "build_identity",
    "build_provenance",
    "build_publishing",
    "build_risk_policy",
    "build_source",
    "build_text_rules",
    "build_visual_rules",
    "canonical_json",
    "contract_schema_path",
    "default_instance_dir",
    "emit_document",
    "instance_dir",
    "load_contract_schema",
    "minimal_instance",
    "module_filename",
    "module_path",
    "parse_document",
    "project_blank_template",
    "read_instance",
    "resolve_repository_template_root",
    "resolve_template_root",
    "validate",
    "validate_dependencies",
    "validate_isolation",
    "validate_schema",
    "write_instance",
    "write_projected_instance",
]
