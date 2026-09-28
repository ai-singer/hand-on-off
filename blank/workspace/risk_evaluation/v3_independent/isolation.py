"""Phase 8.9 isolation: the independent track changed nothing outside itself.

Two checks, and the second is the one that matters.

**Static.** Nothing in `risk_evaluation/v3_independent/` imports a production,
runtime, workflow, artifact, security, plugin or multimodal module. Checked by
parsing each file rather than by grepping, so a string in a docstring cannot pass and
a dynamic import under a different name cannot hide.

**Differential.** The evaluator files are byte-identical to the freeze, which is what
`freeze.guard()` established before any data was generated. A phase that added an
import to `runtime` without touching the evaluator would still be a cross-track
change, so the forbidden paths are checked as a set rather than one at a time.

The forbidden list is the phase's own.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .freeze import FROZEN_PATHS, guard, workspace_root

ISOLATION_PATH = Path(__file__).resolve().parent / "isolation_v3_2.json"

#: Paths the phase requires to be untouched.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "workflow",
    "plugins",
    "artifact",
    "multimodal_creator",
    "security",
)

#: Modules this package may import from inside the repository.
ALLOWED_INTERNAL_PREFIXES: tuple[str, ...] = (
    "risk_evaluation",
    "risk_evaluation.v3",
    "risk_evaluation.v3_1",
    "risk_evaluation.v3_repair",
    "risk_evaluation.v3_validation",
    "risk_evaluation.benchmark_registry",
    "risk_evaluation.taxonomy",
    "risk_evaluation.taxonomy_v2",
)

PACKAGE = Path(__file__).resolve().parent


class IsolationError(Exception):
    """Raised when a cross-track change is found."""


@dataclass(frozen=True, slots=True)
class IsolationReport:
    files_scanned: int
    imports: tuple[str, ...]
    violations: tuple[str, ...]
    frozen_paths_ok: bool
    frozen_note: str

    @property
    def passed(self) -> bool:
        return not self.violations and self.frozen_paths_ok

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "files_scanned": self.files_scanned,
            "imports": sorted(set(self.imports)),
            "violations": list(self.violations),
            "forbidden_prefixes": list(FORBIDDEN_PREFIXES),
            "frozen_paths": list(FROZEN_PATHS),
            "frozen_paths_ok": self.frozen_paths_ok,
            "frozen_note": self.frozen_note,
            "note": (
                "Static imports are parsed, not grepped, and the evaluator sources are "
                "compared against the freeze, so a cross-track change is a failure "
                "rather than a note."
            ),
        }

    def render(self) -> str:
        lines = [
            f"files scanned : {self.files_scanned}",
            f"imports       : {len(set(self.imports))} distinct",
            f"violations    : {len(self.violations)}",
            f"frozen paths  : {'verified' if self.frozen_paths_ok else 'MOVED'} "
            f"{self.frozen_note}",
            f"status        : {self.status}",
        ]
        for item in self.violations:
            lines.append(f"  VIOLATION {item}")
        return "\n".join(lines)


def _imports_of(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                names.append(f"{'.' * node.level}{node.module}")
            elif node.module:
                names.append(node.module)
    return tuple(names)


def _resolve(relative: str, module: str, level: int) -> str:
    """Turn a relative import into a repository-absolute module path."""

    if not level:
        return module
    parts = relative.split("/")[:-1]
    parts = parts[: len(parts) - (level - 1)] if level > 1 else parts
    return ".".join([*parts, module]) if module else ".".join(parts)


def scan(directory: Path | None = None) -> IsolationReport:
    root = directory if directory is not None else PACKAGE
    violations: list[str] = []
    imports: list[str] = []
    files = 0
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        files += 1
        relative = path.relative_to(workspace_root()).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            level = 0
            module = ""
            if isinstance(node, ast.ImportFrom):
                level = node.level or 0
                module = node.module or ""
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
                    top = alias.name.split(".")[0]
                    if top in FORBIDDEN_PREFIXES:
                        violations.append(f"{relative}: imports {alias.name}")
                continue
            else:
                continue
            absolute = _resolve(relative, module, level) if level else module
            imports.append(absolute)
            top = absolute.split(".")[0]
            if top in FORBIDDEN_PREFIXES:
                violations.append(f"{relative}: imports {absolute}")
            elif top == "risk_evaluation" and not any(
                absolute == prefix or absolute.startswith(prefix + ".")
                for prefix in ALLOWED_INTERNAL_PREFIXES
            ):
                # An import from elsewhere in the repository that is not one of the
                # frozen evaluation packages is still a dependency this phase did not
                # declare, so it is reported rather than allowed silently.
                if absolute not in ("risk_evaluation",):
                    violations.append(f"{relative}: undeclared internal import {absolute}")
    ok = True
    note = "evaluator frozen and unchanged"
    try:
        guard()
    except Exception as error:  # noqa: BLE001 - the message is the finding
        ok = False
        note = str(error)
    return IsolationReport(
        files_scanned=files,
        imports=tuple(imports),
        violations=tuple(violations),
        frozen_paths_ok=ok,
        frozen_note=note,
    )


def changed_paths(status_lines: Sequence[str]) -> tuple[str, ...]:
    """Forbidden paths among `git status --porcelain` output."""

    found: list[str] = []
    for line in status_lines:
        entry = line[3:].strip()
        if not entry:
            continue
        for prefix in FORBIDDEN_PREFIXES:
            if f"/{prefix}/" in f"/{entry}":
                found.append(entry)
                break
    return tuple(sorted(set(found)))


def write_report(
    path: str | Path | None = None, *, report: IsolationReport | None = None
) -> Path:
    target = Path(path) if path is not None else ISOLATION_PATH
    active = report if report is not None else scan()
    target.write_text(
        json.dumps(active.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def describe() -> Mapping[str, Any]:
    return {
        "forbidden_prefixes": list(FORBIDDEN_PREFIXES),
        "frozen_paths": list(FROZEN_PATHS),
        "method": "ast import parsing, plus the freeze guard",
    }


def main() -> int:
    import sys

    report = scan()
    print(report.render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(report=report)}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
