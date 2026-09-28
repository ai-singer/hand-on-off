"""Provenance: the chain from a request to every rule in a plugin.

A domain plugin is a **generated** configuration asset, so it has to be able to say
where it came from:

```text
    domain_request  →  domain_catalog  →  asset  →  rule
```

Four links, each either recorded or explicitly marked unrecorded. Nothing here
reconstructs a link the artifact does not carry.

The request digest is a stable hash of what was asked for, computed over the
normalised request in sorted key order, plus the catalog version — because the same
request against a different catalog is a different build. Two callers asking the same
thing compare equal; a caller asking for a different platform does not, even though
the domain is the same.

The *provenance completeness* check is what stops a plugin shipping a rule whose
origin nobody can name. Every rule must resolve to a core skill, an asset and a
status, and every rule that is not available must carry a reason.
"""

from __future__ import annotations

from typing import Any

from .model import DomainPlugin, PluginProvenanceError

#: The chain a plugin's provenance records, in order.
PROVENANCE_CHAIN: tuple[str, ...] = (
    "domain_request",
    "domain_catalog",
    "asset",
    "rule",
)

#: Where each link's value is recorded.
CHAIN_SOURCES: dict[str, str] = {
    "domain_request": "provenance.request_digest",
    "domain_catalog": "provenance.catalog_version",
    "asset": "rule.source_asset and provenance.source_assets",
    "rule": "rule.slot, rule.core_skill, rule.status",
}


def rule_chains(plugin: DomainPlugin) -> tuple[dict[str, Any], ...]:
    """One chain per rule, covering every rule slot and every protocol stage."""

    provenance = plugin.provenance
    chains: list[dict[str, Any]] = []

    for slot in plugin.SLOTS:
        for rule in getattr(plugin, slot):
            chains.append(
                {
                    "slot": slot,
                    "rule": rule.slot,
                    "core_skill": rule.core_skill,
                    "asset": {
                        "asset_id": rule.source_asset,
                        "asset_type": rule.asset_type,
                        "available": rule.available,
                    },
                    "status": rule.status,
                    "reason": rule.reason,
                    "values_source": rule.values_source,
                    "value_count": rule.value_count,
                    "deliverable": rule.deliverable,
                    "request_digest": provenance.request_digest,
                    "catalog_version": provenance.catalog_version,
                    "recorded": True,
                }
            )

    for stage in plugin.protocol_stages:
        chains.append(
            {
                "slot": "protocol_stages",
                "rule": stage.stage,
                "core_skill": stage.core_skill,
                "asset": {
                    "asset_id": stage.source_asset,
                    "asset_type": "",
                    "available": stage.available,
                },
                "status": stage.status,
                "reason": stage.reason,
                "values_source": "catalog",
                "value_count": len(stage.questions),
                "deliverable": stage.domain_term,
                "request_digest": provenance.request_digest,
                "catalog_version": provenance.catalog_version,
                "recorded": True,
            }
        )

    return tuple(chains)


def provenance_document(plugin: DomainPlugin) -> dict[str, Any]:
    """The plugin's full provenance, ready to be read by a reviewer."""

    chains = rule_chains(plugin)
    return {
        "plugin_name": plugin.plugin_name,
        "domain": plugin.domain,
        "version": plugin.version,
        "chain": list(PROVENANCE_CHAIN),
        "chain_sources": dict(CHAIN_SOURCES),
        "generated_by": plugin.provenance.generated_by,
        "generated_at": plugin.provenance.generated_at,
        "catalog_version": plugin.provenance.catalog_version,
        "library_version": plugin.provenance.library_version,
        "request_digest": plugin.provenance.request_digest,
        "source_assets": list(plugin.provenance.source_assets),
        "unavailable_assets": list(plugin.provenance.unavailable_assets),
        "core_skills": list(plugin.provenance.core_skills),
        "summary": {
            "rule_count": len(chains),
            "available_rule_count": sum(1 for c in chains if c["asset"]["available"]),
            "declared_rule_count": sum(
                1 for c in chains if not c["asset"]["available"]
            ),
            "asset_count": len(plugin.provenance.source_assets),
            "unavailable_asset_count": len(plugin.provenance.unavailable_assets),
            "catalog_value_rule_count": sum(
                1 for c in chains if c["values_source"] == "catalog"
            ),
        },
        "rules": list(chains),
        "notes": list(plugin.provenance.notes),
    }


def untraced_rules(plugin: DomainPlugin) -> tuple[str, ...]:
    """Rules whose chain is incomplete.

    A rule is traced when it names a core skill, an asset and a status, and carries a
    reason whenever that status is not ``available``. An empty tuple is the only
    acceptable answer for a plugin that passed validation.
    """

    untraced: list[str] = []
    for slot in plugin.SLOTS:
        for rule in getattr(plugin, slot):
            if not rule.core_skill or not rule.source_asset or not rule.status:
                untraced.append(f"{slot}.{rule.slot}")
            elif not rule.available and not rule.reason:
                untraced.append(f"{slot}.{rule.slot}")
    for stage in plugin.protocol_stages:
        if not stage.core_skill or not stage.status:
            untraced.append(f"protocol_stages.{stage.stage}")
        elif not stage.available and not stage.reason:
            untraced.append(f"protocol_stages.{stage.stage}")
    return tuple(sorted(untraced))


def asset_usage(plugin: DomainPlugin) -> dict[str, tuple[str, ...]]:
    """``{asset_id: (rule names)}`` — which rules read which asset."""

    usage: dict[str, list[str]] = {}
    for slot in plugin.SLOTS:
        for rule in getattr(plugin, slot):
            usage.setdefault(rule.source_asset, []).append(f"{slot}.{rule.slot}")
    for stage in plugin.protocol_stages:
        if stage.source_asset:
            usage.setdefault(stage.source_asset, []).append(
                f"protocol_stages.{stage.stage}"
            )
    return {asset_id: tuple(sorted(names)) for asset_id, names in sorted(usage.items())}


def skill_usage(plugin: DomainPlugin) -> dict[str, tuple[str, ...]]:
    """``{core_skill: (rule names)}`` — which core skill each rule binds to."""

    usage: dict[str, list[str]] = {}
    for slot in plugin.SLOTS:
        for rule in getattr(plugin, slot):
            usage.setdefault(rule.core_skill, []).append(f"{slot}.{rule.slot}")
    for stage in plugin.protocol_stages:
        usage.setdefault(stage.core_skill, []).append(
            f"protocol_stages.{stage.stage}"
        )
    return {skill: tuple(sorted(names)) for skill, names in sorted(usage.items())}


__all__ = [
    "CHAIN_SOURCES",
    "PROVENANCE_CHAIN",
    "asset_usage",
    "provenance_document",
    "rule_chains",
    "skill_usage",
    "untraced_rules",
]
