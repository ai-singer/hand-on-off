"""The Domain Plugin Validator.

Six checks, and each one exists because something could go wrong without it:

| # | Check | Refuses |
| --- | --- | --- |
| 1 | :func:`validate_schema` | a plugin document that is not the declared shape |
| 2 | :func:`validate_protocol` | a plugin that does not implement the unified distillation protocol |
| 3 | :func:`validate_layers` | a universal skill polluted with domain knowledge |
| 4 | :func:`validate_isolation` | runtime code, a prompt, a forbidden reference |
| 5 | :func:`validate_provenance` | a rule whose origin cannot be named |
| 6 | :func:`validate_usability` | a rule no universal skill could act on |

Check 3 is the one this phase exists for. Without it, "universal skills stay
domain-free" is an intention; with it, a polluted skill is a failed build.

Checks 1–3 and 5–6 raise typed errors. :func:`validate_plugin` runs all six and
returns an inspectable report, so a caller can see the whole picture rather than the
first failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .model import (
    DOMAIN_MARKERS,
    FORBIDDEN_MODULES,
    META_SKILLS,
    PLUGIN_CORE_SKILLS,
    PLUGIN_SLOTS,
    PROMPT_KEYS,
    PROMPT_PHRASES,
    PROTOCOL_STAGES,
    RUNTIME_KEYS,
    RUNTIME_SUFFIXES,
    UNIVERSAL_SKILLS,
    DomainPlugin,
    PluginIsolationError,
    PluginLayerError,
    PluginLibraryError,
    PluginProtocolError,
    PluginProvenanceError,
    PluginRuleError,
    PluginSchemaError,
    RuleStatus,
)
from .provenance import untraced_rules
from .schema import validate_schema_document


@dataclass(frozen=True, slots=True)
class PluginValidationReport:
    """The result of validating one plugin."""

    plugin_name: str
    domain: str
    version: str
    checks: Mapping[str, str]
    findings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return all(value == "PASS" for value in self.checks.values())

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "plugin_name": self.plugin_name,
            "domain": self.domain,
            "version": self.version,
            "status": self.status,
            "checks": dict(self.checks),
        }
        if self.findings:
            document["findings"] = list(self.findings)
        return document


@dataclass(frozen=True, slots=True)
class LayerReport:
    """The result of the universal/domain separation audit."""

    universal_skills: tuple[str, ...]
    domain_skills: tuple[str, ...]
    violations: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.violations

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "universal_skill_count": len(self.universal_skills),
            "domain_skill_count": len(self.domain_skills),
            "universal_skills": list(self.universal_skills),
            "domain_skills": list(self.domain_skills),
            "violations": list(self.violations),
        }


# --------------------------------------------------------------------------
# 1. Schema
# --------------------------------------------------------------------------


def validate_schema(
    document: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Check 1: the document matches the domain plugin schema."""

    if not isinstance(document, Mapping):
        raise PluginSchemaError("a domain plugin must be an object")
    validate_schema_document(document, schema=schema)


# --------------------------------------------------------------------------
# 2. Protocol
# --------------------------------------------------------------------------


def validate_protocol(plugin: DomainPlugin) -> None:
    """Check 2: the plugin implements the unified distillation protocol.

    The stages must be present, in order, exactly once each, and each must carry this
    domain's own term for it. A plugin that renamed a stage, dropped one, or reordered
    them is not speaking the protocol, and a universal distiller could not read it.
    """

    if not isinstance(plugin, DomainPlugin):
        raise PluginProtocolError("validate_protocol requires a DomainPlugin")

    stages = tuple(stage.stage for stage in plugin.protocol_stages)
    if stages != PROTOCOL_STAGES:
        raise PluginProtocolError(
            f"plugin {plugin.plugin_name!r} does not implement the protocol in order",
            detail=(
                "expected: " + ", ".join(PROTOCOL_STAGES)
                + "; found: " + (", ".join(stages) or "(none)")
            ),
        )

    orders = tuple(stage.order for stage in plugin.protocol_stages)
    if orders != tuple(range(1, len(PROTOCOL_STAGES) + 1)):
        raise PluginProtocolError(
            f"plugin {plugin.plugin_name!r} numbers its stages inconsistently",
            detail=f"orders: {orders}",
        )

    for stage in plugin.protocol_stages:
        if not stage.domain_term.strip():
            raise PluginProtocolError(
                f"protocol stage {stage.stage!r} declares no domain term",
                detail="the protocol is universal; the vocabulary must be local",
            )
        if stage.core_skill not in PLUGIN_CORE_SKILLS:
            raise PluginLibraryError(
                f"protocol stage {stage.stage!r} binds to core skill "
                f"{stage.core_skill!r}, which the library does not declare"
            )


