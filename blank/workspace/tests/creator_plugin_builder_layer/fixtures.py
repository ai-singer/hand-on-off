"""Shared fixtures for the Creator Skill Library tests.

The plugin build is not cheap — it reads the asset registry and validates — so results
are cached per domain for the life of the process rather than rebuilt per test.
"""

from __future__ import annotations

import atexit
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from creator_plugin_builder import (
    DomainRequest,
    build_domain_plugin,
)

#: The workspace under test.
WORKSPACE = Path(__file__).resolve().parents[2]

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="c05_library_tests_"))
atexit.register(shutil.rmtree, _TEMP_ROOT, True)

_CACHE: dict[str, Any] = {}


def scratch_dir(name: str) -> Path:
    """A fresh, empty directory under the test temporary root."""

    target = _TEMP_ROOT / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def request_for(domain: str, *, sources: tuple[str, ...] = ("creator_a", "creator_b")):
    """A domain request for one of the catalog's domains."""

    return DomainRequest(
        domain=domain,
        platform="xiaohongshu",
        reference_sources=sources,
    )


def build(domain: str, **kwargs: Any) -> Any:
    """Build one domain's plugin, cached."""

    key = f"build:{domain}:{sorted(kwargs.items())}"
    if key not in _CACHE:
        _CACHE[key] = build_domain_plugin(request_for(domain), **kwargs)
    return _CACHE[key]


def plugin(domain: str) -> Any:
    """The built plugin for one domain, cached."""

    return build(domain).plugin


def all_plugins() -> tuple[Any, ...]:
    """Every catalog domain's plugin, in domain order."""

    return tuple(plugin(domain) for domain in ("finance", "sports", "technology"))


def as_document(value: Any) -> Any:
    """A deep, mutable copy of a document."""

    return json.loads(json.dumps(value))
