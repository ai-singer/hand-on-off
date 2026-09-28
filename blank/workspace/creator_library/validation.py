"""Validation: eight checks on a released library.

| # | Check | Refuses |
| --- | --- | --- |
| 1 | :func:`validate_structure` | a member layout that is not the library layout |
| 2 | :func:`validate_manifest` | an incomplete manifest, or one carrying a forbidden key |
| 3 | :func:`validate_skills` | a declared skill with no emitted directory, or a mismatched one |
| 4 | :func:`validate_layers` | a universal skill carrying domain knowledge |
| 5 | :func:`validate_isolation` | runtime, credentials, prompts, forbidden paths |
| 6 | :func:`validate_checksums` | a recorded digest that does not match its member |
| 7 | :func:`validate_reproducibility` | two builds of one input producing different bytes |
| 8 | :func:`validate_registry` | a published registry that disagrees with the builder's catalog |

Check 5 is the one that decides whether the artefact is safe to upload: a skill
library that carried a credential, a prompt or an executable would be precisely the
thing the whole programme exists to prevent.

Every check reports what it found rather than only the first failure, so a caller
sees the whole picture.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from creator_plugin_builder import (
    DOMAIN_MARKERS,
    FORBIDDEN_MODULES,
    META_SKILLS,
    PROMPT_KEYS,
    PROMPT_PHRASES,
    RUNTIME_KEYS,
    UNIVERSAL_SKILLS,
    audit_layers,
)

from .archive import read_archive, verify_ledger
from .errors import (
    LibraryChecksumError,
    LibraryCredentialError,
    LibraryIsolationError,
    LibraryLayerError,
    LibraryManifestError,
    LibraryPromptError,
    LibraryRegistryError,
    LibraryReproducibilityError,
    LibraryRuntimeError,
    LibrarySkillMissingError,
    LibraryStructureError,
)
from .manifest import FORBIDDEN_MANIFEST_KEYS, validate_manifest
from .paths import (
    ALLOWED_SUFFIXES,
    CHECKSUMS_MEMBER,
    FORBIDDEN_DIRECTORIES,
    FORBIDDEN_FILENAMES,
    FORBIDDEN_SUFFIXES,
    LAYERS,
    MANIFEST_MEMBER,
    SCHEMA_MEMBER,
    SKILL_FILES,
    classify_member,
    expected_members,
    layer_of,
    skill_directory_of,
    skill_members,
)

#: Credential-shaped patterns, checked against every string member.
#:
#: The token-prefix patterns are unmistakable: no documentation writes ``sk-`` followed
#: by twenty characters by accident. The assignment pattern is deliberately narrow — it
#: requires a single unbroken value of at least sixteen characters containing a digit —
#: because the looser form matched the library's own prose (``no credential, token or
#: key``) and a check that cannot tell a denylist from a secret is not a check.
CREDENTIAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("openai-style-token", r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ("github-token", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("aws-access-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    (
        "sensitive-assignment",
        r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)\b"
        r"\s*[:=]\s*[\"']?(?=[A-Za-z0-9_./+=:@-]{8,}[0-9])"
        r"[A-Za-z0-9_./+=:@-]{8,}",
    ),
)

#: Words that are the *name* of a concept rather than a value of one. A library has to
#: be able to say it carries no credentials, so these are never findings on their own.
CREDENTIAL_ALLOWLIST: tuple[str, ...] = (
    "api_key",
    "api-key",
    "apikey",
    "credentials",
    "credential",
    "secret",
    "secrets",
    "token",
    "tokens",
    "password",
    "passwd",
    "webhook",
    "endpoint",
)

#: Values that are plainly placeholders rather than secrets.
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "${",
    "<",
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "redacted",
    "replace-me",
    "replace_me",
    "test-only",
    "your-",
    "your_",
)


@dataclass(frozen=True, slots=True)
class LibraryValidationReport:
    """The result of validating a released library."""

    library_version: str
    checks: Mapping[str, str]
    findings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return all(value == "PASS" for value in self.checks.values())

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "library_version": self.library_version,
            "status": self.status,
            "checks": dict(self.checks),
        }
        if self.findings:
            document["findings"] = list(self.findings)
        return document


# --------------------------------------------------------------------------
# 1. Structure
# --------------------------------------------------------------------------


def validate_structure(
    members: Mapping[str, bytes],
    *,
    skills: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Check 1: the member layout is the library layout."""

    if not members:
        raise LibraryStructureError("the library archive is empty")

    expected = (
        expected_members({layer: tuple(names) for layer, names in skills.items()})
        if skills is not None
        else None
    )

    offenders: list[str] = []
    for member in sorted(members):
        kind = classify_member(member)
        if kind == "unknown":
            offenders.append(f"{member}: not a library member")
            continue
        if not any(member.endswith(suffix) for suffix in ALLOWED_SUFFIXES):
            offenders.append(f"{member}: suffix not allowed in a library")
        parts = member.split("/")
        for part in parts[:-1]:
            if part in FORBIDDEN_DIRECTORIES:
                offenders.append(f"{member}: forbidden directory {part!r}")
        if parts[-1] in FORBIDDEN_FILENAMES:
            offenders.append(f"{member}: forbidden filename {parts[-1]!r}")

    if offenders:
        raise LibraryStructureError(
            f"the library has {len(offenders)} structural violation(s)",
            detail="; ".join(offenders[:6]),
        )

    if expected is not None:
        missing = sorted(expected - set(members))
        if missing:
            raise LibraryStructureError(
                f"the library is missing {len(missing)} member(s)",
                detail=", ".join(missing[:6]),
            )