# --------------------------------------------------------------------------
# 3. Layers — the boundary this phase exists for
# --------------------------------------------------------------------------


def contains_domain_marker(text: str) -> tuple[str, ...]:
    """Every domain word a blob of text carries, sorted."""

    lowered = text.lower()
    return tuple(sorted({marker for marker in DOMAIN_MARKERS if marker in lowered}))


def audit_layers(
    declarations: Mapping[str, Any] | None = None,
    *,
    markers: Sequence[str] | None = None,
) -> LayerReport:
    """Audit the library's own skill declarations for domain pollution.

    Returns a report rather than raising, so a caller can see every violation at
    once. :func:`validate_layers` turns a failing report into a refusal.
    """

    from .library import skill_declarations

    active = skill_declarations() if declarations is None else dict(declarations)
    active_markers = tuple(DOMAIN_MARKERS if markers is None else markers)

    violations: list[str] = []
    universal: list[str] = []
    domain: list[str] = []

    for name, declaration in sorted(active.items()):
        layer = str(declaration.get("layer", ""))
        if layer == "meta":
            continue
        if layer != "universal":
            violations.append(f"{name}: unknown layer {layer!r}")
            continue
        universal.append(name)

        blob = _flatten(declaration)
        hits = [m for m in active_markers if m in blob]
        if hits:
            violations.append(
                f"{name}: universal skill carries domain vocabulary "
                f"({', '.join(sorted(set(hits)))})"
            )
        for key in ("domain_rules", "domain_keywords", "domain_terms"):
            if key in declaration:
                violations.append(f"{name}: universal skill declares {key!r}")

    return LayerReport(
        universal_skills=tuple(sorted(universal)),
        domain_skills=tuple(sorted(domain)),
        violations=tuple(sorted(violations)),
    )


def validate_layers(declarations: Mapping[str, Any] | None = None) -> LayerReport:
    """Check 3: refuse a library whose universal skills carry domain knowledge."""

    report = audit_layers(declarations)
    if not report.passed:
        raise PluginLayerError(
            f"{len(report.violations)} universal/domain layer violation(s)",
            detail="; ".join(report.violations[:6]),
        )
    return report


# --------------------------------------------------------------------------
# 4. Isolation
# --------------------------------------------------------------------------


def validate_isolation(plugin: DomainPlugin) -> None:
    """Check 4: no runtime, no prompt, no forbidden reference, no entry point.

    Two different questions:

    - **Does the document carry a forbidden *name*?** Checked against every key and
      every string value in the document. A rule whose slot is literally
      ``agent_loop``, or whose slot is ``loop_kind`` with the value ``"runtime"``, is
      naming runtime behaviour either way, and neither has a place in a
      configuration asset.
    - **Does the content contain a forbidden *thing*?** Prompt phrasing, a reference
      to a forbidden module, or a runtime file suffix.
    """

    document = plugin.as_dict()
    offenders: list[str] = []

    for path, key, value in _leaves(document):
        lowered_key = key.lower()
        if lowered_key in RUNTIME_KEYS:
            offenders.append(f"{path}: runtime key {key!r}")
        if lowered_key in PROMPT_KEYS:
            offenders.append(f"{path}: prompt key {key!r}")
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if lowered in RUNTIME_KEYS:
            offenders.append(f"{path}: names runtime behaviour {value!r}")
        if lowered in PROMPT_KEYS:
            offenders.append(f"{path}: names a prompt {value!r}")
        for phrase in PROMPT_PHRASES:
            if phrase in lowered:
                offenders.append(f"{path}: prompt phrase {phrase!r}")
        for module in FORBIDDEN_MODULES:
            if re.search(rf"(?<![\w-]){re.escape(module)}(?![\w-])", lowered):
                offenders.append(f"{path}: references module {module!r}")
        for suffix in RUNTIME_SUFFIXES:
            if lowered.endswith(suffix):
                offenders.append(f"{path}: runtime suffix {suffix!r}")

    if offenders:
        raise PluginIsolationError(
            f"plugin {plugin.plugin_name!r} carries {len(offenders)} isolation "
            "violation(s)",
            detail="; ".join(sorted(set(offenders))[:6]),
        )


