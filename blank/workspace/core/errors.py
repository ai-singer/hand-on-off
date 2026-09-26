"""Framework-specific errors with stable meanings for callers."""


class CreatorFrameworkError(Exception):
    """Base class for expected framework failures."""


class InvalidSourceError(CreatorFrameworkError, ValueError):
    """Raised when a raw source violates the input contract."""


class PluginLoadError(CreatorFrameworkError, RuntimeError):
    """Raised when a Creator plugin cannot satisfy the plugin protocol."""


class ArtifactValidationError(CreatorFrameworkError, ValueError):
    """Raised when an artifact does not match the unified schema contract."""
