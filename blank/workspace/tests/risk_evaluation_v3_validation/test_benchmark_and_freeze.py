"""Step 1 to Step 4: the benchmark, the audit, and the freeze."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3_validation.audit import (
    AUDIT_PATH,
    DEVELOPMENT_OVERLAP,
    EXACT_OVERLAP,
    FAIL,
    FINDING_KINDS,
    LABEL_INCOMPLETE,
    NEAR_DUPLICATE,
    NEAR_DUPLICATE_THRESHOLD,
    PASS,
    audit,
    historical_texts,
    jaccard,
    normalize_text,
    token_set,
    write_report as write_audit,
)
from risk_evaluation.v3_validation.cases import (
    AMBIGUOUS_BOUNDARY,
    AUTHOR_ENDORSED_RISK,
    AUTHOR_REJECTION,
    BENCHMARK_ID,
    CASES,
    CONTAMINATED_CASE_IDS,
    DATASET_PATH,
    GROUP_NAMES,
    MINIMUM_CASES,
    NEUTRAL_EDUCATION,
    TARGET_GROUP_SIZES,
    THIRD_PARTY_CLAIM,
    ClaimLabel,
    ValidationCase,
    blind_records,
    case_index,
    category_counts,
    dataset_payload,
    decontaminated_cases,
    group_cases,
    group_sizes,
    write_dataset,
    write_decontaminated,
)
from risk_evaluation.v3_validation.freeze import (
    FREEZE_PATH,
    VERIFIED_KEYS,
    FreezeError,
    build_freeze,
    configuration_hash,
    dataset_hash,
    decision_policy_hash,
    evaluator_hash,
    load_freeze,
    taxonomy_hash,
    verify_freeze,
    write_freeze,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class BenchmarkShapeTests(unittest.TestCase):
    def test_the_benchmark_meets_the_minimum_size(self) -> None:
        self.assertGreaterEqual(len(CASES), MINIMUM_CASES)

    def test_the_composition_matches_the_phase(self) -> None:
        self.assertEqual(
            group_sizes(),
            {
                AUTHOR_ENDORSED_RISK: 25,
                THIRD_PARTY_CLAIM: 20,
                AUTHOR_REJECTION: 15,
                NEUTRAL_EDUCATION: 20,
                AMBIGUOUS_BOUNDARY: 20,
            },
        )

    def test_every_group_meets_its_target(self) -> None:
        sizes = group_sizes()
        for group, target in TARGET_GROUP_SIZES.items():
            self.assertGreaterEqual(sizes[group], target, group)

    def test_all_five_categories_are_covered(self) -> None:
        self.assertEqual(
            set(category_counts()),
            {
                "financial_guarantee",
                "investment_advice",
                "market_prediction",
                "unverified_information",
                "emotional_manipulation",
            },
        )

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in CASES]

        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_carries_an_annotation_reason(self) -> None:
        for case in CASES:
            self.assertTrue(case.annotation_reason.strip(), case.case_id)

    def test_every_case_names_a_guide_section(self) -> None:
        for case in CASES:
            self.assertIn("guide", case.as_dict()["basis"].lower(), case.case_id)

    def test_case_index_maps_every_id(self) -> None:
        self.assertEqual(len(case_index()), len(CASES))

    def test_group_lookup_returns_the_whole_group(self) -> None:
        for group, size in group_sizes().items():
            self.assertEqual(len(group_cases(group)), size, group)


class BenchmarkLabelTests(unittest.TestCase):
    def test_an_unknown_group_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ValidationCase("X-1", "nope", "text", (), (ClaimLabel("author", "endorsed"),), "why")

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ValidationCase("X-1", AUTHOR_ENDORSED_RISK, " ", (), (ClaimLabel("author", "endorsed"),), "why")

    def test_a_missing_annotation_reason_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ValidationCase("X-1", AUTHOR_ENDORSED_RISK, "text", (), (ClaimLabel("author", "endorsed"),), " ")

    def test_an_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ValidationCase("X-1", AUTHOR_ENDORSED_RISK, "text", ("nope",), (ClaimLabel("author", "endorsed"),), "why")

    def test_a_bad_speaker_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClaimLabel("nobody", "endorsed")

    def test_a_bad_stance_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClaimLabel("author", "shrugged")

    def test_a_bad_relation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClaimLabel("author", "endorsed", "VIBES")

    def test_the_neutral_group_never_expects_risk(self) -> None:
        for case in group_cases(NEUTRAL_EDUCATION):
            self.assertFalse(case.expects_risk, case.case_id)

    def test_the_rejection_group_expects_no_author_voice_category(self) -> None:
        author_voice = {
            "investment_advice",
            "market_prediction",
            "financial_guarantee",
            "emotional_manipulation",
        }
        for case in group_cases(AUTHOR_REJECTION):
            self.assertEqual(
                set(case.categories) & author_voice, set(), case.case_id
            )

    def test_expects_risk_follows_the_categories(self) -> None:
        for case in CASES:
            self.assertEqual(case.expects_risk, bool(case.categories))

    def test_every_case_labels_its_claims(self) -> None:
        for case in CASES:
            self.assertTrue(case.claims, case.case_id)


class BlindRecordTests(unittest.TestCase):
    """Step 5: the labels must not be reachable from the prediction input."""

    def test_blind_records_carry_only_id_and_text(self) -> None:
        for record in blind_records():
            self.assertEqual(set(record), {"id", "text"})

    def test_blind_records_cover_every_case(self) -> None:
        self.assertEqual(len(blind_records()), len(CASES))

    def test_no_label_leaks_into_a_blind_record(self) -> None:
        """Checked on the record's keys, not on a substring of its text.

        Searching for the word `stance` anywhere in the payload matches
        `circumstances`, which is a word in one of the cases and not a label.
        """

        for record in blind_records():
            self.assertEqual(set(record), {"id", "text"})
            self.assertNotIn("categories", record)
            self.assertNotIn("annotation_reason", record)


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = audit()

    def test_the_audit_covers_every_case(self) -> None:
        self.assertEqual(self.report.case_count, len(CASES))

    def test_the_audit_checks_the_historical_sources(self) -> None:
        self.assertGreaterEqual(len(self.report.sources_checked), 10)

    def test_the_audit_checks_the_development_sets(self) -> None:
        sources = historical_texts()

        self.assertIn("development/risk-evaluation", sources)
        self.assertIn("development/independent", sources)

    def test_the_benchmark_fails_the_audit(self) -> None:
        """One case is reused verbatim from Phase 8.3, and that is a FAIL."""

        self.assertEqual(self.report.status, FAIL)
        self.assertEqual(len(self.report.of_kind(EXACT_OVERLAP)), 1)

    def test_the_contaminated_case_is_the_recorded_one(self) -> None:
        finding = self.report.of_kind(EXACT_OVERLAP)[0]

        self.assertEqual(finding.case_ids, CONTAMINATED_CASE_IDS)
        self.assertEqual(finding.source, "phase-8.3/experiment")

    def test_the_contaminated_case_was_not_deleted(self) -> None:
        """The phase forbids removing it and recomputing."""

        self.assertIn("IV-037", case_index())

    def test_there_are_no_near_duplicates(self) -> None:
        self.assertEqual(self.report.of_kind(NEAR_DUPLICATE), ())

    def test_there_is_no_development_overlap(self) -> None:
        self.assertEqual(self.report.of_kind(DEVELOPMENT_OVERLAP), ())

    def test_there_are_no_label_findings(self) -> None:
        self.assertEqual(self.report.of_kind(LABEL_INCOMPLETE), ())

    def test_the_decontaminated_subset_passes(self) -> None:
        report = audit(decontaminated_cases())

        self.assertEqual(report.status, PASS)
        self.assertEqual(report.findings, ())
        self.assertEqual(report.case_count, len(CASES) - len(CONTAMINATED_CASE_IDS))

    def test_a_synthetic_overlap_is_detected(self) -> None:
        """The audit must actually detect what it claims to detect."""

        known = "The fund cannot lose money at all."
        report = audit(
            [ValidationCase("X-1", AUTHOR_ENDORSED_RISK, known, (), (ClaimLabel("unknown", "uncertain"),), "why")],
            historical={"phase-8.3/experiment": [known]},
        )

        self.assertEqual(report.status, FAIL)
        self.assertEqual(len(report.of_kind(EXACT_OVERLAP)), 1)

    def test_a_synthetic_near_duplicate_is_detected(self) -> None:
        cases = [
            ValidationCase("X-1", AUTHOR_ENDORSED_RISK, "The fund cannot lose your money at all", (), (ClaimLabel("unknown", "uncertain"),), "why"),
            ValidationCase("X-2", AUTHOR_ENDORSED_RISK, "The fund cannot lose your money at all today", (), (ClaimLabel("unknown", "uncertain"),), "why"),
        ]
        report = audit(cases, historical={})

        self.assertEqual(report.status, FAIL)
        self.assertTrue(report.of_kind(NEAR_DUPLICATE))

    def test_a_missing_label_field_is_detected(self) -> None:
        case = ValidationCase("X-1", AUTHOR_ENDORSED_RISK, "Some fresh text here", (), (ClaimLabel("unknown", "uncertain"),), "why")
        report = audit([case], historical={})

        self.assertEqual(report.of_kind(LABEL_INCOMPLETE), ())

    def test_normalization_is_case_and_punctuation_insensitive(self) -> None:
        self.assertEqual(normalize_text("Buy THIS!"), normalize_text("buy  this"))

    def test_jaccard_bounds(self) -> None:
        self.assertEqual(jaccard(token_set("a b"), token_set("a b")), 1.0)
        self.assertEqual(jaccard(token_set("a b"), token_set("c d")), 0.0)

    def test_the_threshold_matches_phase_7_4(self) -> None:
        self.assertEqual(NEAR_DUPLICATE_THRESHOLD, 0.8)

    def test_the_finding_kinds_are_declared(self) -> None:
        self.assertEqual(
            set(FINDING_KINDS),
            {EXACT_OVERLAP, NEAR_DUPLICATE, DEVELOPMENT_OVERLAP, LABEL_INCOMPLETE},
        )

    def test_the_audit_report_is_json_serializable(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)

    def test_the_audit_artifact_is_written(self) -> None:
        self.assertTrue(AUDIT_PATH.is_file())
        payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], FAIL)
        self.assertIn("nothing is repaired here", payload["note"])


class DatasetArtifactTests(unittest.TestCase):
    def test_the_dataset_file_exists(self) -> None:
        self.assertTrue(DATASET_PATH.is_file())

    def test_the_file_matches_the_cases(self) -> None:
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["case_count"], len(CASES))
        self.assertEqual(len(payload["cases"]), len(CASES))

    def test_the_file_declares_single_annotator_status(self) -> None:
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            payload["annotation"], "single-annotator engineering validation only"
        )

    def test_the_payload_is_json_serializable(self) -> None:
        json.dumps(dataset_payload(), sort_keys=True)

    def test_writing_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dataset.json"
            write_dataset(target)
            first = target.read_text(encoding="utf-8")
            write_dataset(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_the_decontaminated_dataset_is_written(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "v2.json"
            write_decontaminated(target)
            payload = json.loads(target.read_text(encoding="utf-8"))

            self.assertEqual(payload["version"], "v2")
            self.assertEqual(payload["case_count"], len(CASES) - 1)
            self.assertEqual(payload["excluded_case_ids"], list(CONTAMINATED_CASE_IDS))


class FreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frozen = load_freeze()

    def test_the_freeze_file_exists(self) -> None:
        self.assertTrue(FREEZE_PATH.is_file())

    def test_the_freeze_carries_all_six_components(self) -> None:
        for key in (*VERIFIED_KEYS, "timestamp", "benchmark", "case_count"):
            self.assertIn(key, self.frozen, key)

    def test_the_hashes_are_sha256_digests(self) -> None:
        for key in VERIFIED_KEYS:
            self.assertEqual(len(self.frozen[key]), 64, key)
            int(self.frozen[key], 16)

    def test_the_freeze_records_the_benchmark_and_size(self) -> None:
        self.assertEqual(self.frozen["benchmark"], f"{BENCHMARK_ID}/v1")
        self.assertEqual(self.frozen["case_count"], len(CASES))

    def test_the_freeze_no_longer_matches_and_that_is_the_point(self) -> None:
        """Taken before the Phase 8.6 run, verified after it, and now superseded.

        Phase 8.7 changed the pattern set on purpose, so this freeze must fail
        its own verification: a freeze that survived a repair would mean the
        repair had not touched the pipeline. Exactly one component may have
        moved, and it is the one the repair is allowed to move.
        """

        result = verify_freeze()

        self.assertFalse(result.matches)
        self.assertEqual(result.mismatches, ("evaluator_hash",))

    def test_the_repair_did_not_touch_the_labels_or_the_decision_policy(self) -> None:
        """What the superseded freeze still proves, read the other way round.

        The taxonomy and the decision policy - the rule table, the actions and
        the relation-to-category map - are byte-identical to what Phase 8.6
        froze. The benchmark hash is checked by the Phase 8.7 freeze, which
        asserts it equals the hash recorded here.
        """

        frozen = self.frozen

        self.assertEqual(frozen["taxonomy_hash"], taxonomy_hash())
        self.assertEqual(frozen["decision_policy_hash"], decision_policy_hash())
        self.assertEqual(frozen["benchmark_hash"], dataset_hash())
        self.assertEqual(frozen["configuration_hash"], configuration_hash())
        self.assertNotEqual(frozen["evaluator_hash"], evaluator_hash())

    def test_the_freeze_was_taken_before_the_predictions(self) -> None:
        from risk_evaluation.v3_validation.evaluation import PREDICTION_PATH

        self.assertTrue(PREDICTION_PATH.is_file())
        self.assertLess(
            FREEZE_PATH.stat().st_mtime, PREDICTION_PATH.stat().st_mtime
        )

    def test_the_components_are_mutually_distinct(self) -> None:
        digests = {
            evaluator_hash(),
            taxonomy_hash(),
            decision_policy_hash(),
            dataset_hash(),
            configuration_hash(),
        }

        self.assertEqual(len(digests), 5)

    def test_a_tampered_hash_is_detected(self) -> None:
        import tempfile

        tampered = dict(self.frozen)
        tampered["evaluator_hash"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_freeze(target)

        self.assertFalse(result.matches)
        self.assertEqual(result.mismatches, ("evaluator_hash",))

    def test_the_timestamp_is_excluded_from_verification(self) -> None:
        import tempfile

        tampered = dict(self.frozen)
        tampered["timestamp"] = "1999-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            # The freeze no longer matches the tree, for the evaluator hash. The
            # timestamp still must not be one of the reasons.
            self.assertNotIn("timestamp", verify_freeze(target).mismatches)

    def test_a_missing_freeze_is_reported(self) -> None:
        import tempfile

        with self.assertRaises(FreezeError):
            load_freeze(Path(tempfile.gettempdir()) / "no-such-freeze-v3.json")

    def test_building_a_freeze_twice_gives_the_same_hashes(self) -> None:
        """Re-taking a freeze with nothing changed must not look like a change."""

        first = {k: v for k, v in build_freeze().items() if k != "timestamp"}
        second = {k: v for k, v in build_freeze().items() if k != "timestamp"}

        self.assertEqual(first, second)

    def test_the_freeze_is_json_serializable(self) -> None:
        json.dumps(self.frozen, sort_keys=True)


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("risk_evaluation_v3_validation", top_level)


if __name__ == "__main__":
    unittest.main()
