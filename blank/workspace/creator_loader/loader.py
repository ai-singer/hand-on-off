"""The Creator Instance Loader: read a ``creator_instance`` artifact, standardised.

```
    creator_instance artifact  →  Instance Loader  →  Loaded Creator Configuration
```

This is a **configuration-reading layer**, and nothing more. It does not execute an
agent, does not run a workflow, does not deploy anything, does not call a model, and
does not generate content. It opens documents, checks them, and freezes what it
found.

### What the loader will not do

- **Modify the artifact.** Every document is opened read-only and never written.
- **Fill a missing field.** A gap is reported as ``INSTANCE_FIELD_MISSING``; a
  repaired instance would be a fabricated instance.
- **Enable a capability.** Capability state is read from the artifact and reported.
  The loader has no code path that turns ``unavailable`` into ``available``.
- **Execute an asset.** An asset reference is resolved to a *record* — id, type,
  status, location. Its content is not read, and nothing is rendered from it.
- **Invent provenance.** Where the artifact does not record a step, the step is
  reported as unrecorded.

### Two on-disk layouts

``<dir>/instance.json`` (the C0.4-A aggregate) or ``<dir>/creator_instance.json``
(the C0.1 aggregate) is preferred when present, because it carries the whole
instance in one document. Otherwise the loader assembles the artifact from
``<dir>/<module>.json`` files plus ``<dir>/provenance.json``; the two provenance
shapes that exist in this repository are both understood, and
:func:`load_creator_instance` reports which one it found.

A bare ``<path>/instance.json`` file is also accepted directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_contract import CONTRACT_VERSION, MODULE_NAMES
from creator_mapping import CAPABILITY_MODULES, MAPPED_MODULES

from .errors import (
    INSTANCE_NOT_A_DIRECTORY,
    InstanceDiffError,
    InstanceNotFoundError,
    InstanceUnreadableError,
)
from .model import (
    AssetReference,
    CapabilityState,
    LoadedCapability,
    LoadedCreatorInstance,
    ProvenanceKind,
    freeze,
)
from .provenance import normalize_provenance, parse_provenance, provenance_kind
from .resolver import AssetReferenceResolver
from .validation import (
    capability_state,
    validate_instance,
    validate_loaded,
)

#: Aggregate filenames the loader accepts, in preference order.
AGGREGATE_FILES: tuple[str, ...] = ("instance.json", "creator_instance.json")

#: The provenance filename in the directory layout.
PROVENANCE_FILE = "provenance.json"

#: The seven configuration modules, in contract order.
MODULES: tuple[str, ...] = MAPPED_MODULES

#: Keys whose values are human prose and so are not compared by value in a diff.
_PROSE_KEYS = frozenset({"reason", "note", "description"})


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def read_json(path: Path, *, what: str) -> Any:
    """Read one JSON document, converting every failure into a typed error."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InstanceNotFoundError(f"{what} not found: {path}") from exc
    except IsADirectoryError as exc:
        raise InstanceUnreadableError(f"{what} is a directory: {path}") from exc
    except OSError as exc:
        raise InstanceUnreadableError(f"cannot read {what} {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InstanceUnreadableError(
            f"{what} is not valid JSON: {path}", detail=str(exc)
        ) from exc


def resolve_artifact_path(path: str | Path) -> Path:
    """Normalise a caller-supplied path, rejecting one that does not exist."""

    if isinstance(path, str) and not path.strip():
        raise InstanceNotFoundError("no instance path was supplied")
    target = Path(path)
    if not target.exists():
        raise InstanceNotFoundError(f"instance path does not exist: {target}")
    if target.is_file() and target.suffix.lower() != ".json":
        raise InstanceNotFoundError(
            f"instance path is not a directory or a JSON document: {target}",
            detail="a JSON aggregate document, or a directory of module documents",
            code=INSTANCE_NOT_A_DIRECTORY,
        )
    return target


def read_artifact(
    path: str | Path,
    *,
    layout: str = "prefer-aggregate",
) -> dict[str, Any]:
    """Read an instance artifact into aggregate form, without judging it.

    Returns a plain dictionary carrying at least the seven modules, a
    ``provenance`` block and a ``contract_version``. Raises only on a document that
    cannot be read; shape problems are for :mod:`creator_loader.validation` to
    report, so a caller sees ``INSTANCE_FIELD_MISSING`` rather than
    ``INSTANCE_UNREADABLE`` for a merely incomplete instance.

    Args:
        path: an instance directory, or a single aggregate JSON document.
        layout: ``"prefer-aggregate"`` (the default) reads an aggregate document
            when the directory has one. ``"modules"`` reads the per-module files and
            ``provenance.json`` regardless, which is how a directory whose aggregate
            document has drifted from its module files can still be inspected —
            explicitly, and never as a silent fallback.
    """

    if layout not in ("prefer-aggregate", "modules"):
        raise InstanceUnreadableError(
            f"unknown instance layout {layout!r}",
            detail="expected 'prefer-aggregate' or 'modules'",
        )

    target = resolve_artifact_path(path)

    if target.is_file():
        document = read_json(target, what="instance document")
        return _as_aggregate(document, origin=target)

    if layout == "prefer-aggregate":
        for name in AGGREGATE_FILES:
            candidate = target / name
            if candidate.is_file():
                document = read_json(candidate, what="instance aggregate")
                return _as_aggregate(document, origin=candidate)

    return _assemble_from_modules(target)


