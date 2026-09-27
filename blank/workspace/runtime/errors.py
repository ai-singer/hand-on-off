"""Errors raised while initializing a Creator Agent runtime."""

from __future__ import annotations

from core.errors import CreatorFrameworkError


class RuntimeBootstrapError(CreatorFrameworkError, RuntimeError):
    """Raised when the runtime configuration cannot produce a valid context.

    `bootstrap()` is the single initialization entry point, so every
    configuration, plugin, skill and workflow failure surfaces as this one
    type. The originating exception stays available through `__cause__`.
    """
