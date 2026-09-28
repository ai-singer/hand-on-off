"""Shared fixtures for the Creator Instance Loader tests.

Deliberately small and explicit. Every fixture is built through the real upstream
layers — :mod:`creator_skill`, :mod:`creator_mapping`, :mod:`creator_projection` —
so a loader test exercises a genuine artifact rather than a hand-rolled dictionary
that happens to have the right keys.
"""

from __future__ import annotations

import atexit
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from creator_mapping import (
    BundleAssetResolver,
    map_bundle_to_instance,
    write_mapped_instance,
)
from creator_projection import AssetRegistry, project_instance, write_instance
from creator_skill import (
    DEFAULT_SKILL_CATALOG,
    CreatorRequest,
    SkillComposer,
    SkillRegistry,
)

#: The workspace under test.
WORKSPACE = Path(__file__).resolve().parents[2]

#: A directory that exists for the life of the process, cleaned up on exit.
_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="c04b_loader_tests_"))
atexit.register(shutil.rmtree, _TEMP_ROOT, True)


def scratch_dir(name: str) -> Path:
    """Return a fresh, empty directory under the test temporary root."""

    target = _TEMP_ROOT / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def skill_registry() -> SkillRegistry:
    return SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)


def finance_request(
    *,
    creator_id: str = "finance_xhs",
    with_visual: bool = True,
) -> CreatorRequest:
    """The finance / xiaohongshu request the whole programme is exercised against."""

    return CreatorRequest(
        domain="finance",
        platform="xiaohongshu",
        style="education",
        creator_id=creator_id,
        declared_capabilities=("visual-style-distillation",) if with_visual else (),
    )


def finance_bundle(*, creator_id: str = "finance_xhs", with_visual: bool = True):
    """Compose the finance request into a skill bundle."""

    request = finance_request(creator_id=creator_id, with_visual=with_visual)
    return SkillComposer(skill_registry()).compose(request).bundle


def mapping_resolver(registry: SkillRegistry | None = None) -> BundleAssetResolver:
    """A bundle asset resolver over the workspace's real asset registry.

    The explicit ``None`` check is deliberate: :class:`SkillRegistry` defines
    ``__len__``, so an *empty* registry is falsy and an ``or`` fallback would
    silently substitute a populated one.
    """

    active = skill_registry() if registry is None else registry
    return BundleAssetResolver(AssetRegistry.load(WORKSPACE), active)


def mapped_instance(*, creator_id: str = "finance_xhs", with_visual: bool = True):
    """Map the finance bundle to an instance, in memory."""

    bundle = finance_bundle(creator_id=creator_id, with_visual=with_visual)
    return map_bundle_to_instance(bundle, resolver=mapping_resolver())


def write_mapped(name: str = "mapped", **kwargs: Any) -> Path:
    """Write a mapped instance to disk and return its directory."""

    root = scratch_dir(name)
    mapped = mapped_instance(**kwargs)
    write_mapped_instance(mapped, root / "creator_instance")
    return root / "creator_instance" / mapped.creator_id


def write_projected(name: str = "projected", *, layout: str = "c01") -> Path:
    """Write a projected instance and return its directory.

    ``layout="c01"`` writes the projection's own in-memory instance in the aggregate
    layout the C0.1 contract describes, which is the contract-valid form.

    ``layout="writer"`` uses :func:`creator_projection.write_instance` unchanged.
    That writer emits a top-level ``field_provenance`` key the contract schema
    forbids, so this layout is the one the loader must *reject*; it exists so the
    divergence is pinned by a test rather than discovered later.
    """

    root = scratch_dir(name)
    result = project_instance(WORKSPACE, creator_id="template_creator")
    target = root / "template_creator"

    if layout == "writer":
        write_instance(result, root)
        return target

    if layout != "c01":
        raise ValueError(f"unknown projected layout {layout!r}")

    target.mkdir(parents=True, exist_ok=True)
    (target / "creator_instance.json").write_text(
        json.dumps(dict(result.instance), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def write_projection_directory(name: str = "projected_dir") -> Path:
    """Write a projection in its native directory layout, aggregate removed.

    The projection's aggregate document violates the contract schema, but its
    per-module files and ``provenance.json`` do not. Removing the aggregate is how a
    caller reads the projection through the ``modules`` layout — explicitly, and
    without the loader silently preferring one document over another.
    """

    root = scratch_dir(name)
    result = project_instance(WORKSPACE, creator_id="template_creator")
    write_instance(result, root)
    target = root / "template_creator"
    (target / "instance.json").unlink()
    return target


def as_document(instance: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep, mutable copy of a document."""

    return json.loads(json.dumps(instance))