def _as_aggregate(document: Any, *, origin: Path) -> dict[str, Any]:
    """Validate that a document is an object and return a mutable copy of it."""

    if not isinstance(document, Mapping):
        raise InstanceUnreadableError(
            f"instance document must be a JSON object: {origin}",
            detail=f"found {type(document).__name__}",
        )
    return {str(key): value for key, value in document.items()}


def _assemble_from_modules(directory: Path) -> dict[str, Any]:
    """Build the aggregate from per-module files plus ``provenance.json``."""

    found: dict[str, Any] = {}
    for module in MODULE_NAMES:
        candidate = directory / f"{module}.json"
        if candidate.is_file():
            found[module] = read_json(candidate, what=f"{module} module")

    provenance_path = directory / PROVENANCE_FILE
    if provenance_path.is_file():
        # The directory `provenance.json` is not the aggregate shape: it nests the
        # contract module blocks under `modules`. Normalise on read so everything
        # downstream sees one shape.
        found["provenance"] = normalize_provenance(
            read_json(provenance_path, what="provenance module")
        )

    if not found:
        raise InstanceNotFoundError(
            f"no instance documents found in {directory}",
            detail=(
                "expected one of "
                + ", ".join(AGGREGATE_FILES)
                + ", or per-module files"
            ),
        )

    # A missing module is deliberately *not* reported here: assembling is reading,
    # and the check that reports INSTANCE_MODULE_MISSING runs on the assembled
    # document so one code covers both layouts.
    found.setdefault("contract_version", CONTRACT_VERSION)
    return found


# --------------------------------------------------------------------------
# Capability derivation
# --------------------------------------------------------------------------