def _leaves(document: Any) -> list[tuple[str, str, Any]]:
    """Every ``(path, key name, value)`` triple in a document.

    A list element is walked with the same path it sits at and the key name its
    parent used, so a rule inside ``source_rules[0]`` is still inspected for the key
    names it carries — ``slot``, ``core_skill`` and the rest. Returning early on a
    list would silently skip every rule in the document, which is exactly the bug
    this function had.
    """

    found: list[tuple[str, str, Any]] = []

    def walk(node: Any, path: str, key: str) -> None:
        if isinstance(node, Mapping):
            for child_key, value in node.items():
                child_path = f"{path}.{child_key}" if path else str(child_key)
                found.append((child_path, str(child_key), value))
                walk(value, child_path, str(child_key))
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                found.append((f"{path}[{index}]", key, item))
                walk(item, f"{path}[{index}]", key)

    walk(document, "", "")
    return found


def _flatten(document: Any) -> str:
    """A document's keys and string values, lowercased, for marker scanning."""

    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                parts.append(str(key))
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            parts.append(node)

    walk(document)
    return " ".join(parts).lower()


# --------------------------------------------------------------------------
# 5. Provenance
# --------------------------------------------------------------------------


def validate_provenance(plugin: DomainPlugin) -> None:
    """Check 5: every rule can name its origin, and the plugin names its own."""

    provenance = plugin.provenance
    if provenance.domain != plugin.domain:
        raise PluginProvenanceError(
            f"plugin {plugin.plugin_name!r} names domain {plugin.domain!r} but its "
            f"provenance names {provenance.domain!r}"
        )
    if not provenance.source_assets:
        raise PluginProvenanceError(
            f"plugin {plugin.plugin_name!r} names no source asset"
        )
    if not provenance.request_digest:
        raise PluginProvenanceError(
            f"plugin {plugin.plugin_name!r} records no request digest",
            detail="a generated plugin must record what generated it",
        )

    untraced = untraced_rules(plugin)
    if untraced:
        raise PluginProvenanceError(
            f"plugin {plugin.plugin_name!r} has {len(untraced)} untraced rule(s)",
            detail=", ".join(untraced[:8]),
        )

    declared = {
        rule.source_asset for slot in PLUGIN_SLOTS for rule in getattr(plugin, slot)
    }
    unlisted = declared - set(provenance.source_assets)
    if unlisted:
        raise PluginProvenanceError(
            f"plugin {plugin.plugin_name!r} reads assets its provenance omits: "
            + ", ".join(sorted(unlisted))
        )

    if set(plugin.required_core_skills) != set(provenance.core_skills):
        raise PluginProvenanceError(
            f"plugin {plugin.plugin_name!r} requires "
            f"{sorted(plugin.required_core_skills)} but its provenance records "
            f"{sorted(provenance.core_skills)}"
        )


# --------------------------------------------------------------------------
# 6. Usability
# --------------------------------------------------------------------------


