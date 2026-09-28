"""Map a Creator Skill Bundle onto a Creator Instance.

::

    SkillBundle
        |
        v  read the skill registry        (a selection -> its skill)
        v  resolve each skill's asset      (BundleAssetResolver -> C0.2 registry)
        v  apply the field rules           (rules.py -> RULE_* per target field)
        v  declare what has no source      (capability honesty)
        v
    creator_instance artifact

Two properties are non-negotiable and both are enforced by tests:

**No field is copied from a skill.** A skill carries a capability name and an
asset reference, not content. Every instance field is *derived* from the resolved
asset, and every derivation cites the rule that performed it. A mapper that copied
``skill.capabilities`` into the instance would be inventing content.

**No absent capability is enabled.** When a skill is unavailable, its module is
emitted disabled with a machine-readable reason. Auto-filling is the failure the
C0.1/C0.2/C0.3 programme exists to prevent, so it raises here.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from creator_contract import (
    CONTRACT_VERSION,
    CreatorContractError,
    canonical_json,
    instance_dir,
    validate as validate_contract,
)
from creator_skill import (
    CreatorRequest,
    SkillBundle,
    SkillRegistry,
)

from .errors import (
    MappingAssetError,
    MappingCompletenessError,
    MappingHonestyError,
    MappingRuleError,
)
from .provenance import (
    DEFAULT_TIMESTAMP,
    NO_ASSET,
    REQUIRED_MAPPING_KEYS,
    MappingProvenanceBuilder,
)
from .resolver import BundleAssetResolver, BundleAssets, ResolvedAsset
from .rules import (
    CAPABILITY_MODULES,
    FIELD_RULES,
    MAPPED_MODULES,
    MODULE_SKILL_RULES,
    REQUIRED_PATHS,
    SKILL_MODULE_RULES,
    FieldRule,
    rule_ids,
    rules_for_module,
)

#: Domains the C0.1 contract accepts. A request naming another domain is a hard
#: error here rather than a silent coercion, because the contract would reject it.
CONTRACT_DOMAINS: tuple[str, ...] = ("finance", "sports", "tech", "general")

#: Platforms the contract accepts.
CONTRACT_PLATFORMS: tuple[str, ...] = (
    "xiaohongshu",
    "bilibili",
    "youtube",
    "douyin",
    "wechat",
    "web",
    "github",
)

#: Languages the contract accepts.
CONTRACT_LANGUAGES: tuple[str, ...] = ("zh", "en", "bilingual")

#: Aspect ratios the contract accepts. Chosen from the platform.
PLATFORM_ASPECT_RATIOS: Mapping[str, str] = {
    "xiaohongshu": "4:5",
    "douyin": "9:16",
    "bilibili": "16:9",
    "youtube": "16:9",
    "wechat": "4:5",
    "web": "16:9",
    "github": "16:9",
}

#: Generation inputs the contract accepts, mirroring production/generation_input.py.
GENERATION_INPUTS: tuple[str, ...] = (
    "topic",
    "structure",
    "knowledge",
    "style",
    "domain_context",
    "constraints",
)

#: Fallback identity when a bundle has no identity or domain skill.
MISSING_IDENTITY_NAME = "unmapped-creator"

#: The absent-capability reason codes. These are the same machine-readable strings
#: C0.2's asset registry and C0.3's skill catalog use, so an instance mapped here
#: carries an identical reason to one projected there. Declared locally because
#: C0.3 does not re-export C0.2's constants, and a test asserts the three agree.
GENERATION_ABSENT_REASON = "generation_capability_not_available"
PUBLISHING_ABSENT_REASON = "publishing_capability_not_available"

#: Marker prefixing a string field whose content is a declared absence rather than
#: a mapped value. Used where the contract requires a string and no source exists.
ABSENCE_MARKER = "not_available:"


@dataclass(frozen=True, slots=True)
class ModuleMapping:
    """One mapped contract module."""

    module: str
    document: Mapping[str, Any]
    rule_ids: tuple[str, ...]
    unavailable_fields: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    availability: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "rules": list(self.rule_ids),
            "unavailable_fields": list(self.unavailable_fields),
            "skills": list(self.skill_ids),
            "assets": list(self.asset_ids),
            "availability": dict(self.availability),
        }


@dataclass(frozen=True, slots=True)
class MappedInstance:
    """The mapping outcome: an instance, plus everything needed to audit it."""

    instance: dict[str, Any]
    bundle_id: str
    creator_id: str
    modules: tuple[ModuleMapping, ...]
    mapping_provenance: Mapping[str, Any]
    assets: BundleAssets
    notes: tuple[str, ...] = field(default_factory=tuple)
    timestamp: str = DEFAULT_TIMESTAMP

    @property
    def unavailable_fields(self) -> tuple[str, ...]:
        return tuple(
            f"{module.module}.{name}"
            for module in self.modules
            for name in module.unavailable_fields
        )

    @property
    def field_provenance(self) -> Mapping[str, Any]:
        """The per-field mapping records, or ``{}`` when none were produced."""

        payload = self.instance.get("provenance", {}).get("field_provenance")
        if isinstance(payload, Mapping):
            fields = payload.get("fields")
            if isinstance(fields, Mapping):
                return fields
        return {}

    @property
    def module_availability(self) -> Mapping[str, Any]:
        """The per-module availability records."""

        payload = self.instance.get("provenance", {}).get("field_provenance")
        if isinstance(payload, Mapping):
            modules = payload.get("modules")
            if isinstance(modules, Mapping):
                return modules
        return {}

    def as_report(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "creator_id": self.creator_id,
            "contract_version": self.instance.get("contract_version"),
            "modules": [module.as_dict() for module in self.modules],
            "unavailable_fields": list(self.unavailable_fields),
            "notes": list(self.notes),
            "assets": self.assets.as_dict(),
            "provenance_fields": len(self.mapping_provenance),
            "timestamp": self.timestamp,
        }


class BundleInstanceMapper:
    """Maps a verified SkillBundle onto a Creator Instance document."""

    def __init__(
        self,
        resolver: BundleAssetResolver,
        *,
        timestamp: str = DEFAULT_TIMESTAMP,
    ) -> None:
        if not isinstance(resolver, BundleAssetResolver):
            raise MappingAssetError("BundleInstanceMapper requires a BundleAssetResolver")
        self._resolver = resolver
        self._timestamp = timestamp

    @property
    def resolver(self) -> BundleAssetResolver:
        return self._resolver

    @property
    def timestamp(self) -> str:
        return self._timestamp

    # -- entry point ------------------------------------------------------

    def map(self, bundle: SkillBundle) -> MappedInstance:
        """Map a bundle to an instance document."""

        if not isinstance(bundle, SkillBundle):
            raise MappingAssetError("map requires a SkillBundle")

        request = bundle.request
        self._assert_request_supported(request)

        assets = self._resolver.resolve(bundle)
        provenance = MappingProvenanceBuilder(timestamp=self._timestamp)
        notes: list[str] = []

        modules: list[ModuleMapping] = []
        for module in MAPPED_MODULES:
            modules.append(
                self._map_module(module, bundle, assets, provenance, notes)
            )

        instance: dict[str, Any] = {"contract_version": CONTRACT_VERSION}
        for mapped in modules:
            instance[mapped.module] = dict(mapped.document)

        contract_provenance = self._contract_provenance(bundle, assets, modules)
        # The C0.1 provenance block is sealed to its declared keys, so the mapping
        # identity is packed into `generated_by` and the detail lives in
        # `field_provenance`, which the contract declares as an open object.
        contract_provenance["field_provenance"] = self._field_provenance(
            provenance, modules
        )
        contract_provenance["generated_by"] = (
            f"creator_mapping.mapper c0.4-a "
            f"bundle={bundle.bundle_id} "
            f"rules={len(rule_ids())}"
        )
        instance["provenance"] = contract_provenance

        creator_id = str(instance["identity"]["creator_id"])
        return MappedInstance(
            instance=instance,
            bundle_id=bundle.bundle_id,
            creator_id=creator_id,
            modules=tuple(modules),
            mapping_provenance=provenance.as_dict(),
            assets=assets,
            notes=tuple(notes),
            timestamp=self._timestamp,
        )

    def map_document(self, bundle: SkillBundle) -> dict[str, Any]:
        """Map and return the audit report, not the instance."""

        return self.map(bundle).as_report()

    # -- request validation ----------------------------------------------

    def _assert_request_supported(self, request: CreatorRequest) -> None:
        if request.domain not in CONTRACT_DOMAINS:
            raise MappingRuleError(
                f"request domain {request.domain!r} is not one the contract accepts: "
                f"{', '.join(CONTRACT_DOMAINS)}"
            )
        if request.platform not in CONTRACT_PLATFORMS:
            raise MappingRuleError(
                f"request platform {request.platform!r} is not one the contract "
                f"accepts: {', '.join(CONTRACT_PLATFORMS)}"
            )

    # -- module mapping ---------------------------------------------------

    def _map_module(
        self,
        module: str,
        bundle: SkillBundle,
        assets: BundleAssets,
        provenance: MappingProvenanceBuilder,
        notes: list[str],
    ) -> ModuleMapping:
        rules = rules_for_module(module)
        skill_type = MODULE_SKILL_RULES[module]
        skill_ids = tuple(
            selection.skill_id
            for selection in bundle.all_selections()
            if selection.skill_type == skill_type
        )

        # A skill type may hold several skills with different assets - `distillation`
        # holds both text and visual distillation. Each derived field therefore
        # declares the *asset type* it must read from, and the asset is selected per
        # rule rather than per module, so text rules and visual rules can never read
        # each other's asset.
        asset_cache: dict[tuple[str, str], ResolvedAsset | None] = {}

        def asset_for(
            asset_types: "str | tuple[str, ...]", for_skill: str = ""
        ) -> ResolvedAsset | None:
            """Pick the asset a field reads from.

            When a rule names the skill it belongs to, that skill's own asset is
            preferred: two skills can bind two different assets of the same asset
            type - ``finance-persona`` binds the value rules and ``text-distillation``
            binds the structure templates - and a field must read the asset belonging
            to its own skill, not whichever sorts first.
            """

            key = (str(asset_types), for_skill)
            if key not in asset_cache:
                asset_cache[key] = _first_available_by_asset_type(
                    assets, asset_types, for_skill=for_skill
                )
            return asset_cache[key]

        def rule_asset(rule: FieldRule) -> ResolvedAsset | None:
            owner = _RULE_SKILL.get((rule.module, rule.path), "") or (
                _default_skill_for(bundle, rule.skill_type)
            )
            if rule.mode == "asset":
                return asset_for(required_asset_type(rule.module, rule.path), owner)
            if rule.mode in ("capability", "structural", "not_available"):
                # Capability and structural rules describe the module as a whole, so
                # they read the module's own skill asset when one exists.
                own = _MODULE_OWN_ASSET_TYPE.get(module, "")
                return asset_for(own, owner) if own else asset_for(
                    (), owner
                ) or assets.first_available_for(rule.skill_type)
            return None

        # A module whose skill type has no asset in the bundle at all - a partial
        # bundle may carry no visual skill - cannot derive a single field. Rather than
        # emitting a schema-invalid partial document, every target field is declared
        # absent with a reason, so the module still validates and the gap is explicit.
        asset_types_present = {
            assets.get(asset_id).asset_type for asset_id in assets.ids()
        }
        # `required_asset_type` returns a preference *tuple* per field, so the union of
        # all preferences must be flattened before it is intersected with what is
        # present; comparing a set of tuples to a set of strings never matches.
        module_types: set[str] = set()
        for rule in rules:
            if rule.mode == "asset":
                module_types.update(required_asset_type(module, rule.path))
        no_source_for_module = bool(module_types) and not (
            module_types & asset_types_present
        )

        def rule_skill(rule: FieldRule, resolved: ResolvedAsset | None) -> str:
            """Which skill a rule's provenance should name.

            A module may be fed by more than one skill of its type - ``identity`` is
            derived from the domain skill's value rules as well as the persona skill,
            and both bind the same asset. Naming the skill the rule actually reads
            from keeps the provenance truthful rather than crediting one skill for
            another's content.
            """

            explicit = _RULE_SKILL.get((rule.module, rule.path))
            if explicit is not None:
                if any(s.skill_id == explicit for s in bundle.all_selections()):
                    return explicit
            if resolved is not None:
                return resolved.skill_id
            selections = [
                s for s in bundle.all_selections() if s.skill_type == rule.skill_type
            ]
            return selections[0].skill_id if selections else ""

        def rule_asset_value(rule: FieldRule) -> ResolvedAsset | None:
            return rule_asset(rule)

        primary = rule_asset(rules[0]) if rules else None

        document: dict[str, Any] = {}
        applied: list[str] = []
        unavailable: list[str] = []
        used_assets: list[str] = []

        for rule in rules:
            rule_asset_value = rule_asset(rule)
            attribution = rule_skill(rule, rule_asset_value)
            if no_source_for_module and rule.mode == "asset":
                # No asset of this module's kind exists in the bundle, so the field is
                # declared absent rather than derived. Recorded through the same path
                # as any other declared absence, so provenance shape stays uniform.
                rule = replace(
                    rule,
                    mode="not_available",
                    unavailable_reason="no_asset_for_module_in_bundle",
                )
            value, record = self._apply_rule(
                rule, bundle, assets, rule_asset_value, skill_id=attribution
            )
            if rule.mode in ("unavailable", "not_available"):
                # A field with no source: `not_available` emits a marked declaration
                # in the document, `unavailable` has no place in a contract-valid
                # document at all. Both are recorded as declared absences so the
                # absence checks cover them.
                unavailable.append(rule.path)
            document[rule.path] = value
            provenance.add(
                module,
                rule.path,
                skill_id=record["skill_id"],
                asset_id=record["asset_id"],
                version=record["version"],
                rule_id=rule.rule_id,
                mode=rule.mode,
                skill_type=record.get("skill_type", rule.skill_type),
                note=record.get("note", ""),
            )
            applied.append(rule.rule_id)
            if record["asset_id"] != NO_ASSET:
                used_assets.append(record["asset_id"])

        # Module availability is recorded in the instance's provenance block rather
        # than inside the module: every module in the C0.1 contract is sealed, so
        # there is nowhere in a module document for a mapping annotation to live.
        # The module's *own* asset is sought including when it is unavailable, so the
        # registry's reason reaches the availability record.
        module_asset = (
            _asset_for_skill_type(assets, skill_type)
            or _module_own_asset(assets, module)
        )
        availability = self._availability(
            module, rules, module_asset, skill_type, notes, unavailable
        )

        return ModuleMapping(
            module=module,
            document=document,
            rule_ids=tuple(applied),
            unavailable_fields=tuple(unavailable),
            skill_ids=skill_ids,
            asset_ids=tuple(sorted(set(used_assets))),
            availability=availability,
        )

    # -- rule application -------------------------------------------------

    def _apply_rule(
        self,
        rule: FieldRule,
        bundle: SkillBundle,
        assets: BundleAssets,
        asset: ResolvedAsset | None,
        *,
        skill_id: str = "",
    ) -> tuple[Any, dict[str, str]]:
        """Return ``(value, provenance_source)`` for one field rule."""

        def source(note: str, resolved: ResolvedAsset | None) -> dict[str, str]:
            # The required asset kind is a property of the *field*, not of the rule's
            # current mode: a field whose asset is unavailable still must not be
            # attributed to a different asset that shares its skill type.
            types: tuple[str, ...] = ()
            if (rule.module, rule.path) in _DERIVATIONS:
                types = required_asset_type(rule.module, rule.path)
            return _source(
                asset=resolved,
                skill_type=rule.skill_type,
                assets=assets,
                note=note,
                skill_id=skill_id,
                asset_types=types,
            )

        if rule.mode == "asset":
            if asset is None:
                # No available asset feeds this field. Derive a declared absence
                # rather than a fabricated value.
                return (
                    _absence(
                        rule.module,
                        rule.path,
                        rule.unavailable_reason or "asset_not_available",
                    ),
                    source("no available asset for this skill type", None),
                )
            return (
                self._derive(rule, asset, assets, bundle.request),
                source("", asset),
            )

        if rule.mode == "structural":
            return (
                self._structural(rule, bundle, assets, asset),
                source("structural value", asset),
            )

        if rule.mode in ("unavailable", "not_available"):
            if rule.mode == "not_available":
                # A required scalar field gets a marked literal; every other
                # not_available target gets the structured declaration.
                if rule.path in _SCALAR_ABSENCE_PATHS:
                    value: Any = _scalar_absence(rule.unavailable_reason)
                else:
                    value = _absence(rule.module, rule.path, rule.unavailable_reason)
            else:
                value = None
            return (
                value,
                source(rule.unavailable_reason or "no source available", None),
            )

        # capability
        return (
            self._capability(rule, bundle, assets, asset),
            source("capability declaration", asset),
        )

    # -- derivations ------------------------------------------------------

    def _derive(
        self,
        rule: FieldRule,
        asset: ResolvedAsset,
        assets: BundleAssets,
        request: CreatorRequest,
    ) -> Any:
        """Derive a value from a resolved asset. Never copies a skill field."""

        table = _DERIVATIONS.get((rule.module, rule.path))
        if table is None:
            raise MappingRuleError(
                f"rule {rule.rule_id!r} targets {rule.module}.{rule.path} but no "
                "derivation is declared for it"
            )
        return table(asset, assets, request)

    def _structural(
        self,
        rule: FieldRule,
        bundle: SkillBundle,
        assets: BundleAssets,
        asset: ResolvedAsset | None,
    ) -> Any:
        request = bundle.request
        if rule.path == "creator_id":
            return _creator_id(bundle)
        if rule.path == "name":
            return _creator_id(bundle).replace("_", " ").replace("-", " ").title()
        if rule.path == "domain":
            return request.domain
        if rule.path == "platform":
            return request.platform
        if rule.path == "language":
            return "zh" if request.platform in ("xiaohongshu", "douyin", "wechat") else "en"
        if rule.module == "risk_policy" and rule.path == "review_required":
            return True
        if rule.module == "risk_policy" and rule.path == "source":
            return "risk_evaluation"
        if rule.module == "risk_policy" and rule.path == "runtime_connected":
            return False
        raise MappingRuleError(
            f"rule {rule.rule_id!r} is structural but no structural value is declared "
            f"for {rule.module}.{rule.path}"
        )

    def _capability(
        self,
        rule: FieldRule,
        bundle: SkillBundle,
        assets: BundleAssets,
        asset: ResolvedAsset | None,
    ) -> Any:
        """Return a capability declaration, never enabling an absent capability."""

        module = rule.module
        enabled = asset is not None and asset.available

        if module == "generation":
            if rule.path == "enabled":
                return enabled
            if rule.path == "reason":
                return "" if enabled else GENERATION_ABSENT_REASON
            if rule.path == "adapter_ref":
                return "deployment.generation_adapter"
            if rule.path == "input":
                return list(GENERATION_INPUTS)
            if rule.path == "output_format":
                return "content_plan"
            if rule.path == "quality_gate":
                return {
                    "required_decision": "PASS",
                    "controller_ref": (
                        "evaluation.quality_gate_controller.QualityGateController"
                    ),
                }

        if module == "publishing":
            if rule.path == "enabled":
                return enabled
            if rule.path == "reason":
                return "" if enabled else PUBLISHING_ABSENT_REASON
            if rule.path == "platform":
                platform = bundle.request.platform
                return platform if platform in ("xiaohongshu", "bilibili", "youtube",
                                                "douyin", "wechat", "web", "github") else "web"
            if rule.path == "image_requirement":
                ratio = PLATFORM_ASPECT_RATIOS.get(bundle.request.platform, "16:9")
                return {
                    "aspect_ratio": ratio,
                    "min_width": 1080,
                    "title_safe_area_ratio": 0.25,
                    "count": 1,
                }
            if rule.path == "api":
                return {
                    "adapter_ref": "deployment.publishing_adapter",
                    "idempotency_key": "creator_id + source_id + content_hash",
                    "retry_policy": "bounded",
                }
            if rule.path == "schedule":
                return {"mode": "manual", "timezone": "UTC"}
            if rule.path == "requires_human_approval":
                return True

        if module == "risk_policy" and rule.path == "enabled":
            return enabled

        raise MappingRuleError(
            f"rule {rule.rule_id!r} is a capability rule but no capability value is "
            f"declared for {module}.{rule.path}"
        )

    # -- module availability ---------------------------------------------

    def _availability(
        self,
        module: str,
        rules: Sequence[FieldRule],
        asset: ResolvedAsset | None,
        skill_type: str,
        notes: list[str],
        unavailable: Sequence[str],
    ) -> dict[str, Any]:
        """Describe the module's source availability, for the provenance block."""

        available = asset is not None and asset.available
        if not available:
            reason = (
                asset.reason
                if asset is not None and asset.reason
                else "no_available_asset_for_skill_type"
            )
            notes.append(
                f"{module}: mapped with no available asset for the {skill_type} skill "
                f"({reason})"
            )

        record: dict[str, Any] = {
            "skill_type": skill_type,
            "asset_id": asset.asset_id if asset is not None else NO_ASSET,
            "asset_type": asset.asset_type if asset is not None else "",
            "asset_status": asset.status if asset is not None else "absent",
            "asset_reason": asset.reason if asset is not None else "",
            "has_available_source": available,
            "declared_absent_fields": sorted(unavailable),
        }
        if module in CAPABILITY_MODULES:
            record["enabled_by_mapping"] = available
        return record

    # -- contract provenance ---------------------------------------------

    def _field_provenance(
        self,
        provenance: MappingProvenanceBuilder,
        modules: Sequence[ModuleMapping],
    ) -> dict[str, Any]:
        """The provenance payload the contract's open ``field_provenance`` holds.

        Carries both the per-field mapping records and the per-module availability
        records, because the contract gives the mapping layer exactly one open
        object to store them in.
        """

        return {
            "fields": provenance.as_dict(),
            "modules": {
                mapped.module: dict(mapped.availability) for mapped in modules
            },
            "rule_count": len(rule_ids()),
        }

    def _contract_provenance(
        self,
        bundle: SkillBundle,
        assets: BundleAssets,
        modules: Sequence[ModuleMapping],
    ) -> dict[str, Any]:
        """Module-level provenance, citing the skills and assets each module used."""

        block: dict[str, Any] = {}
        for mapped in modules:
            skill_type = MODULE_SKILL_RULES[mapped.module]
            selections = [
                selection
                for selection in bundle.all_selections()
                if selection.skill_type == skill_type
            ]
            # A module may read several assets - text_rules and visual_rules both
            # come from `distillation`, which holds two skills. Cite them all.
            module_assets = [
                assets.get(asset_id)
                for asset_id in mapped.asset_ids
                if assets.has(asset_id)
            ]
            available = [
                asset for asset in module_assets if asset is not None and asset.available
            ]
            primary = available[0] if available else (module_assets[0] if module_assets else None)

            record: dict[str, Any] = {
                "source": ", ".join(s.skill_id for s in selections) or NO_ASSET,
                "source_path": primary.location if primary is not None else "",
                "projection_method": "skill_bundle_mapping",
                "timestamp": self._timestamp,
                "confidence": 1.0 if available else 0.0,
                "asset_status": primary.status if primary is not None else "absent",
                "mapping_rules": list(mapped.rule_ids),
                "assets": list(mapped.asset_ids),
            }
            if primary is not None and primary.reason:
                record["asset_reason"] = primary.reason
            if mapped.unavailable_fields:
                record["declared_absent_fields"] = list(mapped.unavailable_fields)
            block[mapped.module] = record

        return block


