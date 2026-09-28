"""On-disk layout and serialisation for a Creator Instance.

Layout
------

::

    creator_instance/<creator_id>/
        identity.json        source.json        text_rules.json
        visual_rules.json    risk_policy.json   generation.json
        publishing.json      provenance.json
        creator_instance.json          # aggregate, same content as the eight

The document form is **canonical JSON**. JSON is a strict subset of YAML 1.2, so
these files are valid YAML documents for any YAML tool; emitting JSON keeps the
layer dependency-free, exactly as ``multimodal_creator.profile`` does for
``visual_profile.yaml``. :func:`emit_document` additionally provides a
JSON-subset emitter for readers that accept only the flattened form.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import CreatorContractError

#: Version of the on-disk artifact layout (not the semantic contract version).
ARTIFACT_CONTRACT_VERSION = "c0.1.0"

#: The eight instance modules, in canonical order.
MODULE_NAMES: tuple[str, ...] = (
    "identity",
    "source",
    "text_rules",
    "visual_rules",
    "risk_policy",
    "generation",
    "publishing",
    "provenance",
)

#: Module name -> filename.
MODULE_FILES: Mapping[str, str] = {name: f"{name}.json" for name in MODULE_NAMES}

#: Filename of the aggregate document.
AGGREGATE_FILENAME = "creator_instance.json"

#: Filename of the optional flattened form.
YAML_FILENAME = "creator_instance.yaml"


def module_filename(module: str) -> str:
    """Return the filename for a module name, rejecting unknown modules."""

    try:
        return MODULE_FILES[module]
    except KeyError as exc:
        raise CreatorContractError(
            f"unknown creator instance module {module!r}; "
            f"expected one of: {', '.join(MODULE_NAMES)}"
        ) from exc


def instance_dir(root: str | Path, creator_id: str) -> Path:
    """Return ``<root>/<creator_id>``, rejecting unsafe creator ids."""

    if not isinstance(creator_id, str) or not creator_id.strip():
        raise CreatorContractError("creator_id must be a non-empty string")
    if creator_id != creator_id.strip():
        raise CreatorContractError("creator_id must not have surrounding whitespace")
    forbidden = set('\\/:*?"<>|')
    if forbidden & set(creator_id) or creator_id in {".", ".."}:
        raise CreatorContractError(
            f"creator_id {creator_id!r} is not usable as a directory name"
        )
    return Path(root) / creator_id


def default_instance_dir(creator_id: str, root: str | Path = "creator_instance") -> Path:
    """Return the conventional instance directory for a creator id."""

    return instance_dir(root, creator_id)


def module_path(root: str | Path, creator_id: str, module: str) -> Path:
    """Return the path of one module file inside an instance directory."""

    return instance_dir(root, creator_id) / module_filename(module)


def contract_schema_path(workspace_root: str | Path | None = None) -> Path:
    """Return the path of ``schemas/creator_instance.schema.json``.

    Defaults to the workspace containing this package, so the schema is found
    without a caller-supplied path and without depending on the current working
    directory.
    """

    if workspace_root is not None:
        return Path(workspace_root) / "schemas" / "creator_instance.schema.json"
    return Path(__file__).resolve().parents[1] / "schemas" / "creator_instance.schema.json"


def canonical_json(document: Mapping[str, Any] | Sequence[Any]) -> str:
    """Serialise a document as canonical JSON with a trailing newline.

    Deterministic: keys are sorted and non-ASCII is preserved literally, so two
    runs over equal content produce byte-identical output.
    """

    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_document(path: str | Path, document: Mapping[str, Any]) -> Path:
    """Write one document as canonical JSON, creating parent directories."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(document), encoding="utf-8")
    return target


