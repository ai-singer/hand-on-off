"""The Domain Plugin Builder: a request in, a domain plugin document out.

```text
      domain_request.yaml
   { domain, platform, reference_sources }
                    |
                    v
            build_domain_plugin
                    |
                    v
        domain_finance_plugin  (a DomainPlugin document)
```

The builder produces a **plugin**, never a creator. It says what one domain is about
so that the Universal Creator Skills do not have to, and it produces nothing else:
no instance, no runtime, no deployment.

## What the builder will not do

- **It will not invent a domain.** An unknown domain is ``DOMAIN_NOT_FOUND``, not a
  plugin assembled from the nearest match.
- **It will not invent a rule.** Every asset-backed rule binds to a real registered
  asset and takes its status from that asset rather than asserting it. Every
  taxonomy rule is labelled as the architecture's declaration rather than a
  distilled artifact.
- **It will not invent a persona.** Every persona-producing asset in this repository
  is registered and unusable, so the identity records ``persona.available: false``
  with the registry's own reason.
- **It will not invent domain vocabulary.** The catalog supplies protocol terms and
  topic taxonomies; the builder only assembles them. A domain the catalog describes
  structurally but not verbally would arrive with empty terms, and the schema and
  validator would refuse it rather than filling the gap.

## Request input

:func:`load_domain_request` reads ``domain_request.yaml`` through the project's own
dependency-free YAML subset parser — no new dependency, and the same parser the
projection layer already uses.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_projection import AssetRegistry, parse_yaml_subset

from .model import (
    ABSENCE_MARKER,
    DEFAULT_TIMESTAMP,
    PLUGIN_FORMAT_VERSION,
    PROTOCOL_STAGES,
    DistillationStage,
    DomainIdentity,
    DomainNotFoundError,
    DomainPlugin,
    DomainRequest,
    DomainRequestError,
    PluginBuilderError,
    PluginProvenance,
    PluginProvenanceError,
    PluginRegistryError,
    PluginRuleError,
    RuleBinding,
    RuleStatus,
)
from .registry import (
    CATALOG_VERSION,
    DECLARED_ASSETS,
    DEFAULT_DOMAIN_CATALOG,
    GENERAL_TEXT_RULES,
    LIBRARY_VERSION,
    TAXONOMY_REASON,
    DomainEntry,
    DomainRegistry,
)

#: Default directory for a written plugin.
DEFAULT_PLUGIN_DIR = "domain_plugins"

#: Suffix for a written plugin document.
PLUGIN_SUFFIX = ".plugin.json"

#: Suffix for a written provenance document.
PROVENANCE_SUFFIX = ".provenance.json"

#: The builder identity recorded in ``generated_by``.
GENERATED_BY = "creator_plugin_builder.builder c0.5"

#: The persona asset every domain identity is bound to.
PERSONA_ASSET = "nuwa_persona_skill"


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------


def domain_request_from_document(document: Mapping[str, Any]) -> DomainRequest:
    """Build a :class:`DomainRequest` from a parsed request document."""

    if not isinstance(document, Mapping):
        raise DomainRequestError("a domain request must be an object")

    unknown = set(document) - {
        "domain",
        "platform",
        "style",
        "reference_sources",
        "reference_creator",
    }
    if unknown:
        raise DomainRequestError(
            "domain request has unexpected keys: " + ", ".join(sorted(unknown)),
            detail="accepted keys: domain, platform, style, reference_sources",
        )

    sources = document.get("reference_sources", ())
    if isinstance(sources, str):
        sources = (sources,)
    if not isinstance(sources, (list, tuple)):
        raise DomainRequestError("reference_sources must be a list")

    reference = str(document.get("reference_creator", "")).strip()
    if reference and not sources:
        # The brief's earlier shape used a single `reference_creator`. Accept it,
        # and fold it into the list so downstream code has one representation.
        sources = (reference,)

    return DomainRequest(
        domain=str(document.get("domain", "")).strip(),
        platform=str(document.get("platform", "")).strip(),
        style=str(document.get("style", "")).strip(),
        reference_sources=tuple(str(item).strip() for item in sources),
    )


def load_domain_request(path: str | Path) -> DomainRequest:
    """Read ``domain_request.yaml`` (or ``.json``) into a request.

    YAML is read with :func:`creator_projection.parse_yaml_subset`, the project's own
    dependency-free subset parser, so this adds no dependency.
    """

    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DomainRequestError(f"domain request not found: {target}") from exc
    except OSError as exc:
        raise DomainRequestError(
            f"cannot read domain request {target}: {exc}"
        ) from exc

    if target.suffix.lower() == ".json":
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DomainRequestError(
                f"domain request is not valid JSON: {target}", detail=str(exc)
            ) from exc
    else:
        try:
            document = parse_yaml_subset(text, origin=str(target))
        except Exception as exc:
            raise DomainRequestError(
                f"cannot parse domain request {target}", detail=str(exc)
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise DomainRequestError(
                f"cannot parse domain request {target}", detail=str(exc)
            ) from exc

    return domain_request_from_document(document)


# --------------------------------------------------------------------------
# Rule assembly
# --------------------------------------------------------------------------


def _binding(
    *,
    slot: str,
    core_skill: str,
    asset_id: str,
    registry: AssetRegistry,
    deliverable: str,
) -> RuleBinding:
    """Resolve one asset-backed rule against the registry.

    The status is read from the asset, never asserted. An available asset yields an
    available rule; a registered-but-unusable asset yields a declared rule carrying
    that asset's own reason; an asset the registry does not declare is reported.
    """

    if not registry.ids() or asset_id not in registry.ids():
        raise PluginRuleError(
            f"rule {slot!r} binds to asset {asset_id!r}, which this workspace's "
            "registry does not declare",
            detail="an asset-backed rule must bind to a registered asset",
        )
    asset = registry.get(asset_id)
    if asset.available:
        status = RuleStatus.AVAILABLE.value
        reason = ""
    elif asset.status == "unavailable":
        status = RuleStatus.DECLARED.value
        reason = asset.reason or ABSENCE_MARKER + "no_reason_recorded"
    else:
        status = RuleStatus.UNAVAILABLE.value
        reason = asset.reason or ABSENCE_MARKER + "asset_not_available"

    return RuleBinding(
        slot=slot,
        core_skill=core_skill,
        source_asset=asset_id,
        asset_type=asset.asset_type,
        status=status,
        reason=reason,
        values=(),
        values_source="asset",
        deliverable=deliverable,
    )


def _taxonomy_binding(
    *,
    slot: str,
    core_skill: str,
    asset_id: str,
    registry: AssetRegistry,
    deliverable: str,
    values: Sequence[str],
) -> RuleBinding:
    """Build one taxonomy rule: the domain's own vocabulary, labelled as such.

    The rule still names a real asset — the asset that will carry these values once a
    distillation pipeline produces them. Its status is that asset's status, and the
    values are marked ``catalog`` so a reviewer can see they are the architecture's
    declaration rather than something read from an artifact.
    """

    if asset_id not in registry.ids():
        raise PluginRuleError(
            f"taxonomy rule {slot!r} binds to asset {asset_id!r}, which this "
            "workspace's registry does not declare"
        )
    asset = registry.get(asset_id)
    return RuleBinding(
        slot=slot,
        core_skill=core_skill,
        source_asset=asset_id,
        asset_type=asset.asset_type,
        status=RuleStatus.DECLARED.value,
        reason=TAXONOMY_REASON,
        values=tuple(values),
        values_source="catalog",
        deliverable=deliverable,
    )


def _protocol_stages(
    entry: DomainEntry, registry: AssetRegistry, request: DomainRequest
) -> tuple[DistillationStage, ...]:
    """Spell the unified protocol in this domain's vocabulary."""

    terms = {stage: (term, questions) for stage, term, questions in entry.protocol_terms}
    missing = [stage for stage in PROTOCOL_STAGES if stage not in terms]
    if missing:
        raise PluginRuleError(
            f"domain {entry.domain!r} does not spell the protocol fully",
            detail="missing stages: " + ", ".join(missing),
        )

    asset_id = "text_structure_templates"
    if asset_id in registry.ids():
        asset = registry.get(asset_id)
        status = (
            RuleStatus.AVAILABLE.value if asset.available else RuleStatus.DECLARED.value
        )
        reason = "" if asset.available else (
            asset.reason or ABSENCE_MARKER + "unavailable"
        )
    else:
        status = RuleStatus.UNAVAILABLE.value
        reason = ABSENCE_MARKER + "structure_templates_not_registered"

    stages: list[DistillationStage] = []
    for order, stage in enumerate(PROTOCOL_STAGES, 1):
        term, questions = terms[stage]
        stages.append(
            DistillationStage(
                stage=stage,
                domain_term=term,
                core_skill="text-distillation",
                status=status,
                order=order,
                source_asset=asset_id,
                reason=reason,
                questions=tuple(questions),
            )
        )
    return tuple(stages)


