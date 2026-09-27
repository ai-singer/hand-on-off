"""Artifact validation for deployable Creator Agent instances.

Deployment is gated on a manifest that was generated from the artifact being
shipped. Validation answers four questions before an artifact may be deployed:

1. is the manifest present and structurally valid?
2. do the declared files exist, at the declared size and hash?
3. does the artifact declare a runtime contract this runtime implements?
4. are the declared runtime config, plugins and skills actually present, and
   do they agree with the configuration the artifact ships?

Validation collects every finding instead of stopping at the first one, so a
failed release reports the whole picture in a single run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from artifact.manifest import (
    CONFIG_RELATIVE,
    MANIFEST_NAME,
    iter_artifact_files,
    major_version,
    sha256_file,
)
from config.runtime import load_runtime_config
from core.errors import ArtifactValidationError
from core.schema_validation import validate_schema_instance
from runtime import SUPPORTED_CONFIG_VERSION
from runtime.bootstrap import SKILL_PACKAGE_PARTS

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    message: str
    path: str | None = None

    def render(self) -> str:
        location = f" ({self.path})" if self.path else ""
        return f"[{self.rule}] {self.message}{location}"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    artifact_dir: Path
    manifest_path: Path | None
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    def render(self) -> str:
        if self.ok:
            return f"PASS {self.artifact_dir}"
        lines = [f"FAIL {self.artifact_dir} ({len(self.findings)} finding(s))"]
        lines.extend(f"  {finding.render()}" for finding in self.findings)
        return "\n".join(lines)


def validate_artifact(
    artifact_dir: str | Path,
    *,
    manifest_path: str | Path | None = None,
    runtime_version: str | None = None,
) -> ValidationResult:
    """Validate an artifact directory against its manifest."""

    root = Path(artifact_dir)
    if not root.is_dir():
        return _fail(root, None, "artifact-missing", f"artifact directory does not exist: {root}")

    target = Path(manifest_path) if manifest_path is not None else root / MANIFEST_NAME
    if not target.is_file():
        return _fail(root, target, "manifest-missing", f"artifact manifest not found: {target}")

    try:
        manifest = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(root, target, "manifest-missing", f"cannot read artifact manifest: {exc}")

    if not isinstance(manifest, dict):
        return _fail(root, target, "manifest-invalid", "artifact manifest root must be an object")

    try:
        validate_schema_instance(manifest, SCHEMA_PATH, root_name="manifest")
    except ArtifactValidationError as exc:
        return _fail(root, target, "manifest-invalid", str(exc))

    findings: list[Finding] = []
    supported = runtime_version or SUPPORTED_CONFIG_VERSION
    findings.extend(_check_runtime(manifest, supported))
    findings.extend(_check_config(root, manifest))
    findings.extend(_check_components(root, manifest))
    findings.extend(_check_files(root, manifest))
    findings.extend(_check_unlisted(root, target, manifest))
    return ValidationResult(root, target, tuple(findings))


def _fail(
    root: Path, target: Path | None, rule: str, message: str
) -> ValidationResult:
    return ValidationResult(root, target, (Finding(rule, message),))


def _check_runtime(manifest: Mapping[str, Any], supported: str) -> list[Finding]:
    """The artifact must declare a runtime contract this runtime implements."""

    required = manifest["runtime_version"]
    if major_version(required) != major_version(supported):
        return [
            Finding(
                "runtime-incompatible",
                f"artifact requires runtime contract {required!r} but this runtime "
                f"implements {supported!r}",
            )
        ]
    return []


def _check_config(root: Path, manifest: Mapping[str, Any]) -> list[Finding]:
    """The shipped runtime config must exist and agree with the manifest."""

    relative = "/".join(CONFIG_RELATIVE)
    config_path = root.joinpath(*CONFIG_RELATIVE)
    if not config_path.is_file():
        return [Finding("config-missing", "artifact does not ship a runtime config", relative)]

    try:
        config = load_runtime_config(config_path)
    except ValueError as exc:
        return [Finding("config-missing", f"artifact runtime config is invalid: {exc}", relative)]

    findings: list[Finding] = []
    if config.version != manifest["config_version"]:
        findings.append(
            Finding(
                "config-mismatch",
                f"manifest config_version {manifest['config_version']!r} does not match "
                f"the artifact runtime config version {config.version!r}",
                relative,
            )
        )
    if sorted(config.plugins.enabled) != sorted(manifest["enabled_plugins"]):
        findings.append(
            Finding(
                "config-mismatch",
                "manifest enabled_plugins do not match the artifact runtime config",
                relative,
            )
        )
    if sorted(config.skills.enabled) != sorted(manifest["enabled_skills"]):
        findings.append(
            Finding(
                "config-mismatch",
                "manifest enabled_skills do not match the artifact runtime config",
                relative,
            )
        )
    return findings


def _check_components(root: Path, manifest: Mapping[str, Any]) -> list[Finding]:
    """Declared plugins and skills must exist inside the artifact."""

    findings: list[Finding] = []
    for module_path in manifest["enabled_plugins"]:
        relative = Path(*module_path.split("."))
        if not (root / relative / "__init__.py").is_file():
            findings.append(
                Finding(
                    "plugin-missing",
                    f"plugin package {module_path!r} is not present in the artifact",
                    relative.as_posix(),
                )
            )
    for name in manifest["enabled_skills"]:
        relative = Path(*SKILL_PACKAGE_PARTS) / name / "manifest.json"
        if not (root / relative).is_file():
            findings.append(
                Finding(
                    "skill-missing",
                    f"skill {name!r} has no manifest in the artifact",
                    relative.as_posix(),
                )
            )
    return findings


def _check_files(root: Path, manifest: Mapping[str, Any]) -> list[Finding]:
    """Every declared file must exist, at the declared size and hash."""

    findings: list[Finding] = []
    for entry in manifest["files"]:
        relative = entry["path"]
        path = root / relative
        if not path.is_file():
            findings.append(
                Finding("file-missing", "declared file is missing from the artifact", relative)
            )
            continue
        actual_size = path.stat().st_size
        if actual_size != entry["size"]:
            findings.append(
                Finding(
                    "size-mismatch",
                    f"declared size {entry['size']} does not match actual size {actual_size}",
                    relative,
                )
            )
        if sha256_file(path) != entry["sha256"]:
            findings.append(
                Finding(
                    "hash-mismatch",
                    "declared sha256 does not match the file content",
                    relative,
                )
            )
    return findings


def _check_unlisted(
    root: Path, target: Path, manifest: Mapping[str, Any]
) -> list[Finding]:
    """An artifact must not carry files the manifest does not declare."""

    declared = {entry["path"] for entry in manifest["files"]}
    excluded: tuple[str, ...] = ()
    try:
        if target.resolve().is_relative_to(root.resolve()):
            excluded = (target.resolve().relative_to(root.resolve()).as_posix(),)
    except (OSError, ValueError):
        excluded = ()

    return [
        Finding(
            "extra-file",
            "artifact contains a file the manifest does not declare",
            relative.as_posix(),
        )
        for relative in iter_artifact_files(root, exclude=excluded)
        if relative.as_posix() not in declared
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a deployable Creator Agent artifact against its manifest."
    )
    parser.add_argument("artifact_dir", help="Artifact directory to validate")
    parser.add_argument("--manifest", dest="manifest_path", default=None)
    parser.add_argument("--runtime-version", dest="runtime_version", default=None)
    args = parser.parse_args(argv)

    result = validate_artifact(
        args.artifact_dir,
        manifest_path=args.manifest_path,
        runtime_version=args.runtime_version,
    )
    if result.ok:
        print(f"Artifact validation PASS: {result.artifact_dir}")
        return 0

    print(
        f"Artifact validation FAIL: {len(result.findings)} finding(s).",
        file=sys.stderr,
    )
    for finding in result.findings:
        print(f"  {finding.render()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
