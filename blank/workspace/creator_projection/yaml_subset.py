"""A small, dependency-free YAML-subset reader.

The project ships ``dependencies = []``, so no YAML library is available. Two
documents in the projection layer need parsing:

* ``creator_projection/assets.yaml`` — the asset registry;
* ``docs/m5/profiles/visual_profile.yaml`` — the flattened M5 profile.

Both are simple: comments, ``key: value`` scalars, nested mappings by
indentation, ``- `` sequence items, ``- `` mapping items, and ``>`` /
``|`` block scalars. This module supports exactly that and nothing more, and says
so rather than pretending to be a YAML implementation.
"""

from __future__ import annotations

from typing import Any

from .errors import ProjectionParseError

#: Keys that must be coerced to a list when their block turns out to be empty.
_SEQUENCE_HINT_KEYS: frozenset[str] = frozenset()


def parse_yaml_subset(payload: str, *, origin: str = "<string>") -> dict[str, Any]:
    """Parse the supported YAML subset into plain Python data.

    Raises:
        ProjectionParseError: on a malformed line or a non-mapping root.
    """

    if not isinstance(payload, str):
        raise ProjectionParseError(f"{origin}: yaml payload must be a string")

    lines = payload.splitlines()
    value, index = _parse_mapping(lines, 0, -1, origin)
    # Skip any trailing blank/comment lines; anything else is unexpected.
    while index < len(lines):
        raw = lines[index]
        index += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        raise ProjectionParseError(
            f"{origin}: content after the root mapping is not supported: {raw!r}"
        )
    if not isinstance(value, dict):
        raise ProjectionParseError(f"{origin}: root must be a mapping")
    return value


def _indent(raw: str) -> int:
    return len(raw) - len(raw.lstrip(" "))


def _significant(lines: list[str], index: int) -> tuple[str, int] | None:
    """Return the next non-blank, non-comment line and its index."""

    while index < len(lines):
        raw = lines[index]
        if raw.strip() and not raw.lstrip().startswith("#"):
            return raw, index
        index += 1
    return None


def _parse_scalar(text: str) -> Any:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in {"null", "~", ""}:
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _read_block_scalar(
    lines: list[str], index: int, parent_indent: int, folded: bool
) -> tuple[str, int]:
    collected: list[str] = []
    while index < len(lines):
        raw = lines[index]
        if raw.strip() and _indent(raw) <= parent_indent:
            break
        index += 1
        collected.append(raw.strip())
    if folded:
        return " ".join(part for part in collected if part), index
    return "\n".join(collected).strip(), index


def _is_sequence_start(lines: list[str], index: int, parent_indent: int) -> bool:
    """Peek at the first significant line of a nested block."""

    found = _significant(lines, index)
    if found is None:
        return False
    raw, _ = found
    return _indent(raw) > parent_indent and raw.strip().startswith("- ")


def _parse_mapping(
    lines: list[str], index: int, parent_indent: int, origin: str
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}

    while True:
        found = _significant(lines, index)
        if found is None:
            return result, len(lines)
        raw, position = found
        indent = _indent(raw)
        if indent <= parent_indent:
            return result, position
        line = raw.strip()

        if line.startswith("- "):
            raise ProjectionParseError(
                f"{origin}: sequence item where a mapping key was expected: {line!r}"
            )
        if ":" not in line:
            raise ProjectionParseError(
                f"{origin}: line is neither a mapping entry nor a sequence item: {line!r}"
            )

        index = position + 1
        key, _, rest = line.partition(":")
        key = key.strip()
        if not key:
            raise ProjectionParseError(f"{origin}: mapping entry with an empty key")

        rest = rest.strip()

        if rest in {">", "|"}:
            result[key], index = _read_block_scalar(lines, index, indent, rest == ">")
            continue
        if rest:
            result[key] = _parse_scalar(rest)
            continue

        # Empty value: the block may be a mapping, a sequence, or empty.
        if _is_sequence_start(lines, index, indent):
            result[key], index = _parse_sequence(lines, index, indent, origin)
        else:
            nested, next_index = _parse_mapping(lines, index, indent, origin)
            if nested:
                result[key] = nested
                index = next_index
            else:
                # No nested mapping: decide between [] and {} from any deeper line.
                deeper = _significant(lines, next_index)
                if deeper is not None and _indent(deeper[0]) > indent:
                    raise ProjectionParseError(
                        f"{origin}: unsupported nested structure under {key!r}"
                    )
                result[key] = {}
                index = next_index
    # unreachable


def _parse_sequence(
    lines: list[str], index: int, parent_indent: int, origin: str
) -> tuple[list[Any], int]:
    items: list[Any] = []
    sequence_indent: int | None = None

    while True:
        found = _significant(lines, index)
        if found is None:
            return items, len(lines)
        raw, position = found
        indent = _indent(raw)
        line = raw.strip()

        if not line.startswith("- "):
            return items, position
        if sequence_indent is None:
            sequence_indent = indent
        elif indent < sequence_indent:
            return items, position

        index = position + 1
        entry = line[2:].strip()

        if not entry:
            nested, index = _parse_mapping(lines, index, indent, origin)
            items.append(nested)
            continue

        if ":" in entry and not entry.startswith(('"', "'")):
            key, _, rest = entry.partition(":")
            key = key.strip()
            rest = rest.strip()
            item: dict[str, Any] = {}
            if rest in {">", "|"}:
                item[key], index = _read_block_scalar(lines, index, indent, rest == ">")
            elif rest:
                item[key] = _parse_scalar(rest)
            else:
                if _is_sequence_start(lines, index, indent):
                    item[key], index = _parse_sequence(lines, index, indent, origin)
                else:
                    nested, index = _parse_mapping(lines, index, indent, origin)
                    item[key] = nested
            # Continuation entries of the same mapping item are more-indented.
            extra, index = _parse_mapping(lines, index, indent, origin)
            item.update(extra)
            items.append(item)
            continue

        items.append(_parse_scalar(entry))
    # unreachable


__all__ = ["parse_yaml_subset"]