def capability_records(instance: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the per-module provenance records a capability state is read from."""

    provenance = instance.get("provenance")
    if not isinstance(provenance, Mapping):
        return {}
    block = normalize_provenance(provenance)
    payload = block.get("field_provenance")
    if isinstance(payload, Mapping) and isinstance(payload.get("modules"), Mapping):
        return payload["modules"]
    return {module: block.get(module, {}) for module in MODULES}


def derive_capabilities(
    instance: Mapping[str, Any],
    provenance: Any,
) -> dict[str, LoadedCapability]:
    """Build one :class:`LoadedCapability` per module, from the artifact alone."""

    records = capability_records(instance)
    traces = getattr(provenance, "field_traces", {})
    module_skills: dict[str, set[str]] = {}
    for trace in traces.values():
        module_skills.setdefault(trace.module, set()).add(trace.skill_id)

    capabilities: dict[str, LoadedCapability] = {}
    for module in MODULES:
        record = records.get(module)
        record = record if isinstance(record, Mapping) else {}
        body = instance.get(module)
        body = body if isinstance(body, Mapping) else {}

        enabled: bool | None
        if module in CAPABILITY_MODULES:
            declared = body.get("enabled")
            enabled = declared if isinstance(declared, bool) else None
            reason = str(body.get("reason", "")).strip()
        else:
            # A non-capability module has no enabled flag; it is not "enabled",
            # and claiming it were would be the same dishonesty in reverse.
            enabled = None
            reason = str(record.get("reason", record.get("asset_reason", ""))).strip()

        capabilities[module] = LoadedCapability(
            module=module,
            state=CapabilityState(capability_state(record, enabled=enabled)),
            enabled=enabled,
            reason=reason,
            skill_type=str(record.get("skill_type", "")).strip(),
            skill_ids=tuple(sorted(module_skills.get(module, set()))),
            asset_id=str(record.get("asset_id", record.get("source", ""))).strip(),
            asset_status=str(record.get("asset_status", "")).strip(),
        )
    return capabilities


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_creator_instance(
    path: str | Path,
    *,
    resolver: AssetReferenceResolver | None = None,
    workspace_root: str | Path | None = None,
    strict: bool = True,
    layout: str = "prefer-aggregate",
) -> LoadedCreatorInstance:
    """Load a ``creator_instance`` artifact as an immutable configuration object.

    Args:
        path: an instance directory, or a single aggregate JSON document.
        resolver: how asset references are resolved. When omitted, the loader builds
            one over ``workspace_root``. Passing ``None`` explicitly still builds
            one; there is no way to load an instance with asset resolution silently
            disabled.
        workspace_root: the workspace whose asset registry and contract schema are
            used. Defaults to this repository's own workspace.
        strict: when true (the default), every pre-load check must pass. When false,
            only readability and presence are enforced — a caller that wants to
            inspect a broken artifact can, but the failure is still recorded in
            ``loaded.validation``.
        layout: which on-disk layout to read. See :func:`read_artifact`.

    Raises:
        LoaderError: with a stable code, on any failed check. The artifact is never
            modified and never repaired.
    """

    if resolver is None and workspace_root is None:
        workspace_root = _workspace_root()

    raw = read_artifact(path, layout=layout)

    if not isinstance(raw.get("provenance"), Mapping):
        from .errors import InstanceProvenanceMissingError

        raise InstanceProvenanceMissingError(
            "the artifact carries no provenance block",
            detail="an instance with no provenance cannot be loaded or traced",
        )

    if resolver is None:
        resolver = AssetReferenceResolver.for_workspace(workspace_root)

    if strict:
        checks = validate_instance(raw, workspace_root=workspace_root)
    else:
        checks = {"strict": "SKIPPED"}

    loaded = build_loaded_instance(
        raw, source_path=Path(path), resolver=resolver, validation=checks
    )

    if strict:
        validate_loaded(loaded)

    return loaded


def build_loaded_instance(
    instance: Mapping[str, Any],
    *,
    source_path: Path,
    resolver: AssetReferenceResolver | None = None,
    validation: Mapping[str, str] | None = None,
) -> LoadedCreatorInstance:
    """Build the immutable loaded object from an aggregate document.

    Split out from :func:`load_creator_instance` so the model can be exercised
    directly, but it performs no check of its own: a caller reaching this function
    is responsible for having validated first.
    """

    provenance = parse_provenance(
        instance.get("provenance", {}), resolver=resolver
    )
    capabilities = derive_capabilities(instance, provenance)

    modules = {
        module: freeze(instance[module])
        for module in MODULES
        if module in instance
    }

    identity = instance.get("identity")
    creator_id = ""
    if isinstance(identity, Mapping):
        creator_id = str(identity.get("creator_id", "")).strip()
    if not creator_id:
        creator_id = source_path.parent.name if source_path.is_file() else source_path.name

    return LoadedCreatorInstance(
        instance_id=creator_id,
        source_path=source_path,
        contract_version=str(instance.get("contract_version", "")),
        modules=freeze(modules),
        raw_provenance=freeze(instance.get("provenance", {})),
        provenance=provenance,
        capabilities=freeze(capabilities),
        asset_references=freeze(provenance.asset_references),
        validation=freeze(dict(validation or {})),
    )


def _workspace_root() -> Path:
    """Return this repository's workspace root, without importing a layer that runs."""

    # blank/workspace/creator_loader/loader.py -> blank/workspace
    return Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstanceDiff:
    """What changed between two loaded instances.

    Four named axes, because a caller usually cares about exactly one of them: did
    the *identity* move, did the *skills* move, did the *assets* move, or did a
    *capability* move. A field that changed within an unchanged module is reported
    under ``fields``.
    """

    instance_a: str
    instance_b: str
    same: bool
    identity_changed: tuple[str, ...] = ()
    skills_changed: tuple[str, ...] = ()
    assets_changed: tuple[str, ...] = ()
    capabilities_changed: tuple[str, ...] = ()
    fields_changed: tuple[str, ...] = ()
    modules_changed: tuple[str, ...] = ()
    kind_changed: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return not self.same

    @property
    def axes(self) -> tuple[str, ...]:
        """The axes that actually moved, for a one-line summary."""

        moved = []
        if self.identity_changed:
            moved.append("identity")
        if self.skills_changed:
            moved.append("skills")
        if self.assets_changed:
            moved.append("assets")
        if self.capabilities_changed:
            moved.append("capabilities")
        if self.fields_changed:
            moved.append("fields")
        if self.modules_changed:
            moved.append("modules")
        if self.kind_changed:
            moved.append("provenance_kind")
        return tuple(moved)

    def summary(self) -> str:
        """A deterministic, one-line description."""

        if self.same:
            return "identical"
        return "changed: " + ", ".join(self.axes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "instance_a": self.instance_a,
            "instance_b": self.instance_b,
            "same": self.same,
            "changed": self.changed,
            "summary": self.summary(),
            "axes": list(self.axes),
            "identity_changed": list(self.identity_changed),
            "skills_changed": list(self.skills_changed),
            "assets_changed": list(self.assets_changed),
            "capabilities_changed": list(self.capabilities_changed),
            "fields_changed": list(self.fields_changed),
            "modules_changed": list(self.modules_changed),
            "kind_changed": list(self.kind_changed),
        }

    def __getitem__(self, key: str) -> Any:
        """Allow ``diff["skills_changed"]`` as well as ``diff.skills_changed``."""

        try:
            return self.as_dict()[key]
        except KeyError as exc:
            raise InstanceDiffError(f"instance diff has no field {key!r}") from exc

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)


