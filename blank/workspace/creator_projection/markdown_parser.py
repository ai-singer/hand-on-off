"""Markdown → structure converter.

Scope: **structural conversion only.** This module splits a Markdown document
into ordered sections and preserves each section's original text verbatim. It
does not summarise, rewrite, reinterpret, or generate persona content.

What it extracts, per section: the heading title and level, the section body
unchanged, the bullet items, and the blockquote lines. That is the entire
contract - a mapper decides what a section *means*; the parser only reports what
is *there*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from .errors import ProjectionParseError

#: A level-1..6 ATX heading.
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

#: A line that is only hashes (a heading with no title), outside a code fence.
_BARE_HASHES = re.compile(r"^#{1,6}\s*$")

#: A bullet item, including nested indentation.
_BULLET = re.compile(r"^\s*[-*+]\s+(.*?)\s*$")

#: A numbered item.
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*?)\s*$")

#: A blockquote line.
_QUOTE = re.compile(r"^\s*>\s?(.*?)\s*$")

#: A YAML frontmatter fence.
_FRONTMATTER_FENCE = "---"

#: A fenced code block fence, optionally with a language.
_CODE_FENCE = re.compile(r"^\s*```")


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    """One heading and everything under it, preserved verbatim."""

    title: str
    level: int
    content: str
    bullets: tuple[str, ...]
    quotes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "content": self.content,
            "bullets": list(self.bullets),
            "quotes": list(self.quotes),
        }


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """A parsed Markdown document."""

    frontmatter: dict[str, str]
    preamble: str
    sections: tuple[MarkdownSection, ...]

    def titles(self) -> tuple[str, ...]:
        return tuple(section.title for section in self.sections)

    def section(self, title: str) -> MarkdownSection | None:
        """Return a section by exact title (case-sensitive)."""

        for candidate in self.sections:
            if candidate.title == title:
                return candidate
        return None

    def find(self, *needles: str) -> MarkdownSection | None:
        """Return the first section whose title contains any needle (case-insensitive)."""

        lowered = [needle.lower() for needle in needles]
        for candidate in self.sections:
            haystack = candidate.title.lower()
            if any(needle in haystack for needle in lowered):
                return candidate
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dict(self.frontmatter),
            "preamble": self.preamble,
            "sections": [section.as_dict() for section in self.sections],
        }


def parse_frontmatter(payload: str) -> tuple[dict[str, str], str]:
    """Split leading ``---`` frontmatter from the body.

    Supports ``key: value`` scalars and ``key: |`` folded continuation lines,
    which is what the persona skills use for their ``description``.
    """

    lines = payload.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, payload

    frontmatter: dict[str, str] = {}
    current_key: str | None = None
    index = 1
    while index < len(lines):
        raw = lines[index]
        index += 1
        if raw.strip() == _FRONTMATTER_FENCE:
            return frontmatter, "\n".join(lines[index:])
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if current_key is not None and (raw.startswith(" ") or raw.startswith("\t")):
            frontmatter[current_key] = f"{frontmatter[current_key]} {raw.strip()}".strip()
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value in {"|", ">"}:
            frontmatter[key] = ""
            current_key = key
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        frontmatter[key] = value
        current_key = key

    # Unterminated frontmatter: treat the whole payload as body.
    return {}, payload


def parse_markdown(payload: str) -> MarkdownDocument:
    """Parse a Markdown document into frontmatter, preamble, and sections.

    Raises:
        ProjectionParseError: when a heading is malformed or the document is
            empty.
    """

    if not isinstance(payload, str):
        raise ProjectionParseError("markdown payload must be a string")

    frontmatter, body = parse_frontmatter(payload)
    lines = body.splitlines()

    preamble_lines: list[str] = []
    raw_sections: list[tuple[str, int, list[str]]] = []
    current: tuple[str, int, list[str]] | None = None
    in_code = False

    for raw in lines:
        if _CODE_FENCE.match(raw):
            in_code = not in_code
            if current is None:
                preamble_lines.append(raw)
            else:
                current[2].append(raw)
            continue

        if not in_code:
            if _BARE_HASHES.match(raw):
                raise ProjectionParseError(f"markdown heading with no title: {raw!r}")
            heading = _HEADING.match(raw)
            if heading:
                hashes, title = heading.group(1), heading.group(2).strip()
                if not title:
                    raise ProjectionParseError(
                        f"markdown heading with no title: {raw!r}"
                    )
                if current is not None:
                    raw_sections.append(current)
                current = (title, len(hashes), [])
                continue

        if current is None:
            preamble_lines.append(raw)
        else:
            current[2].append(raw)

    if current is not None:
        raw_sections.append(current)

    sections = tuple(
        MarkdownSection(
            title=title,
            level=level,
            content="\n".join(body_lines).strip(),
            bullets=_collect(body_lines, _BULLET),
            quotes=_collect(body_lines, _QUOTE),
        )
        for title, level, body_lines in raw_sections
    )

    return MarkdownDocument(
        frontmatter=frontmatter,
        preamble="\n".join(preamble_lines).strip(),
        sections=sections,
    )


def _collect(lines: Sequence[str], pattern: re.Pattern[str]) -> tuple[str, ...]:
    """Collect the first capture group of every matching line, code blocks skipped."""

    found: list[str] = []
    in_code = False
    for raw in lines:
        if _CODE_FENCE.match(raw):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = pattern.match(raw)
        if match and match.group(1):
            found.append(match.group(1))
    return tuple(found)


def sections_as_dicts(document: MarkdownDocument) -> list[dict[str, Any]]:
    """Return the section list in the shape the contract expects."""

    return [section.as_dict() for section in document.sections]


def section_titles(document: MarkdownDocument) -> list[str]:
    """Return section titles in document order."""

    return list(document.titles())


__all__ = [
    "MarkdownDocument",
    "MarkdownSection",
    "parse_frontmatter",
    "parse_markdown",
    "section_titles",
    "sections_as_dicts",
]
