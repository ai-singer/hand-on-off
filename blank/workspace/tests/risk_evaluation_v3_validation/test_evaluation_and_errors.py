"""Step 5 to Step 8: blind evaluation, metrics, claims and error analysis."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3.pipeline import RiskEvaluationPipeline
from risk_evaluation.v3_validation.cases import CASES, blind_records, decontaminated_cases
from risk_evaluation.v3_validation.claims import (
    NOT_SUPPORTED,
    PARTIALLY_SUPPORTED,
    SUPPORTED,
    guarantee_form_outcomes,
    verify_attribution,
    verify_claims,
    verify_decision,
    verify_intent,
)
from risk_evaluation.v3_validation.errors import (
    ANNOTATION_AMBIGUITY,
    ATTRIBUTION_ERROR,
    CATEGORIES,
    DECISION_POLICY_ERROR,
    FALLBACK_PROPAGATION,
    INFLECTED_VERB,
    INTENT_DETECTION_ERROR,
    LEXICAL_GAP,
    MECHANISMS,
    NOVEL_REJECTION_CUE,
    NOVEL_SOURCE_NOUN,
    UNKNOWN_LANGUAGE_PATTERN,
    analyse,
    annotation_ambiguity,
    diagnose,
)
from risk_evaluation.v3_validation.evaluation import (
    METRICS_PATH,
    PREDICTION_PATH,
    EvaluationError,
    join,
    predict,
    score,
    write_metrics,
    write_predictions,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class BlindPredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.predictions = predict(blind_records())
        cls.metrics = score(cls.predictions)

    def test_every_case_is_predicted(self) -> None:
        self.assertEqual(len(self.predictions), len(CASES))

    def test_a_record_without_an_id_is_rejected(self) -> None:
        with self.assertRaises(EvaluationError):
            predict([{"text": "something"}])

    def test_a_record_without_text_is_rejected(self) -> None:
        with self.assertRaises(EvaluationError):
            predict([{"id": "X-1"}])

    def test_extra_fields_are_ignored(self) -> None:
        """A label passed in by accident cannot influence the prediction."""

        honest = predict([{"id": "IV-001", "text": CASES[0].text}])
        noisy = predict(
            [{"id": "IV-001", "text": CASES[0].text, "categories": ["nonsense"]}]
        )

        self.assertEqual(honest[0].categories, noisy[0].categories)

    def test_scoring_a_missing_prediction_raises(self) -> None:
        with self.assertRaises(EvaluationError):
            join(self.predictions[:-1])

    def test_every_prediction_carries_a_trace(self) -> None:
        for item in self.predictions:
            self.assertTrue(item.trace)

    def test_the_baseline_is_kept_alongside(self) -> None:
        for item in self.predictions:
            self.assertIsInstance(item.baseline, tuple)

    def test_prediction_is_deterministic(self) -> None:
        again = predict(blind_records())

        self.assertEqual(
            [i.categories for i in again], [i.categories for i in self.predictions]
        )

    def test_the_prediction_artifact_is_written(self) -> None:
        self.assertTrue(PREDICTION_PATH.is_file())
        payload = json.loads(PREDICTION_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["mode"], "blind")
        self.assertEqual(len(payload["predictions"]), len(CASES))

    def test_the_artifact_does_not_contain_labels(self) -> None:
        payload = json.loads(PREDICTION_PATH.read_text(encoding="utf-8"))

        self.assertNotIn("annotation_reason", json.dumps(payload["predictions"]))

    def test_writing_predictions_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "p.json"
            write_predictions(target, self.predictions)
            first = target.read_text(encoding="utf-8")
            write_predictions(target, self.predictions)

            self.assertEqual(first, target.read_text(encoding="utf-8"))


class MetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = score(predict(blind_records()))

    def test_every_case_is_scored(self) -> None:
        self.assertEqual(len(self.metrics.outcomes), len(CASES))

    def test_attribution_metrics_are_pinned(self) -> None:
        # Phase 8.6 measured speaker 0.7400 and stance 0.7900. Phase 8.7 typed the
        # source a statement is reported through, which is the axis Phase 8.6
        # found the layer could not answer: `The regulator said ...` and `Traders
        # say ...` both came back `unknown`.
        attribution = self.metrics.attribution

        self.assertEqual(attribution.split_accuracy, 1.0)
        self.assertEqual(attribution.speaker_accuracy, 0.99)
        self.assertEqual(attribution.stance_accuracy, 0.98)

    def test_intent_metrics_are_pinned(self) -> None:
        # Phase 8.6 measured 27/40 (0.6750); Phase 8.7 brought it to 35/40 (0.8750).
        # Phase 8.8's modal layer added IV-098, a hedged prediction
        # (`Perhaps the fund will outperform its benchmark.`) that no Phase 8.4
        # frame could reach. PREDICTION and ADVICE are still the two relations with
        # misses, listed as open in the Phase 8.8 report.
        intent = self.metrics.intent

        self.assertEqual(intent.expected_total, 40)
        self.assertEqual(intent.recalled, 36)
        self.assertEqual(intent.recall, 0.9)
        self.assertGreater(intent.precision, 0.0)
        self.assertLessEqual(intent.precision, 1.0)

    def test_decision_metrics_are_pinned(self) -> None:
        # Phase 8.6 measured tp/fp/fn/tn 31/9/6/54, precision 0.7750,
        # recall 0.8378, fpr 0.1429, fnr 0.1622. Phase 8.7 took it to
        # 36/2/1/61. Phase 8.8 removed the last two false positives: both were
        # directive verbs in third person - `Custodians hold assets on behalf of
        # the fund.` and `Assuming rates hold, income is likely to be stable.` -
        # which the ADVICE boundary now recognises as statements rather than
        # directives. One false negative remains: IV-094, the promoter annotation
        # conflict that Phase 8.7 recorded and deliberately did not resolve.
        decision = self.metrics.decision

        self.assertEqual(decision.counts["tp"], 36)
        self.assertEqual(decision.counts["fp"], 0)
        self.assertEqual(decision.counts["fn"], 1)
        self.assertEqual(decision.counts["tn"], 63)
        self.assertEqual(decision.precision, 1.0)
        self.assertEqual(decision.recall, 0.973)
        self.assertEqual(decision.false_positive_rate, 0.0)
        self.assertEqual(decision.false_negative_rate, 0.027)

    def test_trace_metrics_are_complete(self) -> None:
        trace = self.metrics.trace

        self.assertEqual(trace.claim_evidence_rate, 1.0)
        self.assertEqual(trace.decision_evidence_rate, 1.0)
        self.assertEqual(trace.span_completeness, 1.0)
        self.assertEqual(trace.claims, 100)

    def test_every_relation_is_reported_separately(self) -> None:
        per_relation = self.metrics.intent.per_relation()

        self.assertEqual(
            set(per_relation), {"GUARANTEE", "RISK_REMOVED", "PREDICTION", "ADVICE"}
        )

    def test_per_relation_recall_matches_the_totals(self) -> None:
        per_relation = self.metrics.intent.per_relation()
        found = sum(v["found"] for v in per_relation.values())
        expected = sum(v["expected"] for v in per_relation.values())

        self.assertEqual(found, self.metrics.intent.recalled)
        self.assertEqual(expected, self.metrics.intent.expected_total)

    def test_scoring_is_reproducible(self) -> None:
        again = score(predict(blind_records()))

        self.assertEqual(again.as_dict(), self.metrics.as_dict())

    def test_the_clean_subset_is_also_scored(self) -> None:
        clean = score(predict(blind_records()), decontaminated_cases())

        self.assertEqual(len(clean.outcomes), len(CASES) - 1)

    def test_metrics_are_json_serializable(self) -> None:
        json.dumps(self.metrics.as_dict(), sort_keys=True)

    def test_the_metrics_artifact_is_written(self) -> None:
        self.assertTrue(METRICS_PATH.is_file())
        payload = json.loads(METRICS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(payload["cases"]), len(CASES))
        self.assertIn("from id and text only", payload["note"])

    def test_render_states_all_four_metric_families(self) -> None:
        rendered = self.metrics.render()

        for token in ("attribution", "intent", "decision", "trace"):
            self.assertIn(token, rendered)


class BaselineComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = score(predict(blind_records()))

    def test_the_baseline_is_worse_or_equal_on_accuracy(self) -> None:
        baseline = sum(1 for i in self.metrics.outcomes if i.baseline_correct)
        v3 = self.metrics.decision.correct

        self.assertGreaterEqual(v3, baseline)

    def test_the_baseline_numbers_are_reported(self) -> None:
        from risk_evaluation.v3_validation.evaluation import _outcome

        baseline_outcomes = [
            _outcome(item.case.expects_risk, bool(item.prediction.baseline))
            for item in self.metrics.outcomes
        ]

        self.assertEqual(len(baseline_outcomes), len(CASES))


class ClaimVerificationTests(unittest.TestCase):
    """Step 7: Phase 8.5's claims, one at a time."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = score(predict(blind_records()))
        cls.verdicts = verify_claims(cls.metrics)

    def test_three_claims_are_verified(self) -> None:
        self.assertEqual(len(self.verdicts), 3)

    def test_every_verdict_is_a_declared_value(self) -> None:
        for item in self.verdicts:
            self.assertIn(item.verdict, (SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED))

    def test_each_claim_reports_the_cases_behind_it(self) -> None:
        for item in self.verdicts:
            self.assertTrue(item.sub_claims)
            for sub in item.sub_claims:
                self.assertGreaterEqual(sub.total, 0)
                self.assertEqual(sub.correct <= sub.total, True)

    def test_claim_one_is_supported(self) -> None:
        """Phase 8.6 returned PARTIALLY_SUPPORTED here: speaker accuracy was 74%.

        Phase 8.7 typed the source, so quoted third-party claims went 17/20 to
        20/20, author rejections 12/15 to 15/15, and speaker accuracy to 96%.
        """

        verdict = verify_attribution(self.metrics)

        self.assertEqual(verdict.verdict, SUPPORTED)

    def test_claim_two_is_supported(self) -> None:
        """Phase 8.6 returned NOT_SUPPORTED here: seven guarantee cases matched no
        frame at all, so the claim rested on the forms that happened to fire.

        Phase 8.7 gave the frames the inflected verbs and the negated copula, and
        the `guarantee text no frame matched` sub-claim is gone rather than
        passing - a sub-claim that cannot be built is the strongest form of it
        holding, and section 3 of the Phase 8.7 report says which case each repair
        answered.
        """

        verdict = verify_intent(self.metrics)

        self.assertEqual(verdict.verdict, SUPPORTED)
        self.assertNotIn(
            "guarantee text no frame matched", [s.name for s in verdict.sub_claims]
        )

    def test_claim_three_is_supported(self) -> None:
        verdict = verify_decision(self.metrics)

        self.assertEqual(verdict.verdict, SUPPORTED)

    def test_the_guarantee_forms_are_grouped_by_frame_kind(self) -> None:
        by_form = guarantee_form_outcomes(self.metrics.outcomes)

        self.assertIn("copular", by_form)
        self.assertTrue(by_form["copular"])

    def test_the_unmatched_bucket_is_empty(self) -> None:
        """Phase 8.6 had 7 guarantee cases whose text no frame matched.

        The bucket is still built by the same code, so an unmatched case would
        reappear here rather than being silently dropped from the grouping.
        """

        by_form = guarantee_form_outcomes(self.metrics.outcomes)

        self.assertNotIn("unmatched", by_form)
        self.assertIn("copular", by_form)

    def test_the_verification_is_json_serializable(self) -> None:
        from risk_evaluation.v3_validation.claims import payload

        json.dumps(payload(self.metrics), sort_keys=True)


