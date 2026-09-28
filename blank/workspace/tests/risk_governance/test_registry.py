from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.benchmark_registry import (
    ADVERSARIAL_ANNOTATION_PROTOCOL,
    ANNOTATION_PROTOCOL,
    ANNOTATION_PROTOCOL_V2,
    ANNOTATION_VERSION,
    ANNOTATION_VERSION_V2,
    BENCHMARK_EXPORTS,
    CASES_NAME,
    LABELS_NAME,
    MANIFEST_NAME,
    STATUSES,
    BenchmarkRecord,
    BenchmarkRegistry,
    BenchmarkRegistryError,
    annotation_field_names,
    build_record,
    dataset_hash,
    decontaminated_cases,
)


class RegistryLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = BenchmarkRegistry()

    def test_registry_lists_every_version(self) -> None:
        """Phase 7.5 extended the registry to four versions; Phase 8.1 added the
        generated adversarial family as a namespaced benchmark id; Phase 8.9 added
        the independent validation benchmark, which is a namespace of its own."""

        keys = {
            (record.benchmark_id, record.version)
            for record in self.registry.list_benchmarks()
        }

        self.assertEqual(
            keys,
            {
                ("semantic", "v1"),
                ("semantic", "v2"),
                ("semantic", "v3"),
                ("semantic", "v4"),
                ("semantic/adversarial", "v1"),
                ("risk/independent", "v1"),
            },
        )

    def test_a_namespaced_id_resolves_to_a_nested_directory(self) -> None:
        record = self.registry.get("semantic/adversarial", "v1")

        self.assertEqual(record.path_parts, ("semantic", "adversarial", "v1"))
        self.assertEqual(
            self.registry.directory(record).relative_to(self.registry.root).parts,
            ("semantic", "adversarial", "v1"),
        )

    def test_versions_shared_across_benchmark_ids_are_not_ambiguous(self) -> None:
        """`semantic/v1` and `semantic/adversarial/v1` both exist."""

        first = self.registry.get("semantic", "v1")
        second = self.registry.get("semantic/adversarial", "v1")

        self.assertNotEqual(first.dataset_hash, second.dataset_hash)
        self.assertNotEqual(first.case_count, second.case_count)

    def test_get_by_id_and_version(self) -> None:
        record = self.registry.get("semantic", "v2")

        self.assertEqual(record.version, "v2")
        self.assertEqual(record.case_count, 62)

    def test_get_without_version_is_unambiguous_for_single_version_ids(self) -> None:
        with self.assertRaises(BenchmarkRegistryError):
            self.registry.get("semantic")

    def test_unknown_benchmark_is_rejected(self) -> None:
        with self.assertRaises(BenchmarkRegistryError):
            self.registry.get("does-not-exist", "v1")

    def test_every_version_directory_has_the_three_files(self) -> None:
        for record in self.registry.list_benchmarks():
            directory = self.registry.directory(record)
            for name in (MANIFEST_NAME, CASES_NAME, LABELS_NAME):
                self.assertTrue((directory / name).is_file(), f"{record.version}/{name}")


class RegistryManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = BenchmarkRegistry()

    def test_manifest_carries_every_required_field(self) -> None:
        required = {
            "id",
            "version",
            "case_count",
            "dataset_hash",
            "annotation_protocol",
            "created_by",
            "status",
        }

        for record in self.registry.list_benchmarks():
            payload = record.as_dict()
            for field in required:
                self.assertIn(field, payload, record.version)

    def test_manifest_records_the_annotation_contract(self) -> None:
        """Each version names the guide it was labelled under.

        v1 and v2 were labelled under guide v1; Phase 7.5's v3 and v4 under
        guide v2; Phase 8.1's generated cases under guide v2 plus the
        adversarial-generation protocol. A version's protocol is fixed at export
        and never rewritten. Keyed by the full name, because the version alone
        is no longer unique across benchmark ids.
        """

        expected = {
            ("semantic", "v1"): (ANNOTATION_VERSION, ANNOTATION_PROTOCOL),
            ("semantic", "v2"): (ANNOTATION_VERSION, ANNOTATION_PROTOCOL),
            ("semantic", "v3"): (ANNOTATION_VERSION_V2, ANNOTATION_PROTOCOL_V2),
            ("semantic", "v4"): (ANNOTATION_VERSION_V2, ANNOTATION_PROTOCOL_V2),
            ("semantic/adversarial", "v1"): (
                ANNOTATION_VERSION_V2,
                ADVERSARIAL_ANNOTATION_PROTOCOL,
            ),
            # Phase 8.9 labels under guide v2 plus its own protocol, which is where
            # the two-annotator and adjudication rules live. Recorded here rather
            # than defaulted, so a version that appears without being registered
            # still fails this test.
            ("risk/independent", "v1"): (
                "3.0.0",
                "docs/RISK_ANNOTATION_GUIDE_v2.md@2.0.0+"
                "docs/INDEPENDENT_ANNOTATION_PROTOCOL_V3.md@3.0.0",
            ),
        }
        seen = set()
        for record in self.registry.list_benchmarks():
            key = (record.benchmark_id, record.version)
            version, protocol = expected[key]
            self.assertEqual(record.annotation_version, version)
            self.assertEqual(record.annotation_protocol, protocol)
            self.assertIn("RISK_ANNOTATION_GUIDE", record.annotation_protocol)
            seen.add(key)

        self.assertEqual(seen, set(expected))

    def test_status_is_a_known_value(self) -> None:
        for record in self.registry.list_benchmarks():
            self.assertIn(record.status, STATUSES)

    def test_v1_is_recorded_as_contaminated_and_v2_as_frozen(self) -> None:
        self.assertEqual(self.registry.get("semantic", "v1").status, "contaminated")
        self.assertEqual(self.registry.get("semantic", "v2").status, "frozen")

    def test_manifest_counts_match_the_records(self) -> None:
        for record in self.registry.list_benchmarks():
            records = self.registry.load_records(record)

            self.assertEqual(record.case_count, len(records))
            groups: dict[str, int] = {}
            for item in records:
                groups[item["group"]] = groups.get(item["group"], 0) + 1
            self.assertEqual(dict(record.group_counts), groups)

    def test_manifest_categories_match_the_labels(self) -> None:
        for record in self.registry.list_benchmarks():
            labels = self.registry.load_labels(record)

            self.assertEqual(
                set(record.categories), set(labels["category_index"])
            )

    def test_created_by_names_the_producing_phase(self) -> None:
        """Provenance is per version, not a global default.

        The generated adversarial family comes from Phase 8.1; recording it as
        Phase 7.4 would send a reader to results it has nothing to do with.
        """

        expected = {
            ("semantic", "v1"): "phase-7.4",
            ("semantic", "v2"): "phase-7.4",
            ("semantic", "v3"): "phase-7.4",
            ("semantic", "v4"): "phase-7.4",
            ("semantic/adversarial", "v1"): "phase-8.1",
            ("risk/independent", "v1"): "phase-8.9",
        }
        for record in self.registry.list_benchmarks():
            key = (record.benchmark_id, record.version)

            self.assertIn(expected[key], record.created_by, str(key))


class RegistryHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = BenchmarkRegistry()

    def test_dataset_hash_is_a_sha256_digest(self) -> None:
        for record in self.registry.list_benchmarks():
            self.assertEqual(len(record.dataset_hash), 64)
            int(record.dataset_hash, 16)

    def test_stored_datasets_still_match_their_manifest_hash(self) -> None:
        for record in self.registry.list_benchmarks():
            self.assertTrue(self.registry.verify(record), record.version)

    def test_verify_all_reports_true_for_both(self) -> None:
        self.assertEqual(
            set(self.registry.verify_all().values()), {True}
        )

    def test_changing_a_case_changes_the_hash(self) -> None:
        records = [dict(item) for item in self.registry.load_records(
            self.registry.get("semantic", "v2")
        )]
        original = dataset_hash(records)
        records[0]["expected_categories"] = ["emotional_manipulation"]

        self.assertNotEqual(dataset_hash(records), original)

    def test_changing_annotation_prose_changes_the_hash(self) -> None:
        """The hash covers the complete record, prose included."""

        records = [dict(item) for item in self.registry.load_records(
            self.registry.get("semantic", "v2")
        )]
        original = dataset_hash(records)
        records[0]["annotation_reason"] = "edited after the fact"

        self.assertNotEqual(dataset_hash(records), original)

    def test_reordering_cases_changes_the_hash(self) -> None:
        records = [dict(item) for item in self.registry.load_records(
            self.registry.get("semantic", "v2")
        )]

        self.assertNotEqual(dataset_hash(records), dataset_hash(list(reversed(records))))

    def test_hash_is_stable_across_calls(self) -> None:
        records = self.registry.load_records(self.registry.get("semantic", "v1"))

        self.assertEqual(dataset_hash(records), dataset_hash(records))

    def test_verify_detects_a_tampered_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tampered = BenchmarkRegistry(directory)
            source = BenchmarkRegistry()
            record = source.get("semantic", "v2")
            target = tampered.directory(record)
            target.mkdir(parents=True)
            payload = json.loads(
                (source.directory(record) / MANIFEST_NAME).read_text(encoding="utf-8")
            )
            (target / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
            records = list(source.load_records(record))
            records[0]["text"] = "tampered text"
            (target / CASES_NAME).write_text(json.dumps(records), encoding="utf-8")
            (target / LABELS_NAME).write_text("{}", encoding="utf-8")

            loaded = tampered.get("semantic", "v2")

            self.assertFalse(tampered.verify(loaded))


class RegistryExportTests(unittest.TestCase):
    def test_export_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            BenchmarkRegistry(first).export()
            BenchmarkRegistry(second).export()

            for (benchmark_id, version) in BENCHMARK_EXPORTS:
                for name in (MANIFEST_NAME, CASES_NAME, LABELS_NAME):
                    left = Path(first, benchmark_id, version, name).read_text(
                        encoding="utf-8"
                    )
                    right = Path(second, benchmark_id, version, name).read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(left, right, f"{version}/{name}")

    def test_exported_records_carry_every_annotation_field(self) -> None:
        registry = BenchmarkRegistry()

        for record in registry.list_benchmarks():
            for payload in registry.load_records(record):
                for field in annotation_field_names():
                    self.assertIn(field, payload, payload["id"])

    def test_labels_index_agrees_with_the_cases(self) -> None:
        registry = BenchmarkRegistry()

        for record in registry.list_benchmarks():
            labels = registry.load_labels(record)
            records = registry.load_records(record)

            self.assertEqual(labels["case_count"], len(records))
            self.assertEqual(
                set(labels["by_case"]), {item["id"] for item in records}
            )
            for item in records:
                self.assertEqual(
                    labels["by_case"][item["id"]], item["expected_categories"]
                )
            indexed = sorted(
                case_id for ids in labels["group_index"].values() for case_id in ids
            )
            self.assertEqual(indexed, sorted(item["id"] for item in records))

    def test_v2_is_the_decontaminated_subset_of_v1(self) -> None:
        registry = BenchmarkRegistry()
        v1_ids = {item["id"] for item in registry.load_records(registry.get("semantic", "v1"))}
        v2_ids = {item["id"] for item in registry.load_records(registry.get("semantic", "v2"))}

        self.assertTrue(v2_ids < v1_ids)
        self.assertEqual(len(v2_ids), 62)
        self.assertEqual(
            len(v2_ids), len(decontaminated_cases())
        )

    def test_build_record_rejects_an_unknown_status(self) -> None:
        with self.assertRaises(BenchmarkRegistryError):
            build_record("x", "v1", [{"id": "a"}], status="whatever")

    def test_build_record_rejects_an_empty_dataset(self) -> None:
        with self.assertRaises(BenchmarkRegistryError):
            build_record("x", "v1", [])

    def test_record_round_trips_through_its_manifest(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get("semantic", "v1")

        restored = registry._record_from_manifest(json.loads(json.dumps(record.as_dict())))

        self.assertEqual(restored, record)
        self.assertIsInstance(restored, BenchmarkRecord)


if __name__ == "__main__":
    unittest.main()
