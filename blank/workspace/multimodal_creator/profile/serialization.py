"""Profile serialisation and Creator Factory emission (Phase M5, Tasks 3 and 4).

Two outputs, for two audiences.

**Profile JSON** — the complete, traceable document, for storage and later
re-derivation. Round-trips exactly.

**``visual_profile.yaml``** — the flattened config a Creator Instance Factory
consumes. It carries the rules *and* the provenance for each rule group, so the
factory can record where an instance's visual configuration came from instead of
adopting an unattributed rule set.

The YAML writer is dependency-free (``pyproject.toml`` declares
``dependencies = []``), emitting a deliberately small subset: nested mappings,
block sequences, and plain scalars. It is a config emitter, not a general YAML
library, and it says so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .model import (
    PROFILE_VERSION,
    PROVENANCE_FAMILIES,
    ProfileError,
    VisualCreatorProfile,
)
from .validation import validate_profile

#: Name of the flattened config file the factory reads.
YAML_FILENAME = "visual_profile.yaml"

#: Keys that must never be emitted, checked again at emission time so a future
#: change to the model cannot smuggle one into the factory config.
_FORBIDDEN_EMISSION_KEYS = frozenset(
    {
        "prompt",
        "model",
        "renderer",
        "generate",
        "image",
        "pixels",
        "base64",
        "deploy",
        "publish",
        "endpoint",
        "credentials",
    }
)


class SerializationError(ProfileError):
    """Raised when a profile cannot be serialised or written."""


def to_json(profile: VisualCreatorProfile, *, indent: int = 2) -> str:
    """Serialise a profile to JSON, validating it first."""

    validate_profile(profile)
    return json.dumps(profile.as_dict(), indent=indent, sort_keys=False) + "\n"


def from_json(payload: str) -> VisualCreatorProfile:
    """Rebuild a profile from JSON, validating provenance on the way in."""

    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SerializationError(f"profile JSON is not valid: {exc}") from exc
    return from_dict(document)


def from_dict(document: Mapping[str, Any]) -> VisualCreatorProfile:
    """Rebuild a profile from a mapping.

    Validates the document first, so a malformed or forbidden document is
    reported by name rather than surfacing as a confusing constructor error deep
    inside the model.
    """

    from .model import (
        AttentionStrategy,
        CompositionRules,
        ConstraintLayer,
        FieldProvenance,
        HierarchyPattern,
        VisualIdentity,
    )
    from .validation import validate_document

    validate_document(document)

    identity = VisualIdentity(**dict(document["visual_identity"]))
    rules = CompositionRules(**dict(document["composition_rules"]))
    attention = AttentionStrategy(order=dict(document["attention_strategy"]))
    hierarchy = HierarchyPattern(tiers=dict(document["hierarchy_pattern"]))
    constraints = ConstraintLayer(**dict(document["constraints"]))

    provenance: dict[str, FieldProvenance] = {}
    for family, record in document["provenance"].items():
        source = dict(record["source"])
        provenance[family] = FieldProvenance(
            source_phase=str(source["phase"]),
            artifact_id=str(source["artifact"]),
            artifact_kind=str(source["artifact_kind"]),
            derivation=str(record["derivation"]),
            confidence=float(record["confidence"]),
            evidence=dict(record.get("evidence", {})),
        )

    profile = VisualCreatorProfile(
        profile_id=str(document["profile_id"]),
        creator_id=str(document["creator_id"]),
        version=str(document["profile_version"]),
        visual_identity=identity,
        composition_rules=rules,
        attention_strategy=attention,
        hierarchy_pattern=hierarchy,
        constraints=constraints,
        provenance=provenance,
        source_pattern_ids=tuple(str(v) for v in document["source_pattern_ids"]),
        support=int(document["support"]),
        confidence=float(document["confidence"]),
        notes=tuple(str(note) for note in document.get("notes", ())),
    )
    validate_profile(profile)
    return profile


def write_json(profile: VisualCreatorProfile, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_json(profile), encoding="utf-8")
    return target


def read_json(path: str | Path) -> VisualCreatorProfile:
    return from_json(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Creator Factory emission
# --------------------------------------------------------------------------


def factory_config(profile: VisualCreatorProfile) -> dict[str, Any]:
    """Flatten a profile into the config a Creator Instance Factory reads.

    Every rule group is emitted **with its provenance**, so a generated instance
    can record which M4 artifact produced its visual configuration. The factory
    is expected to use this to write its own ``visual_rules.yaml`` for a new
    instance; M5 does not write into any instance directory itself.
    """

    validate_profile(profile)

    def sourced(values: Sequence[str], family: str) -> list[dict[str, Any]]:
        record = profile.provenance[family]
        return [
            {
                "rule": value,
                "source_phase": record.source_phase,
                "source_artifact": record.artifact_id,
                "confidence": record.confidence,
            }
            for value in values
        ]

    config = {
        "visual_profile": {
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "creator_id": profile.creator_id,
            "support": profile.support,
            "confidence": profile.confidence,
            "confidence_floor": profile.weakest_confidence(),
        },
        "identity": dict(profile.visual_identity.as_dict()),
        "composition": {
            "preferred_layout": list(profile.composition_rules.preferred),
            "forbidden_layout": list(profile.composition_rules.forbidden),
        },
        "attention": dict(profile.attention_strategy.order),
        "hierarchy": dict(profile.hierarchy_pattern.tiers),
        "constraints": {
            "must_have": list(profile.constraints.must_have),
            "avoid": list(profile.constraints.avoid),
        },
        "provenance": {
            family: profile.provenance[family].as_dict()
            for family in PROVENANCE_FAMILIES
        },
        "source_pattern_ids": list(profile.source_pattern_ids),
        "generated_by": f"multimodal_creator.profile {PROFILE_VERSION}",
    }

    _assert_emittable(config)
    return config


def _assert_emittable(config: Mapping[str, Any]) -> None:
    """Final guard before writing: no forbidden key may reach the factory."""

    def keys(document: Any) -> list[str]:
        found: list[str] = []
        if isinstance(document, Mapping):
            for key, value in document.items():
                found.append(str(key).lower())
                found.extend(keys(value))
        elif isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
            for item in document:
                found.extend(keys(item))
        return found

    offenders = sorted(set(keys(config)) & _FORBIDDEN_EMISSION_KEYS)
    if offenders:
        raise SerializationError(
            "refusing to emit a factory config containing: " + ", ".join(offenders)
        )


# --------------------------------------------------------------------------
# Minimal YAML emitter
# --------------------------------------------------------------------------


def _scalar(value: Any) -> str:
    """Render a scalar for the config subset.

    Strings are quoted so a rule name that happens to look like a number or a
    boolean cannot change type on the way into the factory.
    """

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _emit(document: Any, indent: int = 0, *, in_sequence: bool = False) -> list[str]:
    pad = " " * indent
    lines: list[str] = []

    if isinstance(document, Mapping):
        if not document:
            return [f"{pad}{{}}"]
        for key, value in document.items():
            if isinstance(value, Mapping) and value:
                lines.append(f"{pad}{key}:")
                lines.extend(_emit(value, indent + 2))
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                if not value:
                    lines.append(f"{pad}{key}: []")
                elif all(not isinstance(v, (Mapping, list, tuple)) for v in value):
                    lines.append(f"{pad}{key}:")
                    for item in value:
                        lines.append(f"{pad}  - {_scalar(item)}")
                else:
                    lines.append(f"{pad}{key}:")
                    for item in value:
                        rendered = _emit(item, indent + 2, in_sequence=True)
                        if rendered:
                            first = rendered[0].lstrip()
                            lines.append(f"{pad}  - {first}")
                            lines.extend(rendered[1:])
            else:
                lines.append(f"{pad}{key}: {_scalar(value)}")
        return lines

    if isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
        if not document:
            return []
        for item in document:
            lines.append(f"{pad}- {_scalar(item)}")
        return lines

    prefix = "" if in_sequence else pad
    return [f"{prefix}{_scalar(document)}"]


def to_yaml(profile: VisualCreatorProfile) -> str:
    """Serialise the factory config as YAML."""

    config = factory_config(profile)
    body = "\n".join(_emit(config))
    header = (
        "# visual_profile.yaml — generated by multimodal_creator.profile M5\n"
        "#\n"
        "# A distilled configuration asset. Every rule group below carries the M4\n"
        "# artifact it came from. This file contains no generation logic: no prompt,\n"
        "# no model reference, and no image data.\n"
        f"# profile: {profile.profile_id}  creator: {profile.creator_id}\n"
    )
    return header + body + "\n"


def write_yaml(profile: VisualCreatorProfile, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_yaml(profile), encoding="utf-8")
    return target


def parse_emitted_yaml(payload: str) -> dict[str, Any]:
    """Parse back the subset :func:`to_yaml` emits.

    Deliberately narrow: two-space indentation, ``key: value``, ``- item``
    sequences, and quoted scalars. It exists so the round trip can be *tested*
    rather than assumed, which is the only reason a hand-written parser is
    defensible here.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    pending_key: tuple[int, dict[str, Any], str] | None = None

    for raw in payload.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1] if stack else root

        if line.startswith("- "):
            if pending_key is None:
                raise SerializationError("sequence item without a parent key")
            _key_indent, parent, key = pending_key
            if not isinstance(parent.get(key), list):
                parent[key] = []
            item = line[2:].strip()
            if item.endswith(":") or (":" in item and not item.startswith('"')):
                nested: dict[str, Any] = {}
                parent[key].append(nested)
                stack.append((indent, nested))
                key_part, _, value_part = item.partition(":")
                value_part = value_part.strip()
                if value_part:
                    nested[key_part.strip()] = _unscalar(value_part)
                else:
                    pending_key = (indent, nested, key_part.strip())
            else:
                parent[key].append(_unscalar(item))
            continue

        if ":" not in line:
            raise SerializationError(f"cannot parse line: {raw!r}")

        key_part, _, value_part = line.partition(":")
        key = key_part.strip()
        value_part = value_part.strip()

        if value_part == "":
            new_map: dict[str, Any] = {}
            container[key] = new_map
            stack.append((indent, new_map))
            pending_key = (indent, container, key)
        elif value_part == "[]":
            container[key] = []
        else:
            container[key] = _unscalar(value_part)
            pending_key = None

    return root


def _unscalar(text: str) -> Any:
    if text == "null":
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


@dataclass(frozen=True, slots=True)
class WrittenProfile:
    """Paths written for one profile, returned so callers need not reconstruct them."""

    profile_id: str
    json_path: Path
    yaml_path: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "json_path": str(self.json_path),
            "yaml_path": str(self.yaml_path),
        }


def write_profile_bundle(
    profile: VisualCreatorProfile,
    directory: str | Path,
    *,
    json_name: str | None = None,
    yaml_name: str = YAML_FILENAME,
) -> WrittenProfile:
    """Write both representations into one directory."""

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    json_path = write_json(profile, root / (json_name or f"{profile.profile_id}.json"))
    yaml_path = write_yaml(profile, root / yaml_name)
    return WrittenProfile(
        profile_id=profile.profile_id, json_path=json_path, yaml_path=yaml_path
    )


__all__ = [
    "YAML_FILENAME",
    "SerializationError",
    "WrittenProfile",
    "factory_config",
    "from_dict",
    "from_json",
    "parse_emitted_yaml",
    "read_json",
    "to_json",
    "to_yaml",
    "write_json",
    "write_profile_bundle",
    "write_yaml",
]