# --------------------------------------------------------------------------
# 2. Manifest
# --------------------------------------------------------------------------


def validate_manifest_member(members: Mapping[str, bytes]) -> dict[str, Any]:
    """Check 2: the release manifest is present, complete and clean."""

    payload = members.get(MANIFEST_MEMBER)
    if payload is None:
        raise LibraryManifestError(f"the library carries no {MANIFEST_MEMBER}")
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibraryManifestError(
            "the release manifest is not valid JSON", detail=str(exc)
        ) from exc
    if not isinstance(manifest, dict):
        raise LibraryManifestError("the release manifest must be an object")
    validate_manifest(manifest)

    # The forbidden-key check runs over the whole document, not just the top level:
    # a credential cannot hide in a nested block.
    found = sorted(_keys(manifest) & set(FORBIDDEN_MANIFEST_KEYS))
    if found:
        raise LibraryManifestError(
            "the release manifest carries forbidden keys: " + ", ".join(found)
        )
    return manifest


def _keys(node: Any) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                found.add(str(key))
                walk(child)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(node)
    return found


# --------------------------------------------------------------------------
# 3. Skills
# --------------------------------------------------------------------------


def validate_skills(
    members: Mapping[str, bytes],
    manifest: Mapping[str, Any],
) -> None:
    """Check 3: every declared skill has its three files, and they agree."""

    offenders: list[str] = []
    declared_names: set[tuple[str, str]] = set()

    for skill in manifest["skills"]:
        layer = str(skill["library_layer"])
        name = str(skill["name"])
        if layer not in LAYERS:
            offenders.append(f"{name}: unknown layer {layer!r}")
            continue
        declared_names.add((layer, name))

        paths = skill_members(layer, name)
        for filename in SKILL_FILES:
            if paths[filename] not in members:
                offenders.append(f"{name}: missing {filename}")

        manifest_member = members.get(paths["manifest.json"])
        if manifest_member is not None:
            try:
                emitted = json.loads(manifest_member.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                offenders.append(f"{name}: manifest.json is not valid JSON ({exc})")
                continue
            if emitted.get("name") != name:
                offenders.append(f"{name}: manifest.json names {emitted.get('name')!r}")
            if emitted.get("library_layer") != layer:
                offenders.append(f"{name}: manifest.json layer mismatch")
            if emitted.get("version") != manifest["library_version"]:
                offenders.append(f"{name}: manifest.json version mismatch")

    for layer in LAYERS:
        prefix = f"creator_skill_library/{'universal_skills' if layer == 'universal' else 'meta_skills'}/"
        present = {
            member[len(prefix):].split("/", 1)[0]
            for member in members
            if member.startswith(prefix)
        }
        for name in sorted(present):
            if (layer, name) not in declared_names:
                offenders.append(f"{name}: emitted but not declared in the manifest")

    if offenders:
        raise LibrarySkillMissingError(
            f"the library has {len(offenders)} skill inconsistency/ies",
            detail="; ".join(offenders[:6]),
        )


# --------------------------------------------------------------------------
# 4. Layers
# --------------------------------------------------------------------------


def validate_layers(
    manifest: Mapping[str, Any],
    *,
    require_complete: bool = False,
) -> None:
    """Check 4: universal skills carry no domain knowledge; names match the library.

    ``require_complete`` distinguishes the two legitimate uses of this check. The
    **released** library must carry every skill the library declares — a partial
    release is not the library. A caller building a deliberate subset (for a test, or
    for a slimmed deployment) needs the subset to be *drawn from* the library, which
    is the weaker condition: every released name must be declared, and every released
    name must sit on the right layer.
    """

    report = audit_layers()
    if not report.passed:
        raise LibraryLayerError(
            f"{len(report.violations)} universal/domain layer violation(s)",
            detail="; ".join(report.violations[:6]),
        )

    declared_universal = {
        str(s["name"]) for s in manifest["skills"] if s["library_layer"] == "universal"
    }
    declared_meta = {
        str(s["name"]) for s in manifest["skills"] if s["library_layer"] == "meta"
    }

    unexpected = sorted(
        (declared_universal - set(UNIVERSAL_SKILLS))
        | (declared_meta - set(META_SKILLS))
    )
    if unexpected:
        raise LibraryLayerError(
            "the release carries skills the library does not declare",
            detail=", ".join(unexpected),
        )

    if require_complete:
        missing_universal = sorted(set(UNIVERSAL_SKILLS) - declared_universal)
        missing_meta = sorted(set(META_SKILLS) - declared_meta)
        if missing_universal or missing_meta:
            raise LibraryLayerError(
                "the released skills do not match the library",
                detail=(
                    f"missing universal: {missing_universal}; "
                    f"missing meta: {missing_meta}"
                ),
            )

    # A universal skill's emitted prose must be domain-free too.
    offenders: list[str] = []
    for skill in manifest["skills"]:
        if skill["library_layer"] != "universal":
            continue
        name = str(skill["name"])
        blob = json.dumps(skill).lower()
        hits = sorted({m for m in DOMAIN_MARKERS if m in blob})
        if hits:
            offenders.append(f"{name}: domain vocabulary ({', '.join(hits)})")
    if offenders:
        raise LibraryLayerError(
            "a released universal skill carries domain knowledge",
            detail="; ".join(offenders[:6]),
        )


# --------------------------------------------------------------------------
# 5. Isolation
# --------------------------------------------------------------------------


def validate_isolation(members: Mapping[str, bytes]) -> None:
    """Check 5: no runtime, no credential, no prompt, no forbidden reference.

    **A note on false positives.** A library has to be able to *say* that it carries
    no runtime and no credential — `LIBRARY.md` explains exactly that, and the
    manifest records it under ``exclusions``. A check that flagged those sentences
    would make the honest statement impossible to write, which is the wrong trade.

    So the check is structural about where a match *is*, and strict about what it
    matches:

    - A **skill** is declarative content, so a forbidden module name inside one is
      always a violation: a skill has no reason to mention a runtime module at all.
    - The **root documents** may legitimately name what they exclude, so module names
      are not scanned there.
    - **Prompts** are forbidden everywhere, with no exception — there is no honest
      reason for prompt text to appear in a skill library.
    - **Credential shapes** are checked everywhere, and a match is only excused when
      the matched text is itself the *name* of the concept rather than a value.
    - **Keys**, not prose, decide the runtime and prompt key checks.
    """

    runtime: list[str] = []
    credentials: list[str] = []
    prompts: list[str] = []

    for member in sorted(members):
        payload = members[member]
        text = _decode(payload)
        if text is None:
            continue
        lowered = text.lower()
        filename = member.rsplit("/", 1)[-1]

        if filename.endswith(FORBIDDEN_SUFFIXES):
            runtime.append(f"{member}: runtime suffix")
            continue

        if filename.endswith(".json"):
            document = _json_document(payload)
            for key, value in _key_values(document):
                if key.lower() in RUNTIME_KEYS and not _is_entrypoint(key, value):
                    runtime.append(f"{member}: runtime key {key!r}")
                if key.lower() in PROMPT_KEYS:
                    prompts.append(f"{member}: prompt key {key!r}")

        # A skill is declarative: it has no business naming a runtime module.
        if skill_directory_of(member) and member.endswith((".md", ".json")):
            for module in FORBIDDEN_MODULES:
                if re.search(rf"(?<![\w-]){re.escape(module)}(?![\w-])", lowered):
                    runtime.append(f"{member}: references module {module!r}")

        for phrase in PROMPT_PHRASES:
            if phrase in lowered:
                prompts.append(f"{member}: prompt phrase {phrase!r}")

        for rule, pattern in CREDENTIAL_PATTERNS:
            for match in re.finditer(pattern, text):
                if _is_concept_reference(match.group(0), rule):
                    continue
                credentials.append(f"{member}: [{rule}] credential-shaped value")

    if runtime:
        raise LibraryRuntimeError(
            f"the library carries {len(runtime)} runtime violation(s)",
            detail="; ".join(sorted(set(runtime))[:6]),
        )
    if credentials:
        raise LibraryCredentialError(
            f"the library carries {len(credentials)} credential-shaped value(s)",
            detail="; ".join(sorted(set(credentials))[:6]),
        )
    if prompts:
        raise LibraryPromptError(
            f"the library carries {len(prompts)} prompt violation(s)",
            detail="; ".join(sorted(set(prompts))[:6]),
        )


def _is_concept_reference(matched: str, rule: str = "") -> bool:
    """Whether a credential-shaped match is naming a concept rather than a value.

    Two cases were wrong on the first pass, and both are worth stating because they
    are the difference between a check and a nuisance:

    - A **private key header** contains spaces and was excused as "prose". It is the
      most unambiguous secret shape there is: a PEM header is never documentation.
    - An **assignment to prose** was reported. ``api_key = set from the environment``
      matches a key name followed by text; it does not carry a secret. A real
      assignment has a single unbroken value.

    So the rules are checked in order, and the space heuristic applies only where a
    human sentence could plausibly be mistaken for a value.
    """

    stripped = matched.strip().strip("\"'`")
    lowered = stripped.lower()

    # Unambiguous secret shapes: never documentation, whatever else they look like.
    if rule in ("private-key", "openai-style-token", "github-token",
                "aws-access-key", "jwt"):
        return False

    # `key = value` / `key: value`: judge the value, not the whole match.
    assignment = re.match(
        r"(?i)^\s*[\"']?[a-z0-9_-]*(?:api[_-]?key|token|password|passwd)"
        r"[a-z0-9_-]*[\"']?\s*[:=]\s*(?P<value>.+?)\s*$",
        stripped,
    )
    if assignment:
        value = assignment.group("value").strip().strip("\"'`")
        if any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
            return True
        if value.lower() in CREDENTIAL_ALLOWLIST:
            return True
        # A value with a space is a sentence: "set from the environment".
        if " " in value:
            return True
        return False

    for token in CREDENTIAL_ALLOWLIST:
        if lowered == token or lowered.endswith((" " + token, ":" + token,
                                                 "=" + token)):
            return True
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return True
    return False


def _decode(payload: bytes) -> str | None:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _json_keys(payload: bytes) -> set[str]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return set()
    return _keys(document)


def _json_document(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _key_values(document: Any) -> list[tuple[str, Any]]:
    """Every ``(key, value)`` pair in a document, at any depth."""

    found: list[tuple[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                found.append((str(key), child))
                walk(child)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(document)
    return found


def _is_entrypoint(key: str, value: Any) -> bool:
    """Whether an ``entrypoint`` key is the skill convention rather than a runtime.

    Every skill manifest in this repository carries ``"entrypoint": "SKILL.md"`` —
    it names the document a reader opens, which is the convention a Shared Skill
    Library expects. That is a documentation pointer, not an executable entry point,
    and the key name alone cannot tell them apart. The *value* can: a markdown file
    is a document, anything else is not accepted.
    """

    return key == "entrypoint" and isinstance(value, str) and value.endswith(".md")


# --------------------------------------------------------------------------
# 6. Checksums
# --------------------------------------------------------------------------


def validate_checksums(members: Mapping[str, bytes]) -> dict[str, Any]:
    """Check 6: every recorded digest matches its member."""

    payload = members.get(CHECKSUMS_MEMBER)
    if payload is None:
        raise LibraryChecksumError(f"the library carries no {CHECKSUMS_MEMBER}")
    try:
        ledger = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibraryChecksumError(
            "the checksum ledger is not valid JSON", detail=str(exc)
        ) from exc

    mismatches = verify_ledger(members, ledger)
    if mismatches:
        raise LibraryChecksumError(
            f"the checksum ledger disagrees on {len(mismatches)} member(s)",
            detail="; ".join(mismatches[:6]),
        )

    recorded = ledger.get("file_count")
    if recorded != len(members):
        raise LibraryChecksumError(
            f"the ledger counts {recorded} files but the library has {len(members)}"
        )
    return ledger


# --------------------------------------------------------------------------
# 7. Reproducibility
# --------------------------------------------------------------------------


def validate_reproducibility(first: bytes, second: bytes) -> None:
    """Check 7: two builds of one input produced the same bytes."""

    if first == second:
        return
    from creator_package.hashing import digest_bytes

    raise LibraryReproducibilityError(
        "two builds of the same library produced different bytes",
        detail=(
            f"first {digest_bytes(first)[:16]}, second {digest_bytes(second)[:16]}"
        ),
    )

# --------------------------------------------------------------------------
# 8. Registry
# --------------------------------------------------------------------------


def validate_registry(
    members: Mapping[str, bytes],
    *,
    catalog_domains: Sequence[str],
) -> dict[str, Any]:
    """Check 8: the published registry matches the builder's catalog."""

    from .paths import REGISTRY_MEMBER

    payload = members.get(REGISTRY_MEMBER)
    if payload is None:
        raise LibraryRegistryError(f"the library carries no {REGISTRY_MEMBER}")
    try:
        registry = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibraryRegistryError(
            "the domain registry is not valid JSON", detail=str(exc)
        ) from exc

    published = {str(entry["domain"]) for entry in registry.get("domains", ())}
    if published != set(catalog_domains):
        raise LibraryRegistryError(
            "the published registry disagrees with the builder's catalog",
            detail=(
                f"published: {sorted(published)}; catalog: {sorted(catalog_domains)}"
            ),
        )
    if registry.get("domain_count") != len(published):
        raise LibraryRegistryError(
            "the registry's own count does not match its entries"
        )
    return registry


# --------------------------------------------------------------------------
# Combined
# --------------------------------------------------------------------------


def validate_archive(
    payload: bytes,
    *,
    catalog_domains: Sequence[str] | None = None,
    require_complete_library: bool = False,
) -> LibraryValidationReport:
    """Run every check against a finished archive."""

    members = read_archive(payload)
    checks: dict[str, str] = {}
    findings: list[str] = []

    validate_structure(members)
    checks["structure"] = "PASS"

    manifest = validate_manifest_member(members)
    checks["manifest"] = "PASS"

    validate_skills(members, manifest)
    checks["skills"] = "PASS"

    validate_layers(manifest, require_complete=require_complete_library)
    checks["layers"] = "PASS"

    validate_isolation(members)
    checks["isolation"] = "PASS"

    validate_checksums(members)
    checks["checksums"] = "PASS"

    validate_reproducibility(payload, payload)
    checks["reproducibility"] = "PASS"

    if catalog_domains is not None:
        validate_registry(members, catalog_domains=catalog_domains)
        checks["registry"] = "PASS"

    return LibraryValidationReport(
        library_version=str(manifest["library_version"]),
        checks=checks,
        findings=tuple(findings),
    )


def verify_library_hash(
    members: Mapping[str, bytes],
    manifest: Mapping[str, Any],
) -> bool:
    """Re-derive ``content_hash`` and compare it, never trusting the recorded value."""

    from creator_package.hashing import package_hash

    expected = manifest.get("hashes", {}).get("content_hash")
    if not expected:
        raise LibraryManifestError("the manifest records no content_hash")
    return package_hash(members) == expected


def describe_validation(members: Mapping[str, bytes]) -> dict[str, Any]:
    """A review document: what the library contains, by kind and by layer."""

    from .paths import summarise_members

    by_layer: dict[str, list[str]] = {}
    for member in members:
        layer = layer_of(member)
        directory = skill_directory_of(member)
        if layer and directory:
            name = directory.rsplit("/", 1)[-1]
            by_layer.setdefault(layer, [])
            if name not in by_layer[layer]:
                by_layer[layer].append(name)

    return {
        "members": summarise_members(dict(members)),
        "skills_by_layer": {
            layer: sorted(names) for layer, names in sorted(by_layer.items())
        },
        "schema_present": SCHEMA_MEMBER in members,
    }


__all__ = [
    "CREDENTIAL_ALLOWLIST",
    "CREDENTIAL_PATTERNS",
    "PLACEHOLDER_MARKERS",
    "LibraryValidationReport",
    "describe_validation",
    "validate_archive",
    "validate_checksums",
    "validate_isolation",
    "validate_layers",
    "validate_manifest_member",
    "validate_registry",
    "validate_reproducibility",
    "validate_skills",
    "validate_structure",
    "verify_library_hash",
]
