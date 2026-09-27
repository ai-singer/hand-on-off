from __future__ import annotations

import json
import unittest

from risk_evaluation.benchmark_audit import (
    DEVELOPMENT_OVERLAP,
    EXACT_DUPLICATE,
    FAIL,
    FINDING_KINDS,
    NEAR_DUPLICATE,
    NEAR_DUPLICATE_THRESHOLD,
    PASS,
    audit_all,
    audit_benchmark,
    audit_records,
    development_texts,
    jaccard,
    normalize_text,
    token_set,
)
from risk_evaluation.benchmark_registry import BenchmarkRegistry


def _record(case_id: str, text: str, expected=("investment_advice",)) -> dict:
    return {
        "id": case_id,
        "text": text,
        "expected_categories": list(expected),
        "risk_level": "block" if expected else "none",
        "annotation_reason": "synthetic",
        "source_type": "synthetic",
        "created_after_evaluator_freeze": True,
        "group": "risk" if expected else "safe",
    }


class NormalizationTests(unittest.TestCase):
    def test_case_and_punctuation_are_ignored(self) -> None:
        self.assertEqual(
            normalize_text("Buy this stock!"), normalize_text("buy  this   stock")
        )

    def test_chinese_text_is_preserved(self) -> None:
        self.assertEqual(normalize_text("立即买入这只股票。"), "立即买入这只股票")

    def test_token_set_uses_normalized_tokens(self) -> None:
        self.assertEqual(token_set("Buy THIS stock."), frozenset({"buy", "this", "stock"}))

    def test_jaccard_bounds(self) -> None:
        left = frozenset({"a", "b"})
        self.assertEqual(jaccard(left, left), 1.0)
        self.assertEqual(jaccard(left, frozenset({"c"})), 0.0)
        self.assertEqual(jaccard(frozenset(), frozenset()), 1.0)

    def test_jaccard_partial_overlap(self) -> None:
        self.assertEqual(jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})), 0.3333)


class RegisteredBenchmarkAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reports = audit_all()

    def test_v1_fails_the_audit(self) -> None:
        report = self.reports["semantic/v1"]

        self.assertTrue(report.contaminated)
        self.assertEqual(report.status, FAIL)

    def test_v1_findings_are_development_overlap(self) -> None:
        report = self.reports["semantic/v1"]
        counts = report.counts()

        self.assertEqual(counts[DEVELOPMENT_OVERLAP], 38)
        self.assertEqual(report.affected_case_ids.__len__(), 38)
        self.assertEqual(counts[EXACT_DUPLICATE], 0)

    def test_v2_passes_the_audit(self) -> None:
        report = self.reports["semantic/v2"]

        self.assertFalse(report.contaminated)
        self.assertEqual(report.status, PASS)
        self.assertEqual(report.findings, ())

    def test_report_render_states_the_status(self) -> None:
        self.assertIn("FAIL", self.reports["semantic/v1"].render())
        self.assertIn("PASS", self.reports["semantic/v2"].render())

    def test_report_serializes(self) -> None:
        payload = json.loads(json.dumps(self.reports["semantic/v1"].as_dict()))

        self.assertEqual(payload["status"], FAIL)
        self.assertEqual(payload["affected_case_count"], 38)
        self.assertEqual(len(payload["findings"]), 38)

    def test_audit_records_the_dataset_hash(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get("semantic", "v1")

        self.assertEqual(
            self.reports["semantic/v1"].dataset_hash, record.dataset_hash
        )

    def test_development_texts_are_non_empty(self) -> None:
        self.assertGreater(len(development_texts()), 40)

    def test_audit_benchmark_helper_matches_audit_all(self) -> None:
        registry = BenchmarkRegistry()
        direct = audit_benchmark(registry.get("semantic", "v2"), registry)

        self.assertEqual(direct.as_dict(), self.reports["semantic/v2"].as_dict())


class SyntheticDetectionTests(unittest.TestCase):
    """Each detector is exercised against input built to trigger it."""

    def test_exact_duplicate_within_a_benchmark(self) -> None:
        records = [
            _record("a", "Buy this stock now."),
            _record("b", "buy  this stock now"),
            _record("c", "The income statement shows margin."),
        ]

        report = audit_records(records, benchmark_id="x", version="v1", development=())

        kinds = {item.kind for item in report.findings}
        self.assertIn(EXACT_DUPLICATE, kinds)
        self.assertEqual(report.status, FAIL)
        self.assertEqual(
            next(i for i in report.findings if i.kind == EXACT_DUPLICATE).case_ids,
            ("a", "b"),
        )

    def test_near_duplicate_within_a_benchmark(self) -> None:
        records = [
            _record("a", "You should buy this stock today because it is cheap."),
            _record("b", "You should buy this stock today because it is very cheap."),
        ]

        report = audit_records(records, benchmark_id="x", version="v1", development=())

        near = [item for item in report.findings if item.kind == NEAR_DUPLICATE]
        self.assertTrue(near)
        self.assertGreaterEqual(near[0].similarity, NEAR_DUPLICATE_THRESHOLD)
        self.assertEqual(near[0].case_ids, ("a", "b"))

    def test_distinct_cases_are_not_flagged(self) -> None:
        records = [
            _record("a", "You should buy this stock today.", ("investment_advice",)),
            _record("b", "The balance sheet lists assets.", ()),
            _record("c", "据说不具名消息人士透露，公司将重组。", ("unverified_information",)),
        ]

        report = audit_records(records, benchmark_id="x", version="v1", development=())

        self.assertFalse(report.contaminated)
        self.assertEqual(report.status, PASS)

    def test_development_overlap_is_detected(self) -> None:
        records = [_record("a", "Buy now for a guaranteed return.")]

        report = audit_records(
            records,
            benchmark_id="x",
            version="v1",
            development=["buy now for a guaranteed return"],
        )

        self.assertEqual(report.findings[0].kind, DEVELOPMENT_OVERLAP)
        self.assertEqual(report.findings[0].case_ids, ("a",))

    def test_overlap_check_is_optional(self) -> None:
        records = [_record("a", "Buy now for a guaranteed return.")]

        report = audit_records(
            records, benchmark_id="x", version="v1", development=()
        )

        self.assertFalse(report.contaminated)

    def test_counts_cover_every_finding_kind(self) -> None:
        report = audit_records([], benchmark_id="x", version="v1", development=())

        self.assertEqual(set(report.counts()), set(FINDING_KINDS))

    def test_threshold_is_a_probability(self) -> None:
        self.assertGreater(NEAR_DUPLICATE_THRESHOLD, 0.0)
        self.assertLess(NEAR_DUPLICATE_THRESHOLD, 1.0)


if __name__ == "__main__":
    unittest.main()
