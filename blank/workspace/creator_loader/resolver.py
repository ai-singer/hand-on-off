"""Asset reference resolution — read-only, and content-free by design.

The loader records **what an instance references**, not what the referenced asset
contains. Resolving an asset reference means asking the C0.2 registry for its
status, type and location; it does **not** mean reading the asset's document.

That distinction is the point. Loading a ``profile_id`` is configuration; loading
the visual profile's contents, still less rendering anything from it, is not this
layer's business. A caller that wants the asset's content goes to
``creator_projection``'s registry directly and takes responsibility for what it
does with it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_projection import AssetRegistry, ProjectionError

from .errors import InstanceAssetReferenceError
from .model import AssetReference

#: Asset kinds whose absence is a *declared* capability rather than a defect.
DECLARED_ASSET_STATUSES: tuple[str, ...] = ("unavailable",)

#: Fields in a field-provenance record that name an asset.
ASSET_ID_KEYS: tuple[str, ...] = ("asset_id", "asset")


class AssetReferenceResolver:
    """Resolves asset ids to :class:`AssetReference` records, without reading them."""

    def __init__(self, registry: AssetRegistry) -> None:
        if not isinstance(registry, AssetRegistry):
            raise InstanceAssetReferenceError(
                "AssetReferenceResolver requires a creator_projection AssetRegistry"
            )
        self._registry = registry
        self._cache: dict[str, AssetReference] = {}

    @classmethod
    def for_workspace(cls, workspace_root: str | Path) -> "AssetReferenceResolver":
        """Build a resolver over the workspace's asset registry."""

        return cls(AssetRegistry.load(workspace_root))

    @property
    def registry(self) -> AssetRegistry:
        return self._registry

    def knows(self, asset_id: str) -> bool:
        """Whether the registry declares this asset id at all."""

        return asset_id in self._registry.ids()

    def resolve(
        self,
        asset_id: str,
        *,
        skill_id: str | None = None,
        version: str | None = None,
    ) -> AssetReference:
        """Return a reference record for an asset id.

        An asset the registry does not declare is returned with
        ``registered=False`` rather than raising: an instance may legitimately cite
        an asset a given workspace does not ship, and the loader's job is to report
        that, not to fail the load. Only a malformed id raises.

        ``skill_id`` and ``version`` are *attributions*: which skill and which skill
        version the citation came from. Omitting one leaves whatever is already
        known; supplying one sets it, even for an id already resolved, because a
        blank attribution must never shadow a later, better-informed call.
        """

        if not isinstance(asset_id, str) or not asset_id.strip():
            raise InstanceAssetReferenceError(
                "asset reference must be a non-empty string",
                detail=f"skill_id={skill_id!r}",
            )
        asset_id = asset_id.strip()

        cached = self._cache.get(asset_id)
        if cached is not None:
            resolved_skill = cached.skill_id if skill_id is None else skill_id
            resolved_version = cached.version if version is None else version
            if resolved_skill == cached.skill_id and resolved_version == cached.version:
                return cached
            updated = AssetReference(
                asset_id=cached.asset_id,
                asset_type=cached.asset_type,
                asset_status=cached.asset_status,
                reason=cached.reason,
                location=cached.location,
                skill_id=resolved_skill,
                registered=cached.registered,
                version=resolved_version,
            )
            self._cache[asset_id] = updated
            return updated

        if not self.knows(asset_id):
            record = AssetReference(
                asset_id=asset_id,
                asset_type="",
                asset_status="unregistered",
                reason="asset_not_registered_in_this_workspace",
                skill_id=skill_id or "",
                registered=False,
                version=version or "",
            )
            self._cache[asset_id] = record
            return record

        asset = self._registry.get(asset_id)
        record = AssetReference(
            asset_id=asset_id,
            asset_type=asset.asset_type,
            asset_status=asset.status,
            reason=asset.reason or "",
            location=asset.location,
            skill_id=skill_id or "",
            registered=True,
            version=version or "",
        )
        self._cache[asset_id] = record
        return record

    def resolve_many(
        self,
        asset_ids: Sequence[str],
        *,
        skill_id: str | None = None,
        version: str | None = None,
    ) -> dict[str, AssetReference]:
        """Resolve many ids at once, keyed by id, skipping blanks and placeholders."""

        resolved: dict[str, AssetReference] = {}
        for asset_id in asset_ids:
            if not isinstance(asset_id, str) or not asset_id.strip():
                continue
            if asset_id in _NON_ASSET_MARKERS:
                continue
            resolved[asset_id] = self.resolve(
                asset_id, skill_id=skill_id, version=version
            )
        return resolved

    def unregistered(self) -> tuple[str, ...]:
        """Asset ids the registry does not declare."""

        return tuple(
            sorted(
                asset_id
                for asset_id, ref in self._cache.items()
                if not ref.registered
            )
        )

    def declared_unavailable(self) -> tuple[str, ...]:
        """Asset ids the registry declares but marks unavailable."""

        return tuple(
            sorted(
                asset_id
                for asset_id, ref in self._cache.items()
                if ref.registered and not ref.available
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            asset_id: self._cache[asset_id].as_dict()
            for asset_id in sorted(self._cache)
        }


#: Values that stand in for "no asset", and so are not resolved.
_NON_ASSET_MARKERS = frozenset({"(none)", "", "none", "n/a"})

#: The modules an instance's provenance records, so a loose top-level block cannot
#: have unrelated keys mistaken for provenance records.
_CONTRACT_MODULES = frozenset(
    (
        "identity",
        "source",
        "text_rules",
        "visual_rules",
        "risk_policy",
        "generation",
        "publishing",
    )
)


def collect_asset_ids(
    provenance_block: Mapping[str, Any],
    module_records: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Return every asset id a provenance block names, sorted.

    Reads the mapped ``field_provenance.fields`` and ``field_provenance.modules``
    maps when present, and the per-module contract records otherwise, because a
    module's record can name an asset that no field cites — a declared capability
    whose skill contributed no derived field.
    """

    found: dict[str, None] = {}

    payload = provenance_block.get("field_provenance")
    if isinstance(payload, Mapping):
        fields = payload.get("fields")
        if isinstance(fields, Mapping):
            for record in fields.values():
                if isinstance(record, Mapping):
                    _collect_from_record(record, found)
        modules = payload.get("modules")
        if isinstance(modules, Mapping):
            for record in modules.values():
                if isinstance(record, Mapping):
                    _collect_from_record(record, found)

    # Projected (C0.2) records, either passed separately or still at the top level.
    for source in (
        module_records if module_records is not None else provenance_block,
    ):
        if not isinstance(source, Mapping):
            continue
        for name, record in source.items():
            if name not in _CONTRACT_MODULES:
                continue
            if isinstance(record, Mapping):
                _collect_from_record(record, found)

    return tuple(sorted(found))


def _collect_from_record(record: Mapping[str, Any], found: dict[str, None]) -> None:
    """Add every asset id one provenance record names.

    Two record shapes name assets differently and must not be confused:

    - A mapping **availability record** names its asset as ``asset_id``.
    - A contract **provenance block** names the *skill* as ``source`` and its assets
      in ``assets[]``. Reading ``source`` as an asset id there would turn a skill id
      into a phantom unregistered asset, so it is not read at all.

    The presence of ``assets[]`` is what tells them apart; a bare ``source`` with no
    ``assets[]`` is an asset id.
    """

    for key in ASSET_ID_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip() and value not in _NON_ASSET_MARKERS:
            found.setdefault(value.strip(), None)

    assets = record.get("assets")
    has_assets = isinstance(assets, Sequence) and not isinstance(assets, (str, bytes))
    if has_assets:
        for item in assets:
            if isinstance(item, str) and item.strip() and item not in _NON_ASSET_MARKERS:
                found.setdefault(item.strip(), None)
        return

    # No `assets[]`, so this is not a contract block: a `source` here is an asset id.
    source = record.get("source")
    if isinstance(source, str) and source.strip() and source not in _NON_ASSET_MARKERS:
        found.setdefault(source.strip(), None)


__all__ = [
    "ASSET_ID_KEYS",
    "AssetReferenceResolver",
    "DECLARED_ASSET_STATUSES",
    "collect_asset_ids",
]
