"""Deployable artifact manifest generation and validation.

Submodules are re-exported lazily (PEP 562). An eager ``from .manifest import
...`` here would place the submodule in ``sys.modules`` before ``runpy``
executes it as ``__main__``, so ``python -m artifact.manifest`` and
``python -m artifact.validator`` would run a second copy of the module.
"""

from __future__ import annotations

from typing import Any

_MANIFEST_EXPORTS = frozenset(
    {
        "ArtifactManifestError",
        "MANIFEST_NAME",
        "MANIFEST_VERSION",
        "build_manifest",
        "generate_manifest",
        "iter_artifact_files",
        "sha256_file",
    }
)
_VALIDATOR_EXPORTS = frozenset(
    {
        "Finding",
        "ValidationResult",
        "validate_artifact",
    }
)

__all__ = sorted(_MANIFEST_EXPORTS | _VALIDATOR_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _MANIFEST_EXPORTS:
        from . import manifest

        return getattr(manifest, name)
    if name in _VALIDATOR_EXPORTS:
        from . import validator

        return getattr(validator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