def compare_loaded_instances(
    a: LoadedCreatorInstance,
    b: LoadedCreatorInstance,
) -> InstanceDiff:
    """Compare two loaded instances on four axes, plus fields, modules and shape.

    Comparison reads only the loaded objects. Nothing is re-read from disk, so a
    comparison cannot be affected by the artifact changing underneath it.
    """

    for candidate in (a, b):
        if not isinstance(candidate, LoadedCreatorInstance):
            raise InstanceDiffError(
                "compare_loaded_instances requires two loaded instances"
            )

    identity_changed = tuple(
        sorted(
            field_name
            for field_name in _union_fields(
                a.module("identity") if "identity" in a.modules else {},
                b.module("identity") if "identity" in b.modules else {},
            )
            if _identity_field(a, field_name) != _identity_field(b, field_name)
        )
    )

    skills_changed = _tuple_symmetric_difference(a.provenance.skills(), b.provenance.skills())
    assets_changed = _tuple_symmetric_difference(a.provenance.assets(), b.provenance.assets())

    capability_differences: list[str] = []
    for module in sorted(set(a.capabilities) | set(b.capabilities)):
        left = a.capabilities.get(module)
        right = b.capabilities.get(module)
        if left is None or right is None:
            capability_differences.append(module)
            continue
        if (
            left.state != right.state
            or left.enabled != right.enabled
            or left.asset_id != right.asset_id
        ):
            capability_differences.append(module)

    fields_changed = tuple(
        sorted(
            f"{module}.{field_name}"
            for module in MODULES
            for field_name in _union_fields(
                a.modules.get(module, {}), b.modules.get(module, {})
            )
            if _field_value(a, module, field_name) != _field_value(b, module, field_name)
        )
    )

    modules_changed = tuple(
        sorted(
            module
            for module in MODULES
            if (module in a.modules) != (module in b.modules)
        )
    )

    kind_changed: tuple[str, ...] = ()
    if a.provenance_kind != b.provenance_kind:
        kind_changed = (f"{a.provenance_kind}->{b.provenance_kind}",)

    # The bundle id is not an axis of its own: a bundle change is a skill change, and
    # a caller reading `skills_changed` is already asking that question.
    if a.provenance.bundle_id != b.provenance.bundle_id:
        skills_changed = tuple(
            sorted(set(skills_changed) | {f"bundle:{a.provenance.bundle_id}->{b.provenance.bundle_id}"})
        )

    same = not any(
        (
            identity_changed,
            skills_changed,
            assets_changed,
            capability_differences,
            fields_changed,
            modules_changed,
            kind_changed,
        )
    )

    return InstanceDiff(
        instance_a=a.instance_id,
        instance_b=b.instance_id,
        same=same,
        identity_changed=identity_changed,
        skills_changed=skills_changed,
        assets_changed=assets_changed,
        capabilities_changed=tuple(capability_differences),
        fields_changed=fields_changed,
        modules_changed=modules_changed,
        kind_changed=kind_changed,
    )


def _union_fields(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> tuple[str, ...]:
    return tuple(sorted(set(left) | set(right)))


def _field_value(loaded: LoadedCreatorInstance, module: str, field_name: str) -> Any:
    document = loaded.modules.get(module)
    if not isinstance(document, Mapping):
        return _MISSING
    return document.get(field_name, _MISSING)


def _identity_field(loaded: LoadedCreatorInstance, field_name: str) -> Any:
    if field_name in _PROSE_KEYS:
        # Prose legitimately varies between artifacts that mean the same thing.
        return _PROSE
    return _field_value(loaded, "identity", field_name)


def _tuple_symmetric_difference(
    left: Sequence[str], right: Sequence[str]
) -> tuple[str, ...]:
    return tuple(sorted(set(left) ^ set(right)))


class _Missing:
    """Sentinel distinguishing "absent" from a legitimate ``None``."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<absent>"

    def __bool__(self) -> bool:
        return False


_MISSING = _Missing()
_PROSE = _Missing()


__all__ = [
    "AGGREGATE_FILES",
    "InstanceDiff",
    "MODULES",
    "PROVENANCE_FILE",
    "build_loaded_instance",
    "capability_records",
    "compare_loaded_instances",
    "derive_capabilities",
    "load_creator_instance",
    "read_artifact",
    "read_json",
    "resolve_artifact_path",
]
