"""Dynamic Creator plugin loading without domain-specific core imports."""

from __future__ import annotations

import importlib
from typing import Any

from plugin_interface.base import CreatorDistillationPlugin

from .errors import PluginLoadError


def _validate_plugin(plugin: Any, module_path: str) -> CreatorDistillationPlugin:
    if not isinstance(plugin, CreatorDistillationPlugin):
        raise PluginLoadError(
            f"{module_path!r} returned an object that does not implement "
            "CreatorDistillationPlugin"
        )
    identity = plugin.identity
    if not all((identity.name, identity.version, identity.domain, identity.creator_target)):
        raise PluginLoadError(f"{module_path!r} has incomplete plugin identity")
    return plugin


def load_plugin(module_path: str) -> CreatorDistillationPlugin:
    """Load a plugin module exposing a zero-argument `create_plugin` factory."""

    if not module_path or not module_path.strip():
        raise PluginLoadError("plugin module path must be non-empty")
    try:
        module = importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError) as exc:
        raise PluginLoadError(f"cannot import plugin {module_path!r}: {exc}") from exc

    factory = getattr(module, "create_plugin", None)
    if not callable(factory):
        raise PluginLoadError(
            f"plugin {module_path!r} must expose create_plugin()"
        )
    try:
        plugin = factory()
    except Exception as exc:  # plugin construction is an integration boundary
        raise PluginLoadError(
            f"plugin {module_path!r} failed during construction: {exc}"
        ) from exc
    return _validate_plugin(plugin, module_path)