class ErrorAnalysisTests(unittest.TestCase):
    """Step 8: every failure classified, none by number alone."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = score(predict(blind_records()))
        cls.analysis = analyse(cls.metrics.outcomes)

    def test_every_failing_case_is_classified(self) -> None:
        failing = [i.case_id for i in self.metrics.outcomes if not i.correct]
        classified = {d.case_id for d in self.analysis.diagnoses}

        self.assertTrue(set(failing) <= classified)

    def test_attribution_only_failures_are_included(self) -> None:
        """A wrong speaker that did not change the verdict is still a failure."""

        attribution_failures = {i.case_id for i in self.metrics.attribution.errors()}
        classified = {d.case_id for d in self.analysis.diagnoses}

        self.assertTrue(attribution_failures <= classified)

    def test_the_categories_are_the_declared_five(self) -> None:
        counts = self.analysis.counts()

        self.assertEqual(set(counts), set(CATEGORIES))
        self.assertEqual(len(CATEGORIES), 6)  # five named plus unclassified

    def test_every_diagnosis_has_an_explanation(self) -> None:
        for item in self.analysis.diagnoses:
            self.assertTrue(item.explanation.strip(), item.case_id)

    def test_the_mechanisms_are_reported(self) -> None:
        counts = self.analysis.mechanism_counts()

        self.assertEqual(set(counts), set(MECHANISMS))
        self.assertGreater(counts[NOVEL_SOURCE_NOUN], 0)

    def test_the_inflected_verb_defect_is_repaired(self) -> None:
        """Phase 8.6: `Turnover expands sharply next quarter.` matched no frame.

        The detector is still declared in `MECHANISMS` and still runs; what must
        be true after Phase 8.7 is that it fires on nothing, and that the case
        which raised it is decided correctly.
        """

        names = {
            mechanism.name
            for item in self.analysis.diagnoses
            for mechanism in item.mechanisms
        }
        outcome = next(
            item for item in self.metrics.outcomes if item.case_id == "IV-014"
        )

        self.assertIn(INFLECTED_VERB, MECHANISMS)
        self.assertNotIn(INFLECTED_VERB, names)
        self.assertTrue(outcome.correct, outcome.prediction.categories)

    def test_fallback_propagation_is_repaired(self) -> None:
        """Phase 8.6: four neutral sentences kept a keyword `investment_advice`."""

        names = {
            mechanism.name
            for item in self.analysis.diagnoses
            for mechanism in item.mechanisms
        }

        self.assertIn(FALLBACK_PROPAGATION, MECHANISMS)
        self.assertNotIn(FALLBACK_PROPAGATION, names)
        for case_id in ("IV-062", "IV-071", "IV-075", "IV-088"):
            outcome = next(i for i in self.metrics.outcomes if i.case_id == case_id)
            self.assertTrue(outcome.correct, case_id)

    def test_the_rejection_cue_gap_is_repaired(self) -> None:
        """Phase 8.6: eight rejections were phrased with cues the layer lacked."""

        names = {
            mechanism.name
            for item in self.analysis.diagnoses
            for mechanism in item.mechanisms
        }
        rejected = [
            item
            for item in self.metrics.outcomes
            if item.case.group == "author_rejection"
        ]

        self.assertIn(NOVEL_REJECTION_CUE, MECHANISMS)
        self.assertNotIn(NOVEL_REJECTION_CUE, names)
        self.assertTrue(all(item.correct for item in rejected), rejected)

    def test_the_defects_phase_8_6_confirmed_are_all_absent(self) -> None:
        """The three defects the phase names, as one assertion.

        Nothing here says the pipeline is finished. `novel_source_noun` survives
        on one case and the PREDICTION and ADVICE relations still miss five
        between them; both are recorded in the Phase 8.7 report rather than
        asserted away.
        """

        counts = self.analysis.mechanism_counts()

        self.assertEqual(counts[INFLECTED_VERB], 0)
        self.assertEqual(counts[NOVEL_REJECTION_CUE], 0)
        self.assertEqual(counts[FALLBACK_PROPAGATION], 0)
        self.assertEqual(counts[LEXICAL_GAP], 0)

    def test_the_classifier_leaves_nothing_unclassified(self) -> None:
        self.assertEqual(self.analysis.counts()["unclassified"], 0)

    def test_decision_errors_are_counted_separately(self) -> None:
        self.assertEqual(len(self.analysis.decision_errors), len(self.metrics.decision.errors()))

    def test_the_analysis_is_json_serializable(self) -> None:
        json.dumps(self.analysis.as_dict(), sort_keys=True)

    def test_render_states_both_counts(self) -> None:
        rendered = self.analysis.render()

        self.assertIn("classified failures", rendered)
        self.assertIn("verdict was wrong", rendered)


class AmbiguityDetectorTests(unittest.TestCase):
    def test_a_negated_relation_label_is_flagged(self) -> None:
        from risk_evaluation.v3_validation.cases import case_index

        outcome = next(
            item
            for item in score(predict(blind_records())).outcomes
            if item.case_id == "IV-081"
        )
        mechanism = annotation_ambiguity(outcome)

        self.assertIsNotNone(mechanism)
        del case_index

    def test_a_relation_marker_present_is_not_flagged(self) -> None:
        outcome = next(
            item
            for item in score(predict(blind_records())).outcomes
            if item.case_id == "IV-002"
        )

        self.assertIsNone(annotation_ambiguity(outcome))

    def test_the_flag_questions_the_relation_label_not_the_verdict(self) -> None:
        """A correct verdict can still rest on an arguable relation label.

        `We are unconvinced that capital is protected here.` is correctly decided
        as no risk and is labelled `GUARANTEE` although the text contains no
        guarantee vocabulary. The verdict is right and the relation label is a
        reading, and the flag records the second without disputing the first.
        """

        outcomes = score(predict(blind_records())).outcomes
        flagged = [i for i in outcomes if annotation_ambiguity(i) is not None]

        self.assertTrue(flagged)
        for item in flagged:
            self.assertTrue(item.case.expected_relations, item.case_id)
            self.assertNotIn(
                annotation_ambiguity(item).name,
                ("", None),
                item.case_id,
            )

    def test_the_flag_never_marks_a_case_as_wrong(self) -> None:
        """Ambiguity is reported beside the metrics, not folded into them."""

        metrics = score(predict(blind_records()))
        flagged_ids = {
            item.case_id
            for item in metrics.outcomes
            if annotation_ambiguity(item) is not None
        }
        decision_errors = {item.case_id for item in metrics.decision.errors()}

        self.assertTrue(flagged_ids - decision_errors)


class IsolationTests(unittest.TestCase):
    """The pipeline is frozen, and production is untouched."""

    PROTECTED = (
        "risk_evaluation/v3/patterns.py",
        "risk_evaluation/v3/decision.py",
        "risk_evaluation/v3/pipeline.py",
        "risk_evaluation/v3/model.py",
        "risk_evaluation/v3/adapters/attribution.py",
        "risk_evaluation/v3/adapters/intent_pattern.py",
        "risk_evaluation/v3/adapters/semantic.py",
        "risk_evaluation/semantic_evaluator_v2.py",
        "risk_evaluation/taxonomy_v2.py",
        "risk_evaluation/taxonomy.py",
    )

    def test_the_protected_modules_do_not_import_the_validation_package(self) -> None:
        offenders = [
            relative
            for relative in self.PROTECTED
            if "v3_validation" in (WORKSPACE_ROOT / relative).read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_no_production_module_mentions_the_validation_package(self) -> None:
        isolated = (
            "runtime",
            "workflows",
            "production",
            "plugins",
            "core",
            "artifact",
            "security",
            "distillation_core",
        )
        offenders: list[str] = []
        for directory in isolated:
            root = WORKSPACE_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if "v3_validation" in path.read_text(encoding="utf-8"):
                    offenders.append(str(path.relative_to(WORKSPACE_ROOT)))

        self.assertEqual(offenders, [])

    def test_the_validation_package_writes_only_inside_itself(self) -> None:
        package = WORKSPACE_ROOT / "risk_evaluation" / "v3_validation"
        isolated = (
            "runtime",
            "workflows",
            "production",
            "plugins",
            "core",
            "artifact",
            "security",
        )
        offenders: list[str] = []
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for directory in isolated:
                if f'"{directory}/' in text:
                    offenders.append(f"{path.name}: {directory}")

        self.assertEqual(offenders, [])

    def test_the_pipeline_used_is_the_frozen_one(self) -> None:
        from risk_evaluation.v3_validation.freeze import evaluator_hash

        evaluator = RiskEvaluationPipeline()
        before = evaluator.evaluate("This return is guaranteed.").categories
        predict(blind_records())
        after = evaluator.evaluate("This return is guaranteed.").categories

        self.assertEqual(before, after)
        self.assertEqual(evaluator_hash(), evaluator_hash())

    def test_the_benchmark_labels_were_not_edited_after_the_run(self) -> None:
        """The frozen benchmark hash still matches the dataset on disk."""

        from risk_evaluation.v3_validation.freeze import dataset_hash, load_freeze

        self.assertEqual(load_freeze()["benchmark_hash"], dataset_hash())

    def test_the_registry_and_evaluators_are_unchanged(self) -> None:
        from risk_evaluation.benchmark_registry import BenchmarkRegistry
        from risk_evaluation.regression import EVALUATORS

        self.assertEqual(set(EVALUATORS), {"keyword", "semantic"})
        keys = {
            f"{r.benchmark_id}/{r.version}"
            for r in BenchmarkRegistry().list_benchmarks()
        }
        self.assertEqual(
            keys,
            {
                "semantic/v1",
                "semantic/v2",
                "semantic/v3",
                "semantic/v4",
                "semantic/adversarial/v1",
            },
        )


if __name__ == "__main__":
    unittest.main()