def _identity(
    entry: DomainEntry, registry: AssetRegistry, request: DomainRequest
) -> DomainIdentity:
    """Build the domain identity, honest about the missing persona asset."""

    if PERSONA_ASSET in registry.ids():
        asset = registry.get(PERSONA_ASSET)
        available = asset.available
        reason = "" if available else (asset.reason or ABSENCE_MARKER + "unavailable")
    else:
        available = False
        reason = ABSENCE_MARKER + "persona_asset_not_registered"

    return DomainIdentity(
        domain=entry.domain,
        display_name=entry.display_name,
        reference_sources=tuple(request.reference_sources),
        persona_available=available,
        persona_asset=PERSONA_ASSET,
        persona_reason=reason,
        keywords=(),
    )


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def request_digest(request: DomainRequest, *, catalog_version: str) -> str:
    """A stable digest of one request plus the catalog it was read against.

    The catalog version is included because the same request against a different
    catalog is a different build: a plugin built from catalog 1.0.0 is not the plugin
    built from catalog 2.0.0, even for the same domain.
    """

    if not isinstance(request, DomainRequest):
        raise PluginProvenanceError("request_digest requires a DomainRequest")
    payload = {"catalog_version": catalog_version, "request": request.as_dict()}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BuildResult:
    """A built plugin, plus everything needed to audit the build."""

    plugin: DomainPlugin
    request: DomainRequest
    entry: DomainEntry
    catalog_version: str
    library_version: str
    checks: Mapping[str, str]

    @property
    def plugin_name(self) -> str:
        return self.plugin.plugin_name

    @property
    def domain(self) -> str:
        return self.plugin.domain

    @property
    def passed(self) -> bool:
        return all(value == "PASS" for value in self.checks.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin": self.plugin.as_dict(),
            "summary": self.plugin.summary(),
            "request": self.request.as_dict(),
            "catalog_version": self.catalog_version,
            "library_version": self.library_version,
            "checks": dict(self.checks),
        }

    def report(self) -> dict[str, Any]:
        """The audit report: summary and checks, without the whole plugin."""

        return {
            "plugin_name": self.plugin_name,
            "domain": self.domain,
            "version": self.plugin.version,
            "status": "PASS" if self.passed else "FAIL",
            "checks": dict(self.checks),
            "summary": self.plugin.summary(),
        }


