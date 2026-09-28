"""Asset registry: the single declared source of every projection input.

The registry exists so the projection layer contains **no hard-coded asset
paths**. Every path the mappers read comes from ``assets.yaml``, and every asset
declares whether it is actually available. An asset that documentation references
but no implementation provides is registered as ``unavailable`` with a
machine-readable reason, so the projection can mark the gap rather than invent
the capability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .errors import ProjectionAssetError, ProjectionAssetUnavailableError, ProjectionParseError
from .yaml_subset import parse_yaml_subset

#: Registry filename, next to this module.
REGISTRY_FILENAME = "assets.yaml"

#: Asset types the registry recognises.
ASSET_TYPES: tuple[str, ...] = (
    "identity_source",
    "visual_rules",
    "text_rules",
    "risk_reference",
    "source_rules",
    "generation_capability",
    "publishing_capability",
    "evaluation_policy",
    "markdown_template",
)

#: Statuses an asset may declare.
ASSET_STATUSES: tuple[str, ...] = ("available", "unavailable")


@dataclass(frozen=True, slots=True)
class Asset:
    """One declared projection input."""

    asset_id: str
    asset_type: str
    location: str
    asset_format: str
    status: str
    reason: str | None
    description: str

    @property
    def available(self) -> bool:
        return self.status == "available"

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.asset_id,
            "type": self.asset_type,
            "location": self.location,
            "format": self.asset_format,
            "status": self.status,
        }
        if self.reason:
            record["reason"] = self.reason
        return record


class AssetRegistry:
    """A validated view over ``assets.yaml``."""

    def __init__(
        self, workspace_root: str | Path, assets: Mapping[str, Asset], version: str
    ) -> None:
        self._workspace_root = Path(workspace_root)
        self._assets = dict(assets)
        self._version = version

    # -- construction -----------------------------------------------------

    @classmethod
    def load(
        cls,
        workspace_root: str | Path,
        registry_path: str | Path | None = None,
    ) -> "AssetRegistry":
        """Read and validate the registry."""

        root = Path(workspace_root)
        path = (
            Path(registry_path)
            if registry_path is not None
            else Path(__file__).resolve().parent / REGISTRY_FILENAME
        )
        try:
            payload = parse_yaml_subset(
                path.read_text(encoding="utf-8"), origin=str(path)
            )
        except FileNotFoundError as exc:
            raise ProjectionAssetError(f"asset registry not found: {path}") from exc
        except OSError as exc:
            raise ProjectionAssetError(f"cannot read asset registry {path}: {exc}") from exc
        except ProjectionParseError as exc:
            raise ProjectionAssetError(f"asset registry is malformed: {exc}") from exc

        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list) or not raw_assets:
            raise ProjectionAssetError(f"{path} declares no assets")

        assets: dict[str, Asset] = {}
        for index, entry in enumerate(raw_assets):
            asset = _build_asset(entry, index, path)
            if asset.asset_id in assets:
                raise ProjectionAssetError(
                    f"{path} declares duplicate asset id {asset.asset_id!r}"
                )
            assets[asset.asset_id] = asset

        version = str(payload.get("version", ""))
        return cls(root, assets, version)

    # -- access -----------------------------------------------------------

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def version(self) -> str:
        return self._version

    def __len__(self) -> int:
        return len(self._assets)

    def __iter__(self) -> Iterator[Asset]:
        return iter(self._assets.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))

    def get(self, asset_id: str) -> Asset:
        try:
            return self._assets[asset_id]
        except KeyError as exc:
            raise ProjectionAssetError(
                f"asset {asset_id!r} is not registered; "
                f"registered ids: {', '.join(self.ids())}"
            ) from exc

    def by_type(self, asset_type: str) -> tuple[Asset, ...]:
        return tuple(
            asset for asset in self._assets.values() if asset.asset_type == asset_type
        )

    def first_available(self, *asset_ids: str) -> Asset | None:
        """Return the first of ``asset_ids`` that is registered and available."""

        for asset_id in asset_ids:
            if self.get(asset_id).available:
                return self.get(asset_id)
        return None

    # -- resolution -------------------------------------------------------

    def path_of(self, asset_id: str) -> Path:
        """Return the absolute path of an asset."""

        return self._workspace_root / self.get(asset_id).location

    def require(self, asset_id: str) -> Asset:
        """Return an asset, raising if it is unavailable."""

        asset = self.get(asset_id)
        if not asset.available:
            raise ProjectionAssetUnavailableError(
                f"asset {asset_id!r} is unavailable "
                f"({asset.reason or 'no reason given'}); "
                f"expected at {asset.location}"
            )
        return asset

    def read_json(self, asset_id: str) -> Mapping[str, Any]:
        """Read an available JSON asset, failing with a typed error."""

        asset = self.require(asset_id)
        path = self._workspace_root / asset.location
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProjectionAssetUnavailableError(
                f"asset {asset_id!r} is registered as available but "
                f"{asset.location} does not exist"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectionAssetError(
                f"cannot read asset {asset_id!r} at {asset.location}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ProjectionAssetError(
                f"asset {asset_id!r} must be a JSON object: {asset.location}"
            )
        return payload

    def read_text(self, asset_id: str) -> str:
        """Read an available text asset."""

        asset = self.require(asset_id)
        path = self._workspace_root / asset.location
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ProjectionAssetUnavailableError(
                f"asset {asset_id!r} is registered as available but "
                f"{asset.location} does not exist"
            ) from exc
        except OSError as exc:
            raise ProjectionAssetError(
                f"cannot read asset {asset_id!r} at {asset.location}: {exc}"
            ) from exc

    def read_yaml(self, asset_id: str) -> Mapping[str, Any]:
        """Read an available YAML-subset asset."""

        asset = self.require(asset_id)
        payload = parse_yaml_subset(
            self.read_text(asset_id),
            origin=str(self._workspace_root / asset.location),
        )
        return payload

    def availability(self) -> dict[str, str]:
        """Map asset id -> status, for reporting."""

        return {asset.asset_id: asset.status for asset in self._assets.values()}

    def unavailable(self) -> tuple[Asset, ...]:
        return tuple(asset for asset in self._assets.values() if not asset.available)


def _looks_absolute(location: str) -> bool:
    """Detect an absolute path without relying on the host platform.

    ``Path("/etc/passwd").is_absolute()`` is ``False`` on Windows because there is
    no drive letter, so the platform check alone would let a POSIX absolute path
    through on a Windows checkout. This guard is deliberately strict.
    """

    if Path(location).is_absolute():
        return True
    if location.startswith(("/", "\\")):
        return True
    # Windows drive letter, e.g. C:\dir or C:/dir
    return len(location) >= 2 and location[1] == ":" and location[0].isalpha()


def _build_asset(entry: Any, index: int, origin: Path) -> Asset:
    if not isinstance(entry, Mapping):
        raise ProjectionAssetError(f"{origin}: asset #{index} must be a mapping")

    asset_id = entry.get("id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ProjectionAssetError(f"{origin}: asset #{index} has no usable id")

    asset_type = entry.get("type")
    if asset_type not in ASSET_TYPES:
        raise ProjectionAssetError(
            f"{origin}: asset {asset_id!r} has unknown type {asset_type!r}; "
            f"expected one of: {', '.join(ASSET_TYPES)}"
        )

    location = entry.get("location")
    if not isinstance(location, str) or not location.strip():
        raise ProjectionAssetError(f"{origin}: asset {asset_id!r} has no location")
    if _looks_absolute(location):
        raise ProjectionAssetError(
            f"{origin}: asset {asset_id!r} location must be workspace-relative, "
            f"got {location!r}"
        )

    asset_format = str(entry.get("format", ""))
    if not asset_format:
        raise ProjectionAssetError(f"{origin}: asset {asset_id!r} has no format")

    status = entry.get("status")
    if status not in ASSET_STATUSES:
        raise ProjectionAssetError(
            f"{origin}: asset {asset_id!r} has unknown status {status!r}; "
            f"expected one of: {', '.join(ASSET_STATUSES)}"
        )

    reason = entry.get("reason")
    if status == "unavailable" and not (isinstance(reason, str) and reason.strip()):
        raise ProjectionAssetError(
            f"{origin}: unavailable asset {asset_id!r} must declare a reason"
        )

    return Asset(
        asset_id=asset_id,
        asset_type=str(asset_type),
        location=str(location),
        asset_format=asset_format,
        status=str(status),
        reason=str(reason) if reason else None,
        description=str(entry.get("description", "")).strip(),
    )


__all__ = [
    "ASSET_STATUSES",
    "ASSET_TYPES",
    "Asset",
    "AssetRegistry",
    "REGISTRY_FILENAME",
]
