"""Resolve a bundle's skills to the assets they are bound to.

A skill names its asset in ``provenance.source_ref``. This module reads that asset
through the **C0.2 asset registry** - the mapping layer contains no asset paths of
its own, so there is exactly one place where an asset location is declared.

An unavailable asset is not an error here. It is resolved to a record carrying its
status and reason, because the mapper must be able to *declare* the absence rather
than substitute a value for it. Only a malformed or unregistered asset raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from creator_projection import AssetRegistry, ProjectionError
from creator_skill import SkillBundle, SkillRegistry, SkillSelection

from .errors import MappingAssetError

#: Asset kinds whose content the mapping layer derives fields from.
DERIVABLE_SOURCE_KINDS: tuple[str, ...] = ("distillation_artifact", "projection")

#: Asset kinds that name a location rather than a registered artifact.
LOCATION_SOURCE_KINDS: tuple[str, ...] = ("template", "manual")


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    """One skill's asset, resolved to a document or to a declared absence."""

    asset_id: str
    asset_type: str
    status: str
    reason: str
    location: str
    document: Mapping[str, Any] | None
    skill_id: str
    skill_type: str
    skill_version: str
    source_kind: str

    @property
    def available(self) -> bool:
        return self.status == "available" and self.document is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "status": self.status,
            "reason": self.reason,
            "location": self.location,
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "skill_version": self.skill_version,
            "source_kind": self.source_kind,
            "loaded": self.available,
        }


@dataclass(frozen=True, slots=True)
class BundleAssets:
    """Every asset a bundle resolves to, keyed by asset id."""

    bundle_id: str
    assets: Mapping[str, ResolvedAsset]
    skills: tuple[SkillSelection, ...]

    def __len__(self) -> int:
        return len(self.assets)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.assets))

    def get(self, asset_id: str) -> ResolvedAsset:
        try:
            return self.assets[asset_id]
        except KeyError as exc:
            raise MappingAssetError(
                f"asset {asset_id!r} was not resolved for bundle "
                f"{self.bundle_id!r}; resolved: {', '.join(self.ids())}"
            ) from exc

    def has(self, asset_id: str) -> bool:
        return asset_id in self.assets

    def available(self) -> tuple[ResolvedAsset, ...]:
        return tuple(asset for asset in self.assets.values() if asset.available)

    def unavailable(self) -> tuple[ResolvedAsset, ...]:
        return tuple(asset for asset in self.assets.values() if not asset.available)

    def by_skill_type(self, skill_type: str) -> tuple[ResolvedAsset, ...]:
        return tuple(
            asset for asset in self.assets.values() if asset.skill_type == skill_type
        )

    def first_available_for(self, skill_type: str) -> ResolvedAsset | None:
        """Return the first available asset a skill of this type resolved to."""

        for asset in self.by_skill_type(skill_type):
            if asset.available:
                return asset
        return None

    def for_skill(self, skill_id: str) -> ResolvedAsset:
        for asset in self.assets.values():
            if asset.skill_id == skill_id:
                return asset
        raise MappingAssetError(
            f"skill {skill_id!r} resolved to no asset in bundle {self.bundle_id!r}"
        )

    def statuses(self) -> dict[str, str]:
        return {asset_id: self.assets[asset_id].status for asset_id in self.ids()}

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "assets": {key: self.assets[key].as_dict() for key in self.ids()},
            "skills": [s.skill_id for s in self.skills],
        }


class BundleAssetResolver:
    """Resolve a bundle's skills to their bound assets.

    Holds both registries: the skill registry to turn a bundle's *selections* back
    into skills, and the asset registry to read what those skills are bound to.
    """

    def __init__(
        self,
        asset_registry: AssetRegistry,
        skill_registry: SkillRegistry,
    ) -> None:
        if not isinstance(asset_registry, AssetRegistry):
            raise MappingAssetError("BundleAssetResolver requires an AssetRegistry")
        if not isinstance(skill_registry, SkillRegistry):
            raise MappingAssetError("BundleAssetResolver requires a SkillRegistry")
        self._assets = asset_registry
        self._skills = skill_registry

    @classmethod
    def default(cls, workspace_root: str | Path) -> "BundleAssetResolver":
        """Build a resolver over the workspace's asset registry and default skills."""

        return cls(
            AssetRegistry.load(workspace_root),
            SkillRegistry.default(validate=False),
        )

    @property
    def asset_registry(self) -> AssetRegistry:
        return self._assets

    @property
    def skill_registry(self) -> SkillRegistry:
        return self._skills

    def resolve(self, bundle: SkillBundle) -> BundleAssets:
        """Resolve every skill in a bundle, including extras."""

        if not isinstance(bundle, SkillBundle):
            raise MappingAssetError("resolve requires a SkillBundle")

        resolved: dict[str, ResolvedAsset] = {}
        skills = bundle.all_selections()
        for selection in skills:
            record = self._resolve_selection(bundle, selection)
            resolved.setdefault(record.asset_id, record)

        return BundleAssets(
            bundle_id=bundle.bundle_id, assets=resolved, skills=tuple(skills)
        )

    # -- internals --------------------------------------------------------

    def _resolve_selection(
        self, bundle: SkillBundle, selection: SkillSelection
    ) -> ResolvedAsset:
        try:
            skill = self._skills.resolve(f"{selection.skill_id}@{selection.version}")
        except Exception as exc:  # registry error type is not exported by design
            raise MappingAssetError(
                f"bundle {bundle.bundle_id!r} selects skill {selection.skill_id!r} "
                f"at version {selection.version!r}, which the skill registry does not "
                f"hold: {exc}"
            ) from exc

        asset_id = str(skill.provenance.source_ref)
        source_kind = str(skill.provenance.source_kind)

        if asset_id not in self._assets.ids():
            raise MappingAssetError(
                f"skill {selection.skill_id!r} names asset {asset_id!r}, which is not "
                "registered in the asset registry"
            )
        asset = self._assets.get(asset_id)

        document: Mapping[str, Any] | None = None
        if asset.available:
            try:
                document = self._read(asset_id, asset.asset_format)
            except ProjectionError as exc:
                raise MappingAssetError(
                    f"cannot read asset {asset_id!r} for skill "
                    f"{selection.skill_id!r}: {exc}"
                ) from exc

        return ResolvedAsset(
            asset_id=asset_id,
            asset_type=asset.asset_type,
            status=asset.status,
            reason=asset.reason or "",
            location=asset.location,
            document=document,
            skill_id=selection.skill_id,
            skill_type=selection.skill_type,
            skill_version=skill.version,
            source_kind=source_kind,
        )

    def _read(self, asset_id: str, asset_format: str) -> Mapping[str, Any]:
        if asset_format == "yaml":
            return self._assets.read_yaml(asset_id)
        if asset_format == "json":
            return self._assets.read_json(asset_id)
        if asset_format == "markdown":
            from creator_projection import parse_markdown

            document = parse_markdown(self._assets.read_text(asset_id))
            return {
                "frontmatter": dict(document.frontmatter),
                "preamble": document.preamble,
                "sections": [section.as_dict() for section in document.sections],
            }
        raise MappingAssetError(
            f"asset {asset_id!r} has format {asset_format!r}, which the mapping layer "
            "cannot derive fields from"
        )


__all__ = [
    "BundleAssetResolver",
    "BundleAssets",
    "DERIVABLE_SOURCE_KINDS",
    "LOCATION_SOURCE_KINDS",
    "ResolvedAsset",
]
