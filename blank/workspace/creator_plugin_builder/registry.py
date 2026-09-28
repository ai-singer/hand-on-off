"""The domain catalog, and the registry a builder draws from.

# What a catalog entry may contain

A domain plugin is *domain data*. It is allowed — required, even — to know that
finance talks about company events and sports talks about fixtures. That knowledge
is the plugin's entire reason to exist, and it is the reason a universal skill must
never hold it.

What an entry may **not** contain is a capability claim it cannot support. So every
rule declares both the domain question it answers and the real registered asset that
answers it today. Where no asset answers a question, the rule says so with the
registry's own reason rather than being filled in with plausible-sounding content.

For the same reason, the entries below are deliberately structural. The *shape* of
the plugin — which slots exist, what each slot is for, how the distillation protocol
is spelled in this domain — is what this phase designs and what the meta skills
generate. The *content* of a domain's rule values is what a real distillation
pipeline produces later, from a real reference source; inventing it here would be
exactly the fabrication the rest of the factory refuses.

# Adding a domain

A new domain is a new :class:`DomainEntry`. It is not a new skill set, and it is not
a change to any universal skill. That is the whole point of the architecture: three
domains today, three hundred later, one library.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .model import (
    PLUGIN_SLOTS,
    PROTOCOL_STAGES,
    PluginRegistryError,
)

#: Catalog version, independent of individual plugin versions.
CATALOG_VERSION = "1.0.0"

#: The library version this catalog was written against.
LIBRARY_VERSION = "1.0.0"

#: The core skills every domain plugin binds to today.
#:
#: Note what is *not* here: ``generation-interface`` and ``publishing-interface``.
#: Both are in the library, and both are declared capabilities with no
#: implementation — so a plugin that needs one names it in ``declared_skills``
#: instead of binding to it. Requiring a capability that does not exist would be the
#: false claim every phase of this programme rejects.
DEFAULT_REQUIREMENTS: tuple[str, ...] = (
    "identity-rules",
    "source-normalization",
    "text-distillation",
    "visual-distillation",
    "risk-review",
)

#: Core skills a plugin names as needing work that does not exist yet.
#:
#: ``identity-rules`` is not a library skill; it is the plugin's own identity slot and
#: is resolved by the builder. These two are the real gaps.
DECLARED_SKILLS: tuple[str, ...] = (
    "generation-interface",
    "publishing-interface",
)

#: The asset every domain binds its source, topic and text rules to today.
#:
#: This is the C0.2 projection of the template's declared value rules and structure
#: templates. It is general-purpose, which is why it can serve every domain — and why
#: a domain-specific rule asset is the single most valuable thing a later phase could
#: add.
GENERAL_TEXT_RULES = "text_distillation_rules"
GENERAL_STRUCTURE_TEMPLATES = "text_structure_templates"
GENERAL_VISUAL_PROFILE = "visual_profile_m5"
GENERAL_RISK_REFERENCE = "risk_policy_reference"

#: Assets that would implement a capability, and are registered but unusable.
DECLARED_ASSETS: tuple[str, ...] = (
    "source_collection_strategy",
    "nuwa_persona_skill",
    "persona_perspective_skill",
    "nuwa_skill_template",
)

#: The reason attached to every rule whose answer is the domain's own taxonomy.
TAXONOMY_REASON = "not_available:domain_taxonomy_is_declared_not_distilled"


@dataclass(frozen=True, slots=True)
class DomainEntry:
    """One catalog entry: a domain, its core skills, and its rule shape.

    ``*_slots`` are ``(slot, asset_id, deliverable)`` triples for asset-backed rules
    and ``(slot, deliverable, values)`` triples for taxonomy rules. The two are kept
    in separate fields rather than distinguished by a flag, because a reader should
    be able to see at a glance which of a domain's rules rest on a real artifact.
    """

    domain: str
    display_name: str
    version: str
    identity_slot: str
    identity_deliverable: str
    source_slots: tuple[tuple[str, str, str], ...]
    topic_taxonomy: tuple[tuple[str, tuple[str, ...]], ...]
    protocol_terms: tuple[tuple[str, str, tuple[str, ...]], ...]
    text_slots: tuple[tuple[str, str, str], ...]
    visual_slots: tuple[tuple[str, str, str], ...]
    risk_slots: tuple[tuple[str, str, str], ...]
    requirements: tuple[str, ...] = DEFAULT_REQUIREMENTS
    platforms: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "display_name": self.display_name,
            "version": self.version,
            "requirements": list(self.requirements),
            "platforms": list(self.platforms),
            "styles": list(self.styles),
            "asset_backed_rule_count": (
                len(self.source_slots)
                + len(self.text_slots)
                + len(self.visual_slots)
                + len(self.risk_slots)
            ),
            "taxonomy_rule_count": len(self.topic_taxonomy),
            "protocol_stage_count": len(self.protocol_terms),
            "notes": list(self.notes),
        }


#: The default domain catalog: finance, sports and technology.
#:
#: Every ``(slot, asset, deliverable)`` triple names a real registered asset. Every
#: ``(slot, deliverable, values)`` triple is the domain's own taxonomy, labelled
#: ``values_source="catalog"`` when it reaches the plugin so a reviewer can see it is
#: the architecture's declaration rather than a distilled artifact.
DEFAULT_DOMAIN_CATALOG: tuple[DomainEntry, ...] = (
    DomainEntry(
        domain="finance",
        display_name="Finance",
        version="1.0.0",
        identity_slot="domain_persona",
        identity_deliverable="who this domain's creator is",
        source_slots=(
            ("discovery", GENERAL_TEXT_RULES, "where this domain's material comes from"),
            ("normalization", GENERAL_TEXT_RULES, "how raw material is normalized"),
        ),
        topic_taxonomy=(
            ("topic_extraction", ("company_event", "market_move", "policy_impact")),
        ),
        protocol_terms=(
            ("observation", "event",
             ("what happened, to whom, and when",)),
            ("context", "background",
             ("what the surrounding situation is",)),
            ("mechanism", "mechanism",
             ("why it happened, by what causal path",)),
            ("consequence", "impact",
             ("who is affected, and how materially",)),
            ("evidence", "evidence",
             ("which source supports each claim",)),
            ("boundary", "boundary",
             ("what the material does not establish",)),
        ),
        text_slots=(
            ("structure", GENERAL_STRUCTURE_TEMPLATES, "the text shape for this domain"),
            ("title_formula", GENERAL_STRUCTURE_TEMPLATES, "how titles are formed"),
        ),
        visual_slots=(
            ("adaptation", GENERAL_VISUAL_PROFILE, "how the visual profile adapts"),
        ),
        risk_slots=(
            ("categories", GENERAL_RISK_REFERENCE, "this domain's risk categories"),
            ("evidence", GENERAL_RISK_REFERENCE, "the evidence a claim must carry"),
        ),
        platforms=("xiaohongshu",),
        notes=(
            "No finance-specific rule asset exists in this repository; every "
            "asset-backed rule binds to the general-purpose text, visual and risk "
            "assets, and says so.",
        ),
    ),
    DomainEntry(
        domain="sports",
        display_name="Sports",
        version="1.0.0",
        identity_slot="domain_persona",
        identity_deliverable="who this domain's creator is",
        source_slots=(
            ("discovery", GENERAL_TEXT_RULES, "where this domain's material comes from"),
            ("normalization", GENERAL_TEXT_RULES, "how raw material is normalized"),
        ),
        topic_taxonomy=(
            ("topic_extraction",
             ("match_outcome", "player_performance", "transfer")),
        ),
        protocol_terms=(
            ("observation", "fixture",
             ("which competition, who played, what the result was",)),
            ("context", "form",
             ("each side's recent record and condition",)),
            ("mechanism", "tactics",
             ("how the result came about",)),
            ("consequence", "standing",
             ("what the result changes for each side",)),
            ("evidence", "statistics",
             ("which figures support the reading",)),
            ("boundary", "sample_limit",
             ("what one match cannot establish",)),
        ),
        text_slots=(
            ("structure", GENERAL_STRUCTURE_TEMPLATES, "the text shape for this domain"),
            ("title_formula", GENERAL_STRUCTURE_TEMPLATES, "how titles are formed"),
        ),
        visual_slots=(
            ("adaptation", GENERAL_VISUAL_PROFILE, "how the visual profile adapts"),
        ),
        risk_slots=(
            ("categories", GENERAL_RISK_REFERENCE, "this domain's risk categories"),
            ("evidence", GENERAL_RISK_REFERENCE, "the evidence a claim must carry"),
        ),
        platforms=("xiaohongshu",),
        notes=(
            "No sports-specific rule asset exists in this repository; every "
            "asset-backed rule binds to the general-purpose text, visual and risk "
            "assets, and says so.",
        ),
    ),
    DomainEntry(
        domain="technology",
        display_name="Technology",
        version="1.0.0",
        identity_slot="domain_persona",
        identity_deliverable="who this domain's creator is",
        source_slots=(
            ("discovery", GENERAL_TEXT_RULES, "where this domain's material comes from"),
            ("normalization", GENERAL_TEXT_RULES, "how raw material is normalized"),
        ),
        topic_taxonomy=(
            ("topic_extraction",
             ("product_launch", "architecture_choice", "adoption_signal")),
        ),
        protocol_terms=(
            ("observation", "release",
             ("what shipped or changed",)),
            ("context", "prior_art",
             ("what it replaces or extends",)),
            ("mechanism", "design",
             ("how it works, and what it trades away",)),
            ("consequence", "adoption",
             ("what it changes for the people who use it",)),
            ("evidence", "benchmarks",
             ("which measurements support the claim",)),
            ("boundary", "scope_limit",
             ("what the evidence does not cover",)),
        ),
        text_slots=(
            ("structure", GENERAL_STRUCTURE_TEMPLATES, "the text shape for this domain"),
            ("title_formula", GENERAL_STRUCTURE_TEMPLATES, "how titles are formed"),
        ),
        visual_slots=(
            ("adaptation", GENERAL_VISUAL_PROFILE, "how the visual profile adapts"),
        ),
        risk_slots=(
            ("categories", GENERAL_RISK_REFERENCE, "this domain's risk categories"),
            ("evidence", GENERAL_RISK_REFERENCE, "the evidence a claim must carry"),
        ),
        platforms=("xiaohongshu",),
        notes=(
            "No technology-specific rule asset exists in this repository; every "
            "asset-backed rule binds to the general-purpose text, visual and risk "
            "assets, and says so.",
        ),
    ),
)


def catalog_domains() -> tuple[str, ...]:
    """Every domain the catalog declares, sorted."""

    return tuple(sorted(entry.domain for entry in DEFAULT_DOMAIN_CATALOG))


def catalog_document() -> dict[str, Any]:
    """The catalog as a plain document, for inspection and for tests."""

    return {
        "catalog_version": CATALOG_VERSION,
        "library_version": LIBRARY_VERSION,
        "domain_count": len(DEFAULT_DOMAIN_CATALOG),
        "domains": [entry.as_dict() for entry in DEFAULT_DOMAIN_CATALOG],
    }


def protocol_document() -> dict[str, Any]:
    """The unified distillation protocol, with each domain's vocabulary for it."""

    return {
        "stages": list(PROTOCOL_STAGES),
        "stage_count": len(PROTOCOL_STAGES),
        "slots": list(PLUGIN_SLOTS),
        "slot_count": len(PLUGIN_SLOTS),
        "domains": {
            entry.domain: {
                "terms": {stage: term for stage, term, _q in entry.protocol_terms},
                "questions": {stage: list(q) for stage, _t, q in entry.protocol_terms},
            }
            for entry in DEFAULT_DOMAIN_CATALOG
        },
    }