def validate_usability(
    plugin: DomainPlugin,
    *,
    registered_assets: Sequence[str] | None = None,
) -> None:
    """Check 6: a universal skill could act on every rule this plugin declares.

    A rule is actionable when it binds to a declared core skill and names a real
    asset. This is the check that makes "the plugin is usable by the core" a
    measurement rather than a hope.
    """

    if not isinstance(plugin, DomainPlugin):
        raise PluginRuleError("validate_usability requires a DomainPlugin")

    known = None if registered_assets is None else set(registered_assets)

    for slot in PLUGIN_SLOTS:
        rules = getattr(plugin, slot)
        if not rules:
            raise PluginRuleError(
                f"plugin {plugin.plugin_name!r} declares no {slot}",
                detail="every rule slot must carry at least one rule",
            )
        for rule in rules:
            if rule.core_skill not in PLUGIN_CORE_SKILLS:
                raise PluginLibraryError(
                    f"{slot}.{rule.slot} binds to core skill {rule.core_skill!r}, "
                    "which the library does not declare"
                )
            if rule.core_skill in META_SKILLS:
                raise PluginLibraryError(
                    f"{slot}.{rule.slot} binds to meta skill {rule.core_skill!r}",
                    detail="a plugin is built by the meta skills, not run by them",
                )
            if not rule.source_asset:
                raise PluginRuleError(
                    f"{slot}.{rule.slot} names no source asset",
                    detail="a rule with no asset has no origin",
                )
            if known is not None and rule.source_asset not in known:
                raise PluginRuleError(
                    f"{slot}.{rule.slot} binds to asset {rule.source_asset!r}, "
                    "which this workspace's registry does not declare"
                )
            if rule.available and rule.status != RuleStatus.AVAILABLE.value:
                raise PluginRuleError(
                    f"{slot}.{rule.slot} reports itself available while its "
                    f"status is {rule.status!r}"
                )

    if not plugin.required_core_skills:
        raise PluginRuleError(
            f"plugin {plugin.plugin_name!r} requires no core skill"
        )

    if not plugin.usable and plugin.fully_available:
        raise PluginRuleError(
            f"plugin {plugin.plugin_name!r} claims every rule is available while "
            "reporting no available rule"
        )

    for skill in plugin.required_core_skills:
        if skill not in UNIVERSAL_SKILLS:
            raise PluginLibraryError(
                f"plugin {plugin.plugin_name!r} requires {skill!r}, which the "
                "library does not declare as a universal skill"
            )


# --------------------------------------------------------------------------
# Combined
# --------------------------------------------------------------------------


def validate_plugin(
    plugin: DomainPlugin,
    *,
    registered_assets: Sequence[str] | None = None,
    schema: Mapping[str, Any] | None = None,
) -> PluginValidationReport:
    """Run all six checks and return an inspectable report."""

    if not isinstance(plugin, DomainPlugin):
        raise PluginRuleError("validate_plugin requires a DomainPlugin")

    checks: dict[str, str] = {}

    validate_schema(plugin.as_dict(), schema=schema)
    checks["schema"] = "PASS"
    validate_protocol(plugin)
    checks["protocol"] = "PASS"
    validate_layers()
    checks["layers"] = "PASS"
    validate_isolation(plugin)
    checks["isolation"] = "PASS"
    validate_provenance(plugin)
    checks["provenance"] = "PASS"
    validate_usability(plugin, registered_assets=registered_assets)
    checks["usability"] = "PASS"

    return PluginValidationReport(
        plugin_name=plugin.plugin_name,
        domain=plugin.domain,
        version=plugin.version,
        checks=checks,
    )


def validate_plugins(
    plugins: Sequence[DomainPlugin],
    *,
    registered_assets: Sequence[str] | None = None,
) -> tuple[PluginValidationReport, ...]:
    """Validate several plugins, in order."""

    return tuple(
        validate_plugin(plugin, registered_assets=registered_assets)
        for plugin in plugins
    )


def describe_validation(
    plugins: Sequence[DomainPlugin],
    *,
    registered_assets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """A single document summarising a batch validation, for review."""

    reports = validate_plugins(plugins, registered_assets=registered_assets)
    return {
        "plugin_count": len(reports),
        "passed": sum(1 for r in reports if r.passed),
        "failed": sum(1 for r in reports if not r.passed),
        "status": "PASS" if all(r.passed for r in reports) else "FAIL",
        "checks": sorted({name for r in reports for name in r.checks}),
        "plugins": [r.as_dict() for r in reports],
    }


__all__ = [
    "LayerReport",
    "PluginValidationReport",
    "audit_layers",
    "contains_domain_marker",
    "describe_validation",
    "validate_isolation",
    "validate_layers",
    "validate_plugin",
    "validate_plugins",
    "validate_protocol",
    "validate_provenance",
    "validate_schema",
    "validate_usability",
]
