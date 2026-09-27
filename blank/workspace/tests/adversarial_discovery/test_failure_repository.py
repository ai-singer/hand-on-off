from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.adversarial.case import AdversarialCase
from risk_evaluation.adversarial.evaluator_bridge import evaluate_case
from risk_evaluation.adversarial.failure_repository import (
    DEFAULT_CREATED_AT,
    FAILURE_ROOT,
    FailureRecord,
    FailureRepository,
    FailureRepositoryError,
    failure_id_for,
    record_from,
    regression_candidates,
)
from risk_evaluation.adversarial.strategies import AttackStrategy


def _miss_result(text: str = "This return is guaranteed.", case_id: str = "ADV-DIR-06"):
    case = AdversarialCase(
        case_id=case_id,
        text=text,
        target_category="financial_guarantee",
        attack_strategy=AttackStrategy.DIRECT_STATEMENT,
        expected_detection=True,
        metadata={"rationale": "synthetic", "expectation_basis": "guide v2 section 7"},
    )
    return evaluate_case(case)


def _hit_result():
    case = AdversarialCase(
        case_id="ADV-DIR-07",
        text="This fund cannot lose money.",
        target_category="financial_guarantee",
        attack_strategy=AttackStrategy.DIRECT_STATEMENT,
        expected_detection=True,
        metadata={"rationale": "synthetic"},
    )
    return evaluate_case(case)


class FailureIdTests(unittest.TestCase):
    def test_ids_are_zero_padded_and_prefixed(self) -> None:
        self.assertEqual(failure_id_for(1), "ADV-F001")
        self.assertEqual(failure_id_for(29), "ADV-F029")

    def test_ids_sort_as_text(self) -> None:
        ids = [failure_id_for(n) for n in range(1, 12)]

        self.assertEqual(ids, sorted(ids))


class RecordShapeTests(unittest.TestCase):
    """Requirement 5: the failure repository records the documented shape."""

    def setUp(self) -> None:
        self.record = record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)

    def test_the_documented_keys_are_present(self) -> None:
        payload = self.record.as_dict()

        for key in (
            "id",
            "text",
            "strategy",
            "expected",
            "actual",
            "severity",
            "created_at",
        ):
            self.assertIn(key, payload)

    def test_the_record_is_traceable_back_to_the_case(self) -> None:
        payload = self.record.as_dict()

        self.assertEqual(payload["case_id"], "ADV-DIR-06")
        self.assertIn("evidence", payload)

    def test_expected_names_the_missed_category(self) -> None:
        self.assertEqual(self.record.expected, "financial_guarantee")

    def test_actual_records_that_nothing_was_reported(self) -> None:
        self.assertEqual(self.record.actual, "none")

    def test_severity_follows_the_target_category(self) -> None:
        self.assertEqual(self.record.severity, "high")

    def test_strategy_is_the_attack_strategy(self) -> None:
        self.assertEqual(self.record.strategy, "direct_statement")

    def test_payload_is_json_serializable(self) -> None:
        json.dumps(self.record.as_dict(), sort_keys=True)

    def test_file_name_derives_from_the_id(self) -> None:
        self.assertEqual(self.record.path_name, "ADV-F001.json")

    def test_only_a_miss_can_become_a_failure(self) -> None:
        with self.assertRaises(FailureRepositoryError):
            record_from(_hit_result(), index=1, created_at=DEFAULT_CREATED_AT)

    def test_normalised_text_is_exposed_for_deduplication(self) -> None:
        self.assertEqual(self.record.normalized_text, "this return is guaranteed")


class RepositoryWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "failures"
        self.repository = FailureRepository(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_an_absent_repository_loads_empty(self) -> None:
        self.assertEqual(self.repository.load(), ())

    def test_write_then_load_round_trips(self) -> None:
        record = record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)
        written = self.repository.write([record])

        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].is_file())

        loaded = self.repository.load()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].as_dict(), record.as_dict())

    def test_one_file_per_failure(self) -> None:
        records = [
            record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT),
            record_from(
                _miss_result(text="Returns are guaranteed.", case_id="ADV-PAR-11"),
                index=2,
                created_at=DEFAULT_CREATED_AT,
            ),
        ]
        self.repository.write(records)

        self.assertEqual(
            sorted(path.name for path in self.root.glob("*.json")),
            ["ADV-F001.json", "ADV-F002.json"],
        )

    def test_load_is_ordered_by_id(self) -> None:
        records = [
            record_from(_miss_result(), index=2, created_at=DEFAULT_CREATED_AT),
            record_from(
                _miss_result(text="Returns are guaranteed.", case_id="ADV-PAR-11"),
                index=1,
                created_at=DEFAULT_CREATED_AT,
            ),
        ]
        self.repository.write(records)

        self.assertEqual(
            [record.failure_id for record in self.repository.load()],
            ["ADV-F001", "ADV-F002"],
        )

    def test_prune_removes_records_not_in_the_new_set(self) -> None:
        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )
        self.repository.write(
            [
                record_from(
                    _miss_result(text="Returns are guaranteed.", case_id="ADV-PAR-11"),
                    index=1,
                    created_at=DEFAULT_CREATED_AT,
                )
            ],
            prune=True,
        )

        self.assertEqual(len(self.repository.load()), 1)

    def test_without_prune_older_records_survive(self) -> None:
        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )
        self.repository.write(
            [
                record_from(
                    _miss_result(text="Returns are guaranteed.", case_id="ADV-PAR-11"),
                    index=2,
                    created_at=DEFAULT_CREATED_AT,
                )
            ]
        )

        self.assertEqual(len(self.repository.load()), 2)

    def test_texts_and_case_ids_are_enumerable(self) -> None:
        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )

        self.assertEqual(
            self.repository.texts(), frozenset({"this return is guaranteed"})
        )
        self.assertEqual(self.repository.existing_case_ids(), frozenset({"ADV-DIR-06"}))

    def test_counts_group_by_strategy(self) -> None:
        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )

        self.assertEqual(self.repository.counts(), {"direct_statement": 1})

    def test_the_committed_repository_is_loadable(self) -> None:
        """The Phase 8.1 run persisted its misses and they still read back."""

        records = FailureRepository(FAILURE_ROOT).load()

        self.assertTrue(records)
        for record in records:
            self.assertTrue(record.failure_id.startswith("ADV-F"))
            self.assertTrue(record.text.strip())


class CollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repository = FailureRepository(Path(self._tmp.name) / "failures")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_only_misses_are_collected(self) -> None:
        records = self.repository.collect([_hit_result(), _miss_result()])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].case_id, "ADV-DIR-06")

    def test_ids_are_assigned_in_sequence(self) -> None:
        records = self.repository.collect(
            [
                _miss_result(),
                _miss_result(text="Returns are guaranteed.", case_id="ADV-PAR-11"),
            ]
        )

        self.assertEqual(
            [record.failure_id for record in records], ["ADV-F001", "ADV-F002"]
        )

    def test_an_already_recorded_case_is_not_collected_again(self) -> None:
        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )
        again = self.repository.collect([_miss_result()])

        self.assertEqual(again, ())

    def test_a_new_case_continues_the_numbering(self) -> None:
        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )
        records = self.repository.collect(
            [_miss_result(text="Returns are guaranteed.", case_id="ADV-PAR-11")]
        )

        self.assertEqual(records[0].failure_id, "ADV-F002")

    def test_duplicate_texts_under_different_ids_are_suppressed(self) -> None:
        """Requirement 6 applied to the repository, not just the generator."""

        self.repository.write(
            [record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT)]
        )
        records = self.repository.collect(
            [_miss_result(text="this  RETURN is guaranteed", case_id="ADV-PAR-99")]
        )

        self.assertEqual(records, ())

    def test_skip_recorded_can_be_disabled_for_a_rebuild(self) -> None:
        records = self.repository.collect([_miss_result()], skip_recorded=False)

        self.assertEqual(records[0].failure_id, "ADV-F001")


class CandidateExportTests(unittest.TestCase):
    """Requirement 7: misses become regression benchmark candidates."""

    def setUp(self) -> None:
        self.records = (
            record_from(_miss_result(), index=1, created_at=DEFAULT_CREATED_AT),
        )

    def test_each_failure_yields_one_candidate(self) -> None:
        self.assertEqual(len(regression_candidates(self.records)), 1)

    def test_a_candidate_carries_the_missed_expectation(self) -> None:
        candidate = regression_candidates(self.records)[0]

        self.assertEqual(candidate["expected_categories"], ["financial_guarantee"])

    def test_a_candidate_is_marked_as_a_candidate(self) -> None:
        candidate = regression_candidates(self.records)[0]

        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["discovered_by"], "phase-8.1-adversarial-discovery")

    def test_a_candidate_keeps_the_case_and_strategy(self) -> None:
        candidate = regression_candidates(self.records)[0]

        self.assertEqual(candidate["origin_case_id"], "ADV-DIR-06")
        self.assertEqual(candidate["attack_strategy"], "direct_statement")

    def test_a_candidate_is_a_valid_benchmark_record(self) -> None:
        candidate = regression_candidates(self.records)[0]

        for key in ("id", "text", "expected_categories", "group"):
            self.assertIn(key, candidate)

    def test_candidates_are_json_serializable(self) -> None:
        json.dumps(list(regression_candidates(self.records)), sort_keys=True)

    def test_no_failures_means_no_candidates(self) -> None:
        self.assertEqual(regression_candidates(()), ())

    def test_the_committed_candidate_file_matches_the_repository(self) -> None:
        from risk_evaluation.adversarial.failure_repository import CANDIDATES_PATH

        self.assertTrue(CANDIDATES_PATH.is_file())
        payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
        records = FailureRepository(FAILURE_ROOT).load()

        self.assertEqual(payload["count"], len(records))
        self.assertEqual(len(payload["candidates"]), len(records))


if __name__ == "__main__":
    unittest.main()