def read_document(path: str | Path) -> dict[str, Any]:
    """Read one canonical JSON document, failing with a typed error."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CreatorContractError(f"instance document not found: {source}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorContractError(f"cannot read instance document {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CreatorContractError(f"instance document must be an object: {source}")
    return payload


def write_instance(
    instance: Mapping[str, Any],
    *,
    root: str | Path = "creator_instance",
    creator_id: str | None = None,
) -> list[Path]:
    """Write all eight module files plus the aggregate document.

    Returns the written paths in canonical module order, with the aggregate
    last. The instance is *not* validated here: validation is an explicit,
    separately reportable step (see :func:`creator_contract.validation.validate`).
    """

    resolved = creator_id or _creator_id_of(instance)
    target_dir = instance_dir(root, resolved)
    written: list[Path] = []
    for module in MODULE_NAMES:
        if module not in instance:
            raise CreatorContractError(
                f"instance is missing module {module!r}; cannot write it"
            )
        written.append(
            write_document(target_dir / module_filename(module), instance[module])
        )
    written.append(write_document(target_dir / AGGREGATE_FILENAME, dict(instance)))
    return written


def read_instance(
    root: str | Path,
    creator_id: str,
) -> dict[str, Any]:
    """Read the aggregate document for an instance, if present.

    Falls back to reassembling from the individual module files, so both layouts
    are readable and a partially written instance is still diagnosable.
    """

    target_dir = instance_dir(root, creator_id)
    aggregate = target_dir / AGGREGATE_FILENAME
    if aggregate.is_file():
        return read_document(aggregate)
    rebuilt: dict[str, Any] = {}
    for module in MODULE_NAMES:
        candidate = target_dir / module_filename(module)
        if candidate.is_file():
            rebuilt[module] = read_document(candidate)
    if not rebuilt:
        raise CreatorContractError(f"no instance documents found in {target_dir}")
    return rebuilt


def _creator_id_of(instance: Mapping[str, Any]) -> str:
    identity = instance.get("identity")
    if not isinstance(identity, Mapping):
        raise CreatorContractError("instance has no identity block")
    creator_id = identity.get("creator_id")
    if not isinstance(creator_id, str) or not creator_id.strip():
        raise CreatorContractError("instance identity has no usable creator_id")
    return creator_id


# --------------------------------------------------------------------------
# JSON-subset emitter (dependency-free, no YAML library)
# --------------------------------------------------------------------------


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _emit_lines(document: Any, indent: int = 0, *, in_sequence: bool = False) -> list[str]:
    pad = " " * indent
    lines: list[str] = []

    if isinstance(document, Mapping):
        if not document:
            return [f"{pad}{{}}"]
        for key, value in document.items():
            if isinstance(value, Mapping) and value:
                lines.append(f"{pad}{key}:")
                lines.extend(_emit_lines(value, indent + 2))
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
                        rendered = _emit_lines(item, indent + 2, in_sequence=True)
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


def emit_document(document: Mapping[str, Any], *, header: str | None = None) -> str:
    """Render a document in the flattened JSON-subset form.

    Deliberately narrow: two-space indentation, ``key: value``, ``- item``
    sequences, and quoted scalars. It exists so the flattened form can be
    produced and round-tripped without a YAML dependency.
    """

    body = "\n".join(_emit_lines(document))
    prefix = f"{header}\n" if header else ""
    return f"{prefix}{body}\n"


def parse_document(payload: str) -> dict[str, Any]:
    """Parse the subset :func:`emit_document` produces.

    Comments (``#``) and blank lines are skipped. Exists so the round trip can be
    tested rather than assumed.
    """

    root: dict[str, Any] = {}
    # stack of (indent, container)
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
                raise CreatorContractError("sequence item without a parent key")
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
            raise CreatorContractError(f"cannot parse line: {raw!r}")

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


__all__ = [
    "AGGREGATE_FILENAME",
    "ARTIFACT_CONTRACT_VERSION",
    "MODULE_FILES",
    "MODULE_NAMES",
    "YAML_FILENAME",
    "canonical_json",
    "contract_schema_path",
    "default_instance_dir",
    "emit_document",
    "instance_dir",
    "module_filename",
    "module_path",
    "parse_document",
    "read_document",
    "read_instance",
    "write_document",
    "write_instance",
]