class DomainRegistry:
    """A registry of domain catalog entries, with request-driven lookup."""

    def __init__(self, entries: Sequence[DomainEntry] | None = None) -> None:
        active = DEFAULT_DOMAIN_CATALOG if entries is None else tuple(entries)
        self._entries: dict[str, DomainEntry] = {}
        for entry in active:
            if not isinstance(entry, DomainEntry):
                raise PluginRegistryError(
                    "a domain registry accepts only DomainEntry records"
                )
            if entry.domain in self._entries:
                raise PluginRegistryError(
                    f"domain {entry.domain!r} is declared twice",
                    detail="one plugin per domain",
                )
            self._entries[entry.domain] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, domain: object) -> bool:
        return domain in self._entries

    def __iter__(self):
        return iter(self.domains())

    def domains(self) -> tuple[str, ...]:
        """Every registered domain, sorted."""

        return tuple(sorted(self._entries))

    def ids(self) -> tuple[str, ...]:
        return self.domains()

    def get(self, domain: str) -> DomainEntry:
        """Return one catalog entry, rejecting an unknown domain."""

        try:
            return self._entries[domain]
        except KeyError as exc:
            raise PluginRegistryError(
                f"unknown domain {domain!r}",
                detail="registered domains: " + ", ".join(self.domains()),
            ) from exc

    def has(self, domain: str) -> bool:
        return domain in self._entries

    def register(self, entry: DomainEntry) -> DomainEntry:
        """Add an entry, rejecting a duplicate."""

        if not isinstance(entry, DomainEntry):
            raise PluginRegistryError(
                "a domain registry accepts only DomainEntry records"
            )
        if entry.domain in self._entries:
            raise PluginRegistryError(f"domain {entry.domain!r} is already registered")
        self._entries[entry.domain] = entry
        return entry

    def unregister(self, domain: str) -> DomainEntry:
        """Remove an entry, rejecting an unknown domain."""

        try:
            return self._entries.pop(domain)
        except KeyError as exc:
            raise PluginRegistryError(f"unknown domain {domain!r}") from exc

    def as_dict(self) -> dict[str, Any]:
        return {
            "catalog_version": CATALOG_VERSION,
            "library_version": LIBRARY_VERSION,
            "domain_count": len(self._entries),
            "domains": {
                domain: self._entries[domain].as_dict()
                for domain in sorted(self._entries)
            },
        }


def default_registry() -> DomainRegistry:
    """A registry over the default catalog."""

    return DomainRegistry(DEFAULT_DOMAIN_CATALOG)


__all__ = [
    "CATALOG_VERSION",
    "DECLARED_ASSETS",
    "DECLARED_SKILLS",
    "DEFAULT_DOMAIN_CATALOG",
    "DEFAULT_REQUIREMENTS",
    "GENERAL_RISK_REFERENCE",
    "GENERAL_STRUCTURE_TEMPLATES",
    "GENERAL_TEXT_RULES",
    "GENERAL_VISUAL_PROFILE",
    "LIBRARY_VERSION",
    "TAXONOMY_REASON",
    "DomainEntry",
    "DomainRegistry",
    "catalog_document",
    "catalog_domains",
    "default_registry",
    "protocol_document",
]