def resolve_workspace_root(workspace_root: str | Path | None) -> Path:
    """The workspace whose asset registry the builder reads."""

    if workspace_root is None:
        return Path(__file__).resolve().parents[1]
    return Path(workspace_root)


def build_domain_plugin(
    request: DomainRequest,
    *,
    workspace_root: str | Path | None = None,
    registry: DomainRegistry | None = None,
    asset_registry: AssetRegistry | None = None,
    version: str = "",
    validate: bool = True,
) -> BuildResult:
    """Build the domain plugin a request asks for.

    Args:
        request: the domain, platform, style and reference sources.
        workspace_root: the workspace whose asset registry is read. Defaults to this
            repository's own workspace.
        registry: the domain catalog to draw from. Defaults to the default catalog.
        asset_registry: the asset registry rules bind against. Defaults to the
            workspace's.
        version: the plugin version. Defaults to the catalog entry's version.
        validate: run every validation layer before returning. On by default.

    Raises:
        DomainNotFoundError: the domain has no catalog entry.
        PluginBuilderError: with a stable code, on any failed check.
    """

    if not isinstance(request, DomainRequest):
        raise PluginRuleError("build_domain_plugin requires a DomainRequest")

    root = resolve_workspace_root(workspace_root)
    domains = DomainRegistry(DEFAULT_DOMAIN_CATALOG) if registry is None else registry
    assets = AssetRegistry.load(root) if asset_registry is None else asset_registry

    if not domains.has(request.domain):
        raise DomainNotFoundError(
            f"no domain plugin for {request.domain!r}",
            detail=(
                "registered domains: " + ", ".join(domains.domains())
                + ". A new domain is a catalog entry, not a new skill set."
            ),
        )

    entry = domains.get(request.domain)

    identity_rules = (
        _binding(
            slot=entry.identity_slot,
            core_skill="identity-rules",
            asset_id=PERSONA_ASSET,
            registry=assets,
            deliverable=entry.identity_deliverable,
        ),
    )
    source_rules = tuple(
        _binding(
            slot=slot,
            core_skill="source-normalization",
            asset_id=asset_id,
            registry=assets,
            deliverable=deliverable,
        )
        for slot, asset_id, deliverable in entry.source_slots
    )
    topic_rules = tuple(
        _taxonomy_binding(
            slot=slot,
            core_skill="text-distillation",
            asset_id=GENERAL_TEXT_RULES,
            registry=assets,
            deliverable="which subjects this domain's material is about",
            values=values,
        )
        for slot, values in entry.topic_taxonomy
    )
    text_rules = tuple(
        _binding(
            slot=slot,
            core_skill="text-distillation",
            asset_id=asset_id,
            registry=assets,
            deliverable=deliverable,
        )
        for slot, asset_id, deliverable in entry.text_slots
    )
    visual_rules = tuple(
        _binding(
            slot=slot,
            core_skill="visual-distillation",
            asset_id=asset_id,
            registry=assets,
            deliverable=deliverable,
        )
        for slot, asset_id, deliverable in entry.visual_slots
    )
    risk_rules = tuple(
        _binding(
            slot=slot,
            core_skill="risk-review",
            asset_id=asset_id,
            registry=assets,
            deliverable=deliverable,
        )
        for slot, asset_id, deliverable in entry.risk_slots
    )
    stages = _protocol_stages(entry, assets, request)

    all_rules = (
        identity_rules + source_rules + topic_rules + text_rules + visual_rules
        + risk_rules
    )
    source_assets = tuple(sorted({rule.source_asset for rule in all_rules}))
    unavailable = tuple(
        sorted(
            {rule.source_asset for rule in all_rules if not rule.available}
            | {
                asset_id
                for asset_id in DECLARED_ASSETS
                if asset_id in assets.ids() and not assets.get(asset_id).available
            }
        )
    )

    resolved_version = version or entry.version
    provenance = PluginProvenance(
        generated_by=GENERATED_BY,
        generated_at=DEFAULT_TIMESTAMP,
        domain=entry.domain,
        request_digest=request_digest(request, catalog_version=CATALOG_VERSION),
        catalog_version=CATALOG_VERSION,
        library_version=LIBRARY_VERSION,
        source_assets=source_assets,
        core_skills=tuple(sorted(set(entry.requirements))),
        unavailable_assets=unavailable,
        notes=entry.notes,
    )

    plugin = DomainPlugin(
        plugin_name=f"domain_{entry.domain}_plugin",
        domain=entry.domain,
        version=resolved_version,
        display_name=entry.display_name,
        identity=_identity(entry, assets, request),
        identity_rules=identity_rules,
        source_rules=source_rules,
        topic_rules=topic_rules,
        protocol_stages=stages,
        text_distillation_rules=text_rules,
        visual_adaptation_rules=visual_rules,
        risk_constraints=risk_rules,
        required_core_skills=tuple(entry.requirements),
        provenance=provenance,
        format_version=PLUGIN_FORMAT_VERSION,
        compatibility={
            "platforms": list(entry.platforms),
            "styles": list(entry.styles),
            "requires_contract_version": "1.0.0",
            "requires_format_version": PLUGIN_FORMAT_VERSION,
        },
        notes=entry.notes,
    )

    checks: dict[str, str] = {}
    if validate:
        from .validator import validate_plugin

        report = validate_plugin(plugin, registered_assets=tuple(assets.ids()))
        checks = dict(report.checks)
        if not report.passed:
            raise PluginBuilderError(
                f"plugin {plugin.plugin_name!r} failed validation",
                detail=json.dumps(report.as_dict(), sort_keys=True),
            )

    return BuildResult(
        plugin=plugin,
        request=request,
        entry=entry,
        catalog_version=CATALOG_VERSION,
        library_version=LIBRARY_VERSION,
        checks=checks,
    )


