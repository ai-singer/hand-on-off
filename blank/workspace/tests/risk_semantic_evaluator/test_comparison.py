from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.benchmark import (
    ADVERSARIAL,
    BENCHMARK_CASES,
    KEYWORD,
    PARAPHRASE,
    SAFE,
    BenchmarkCase,
    compare_evaluators,
    run_benchmark,
)
from risk_evaluation.evaluator import KeywordRiskEvaluator
from risk_evaluation.model import RiskEvaluationResult
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

BASELINE = "keyword-xiaolin-finance-v1"
CANDIDATE = "semantic-intent-v0"

#: Recorded in docs/PHASE_7_2_SEMANTIC_RISK_EVALUATOR_REPORT.md. If either
#: evaluator changes, update that report in the same change.
DOCUMENTED = {
    (BASELINE, "keyword_recall"): 1.0,
    (BASELINE, "paraphrase_recall"): 0.05,
    (BASELINE, "false_positive_rate"): 0.0,
    (BASELINE, "adversarial_accuracy"): 0.4,
    (CANDIDATE, "keyword_recall"): 1.0,
    (CANDIDATE, "paraphrase_recall"): 0.95,
    (CANDIDATE, "false_positive_rate"): 0.0,
    (CANDIDATE, "adversarial_accuracy"): 0.9,
}

#: Production modules that must not import the risk evaluation framework.
ISOLATED_DIRECTORIES = (
    "runtime",
    "workflows",
    "evaluation",
    "distillation_core",
    "plugins",
    "production",
    "core",
    "config",
    "schema_validation",
    "security",
    "artifact",
)


class BenchmarkExecutionTests(unittest.TestCase):
    def test_run_benchmark_accepts_a_custom_evaluator(self) -> None:
        report = run_benchmark(SemanticRiskEvaluator())

        self.assertEqual(report.evaluator, CANDIDATE)
        self.assertEqual(len(report.outcomes), 50)

    def test_run_benchmark_accepts_a_custom_case_list(self) -> None:
        cases = (
            BenchmarkCase("x-1", KEYWORD, "Buy now for a guaranteed return.", ("investment_advice",)),
            BenchmarkCase("x-2", SAFE, "The income statement shows margin."),
        )

        report = run_benchmark(KeywordRiskEvaluator(), cases)

        self.assertEqual(len(report.outcomes), 2)
        self.assertEqual(report.keyword_recall, 1.0)
        self.assertEqual(report.false_positive_rate, 0.0)

    def test_flagged_and_matched_differ_for_safe_cases(self) -> None:
        report = run_benchmark()

        disclaimed = next(o for o in report.outcomes if o.case.case_id == "ad-01")

        self.assertTrue(disclaimed.flagged)
        self.assertFalse(disclaimed.matched)
        self.assertFalse(disclaimed.correct)


class ComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.comparison = compare_evaluators()

    def test_comparison_scores_both_evaluators(self) -> None:
        self.assertEqual(set(self.comparison.reports), {BASELINE, CANDIDATE})
        for report in self.comparison.reports.values():
            self.assertEqual(len(report.outcomes), 50)

    def test_measured_metrics_match_the_report(self) -> None:
        for (evaluator, metric), expected in DOCUMENTED.items():
            with self.subTest(evaluator=evaluator, metric=metric):
                self.assertEqual(self.comparison.metric(evaluator, metric), expected)

    def test_semantic_evaluator_improves_paraphrase_recall(self) -> None:
        delta = self.comparison.delta(
            "paraphrase_recall", baseline=BASELINE, candidate=CANDIDATE
        )

        self.assertGreater(delta, 0.5)
        self.assertEqual(delta, 0.9)

    def test_semantic_evaluator_does_not_regress_keyword_recall(self) -> None:
        delta = self.comparison.delta(
            "keyword_recall", baseline=BASELINE, candidate=CANDIDATE
        )

        self.assertEqual(delta, 0.0)

    def test_semantic_evaluator_does_not_add_false_positives(self) -> None:
        candidate = self.comparison.reports[CANDIDATE]
        baseline = self.comparison.reports[BASELINE]

        self.assertEqual(candidate.false_positive_rate, 0.0)
        self.assertLessEqual(
            len(candidate.false_positives), len(baseline.false_positives)
        )
        self.assertLessEqual(
            len(candidate.adversarial_false_positives),
            len(baseline.adversarial_false_positives),
        )

    def test_case_table_reports_both_evaluators_per_case(self) -> None:
        rows = self.comparison.case_table(baseline=BASELINE, candidate=CANDIDATE)

        self.assertEqual(len(rows), len(BENCHMARK_CASES))
        for row in rows:
            self.assertEqual(
                set(row),
                {
                    "case_id",
                    "kind",
                    "text",
                    "expected",
                    "baseline",
                    "candidate",
                    "candidate_correct",
                },
            )
            self.assertIn("detected", row["baseline"])
            self.assertIn("detected", row["candidate"])

    def test_case_table_covers_every_kind(self) -> None:
        rows = self.comparison.case_table(baseline=BASELINE, candidate=CANDIDATE)
        kinds = {row["kind"] for row in rows}

        self.assertEqual(kinds, {KEYWORD, SAFE, PARAPHRASE, ADVERSARIAL})

    def test_comparison_serializes(self) -> None:
        payload = json.loads(
            json.dumps(
                {name: report.as_dict() for name, report in self.comparison.reports.items()}
            )
        )

        self.assertEqual(payload[CANDIDATE]["metrics"]["paraphrase_recall"], 0.95)
        self.assertEqual(sum(len(r["outcomes"]) for r in payload.values()), 100)

    def test_render_mentions_the_capability_boundary(self) -> None:
        rendered = self.comparison.render(baseline=BASELINE, candidate=CANDIDATE)

        self.assertIn("paraphrase_recall", rendered)
        self.assertIn("keyword_recall", rendered)


class ConfidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluator()

    def test_confidence_is_higher_when_a_booster_fires(self) -> None:
        minimal = self.evaluator.evaluate_text("This opportunity cannot fail.")
        boosted = self.evaluator.evaluate_text(
            "This fund cannot fail as a way to grow capital."
        )

        self.assertEqual(minimal[0].confidence, 0.6)
        self.assertEqual(boosted[0].confidence, 0.7)

    def test_confidence_is_capped(self) -> None:
        results = self.evaluator.evaluate_text(
            "You should buy this stock, sell this share, move your money, "
            "add to your portfolio and allocate your savings to this fund."
        )

        self.assertTrue(results)
        for result in results:
            self.assertLessEqual(result.confidence, 0.9)
            self.assertGreaterEqual(result.confidence, 0.0)

    def test_results_round_trip_through_json(self) -> None:
        results = self.evaluator.evaluate_text(
            "You should buy this stock today.", source_ids=("s-1",)
        )

        restored = [
            RiskEvaluationResult.from_dict(item)
            for item in json.loads(json.dumps([r.as_dict() for r in results]))
        ]

        self.assertEqual(restored, list(results))
        self.assertEqual(restored[0].source_ids, ("s-1",))
        self.assertEqual(restored[0].evaluator, CANDIDATE)

    def test_results_project_into_the_risk_constraint_shape(self) -> None:
        results = self.evaluator.evaluate_text("This opportunity cannot fail.")

        constraint = results[0].to_risk_constraint()

        self.assertEqual(
            set(constraint),
            {"rule_id", "category", "severity", "action", "message", "source_ids"},
        )
        self.assertTrue(constraint["rule_id"].startswith(CANDIDATE))


class ProductionIsolationTests(unittest.TestCase):
    """Step 6: the prototype must not be wired into production."""

    def test_no_production_module_imports_the_framework(self) -> None:
        offenders: list[str] = []
        for directory in ISOLATED_DIRECTORIES:
            root = WORKSPACE_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if "risk_evaluation" in text:
                    offenders.append(str(path.relative_to(WORKSPACE_ROOT)))

        self.assertEqual(offenders, [])

    def test_the_plugin_still_produces_its_own_risk_constraints(self) -> None:
        """Production detection is unchanged: the plugin, not this framework."""

        from core import RawSource, SourceType, load_plugin
        from distillation_core import DistillationEngine

        plugin = load_plugin("plugins.xiaolin_finance")
        artifact = DistillationEngine(plugin).distill(
            [RawSource(source_id="s-1", source_type=SourceType.DOCUMENT, content="Buy now for a guaranteed return.")]
        )

        self.assertTrue(artifact["risk_constraints"])
        self.assertTrue(
            all("evaluator" not in item for item in artifact["risk_constraints"])
        )


if __name__ == "__main__":
    unittest.main()
