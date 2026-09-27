"""Versioned benchmark registry.

A benchmark is a published artefact, not a Python list. Each version lives
under `risk_evaluation/benchmarks/<id>/` with three files:

    manifest.json   identity, hash, counts, status, provenance
    cases.json      the complete annotation records
    labels.json     label index, derived from the cases

`dataset_hash` covers the **complete annotation record** of every case, in
order, so any edit — including prose in `annotation_reason` — changes the hash.
That is deliberately strict: a published dataset is immutable, and a correction
means a new version rather than a quiet edit.

The in-code case tables in `independent_benchmark.py` remain the authoring
source. `export_benchmarks()` writes them out, and the export is deterministic:
re-exporting an unchanged source reproduces byte-identical files.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import benchmark_v2
from .benchmark import BENCHMARK_CASES
from .independent_benchmark import (
    ANNOTATION_FIELDS,
    INDEPENDENT_CASES,
    AnnotationCase,
)


BENCHMARK_ROOT = Path(__file__).resolve().parent / "benchmarks"
ANNOTATION_VERSION = "1.0.0"
ANNOTATION_PROTOCOL = "docs/RISK_ANNOTATION_GUIDE.md@1.0.0"
CREATED_BY = "creator-agent-framework/phase-7.4"
FROZEN = "frozen"
CONTAMINATED = "contaminated"
RETIRED = "retired"
STATUSES = (FROZEN, CONTAMINATED, RETIRED)

#: Fixed export timestamps keep re-export byte-stable.
CREATED_AT = "2026-09-27T00:00:00Z"

MANIFEST_NAME = "manifest.json"
CASES_NAME = "cases.json"
LABELS_NAME = "labels.json"


class BenchmarkRegistryError(Exception):
    """Raised when a benchmark cannot be registered or loaded."""


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    benchmark_id: str
    version: str
    created_at: str
    dataset_hash: str
    case_count: int
    categories: tuple[str, ...]
    annotation_version: str
    annotation_protocol: str
    created_by: str
    status: str
    group_counts: Mapping[str, int]
    source: str

    @property
    def path_parts(self) -> tuple[str, str]:
        return (self.benchmark_id, self.version)

    def as_dict(self) -> dict[str, Any]:
        """The manifest payload."""

        return {
            "id": self.benchmark_id,
            "version": self.version,
            "created_at": self.created_at,
            "case_count": self.case_count,
            "dataset_hash": self.dataset_hash,
            "categories": list(self.categories),
            "annotation_version": self.annotation_version,
            "annotation_protocol": self.annotation_protocol,
            "created_by": self.created_by,
            "status": self.status,
            "group_counts": dict(self.group_counts),
            "source": self.source,
        }


def dataset_hash(records: Sequence[Mapping[str, Any]]) -> str:
    """SHA-256 over the complete annotation records, in order."""

    canonical = json.dumps(
        list(records), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _categories(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    names: set[str] = set()
    for record in records:
        names.update(record["expected_categories"])
    return tuple(sorted(names))


def _group_counts(records: Sequence[Mapping[str, Any]]) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        group = str(record["group"])
        counts[group] = counts.get(group, 0) + 1
    return dict(sorted(counts.items()))


def build_record(
    benchmark_id: str,
    version: str,
    records: Sequence[Mapping[str, Any]],
    *,
    status: str = FROZEN,
    source: str = "",
    created_at: str = CREATED_AT,
    annotation_version: str = ANNOTATION_VERSION,
    annotation_protocol: str = ANNOTATION_PROTOCOL,
) -> BenchmarkRecord:
    if status not in STATUSES:
        raise BenchmarkRegistryError(
            f"status must be one of {STATUSES}, got {status!r}"
        )
    if not records:
        raise BenchmarkRegistryError("a benchmark must contain at least one case")
    return BenchmarkRecord(
        benchmark_id=benchmark_id,
        version=version,
        created_at=created_at,
        dataset_hash=dataset_hash(records),
        case_count=len(records),
        categories=_categories(records),
        annotation_version=annotation_version,
        annotation_protocol=annotation_protocol,
        created_by=CREATED_BY,
        status=status,
        group_counts=_group_counts(records),
        source=source,
    )


def _records_for(cases: Iterable[AnnotationCase]) -> tuple[dict[str, Any], ...]:
    return tuple(case.as_dict() for case in cases)


def _labels_payload(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_case = {str(record["id"]): list(record["expected_categories"]) for record in records}
    group_index: dict[str, list[str]] = {}
    for record in records:
        group_index.setdefault(str(record["group"]), []).append(str(record["id"]))
    category_index: dict[str, list[str]] = {}
    for record in records:
        for name in record["expected_categories"]:
            category_index.setdefault(str(name), []).append(str(record["id"]))
    return {
        "annotation_version": ANNOTATION_VERSION,
        "case_count": len(records),
        "by_case": by_case,
        "group_index": {key: sorted(value) for key, value in sorted(group_index.items())},
        "category_index": {
            key: sorted(value) for key, value in sorted(category_index.items())
        },
    }


def decontaminated_cases() -> tuple[AnnotationCase, ...]:
    """The independent cases whose text does not appear in the development set.

    Derived, never hand-edited. It exists so a clean benchmark version can be
    published without touching the contaminated one, whose cases stay exactly
    as they were measured.
    """

    development = {case.text for case in BENCHMARK_CASES}
    return tuple(case for case in INDEPENDENT_CASES if case.text not in development)


#: Benchmark versions this package publishes.
BENCHMARK_EXPORTS: Mapping[tuple[str, str], tuple[AnnotationCase, ...]] = {
    ("semantic", "v1"): INDEPENDENT_CASES,
    ("semantic", "v2"): decontaminated_cases(),
}

#: Recorded status per version. v1 measured contaminated in Phase 7.3 and is
#: kept as published evidence; v2 is the clean version derived from it.
BENCHMARK_STATUS: Mapping[tuple[str, str], str] = {
    ("semantic", "v1"): CONTAMINATED,
    ("semantic", "v2"): FROZEN,
}

BENCHMARK_SOURCE: Mapping[tuple[str, str], str] = {
    ("semantic", "v1"): "phase-7.3 independent benchmark, measured as published",
    ("semantic", "v2"): "phase-7.4 decontaminated subset of semantic v1",
}

#: Annotation contract for versions labelled under the v2 guide.
ANNOTATION_VERSION_V2 = "2.0.0"
ANNOTATION_PROTOCOL_V2 = "docs/RISK_ANNOTATION_GUIDE_v2.md@2.0.0"

#: Record-based exports, used by versions whose annotation records carry fields
#: the v1 `AnnotationCase` does not model. Added in Phase 7.5; v1 and v2 keep
#: their original export path so their bytes do not change.
RECORD_EXPORTS: Mapping[tuple[str, str], Any] = {
    ("semantic", "v3"): lambda: benchmark_v2.v3_records(),
    ("semantic", "v4"): lambda: benchmark_v2.v4_records(),
}

RECORD_STATUS: Mapping[tuple[str, str], str] = {
    ("semantic", "v3"): CONTAMINATED,
    ("semantic", "v4"): FROZEN,
}

RECORD_SOURCE: Mapping[tuple[str, str], str] = {
    ("semantic", "v3"): "phase-7.5 benchmark labelled under RISK_ANNOTATION_GUIDE_v2, measured as published",
    ("semantic", "v4"): "phase-7.5 decontaminated subset of semantic v3",
}

RECORD_ANNOTATION: Mapping[tuple[str, str], tuple[str, str]] = {
    ("semantic", "v3"): (ANNOTATION_VERSION_V2, ANNOTATION_PROTOCOL_V2),
    ("semantic", "v4"): (ANNOTATION_VERSION_V2, ANNOTATION_PROTOCOL_V2),
}


class BenchmarkRegistry:
    """Read, verify and export versioned benchmarks."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else BENCHMARK_ROOT

    @property
    def root(self) -> Path:
        return self._root

    def directory(self, record: BenchmarkRecord) -> Path:
        return self._root.joinpath(*record.path_parts)

    def list_benchmarks(self) -> tuple[BenchmarkRecord, ...]:
        records: list[BenchmarkRecord] = []
        if not self._root.is_dir():
            return ()
        for path in sorted(self._root.glob(f"*/*/{MANIFEST_NAME}")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._record_from_manifest(payload))
        return tuple(records)

    def get(self, benchmark_id: str, version: str | None = None) -> BenchmarkRecord:
        candidates = [
            item for item in self.list_benchmarks() if item.benchmark_id == benchmark_id
        ]
        if version is not None:
            candidates = [item for item in candidates if item.version == version]
        if not candidates:
            raise BenchmarkRegistryError(
                f"unknown benchmark {benchmark_id!r} version {version!r}"
            )
        if len(candidates) > 1:
            raise BenchmarkRegistryError(
                f"benchmark {benchmark_id!r} has multiple versions; specify one"
            )
        return candidates[0]

    def load_records(self, record: BenchmarkRecord) -> tuple[dict[str, Any], ...]:
        path = self.directory(record) / CASES_NAME
        return tuple(json.loads(path.read_text(encoding="utf-8")))

    def load_cases(self, record: BenchmarkRecord) -> tuple[AnnotationCase, ...]:
        """Rehydrate the stored records as evaluable cases."""

        return tuple(
            AnnotationCase(
                case_id=str(payload["id"]),
                group=str(payload["group"]),
                text=str(payload["text"]),
                expected_categories=tuple(payload["expected_categories"]),
                annotation_reason=str(payload["annotation_reason"]),
                source_type=str(payload["source_type"]),
                created_after_evaluator_freeze=bool(
                    payload["created_after_evaluator_freeze"]
                ),
            )
            for payload in self.load_records(record)
        )

    def load_labels(self, record: BenchmarkRecord) -> dict[str, Any]:
        path = self.directory(record) / LABELS_NAME
        return json.loads(path.read_text(encoding="utf-8"))

    def verify(self, record: BenchmarkRecord) -> bool:
        """True when the stored cases still hash to the manifest value."""

        return dataset_hash(self.load_records(record)) == record.dataset_hash

    def verify_all(self) -> Mapping[str, bool]:
        return {
            f"{item.benchmark_id}/{item.version}": self.verify(item)
            for item in self.list_benchmarks()
        }

    @staticmethod
    def _record_from_manifest(payload: Mapping[str, Any]) -> BenchmarkRecord:
        return BenchmarkRecord(
            benchmark_id=str(payload["id"]),
            version=str(payload["version"]),
            created_at=str(payload["created_at"]),
            dataset_hash=str(payload["dataset_hash"]),
            case_count=int(payload["case_count"]),
            categories=tuple(payload["categories"]),
            annotation_version=str(payload["annotation_version"]),
            annotation_protocol=str(payload["annotation_protocol"]),
            created_by=str(payload["created_by"]),
            status=str(payload["status"]),
            group_counts=dict(payload["group_counts"]),
            source=str(payload.get("source", "")),
        )

    def export(self, key: tuple[str, str] | None = None) -> tuple[Path, ...]:
        """Write every benchmark this package publishes."""

        written: list[Path] = []
        for (benchmark_id, version), cases in BENCHMARK_EXPORTS.items():
            if key is not None and key != (benchmark_id, version):
                continue
            written.extend(
                self._write(
                    benchmark_id,
                    version,
                    _records_for(cases),
                    status=BENCHMARK_STATUS[(benchmark_id, version)],
                    source=BENCHMARK_SOURCE[(benchmark_id, version)],
                )
            )
        for (benchmark_id, version), provider in RECORD_EXPORTS.items():
            if key is not None and key != (benchmark_id, version):
                continue
            annotation_version, annotation_protocol = RECORD_ANNOTATION[
                (benchmark_id, version)
            ]
            written.extend(
                self._write(
                    benchmark_id,
                    version,
                    provider(),
                    status=RECORD_STATUS[(benchmark_id, version)],
                    source=RECORD_SOURCE[(benchmark_id, version)],
                    annotation_version=annotation_version,
                    annotation_protocol=annotation_protocol,
                )
            )
        return tuple(written)

    def _write(
        self,
        benchmark_id: str,
        version: str,
        records: Sequence[Mapping[str, Any]],
        *,
        status: str,
        source: str,
        annotation_version: str = ANNOTATION_VERSION,
        annotation_protocol: str = ANNOTATION_PROTOCOL,
    ) -> tuple[Path, ...]:
        record = build_record(
            benchmark_id,
            version,
            records,
            status=status,
            source=source,
            annotation_version=annotation_version,
            annotation_protocol=annotation_protocol,
        )
        directory = self.directory(record)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / MANIFEST_NAME).write_text(
            json.dumps(record.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (directory / CASES_NAME).write_text(
            json.dumps(list(records), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (directory / LABELS_NAME).write_text(
            json.dumps(_labels_payload(records), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return (
            directory / MANIFEST_NAME,
            directory / CASES_NAME,
            directory / LABELS_NAME,
        )


def annotation_field_names() -> tuple[str, ...]:
    """Fields that must be present on every exported record."""

    return ANNOTATION_FIELDS


def main() -> int:
    import sys

    registry = BenchmarkRegistry()
    if "--export" in sys.argv:
        for path in registry.export():
            print(f"wrote {path.relative_to(registry.root.parent.parent)}")
        return 0
    for record in registry.list_benchmarks():
        state = "OK" if registry.verify(record) else "HASH MISMATCH"
        print(
            f"{record.benchmark_id}/{record.version}: {record.case_count} cases, "
            f"{record.status}, {record.dataset_hash[:16]} [{state}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