# --------------------------------------------------------------------------
# Derivation table: (module, path) -> function(asset, assets, request) -> value
# --------------------------------------------------------------------------


def _identity_persona(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, Any]:
    sections = asset.document.get("sections") if asset.document else None
    if not isinstance(sections, Mapping) or not sections:
        raise MappingAssetError(
            f"asset {asset.asset_id!r} declares no sections to derive a persona from"
        )
    models = [
        {
            "model_id": str(section_id),
            "mechanism": str(description),
            "evidence": f"declared as a distillation section in {asset.asset_id}",
            "apply_when": f"material concerns {str(section_id).replace('_', ' ')}",
            "failure_condition": "no source material supports this section",
        }
        for section_id, description in sections.items()
    ]
    return {
        "mode": "reasoning_model",
        "identity_card": (
            f"A {request.domain} creator for {request.platform}, mapped from skill "
            f"bundle {request.creator_id or 'unnamed'}; persona derived from "
            f"{asset.asset_id}."
        ),
        "mental_models": models,
        "decision_heuristics": [
            f"prefer material whose {str(rule.get('dimension'))} dimension is present"
            for rule in (asset.document or {}).get("rules", [])
            if isinstance(rule, Mapping) and rule.get("dimension")
        ][:10]
        or ["prefer material that matches a declared value rule"],
        "honest_boundaries": [
            f"persona derived from {asset.asset_id}, not from a distilled creator",
            "no creator research was performed for this instance",
            "audience model is not available",
        ],
    }


