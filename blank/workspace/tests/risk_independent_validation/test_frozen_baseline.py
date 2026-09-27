from __future__ import annotations

import copy
import json
import unittest

from risk_evaluation.freeze import (
    FREEZE_PATH,
    build_baseline,
    decision_surface_hash,
    keyword_evaluator_version,
    load_freeze,
    semantic_decision_surface,
    verify_freeze,
)


class FrozenBaselineContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frozen = load_freeze()

    def test_freeze_file_exists_and_is_valid_json(self) -> None:
        self.assertTrue(FREEZE_PATH.is_file())
        self.assertIsInstance(self.frozen, dict)

    def test_freeze_records_every_required_field(self) -> None:
        for key in (
            "freeze_schema_version",
            "semantic_evaluator",
            "keyword_evaluator",
            "semantic_patterns_hash",
            "development_benchmark",
            "independent_benchmark",
            "frozen_before_independent_benchmark",
        ):
            self.assertIn(key, self.frozen, key)

    def test_freeze_names_both_evaluators(self) -> None:
        self.assertEqual(self.frozen["semantic_evaluator"], "semantic-intent-v0")
        self.assertEqual(
            self.frozen["keyword_evaluator"], "keyword-xiaolin-finance-v1"
        )
        self.assertEqual(self.frozen["keyword_evaluator"], keyword_evaluator_version())

    def test_freeze_declares_benchmark_versions(self) -> None:
        self.assertIn("50", self.frozen["development_benchmark"])
        self.assertIn("100", self.frozen["independent_benchmark"])

    def test_freeze_declares_it_preceded_the_independent_benchmark(self) -> None:
        self.assertIs(self.frozen["frozen_before_independent_benchmark"], True)

    def test_freeze_records_the_decision_surface_shape(self) -> None:
        self.assertEqual(
            self.frozen["semantic_signal_classes"],
            sorted(semantic_decision_surface()["signal_patterns"]),
        )
        self.assertEqual(
            sorted(self.frozen["semantic_intent_categories"]),
            sorted(
                pattern["category"]
                for pattern in semantic_decision_surface()["intent_patterns"]
            ),
        )

    def test_hash_is_a_sha256_hex_digest(self) -> None:
        digest = self.frozen["semantic_patterns_hash"]

        self.assertEqual(len(digest), 64)
        int(digest, 16)


class FreezeIntegrityTests(unittest.TestCase):
    """The freeze is what makes the validation run trustworthy."""

    def test_current_evaluator_matches_the_frozen_hash(self) -> None:
        status = verify_freeze()

        self.assertTrue(status.matches, status.render())
        self.assertEqual(status.frozen_hash, status.current_hash)

    def test_a_changed_pattern_changes_the_hash(self) -> None:
        surface = semantic_decision_surface()
        modified = copy.deepcopy(surface)
        modified["signal_patterns"]["directive"].append(r"\bpatch-me\b")

        self.assertNotEqual(decision_surface_hash(modified), decision_surface_hash(surface))

    def test_a_changed_intent_conjunction_changes_the_hash(self) -> None:
        surface = semantic_decision_surface()
        modified = copy.deepcopy(surface)
        modified["intent_patterns"][0]["required"] = ["directive"]

        self.assertNotEqual(decision_surface_hash(modified), decision_surface_hash(surface))

    def test_a_changed_negation_window_changes_the_hash(self) -> None:
        surface = semantic_decision_surface()
        modified = copy.deepcopy(surface)
        modified["negation_window"] = surface["negation_window"] + 1

        self.assertNotEqual(decision_surface_hash(modified), decision_surface_hash(surface))

    def test_hash_is_stable_across_calls(self) -> None:
        self.assertEqual(decision_surface_hash(), decision_surface_hash())

    def test_hash_ignores_key_order(self) -> None:
        surface = semantic_decision_surface()
        reordered = dict(reversed(list(surface.items())))

        self.assertEqual(decision_surface_hash(surface), decision_surface_hash(reordered))

    def test_rebuilt_baseline_matches_the_stored_one(self) -> None:
        stored = load_freeze()
        rebuilt = build_baseline()

        self.assertEqual(stored, rebuilt)

    def test_baseline_serializes_as_json(self) -> None:
        payload = json.dumps(build_baseline(), sort_keys=True)

        self.assertIn("semantic_patterns_hash", json.loads(payload))


if __name__ == "__main__":
    unittest.main()