def build_domain_plugins(
    requests: Sequence[DomainRequest], **kwargs: Any
) -> tuple[BuildResult, ...]:
    """Build several plugins, in the order asked for."""

    return tuple(build_domain_plugin(request, **kwargs) for request in requests)


def describe_domain(request: DomainRequest, **kwargs: Any) -> dict[str, Any]:
    """Build a plugin and return its report, not the plugin."""

    return build_domain_plugin(request, **kwargs).report()


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def plugin_path(
    plugin: DomainPlugin, out_root: str | Path = DEFAULT_PLUGIN_DIR
) -> Path:
    """Where a plugin document belongs."""

    return Path(out_root) / f"{plugin.plugin_name}{PLUGIN_SUFFIX}"


def write_domain_plugin(
    plugin: DomainPlugin, out_root: str | Path = DEFAULT_PLUGIN_DIR
) -> list[Path]:
    """Write one plugin and its provenance, refusing an invalid plugin."""

    from .provenance import provenance_document
    from .validator import validate_plugin

    report = validate_plugin(plugin)
    if not report.passed:
        raise PluginBuilderError(
            f"refusing to write invalid plugin {plugin.plugin_name!r}",
            detail=json.dumps(report.as_dict(), sort_keys=True),
        )

    target = Path(out_root)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    document = plugin_path(plugin, target)
    document.write_text(
        json.dumps(plugin.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    written.append(document)

    chain = target / f"{plugin.plugin_name}{PROVENANCE_SUFFIX}"
    chain.write_text(
        json.dumps(
            provenance_document(plugin), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(chain)

    return written


__all__ = [
    "DEFAULT_PLUGIN_DIR",
    "GENERATED_BY",
    "PERSONA_ASSET",
    "PLUGIN_SUFFIX",
    "PROVENANCE_SUFFIX",
    "BuildResult",
    "build_domain_plugin",
    "build_domain_plugins",
    "describe_domain",
    "domain_request_from_document",
    "load_domain_request",
    "plugin_path",
    "request_digest",
    "resolve_workspace_root",
    "write_domain_plugin",
]