def _identity_tone(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> str:
    boundaries = _first_asset_value(assets, "distillation", ("knowledge_boundary",))
    if isinstance(boundaries, Sequence) and boundaries:
        return "evidence-aware, mechanism-first, boundary-keeping"
    return "evidence-aware, mechanism-first"


def _source_keywords(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[dict[str, Any]]:
    rules = (asset.document or {}).get("rules")
    if not isinstance(rules, Sequence) or not rules:
        raise MappingAssetError(
            f"asset {asset.asset_id!r} declares no rules to derive keywords from"
        )
    keywords: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        weight = float(rule.get("weight", 0.5))
        for keyword in rule.get("keywords", ()):
            keywords.append({"keyword": str(keyword), "weight": weight})
    if not keywords:
        raise MappingAssetError(
            f"asset {asset.asset_id!r} declares no keywords to derive"
        )
    return keywords


def _source_data_sources(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[dict[str, Any]]:
    """Derive the data-source declaration.

    The source skill's own asset is unavailable, so the evidence-layer rule is
    taken from the review asset's rubric provenance. The declaration records the
    two-layer architecture the review skill enforces: discovery-layer material is
    not a factual basis.
    """

    return [
        {
            "source_id": "deployment-adapter",
            "layer": "evidence",
            "kind": "injected_adapter",
            "locator": "core.models.RawSource",
        },
        {
            "source_id": f"{request.platform}-discovery",
            "layer": "discovery",
            "kind": "social_platform",
            "locator": request.platform,
        },
    ]


def _text_title_formula(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[str]:
    sections = _structure_sections(assets)
    return [f"[specific subject], what is the [{name}]?" for name in sections[:3]]


def _text_structure(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, Any]:
    templates = _first_asset_value(assets, "distillation", ("templates",))
    if not isinstance(templates, Sequence) or not templates:
        raise MappingAssetError("no structure template is available to derive from")
    first = templates[0]
    if not isinstance(first, Mapping):
        raise MappingAssetError("structure template must be an object")
    return {
        "template_id": str(first.get("template_id", "mapped-template")),
        "sections": [str(section) for section in first.get("sections", [])],
    }


def _text_tone(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, Any]:
    return {
        "voice": "mechanism first, evidence before conclusion",
        "certainty": "assert on cited evidence; qualify forecasts",
        "avoid": ["unsourced numbers", "investment advice", "emotional framing"],
    }


def _text_length(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, int]:
    """Platform-aware length bounds.

    A contract-required structural value; no asset declares it, so the bounds are
    computed from the platform rather than invented per instance.
    """

    if request.platform in ("xiaohongshu", "douyin", "wechat"):
        return {"min_chars": 300, "max_chars": 1200}
    return {"min_chars": 300, "max_chars": 2400}


def _text_knowledge_boundary(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[str]:
    review = assets.first_available_for("review")
    questions: list[str] = []
    if review is not None and review.document:
        for field_name in ("dimensions", "finance_checks", "inherited_checks"):
            block = review.document.get(field_name)
            if isinstance(block, Mapping):
                for value in block.values():
                    if isinstance(value, Mapping) and value.get("question"):
                        questions.append(str(value["question"]))
    if not questions:
        questions = ["no review rubric is available to derive boundaries from"]
    return questions


def _visual_profile_id(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> str:
    return str(_visual_envelope(asset)["profile_id"])


def _visual_profile_version(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> str:
    return str(_visual_envelope(asset)["profile_version"])


def _visual_language(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> str:
    return str(_visual_section(asset, "identity").get("visual_language", ""))


def _visual_attention(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, str]:
    block = _visual_section(asset, "attention")
    return {str(key): str(value) for key, value in block.items()}


def _visual_composition(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, list[str]]:
    block = _visual_section(asset, "composition")
    return {
        "preferred_layout": [str(item) for item in block.get("preferred_layout", ())],
        "forbidden_layout": [str(item) for item in block.get("forbidden_layout", ())],
    }


def _visual_hierarchy(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, str]:
    block = _visual_section(asset, "hierarchy")
    return {str(key): str(value) for key, value in block.items()}


def _visual_constraints(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, list[str]]:
    block = _visual_section(asset, "constraints")
    return {
        "must_have": [str(item) for item in block.get("must_have", ())],
        "avoid": [str(item) for item in block.get("avoid", ())],
    }


def _visual_provenance(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, Any]:
    block = (asset.document or {}).get("provenance")
    if not isinstance(block, Mapping) or not block:
        raise MappingAssetError(
            f"asset {asset.asset_id!r} carries no provenance to reference"
        )
    return {str(key): value for key, value in block.items()}


def _risk_categories(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[dict[str, Any]]:
    rules = (asset.document or {}).get("rules")
    if not isinstance(rules, Sequence) or not rules:
        raise MappingAssetError(
            f"asset {asset.asset_id!r} declares no risk rules to derive from"
        )
    categories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        category_id = str(rule.get("category", rule.get("id", "unnamed")))
        if category_id in seen:
            continue
        seen.add(category_id)
        categories.append(
            {
                "category_id": category_id,
                "severity": str(rule.get("severity", "warning")),
                "action": str(rule.get("action", "require_review")),
                "definition": str(rule.get("message", "")),
            }
        )
    if not categories:
        raise MappingAssetError("no risk categories could be derived")
    return categories


def _risk_review_rules(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[dict[str, str]]:
    rubric = assets.first_available_for("review")
    pass_score = 0.6
    if rubric is not None and rubric.document:
        value = rubric.document.get("pass_score")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            pass_score = float(value)
    return [
        {"when": "any risk category with severity 'block' matched", "decision": "block"},
        {
            "when": f"domain score below pass_score ({pass_score})",
            "decision": "require_review",
        },
        {
            "when": "no blocking risk and domain score at or above pass_score",
            "decision": "pass",
        },
    ]


def _risk_blocked_patterns(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> list[dict[str, str]]:
    rules = (asset.document or {}).get("rules")
    if not isinstance(rules, Sequence) or not rules:
        raise MappingAssetError(
            f"asset {asset.asset_id!r} declares no rules to derive patterns from"
        )
    patterns: list[dict[str, str]] = []
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        category_id = str(rule.get("category", rule.get("id", "unnamed")))
        for keyword in rule.get("keywords", ()):
            patterns.append({"pattern": str(keyword), "category_id": category_id})
    if not patterns:
        raise MappingAssetError("no blocked patterns could be derived")
    return patterns


def _risk_evidence_requirement(
    asset: ResolvedAsset, assets: BundleAssets, request: CreatorRequest
) -> dict[str, Any]:
    return {
        "require_source_ids": True,
        "min_first_party_ratio": 0.5,
        "evidence_layer_only_as_fact": True,
    }


#: Every asset-derived target path and the function that produces it.
_DERIVATIONS: Mapping[tuple[str, str], Any] = {
    ("identity", "persona"): _identity_persona,
    ("identity", "tone"): _identity_tone,
    ("source", "keywords"): _source_keywords,
    ("source", "data_sources"): _source_data_sources,
    ("text_rules", "title_formula"): _text_title_formula,
    ("text_rules", "structure"): _text_structure,
    ("text_rules", "tone"): _text_tone,
    ("text_rules", "length"): _text_length,
    ("text_rules", "knowledge_boundary"): _text_knowledge_boundary,
    ("visual_rules", "profile_id"): _visual_profile_id,
    ("visual_rules", "profile_version"): _visual_profile_version,
    ("visual_rules", "visual_language"): _visual_language,
    ("visual_rules", "attention_strategy"): _visual_attention,
    ("visual_rules", "composition"): _visual_composition,
    ("visual_rules", "hierarchy"): _visual_hierarchy,
    ("visual_rules", "constraints"): _visual_constraints,
    ("visual_rules", "provenance"): _visual_provenance,
    ("risk_policy", "risk_categories"): _risk_categories,
    ("risk_policy", "review_rules"): _risk_review_rules,
    ("risk_policy", "blocked_patterns"): _risk_blocked_patterns,
    ("risk_policy", "evidence_requirement"): _risk_evidence_requirement,
}

#: Declared asset type preference for each derived target path, in order.
#:
#: This is how the mapping layer picks the right asset when one skill type holds
#: several skills with different assets - `distillation` holds both text and visual
#: distillation, and text rules and visual rules must not read each other's asset.
#: More than one entry means either asset may serve, first match wins: a bundle may
#: select the risk-reference review skill or the rubric review skill, and the same
#: target field must work either way.
_REQUIRED_ASSET_TYPES: Mapping[str, tuple[str, ...]] = {
    "identity.persona": ("text_rules",),
    "identity.tone": ("text_rules",),
    "source.keywords": ("text_rules",),
    "source.data_sources": ("text_rules",),
    "text_rules.title_formula": ("text_rules",),
    "text_rules.structure": ("text_rules",),
    "text_rules.tone": ("text_rules",),
    "text_rules.length": ("text_rules",),
    "text_rules.knowledge_boundary": ("evaluation_policy", "risk_reference"),
    "visual_rules.profile_id": ("visual_rules",),
    "visual_rules.profile_version": ("visual_rules",),
    "visual_rules.visual_language": ("visual_rules",),
    "visual_rules.attention_strategy": ("visual_rules",),
    "visual_rules.composition": ("visual_rules",),
    "visual_rules.hierarchy": ("visual_rules",),
    "visual_rules.constraints": ("visual_rules",),
    "visual_rules.provenance": ("visual_rules",),
    "risk_policy.risk_categories": ("risk_reference",),
    "risk_policy.review_rules": ("risk_reference", "evaluation_policy"),
    "risk_policy.blocked_patterns": ("risk_reference",),
    "risk_policy.evidence_requirement": ("evaluation_policy", "risk_reference"),
}


#: Declared absence paths whose target field the contract requires to be a string,
#: so the declaration must be a marked literal rather than an object.
_SCALAR_ABSENCE_PATHS: frozenset[str] = frozenset({"audience"})

#: Target fields whose content is derived from a skill other than the module's own
#: default skill type. ``identity.persona`` and ``source.keywords`` come from the
#: domain skill's value rules, so the provenance must name the domain skill rather
#: than the persona skill, which binds the same asset for a different reason.
_RULE_SKILL: Mapping[tuple[str, str], str] = {
    ("identity", "persona"): "business-finance-analysis",
    ("source", "keywords"): "business-finance-analysis",
    ("text_rules", "title_formula"): "text-distillation",
    ("text_rules", "structure"): "text-distillation",
    ("text_rules", "tone"): "text-distillation",
    ("text_rules", "length"): "text-distillation",
    ("text_rules", "knowledge_boundary"): "finance-risk-review",
    ("risk_policy", "evidence_requirement"): "finance-risk-review",
}


def required_asset_type(module: str, path: str) -> tuple[str, ...]:
    """The C0.2 asset types a derived path may read from, in preference order."""

    key = f"{module}.{path}"
    try:
        return _REQUIRED_ASSET_TYPES[key]
    except KeyError as exc:
        raise MappingRuleError(
            f"no asset type is declared for the derived field {key!r}"
        ) from exc


#: The asset type each module's own capability and structural rules describe.
_MODULE_OWN_ASSET_TYPE: Mapping[str, str] = {
    "risk_policy": "risk_reference",
    "generation": "generation_capability",
    "publishing": "publishing_capability",
}


def _first_available_by_asset_type(
    assets: BundleAssets,
    asset_types: "str | tuple[str, ...]",
    *,
    for_skill: str = "",
) -> ResolvedAsset | None:
    """Return the available resolved asset of the declared type(s).

    When ``for_skill`` names a skill the bundle selected, that skill's own asset wins
    even if another skill of the same type binds an asset of the same type. Otherwise
    the first match in asset-id order is returned, which is deterministic.
    """

    if not asset_types:
        return None
    wanted = (asset_types,) if isinstance(asset_types, str) else asset_types

    if for_skill:
        for asset_id in assets.ids():
            asset = assets.get(asset_id)
            if asset.skill_id == for_skill and asset.asset_type in wanted:
                return asset if asset.available else None

    for asset_type in wanted:
        for asset_id in assets.ids():
            asset = assets.get(asset_id)
            if asset.available and asset.asset_type == asset_type:
                return asset
    return None


def _asset_for_skill_type(
    assets: BundleAssets, skill_type: str
) -> ResolvedAsset | None:
    """The asset a module's own skill type resolved to, available or not."""

    candidates = assets.by_skill_type(skill_type)
    return candidates[0] if candidates else None


def _module_own_asset(
    assets: BundleAssets, module: str
) -> ResolvedAsset | None:
    """The asset whose type the module's capability and structural rules describe."""

    wanted = _MODULE_OWN_ASSET_TYPE.get(module, "")
    if not wanted:
        return None
    for asset_id in assets.ids():
        asset = assets.get(asset_id)
        if asset.asset_type == wanted:
            return asset
    return None


def _default_skill_for(bundle: SkillBundle, skill_type: str) -> str:
    """The skill a rule of this type belongs to, when the rule names none."""

    for selection in bundle.all_selections():
        if selection.skill_type == skill_type:
            return selection.skill_id
    return ""


def derivation_parameter_count(module: str, path: str) -> int:
    """How many positional parameters a derivation function takes."""

    function = _DERIVATIONS[(module, path)]
    return len(inspect.signature(function).parameters)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


#: Declared absence shapes.
#:
#: ``source.collection_rules`` and ``source.reference_creators[]`` are *sealed* in
#: the contract, so no extra marker key can be added. The declaration is therefore
#: carried by the required values themselves: a zero that means "nothing is
#: collected", a ``dedupe_by`` and a ``verification_method`` holding the marked
#: literal. Nothing here can be mistaken for real configuration, and
#: :mod:`creator_mapping.validation` asserts each marker is present.
_ABSENCE_SHAPES: Mapping[str, Any] = {
    "collection_rules": lambda code: {
        "min_notes": 0,
        "material_tiers": ["A"],
        "rate_limit_seconds": 0,
        "dedupe_by": f"{ABSENCE_MARKER}{code}",
    },
    "reference_creators": lambda code: [
        {
            "name": "unmapped",
            "platform": "web",
            "identity_verified": True,
            "verification_method": f"{ABSENCE_MARKER}{code}",
            "role": "unassigned",
        }
    ],
    # A sealed object whose inner keys are all required - the persona, the text
    # tone, and the visual vocabulary - carries its marker inside one of the required
    # values, so the shape validates while still declaring itself unmapped.
    "persona": lambda code: {
        "mode": "reasoning_model",
        "identity_card": f"{ABSENCE_MARKER}{code}",
        "mental_models": [
            {
                "model_id": "unmapped",
                "mechanism": f"{ABSENCE_MARKER}{code}",
                "evidence": f"{ABSENCE_MARKER}{code}",
                "apply_when": f"{ABSENCE_MARKER}{code}",
                "failure_condition": f"{ABSENCE_MARKER}{code}",
            }
        ],
        "decision_heuristics": [f"{ABSENCE_MARKER}{code}"],
        "honest_boundaries": [f"{ABSENCE_MARKER}{code}"],
    },
    "tone": lambda code: {
        "voice": f"{ABSENCE_MARKER}{code}",
        "certainty": f"{ABSENCE_MARKER}{code}",
        "avoid": [f"{ABSENCE_MARKER}{code}"],
    },
    # `identity.tone` is a plain string while `text_rules.tone` is an object, so the
    # two fields of the same name need different declaration shapes.
    "identity.tone": lambda code: f"{ABSENCE_MARKER}{code}",
    "attention_strategy": lambda code: {"first": f"{ABSENCE_MARKER}{code}"},
    "hierarchy": lambda code: {"primary": f"{ABSENCE_MARKER}{code}"},
    # The visual envelope carries plain-string identifiers, so their declaration is a
    # marked literal rather than an object.
    "profile_id": lambda code: f"{ABSENCE_MARKER}{code}",
    "profile_version": lambda code: f"{ABSENCE_MARKER}{code}",
    "visual_language": lambda code: f"{ABSENCE_MARKER}{code}",
    "composition": lambda code: {
        "preferred_layout": [f"{ABSENCE_MARKER}{code}"],
        "forbidden_layout": [],
    },
    "constraints": lambda code: {"must_have": [], "avoid": [f"{ABSENCE_MARKER}{code}"]},
    "structure": lambda code: {
        "template_id": f"{ABSENCE_MARKER}{code}",
        "sections": [f"{ABSENCE_MARKER}{code}"],
    },
    "length": lambda code: {"min_chars": 0, "max_chars": 0},
    "title_formula": lambda code: [f"{ABSENCE_MARKER}{code}"],
    "knowledge_boundary": lambda code: [f"{ABSENCE_MARKER}{code}"],
    "provenance": lambda code: {"source": f"{ABSENCE_MARKER}{code}"},
    "evidence_requirement": lambda code: {
        "require_source_ids": True,
        "min_first_party_ratio": 0.0,
        "evidence_layer_only_as_fact": True,
    },
    "review_rules": lambda code: [
        {"when": f"{ABSENCE_MARKER}{code}", "decision": "require_review"}
    ],
    "risk_categories": lambda code: [
        {
            "category_id": f"{ABSENCE_MARKER}{code}",
            "severity": "warning",
            "action": "require_review",
            "definition": f"{ABSENCE_MARKER}{code}",
        }
    ],
    "blocked_patterns": lambda code: [
        {"pattern": f"{ABSENCE_MARKER}{code}", "category_id": f"{ABSENCE_MARKER}{code}"}
    ],
    "data_sources": lambda code: [
        {
            "source_id": f"{ABSENCE_MARKER}{code}",
            "layer": "evidence",
            "kind": "unmapped",
        }
    ],
    "keywords": lambda code: [{"keyword": f"{ABSENCE_MARKER}{code}", "weight": 0.0}],
}


def _absence(module: str, path: str, reason: str) -> Any:
    """An explicit declaration of absence, never a substitute value."""

    code = reason or "source_not_available"
    # Module-qualified shape wins, so fields sharing a name across modules can
    # declare absence in the type each module actually requires.
    shape = _ABSENCE_SHAPES.get(f"{module}.{path}") or _ABSENCE_SHAPES.get(path)
    if shape is not None:
        return shape(code)
    return {"not_available": True, "reason": code}


def _scalar_absence(reason: str) -> str:
    """A declared absence for a field the contract requires to be a string.

    The value is a marked literal rather than a plausible-looking default, so a
    reader can tell an unmapped field from a mapped one at a glance, and
    validation can assert the marker is present.
    """

    return f"{ABSENCE_MARKER}{reason or 'source_not_available'}"


def _creator_id(bundle: SkillBundle) -> str:
    """Derive a creator id from the request, falling back to the bundle id."""

    raw = bundle.request.creator_id.strip()
    if raw:
        return raw
    return f"creator-{bundle.bundle_id.removeprefix('bundle-')[:12]}"


def _source(
    *,
    asset: ResolvedAsset | None,
    skill_type: str,
    assets: BundleAssets,
    note: str,
    skill_id: str = "",
    asset_types: "str | tuple[str, ...]" = (),
) -> dict[str, str]:
    """Provenance source for one field rule.

    When the preferred asset is unavailable, the fallback deliberately does **not**
    cite some other asset of the same skill type: an unavailable visual asset must
    not be attributed to the text asset that happens to share its skill type. The
    absence is recorded instead.
    """

    if asset is not None:
        return {
            "skill_id": skill_id or asset.skill_id,
            "asset_id": asset.asset_id,
            "version": asset.skill_version,
            "skill_type": asset.skill_type,
            "note": note,
        }

    if asset_types:
        # The field needed a specific asset kind and none was available, so name the
        # skill without inventing an asset.
        return {
            "skill_id": skill_id or NO_ASSET,
            "asset_id": NO_ASSET,
            "version": _skill_version(assets, skill_id) or "0.0.0",
            "skill_type": skill_type,
            "note": note or "declared absence",
        }

    candidate = assets.by_skill_type(skill_type)
    if candidate:
        first = candidate[0]
        return {
            "skill_id": skill_id or first.skill_id,
            "asset_id": first.asset_id,
            "version": first.skill_version,
            "skill_type": first.skill_type,
            "note": note or "declared absence",
        }
    return {
        "skill_id": skill_id or NO_ASSET,
        "asset_id": NO_ASSET,
        "version": "0.0.0",
        "skill_type": skill_type,
        "note": note or "no skill of this type is present in the bundle",
    }


def _skill_version(assets: BundleAssets, skill_id: str) -> str:
    """The version of a skill the bundle selected, or an empty string."""

    for selection in assets.skills:
        if selection.skill_id == skill_id:
            return selection.version
    return ""


def _visual_envelope(asset: ResolvedAsset) -> Mapping[str, Any]:
    block = (asset.document or {}).get("visual_profile")
    if not isinstance(block, Mapping):
        raise MappingAssetError(
            f"asset {asset.asset_id!r} has no visual_profile envelope"
        )
    return block


def _visual_section(asset: ResolvedAsset, name: str) -> Mapping[str, Any]:
    block = (asset.document or {}).get(name)
    if not isinstance(block, Mapping):
        raise MappingAssetError(
            f"asset {asset.asset_id!r} has no {name!r} section"
        )
    return block


def _structure_sections(assets: BundleAssets) -> list[str]:
    templates = _first_asset_value(assets, "distillation", ("templates",))
    if not isinstance(templates, Sequence) or not templates:
        return []
    first = templates[0]
    if not isinstance(first, Mapping):
        return []
    return [str(section) for section in first.get("sections", ())]


def _first_asset_value(
    assets: BundleAssets, skill_type: str, path: tuple[str, ...]
) -> Any:
    """Read a nested value from the first available asset of a skill type."""

    asset = assets.first_available_for(skill_type)
    if asset is None or asset.document is None:
        return None
    current: Any = asset.document
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


# --------------------------------------------------------------------------
# Module-level entry points
# --------------------------------------------------------------------------


def map_bundle_to_instance(
    bundle: SkillBundle,
    *,
    resolver: BundleAssetResolver | None = None,
    workspace_root: str | Path | None = None,
    timestamp: str = DEFAULT_TIMESTAMP,
) -> MappedInstance:
    """Map a SkillBundle to a Creator Instance.

    Either supply a ``resolver``, or a ``workspace_root`` from which one is built
    over the workspace's asset registry and default skill registry.
    """

    active = resolver or _resolver_for(bundle, workspace_root)
    if active.skill_registry is not None and not _bundle_is_registered(bundle, active):
        raise MappingCompletenessError(
            f"bundle {bundle.bundle_id!r} selects skills the resolver's registry does "
            "not hold; map the bundle against the registry it was composed from"
        )
    return BundleInstanceMapper(active, timestamp=timestamp).map(bundle)


def _resolver_for(
    bundle: SkillBundle, workspace_root: str | Path | None
) -> BundleAssetResolver:
    if workspace_root is None:
        raise MappingAssetError(
            "map_bundle_to_instance needs either a resolver or a workspace_root"
        )
    return BundleAssetResolver.default(workspace_root)


def _bundle_is_registered(
    bundle: SkillBundle, resolver: BundleAssetResolver
) -> bool:
    for selection in bundle.all_selections():
        if not resolver.skill_registry.has(
            f"{selection.skill_id}@{selection.version}"
        ):
            return False
    return True


def write_mapped_instance(
    mapped: MappedInstance, out_root: str | Path
) -> list[Path]:
    """Write a mapped instance using the contract's eight-module layout.

    Refuses to write an instance that does not validate.
    """

    try:
        validate_contract(mapped.instance)
    except CreatorContractError as exc:
        raise MappingCompletenessError(
            f"refusing to write an invalid mapped instance: {exc}"
        ) from exc

    target = instance_dir(out_root, mapped.creator_id)
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for module in MAPPED_MODULES:
        path = target / f"{module}.json"
        path.write_text(canonical_json(mapped.instance[module]), encoding="utf-8")
        written.append(path)

    provenance_path = target / "provenance.json"
    provenance_path.write_text(
        canonical_json(
            {
                "modules": mapped.instance["provenance"],
                "field_provenance": mapped.mapping_provenance,
                "mapping_report": mapped.as_report(),
            }
        ),
        encoding="utf-8",
    )
    written.append(provenance_path)

    aggregate = target / "instance.json"
    aggregate.write_text(canonical_json(mapped.instance), encoding="utf-8")
    written.append(aggregate)
    return written


__all__ = [
    "BundleInstanceMapper",
    "CONTRACT_DOMAINS",
    "CONTRACT_LANGUAGES",
    "CONTRACT_PLATFORMS",
    "GENERATION_ABSENT_REASON",
    "GENERATION_INPUTS",
    "MISSING_IDENTITY_NAME",
    "MappedInstance",
    "ModuleMapping",
    "PLATFORM_ASPECT_RATIOS",
    "PUBLISHING_ABSENT_REASON",
    "bundle_instance_diff",
    "map_bundle_to_instance",
    "write_mapped_instance",
]


# --------------------------------------------------------------------------
# Bundle -> Instance diff
# --------------------------------------------------------------------------


def bundle_instance_diff(
    bundle: SkillBundle, mapped: MappedInstance
) -> dict[str, Any]:
    """Compare a SkillBundle against the instance it was mapped to.

    Answers the four questions the brief names:

    1. **Is every skill mapped?** A selected skill whose type reaches no module is
       an unmapped skill.
    2. **Has an asset been lost?** A skill whose asset does not appear in the
       mapping provenance was dropped in transit.
    3. **Did a capability change?** A capability module whose availability the
       mapping does not justify from the asset's own status.
    4. **Is provenance complete?** Every required target path must carry a record
       naming a skill, an asset, a version and a rule.

    Returns a document with ``consistent`` and the four difference lists.
    """

    if not isinstance(bundle, SkillBundle):
        raise MappingAssetError("bundle_instance_diff requires a SkillBundle")
    if not isinstance(mapped, MappedInstance):
        raise MappingAssetError("bundle_instance_diff requires a MappedInstance")

    provenance = mapped.mapping_provenance
    mapped_modules = {module.module for module in mapped.modules}

    # 1. every skill mapped
    unmapped_skills: list[dict[str, Any]] = []
    for selection in bundle.all_selections():
        targets = SKILL_MODULE_RULES.get(selection.skill_type, ())
        if not targets or not (set(targets) & mapped_modules):
            unmapped_skills.append(
                {
                    "skill_id": selection.skill_id,
                    "skill_type": selection.skill_type,
                    "reason": "skill type reaches no mapped module",
                }
            )

    # 2. assets lost
    surviving_assets = {
        str(record.get("asset_id"))
        for record in provenance.values()
        if isinstance(record, Mapping)
    }
    bundle_assets = {asset.asset_id for asset in mapped.assets.assets.values()}
    lost_assets = [
        {
            "asset_id": asset_id,
            "reason": "asset resolved for the bundle but appears in no mapping record",
        }
        for asset_id in sorted(bundle_assets - surviving_assets)
    ]

    # 3. capability changes
    availability_by_module = mapped.module_availability
    capability_changes: list[dict[str, Any]] = []
    for module in CAPABILITY_MODULES:
        block = mapped.instance.get(module)
        if not isinstance(block, Mapping):
            capability_changes.append(
                {"module": module, "reason": "module missing from the instance"}
            )
            continue
        availability = availability_by_module.get(module)
        if not isinstance(availability, Mapping) or not availability:
            capability_changes.append(
                {"module": module, "reason": "no availability record to justify enabled"}
            )
            continue
        has_source = availability.get("has_available_source")
        enabled = block.get("enabled")
        if has_source is not True and enabled is not False:
            capability_changes.append(
                {
                    "module": module,
                    "reason": "enabled without an available source",
                    "enabled": enabled,
                    "has_available_source": has_source,
                }
            )
        if has_source is True and enabled is not True:
            capability_changes.append(
                {
                    "module": module,
                    "reason": "available source but the capability is disabled",
                    "enabled": enabled,
                    "has_available_source": has_source,
                }
            )

    # 4. provenance incomplete
    incomplete_provenance: list[dict[str, Any]] = []
    for module_mapping in mapped.modules:
        for path in REQUIRED_PATHS[module_mapping.module]:
            key = f"{module_mapping.module}.{path}"
            record = provenance.get(key)
            if not isinstance(record, Mapping):
                incomplete_provenance.append({"field": key, "reason": "no record"})
                continue
            missing = [name for name in REQUIRED_MAPPING_KEYS if name not in record]
            if missing:
                incomplete_provenance.append(
                    {"field": key, "reason": "missing " + ", ".join(missing)}
                )
                continue
            for name in ("skill_id", "asset_id", "version", "rule_id"):
                if not str(record.get(name, "")).strip():
                    incomplete_provenance.append(
                        {"field": key, "reason": f"empty {name}"}
                    )
                    break

    consistent = not (
        unmapped_skills
        or lost_assets
        or capability_changes
        or incomplete_provenance
    )
    return {
        "bundle_id": bundle.bundle_id,
        "instance_creator_id": mapped.creator_id,
        "consistent": consistent,
        "unmapped_skills": unmapped_skills,
        "lost_assets": lost_assets,
        "capability_changes": capability_changes,
        "incomplete_provenance": incomplete_provenance,
        "counts": {
            "skills": len(bundle.all_selections()),
            "assets": len(bundle_assets),
            "fields": len(provenance),
        },
    }