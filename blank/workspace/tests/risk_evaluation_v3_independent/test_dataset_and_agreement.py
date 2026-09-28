"""Dataset provenance, agreement arithmetic, and adjudication."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3_independent.adjudication import (
    RESOLUTIONS,
    Ruling,
    RESOLVED_A,
    RESOLVED_B,
    RESOLVED_THIRD,
    UNRESOLVED,
    adjudicate,
    describe as describe_adjudication,
)
from risk_evaluation.v3_independent.agreement import (
    BANDS,
    UNDEFINED,
    AgreementReport,
    band_for,
    cohen_kappa,
    describe as describe_agreement,
    measure,
)
from risk_evaluation.v3_independent.build import (
    Annotation,
    BuildError,
    CATEGORIES,
    LABEL_FIELDS,
)
from risk_evaluation.v3_independent.dataset import (
    ANNOTATION_PROTOCOL,
    ANNOTATION_VERSION,
    BENCHMARK_DIR,
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    PROVENANCE,
    DatasetError,
    achieved_distribution,
    build_records,
    label_payload,
    load_manifest,
    load_records,
    manifest,
)


def annotation(case_id: str, **overrides) -> Annotation:
    base = {
        "case_id": case_id,
        "claim": "text",
        "speaker": "author",
        "stance": "endorsed",
        "intent": "PREDICTION",
        "certainty": "certain",
        "severity": "warning",
        "decision": ("market_prediction",),
        "reason": "guide 2",
    }
    base.update(overrides)
    return Annotation(**base)


class KappaTests(unittest.TestCase):
    def test_perfect_agreement_is_one(self) -> None:
        kappa, note = cohen_kappa(["a", "b", "a"], ["a", "b", "a"])
        self.assertEqual(kappa, 1.0)
        self.assertEqual(note, "")

    def test_total_disagreement_is_below_zero(self) -> None:
        kappa, _ = cohen_kappa(["a", "a", "b", "b"], ["b", "b", "a", "a"])
        self.assertIsNotNone(kappa)
        self.assertLess(kappa, 0.0)

    def test_chance_agreement_is_about_zero(self) -> None:
        left = ["a", "b"] * 25
        right = ["a", "a", "b", "b"] * 12 + ["a", "b"]
        kappa, _ = cohen_kappa(left, right)
        self.assertIsNotNone(kappa)
        self.assertGreater(kappa, -0.2)
        self.assertLess(kappa, 0.2)

    def test_a_known_value_matches_hand_computation(self) -> None:
        # 10 cases, two categories, po = 0.8, pe = 0.5 -> kappa = 0.6
        left = ["a"] * 5 + ["b"] * 5
        right = ["a"] * 4 + ["b"] + ["a"] + ["b"] * 4
        kappa, _ = cohen_kappa(left, right)
        self.assertEqual(kappa, 0.6)

    def test_unequal_lengths_are_rejected(self) -> None:
        with self.assertRaises(BuildError):
            cohen_kappa(["a"], ["a", "b"])

    def test_no_cases_is_undefined(self) -> None:
        kappa, note = cohen_kappa([], [])
        self.assertIsNone(kappa)
        self.assertEqual(note, "no cases")

    def test_a_degenerate_marginal_is_undefined_not_one(self) -> None:
        kappa, note = cohen_kappa(["a"] * 5, ["a"] * 5)
        self.assertIsNone(kappa)
        self.assertIn("chance agreement is 1", note)

    def test_the_bands_cover_the_whole_range(self) -> None:
        for value in (-0.5, 0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
            self.assertNotEqual(band_for(value), "out of range", value)

    def test_the_band_names_are_landis_and_koch(self) -> None:
        names = [name for _, name in BANDS]
        self.assertEqual(
            names,
            ["worse than chance", "slight", "fair", "moderate", "substantial"],
        )

    def test_the_band_boundaries(self) -> None:
        self.assertEqual(band_for(0.0), "slight")
        self.assertEqual(band_for(0.2), "slight")
        self.assertEqual(band_for(0.205), "slight")
        self.assertEqual(band_for(0.21), "fair")
        self.assertEqual(band_for(0.41), "moderate")
        self.assertEqual(band_for(0.61), "substantial")
        self.assertEqual(band_for(0.81), "almost perfect")
        self.assertEqual(band_for(-0.01), "worse than chance")

    def test_no_kappa_falls_outside_every_band(self) -> None:
        """The published bands have a hole at each boundary; this table must not."""

        for step in range(-100, 201):
            value = step / 100
            self.assertNotEqual(band_for(value), "out of range", value)


class MeasureTests(unittest.TestCase):
    def _labels(self, left, right):
        return {"A": tuple(left), "B": tuple(right)}

    def test_identical_label_sets_produce_perfect_category_kappa(self) -> None:
        # The decisions have to vary, or a category that is absent everywhere has an
        # expected agreement of 1 and no kappa to report: a perfect score on a field
        # with one value is undefined, not 1.0.
        items = [
            annotation(
                f"IND-{i:04d}",
                decision=("market_prediction",) if i % 2 else ("investment_advice",),
                severity="warning" if i % 2 else "block",
                certainty="certain" if i % 2 else "probable",
                speaker="author" if i % 2 else "third_party",
                stance="endorsed" if i % 2 else "quoted",
                intent="PREDICTION" if i % 2 else "ADVICE",
            )
            for i in range(10)
        ]
        report = measure(self._labels(items, items))
        self.assertEqual(report.cases, 10)
        # Only the two categories the fixture varies can have a kappa; the other
        # three are absent everywhere, which is undefined rather than perfect.
        for row in report.categories:
            if row.field in ("market_prediction", "investment_advice"):
                self.assertEqual(row.kappa, 1.0, row.field)
            else:
                self.assertIsNone(row.kappa, row.field)
        for row in report.fields:
            self.assertEqual(row.kappa, 1.0, row.field)
        self.assertEqual(report.exact_decision_agreement, 1.0)
        self.assertEqual(report.disagreements, ())

    def test_a_category_absent_everywhere_has_no_kappa(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(10)]
        report = measure(self._labels(items, items))
        row = next(item for item in report.categories if item.field == "unverified_information")
        self.assertIsNone(row.kappa)
        self.assertEqual(row.band, UNDEFINED)
        self.assertIn("chance agreement is 1", row.note)

    def test_a_decision_disagreement_is_recorded(self) -> None:
        left = [annotation("IND-0001"), annotation("IND-0002")]
        right = [
            annotation("IND-0001"),
            annotation("IND-0002", decision=(), severity="none"),
        ]
        report = measure(self._labels(left, right))
        fields = {item.field for item in report.disagreements}
        self.assertIn("decision", fields)
        self.assertIn("severity", fields)
        self.assertEqual(report.affected_cases, ("IND-0002",))

    def test_each_field_gets_its_own_kappa(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(6)]
        report = measure(self._labels(items, items))
        self.assertEqual({row.field for row in report.fields}, set(LABEL_FIELDS))
        self.assertEqual(len(report.fields), 5)

    def test_each_category_gets_its_own_kappa(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(6)]
        report = measure(self._labels(items, items))
        self.assertEqual({row.field for row in report.categories}, set(CATEGORIES))

    def test_a_pooled_kappa_is_not_reported(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(6)]
        report = measure(self._labels(items, items))
        payload = report.as_dict()
        self.assertNotIn("kappa", payload)
        self.assertIn("fields", payload)
        self.assertIn("categories", payload)

    def test_mismatched_case_sets_are_rejected(self) -> None:
        with self.assertRaises(BuildError):
            measure(
                {
                    "A": (annotation("IND-0001"),),
                    "B": (annotation("IND-0002"),),
                }
            )

    def test_three_annotators_are_rejected(self) -> None:
        items = (annotation("IND-0001"),)
        with self.assertRaises(BuildError):
            measure({"A": items, "B": items, "C": items}, annotators=("A", "B", "C"))

    def test_the_disagreement_rate_counts_field_units(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(4)]
        report = measure(self._labels(items, items))
        self.assertEqual(report.disagreement_rate, 0.0)

    def test_group_agreement_is_reported_when_groups_are_given(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(4)]
        groups = {"IND-0000": "safe", "IND-0001": "safe", "IND-0002": "boundary", "IND-0003": "boundary"}
        report = measure(self._labels(items, items), groups=groups)
        self.assertEqual(set(report.by_group), {"safe", "boundary"})
        self.assertEqual(report.by_group["safe"]["cases"], 2)

    def test_the_report_renders_every_field(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(4)]
        rendered = measure(self._labels(items, items)).render()
        for field in LABEL_FIELDS:
            self.assertIn(field, rendered)
        self.assertIn(UNDEFINED, rendered)  # severity is constant here

    def test_the_report_serialises(self) -> None:
        items = [annotation(f"IND-{i:04d}") for i in range(4)]
        json.dumps(measure(self._labels(items, items)).as_dict(), sort_keys=True)

    def test_the_module_declares_it_does_not_pool(self) -> None:
        self.assertFalse(describe_agreement()["pooled_kappa_reported"])


class RulingTests(unittest.TestCase):
    def test_a_valid_ruling_parses(self) -> None:
        item = Ruling(
            case_id="IND-0001",
            field="certainty",
            first="n/a",
            second="possible",
            ruling="possible",
            basis="guide 1.2",
            resolution=RESOLVED_B,
        )
        self.assertTrue(item.resolved)
        self.assertEqual(item.categories, ())

    def test_a_decision_ruling_splits_categories(self) -> None:
        item = Ruling(
            case_id="IND-0001",
            field="decision",
            first="investment_advice",
            second="(none)",
            ruling="investment_advice, market_prediction",
            basis="guide 2",
            resolution=RESOLVED_THIRD,
        )
        self.assertEqual(item.categories, ("investment_advice", "market_prediction"))

    def test_an_empty_decision_ruling_means_no_category(self) -> None:
        item = Ruling(
            case_id="IND-0001",
            field="decision",
            first="investment_advice",
            second="(none)",
            ruling="",
            basis="guide 7: method guidance is negative",
            resolution=RESOLVED_B,
        )
        self.assertEqual(item.categories, ())
        self.assertTrue(item.resolved)

    def test_an_unknown_resolution_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            Ruling("IND-0001", "certainty", "a", "b", "possible", "guide", "vibes")

    def test_an_unknown_category_in_a_ruling_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            Ruling("IND-0001", "decision", "a", "b", "vibes", "guide", RESOLVED_A)

    def test_an_out_of_range_value_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            Ruling("IND-0001", "speaker", "a", "b", "nobody", "guide", RESOLVED_A)

    def test_an_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(BuildError):
            Ruling("IND-0001", "mood", "a", "b", "x", "guide", RESOLVED_A)

    def test_the_resolution_values_are_declared(self) -> None:
        self.assertEqual(
            set(RESOLUTIONS),
            {RESOLVED_A, RESOLVED_B, RESOLVED_THIRD, UNRESOLVED},
        )

    def test_the_module_declares_the_unresolved_policy(self) -> None:
        described = describe_adjudication()
        self.assertIn("excluded", described["unresolved_policy"])


class AdjudicateTests(unittest.TestCase):
    def test_an_agreed_field_survives_untouched(self) -> None:
        labels = {
            "A": (annotation("IND-0001"),),
            "B": (annotation("IND-0001"),),
        }
        found = adjudicate(labels, ())
        self.assertEqual(found[0].annotation.speaker, "author")
        self.assertFalse(found[0].disputed_fields)

    def test_a_resolved_dispute_takes_the_ruling(self) -> None:
        labels = {
            "A": (annotation("IND-0001", speaker="author"),),
            "B": (annotation("IND-0001", speaker="unknown"),),
        }
        ruling = Ruling(
            "IND-0001", "speaker", "author", "unknown", "unknown", "guide 4", RESOLVED_B
        )
        found = adjudicate(labels, (ruling,))
        self.assertEqual(found[0].annotation.speaker, "unknown")
        self.assertTrue(found[0].resolved)

    def test_an_unresolved_dispute_leaves_the_case_unresolved(self) -> None:
        labels = {
            "A": (annotation("IND-0001", speaker="author"),),
            "B": (annotation("IND-0001", speaker="unknown"),),
        }
        ruling = Ruling(
            "IND-0001", "speaker", "author", "unknown", "", "guide unclear", UNRESOLVED
        )
        found = adjudicate(labels, (ruling,))
        self.assertFalse(found[0].resolved)
        self.assertEqual(found[0].unresolved_fields, ("speaker",))

    def test_a_third_reading_replaces_both(self) -> None:
        labels = {
            "A": (annotation("IND-0001", decision=("investment_advice",), severity="block"),),
            "B": (annotation("IND-0001", decision=(), severity="none"),),
        }
        ruling = Ruling(
            "IND-0001",
            "decision",
            "investment_advice",
            "(none)",
            "unverified_information",
            "guide 3.1",
            RESOLVED_THIRD,
        )
        found = adjudicate(labels, (ruling,))
        self.assertEqual(found[0].annotation.decision, ("unverified_information",))

    def test_the_adjudicated_case_records_its_rulings(self) -> None:
        labels = {
            "A": (annotation("IND-0001", speaker="author"),),
            "B": (annotation("IND-0001", speaker="unknown"),),
        }
        ruling = Ruling(
            "IND-0001", "speaker", "author", "unknown", "author", "guide 4", RESOLVED_A
        )
        payload = adjudicate(labels, (ruling,))[0].as_dict()
        self.assertEqual(payload["rulings"][0]["basis"], "guide 4")
        self.assertTrue(payload["resolved"])

    def test_adjudication_needs_both_annotators(self) -> None:
        labels = {"A": (annotation("IND-0001"),), "B": (annotation("IND-0001"),)}
        with self.assertRaises(TypeError):
            adjudicate(labels)  # type: ignore[call-arg]


class DatasetProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = load_records()
        cls.manifest = load_manifest()

    def test_the_benchmark_is_where_the_phase_says(self) -> None:
        self.assertEqual(BENCHMARK_ID, "risk/independent")
        self.assertEqual(BENCHMARK_VERSION, "v1")
        self.assertTrue(BENCHMARK_DIR.is_dir())
        self.assertEqual(BENCHMARK_DIR.parts[-3:], ("risk", "independent", "v1"))

    def test_the_dataset_has_three_hundred_cases(self) -> None:
        self.assertEqual(len(self.records), 300)

    def test_the_provenance_declares_synthetic_and_machine_annotated(self) -> None:
        self.assertTrue(PROVENANCE["synthetic"])
        self.assertFalse(PROVENANCE["human_annotators"])
        self.assertEqual(PROVENANCE["annotator_kind"], "machine")
        self.assertEqual(PROVENANCE["annotators"], 2)

    def test_the_provenance_says_the_authors_are_not_the_evaluator_author(self) -> None:
        self.assertTrue(PROVENANCE["independent_of_evaluator_author"])
        self.assertFalse(PROVENANCE["dataset_authors_are_evaluator_author"])
        self.assertEqual(PROVENANCE["dataset_authors"], 30)

    def test_the_provenance_refuses_the_real_world_claim(self) -> None:
        text = PROVENANCE["real_world_accuracy"].lower()
        self.assertIn("unknown", text)
        self.assertIn("not", text)

    def test_the_provenance_refuses_the_human_agreement_claim(self) -> None:
        text = PROVENANCE["agreement_kind"].lower()
        self.assertIn("not human", text)

    def test_the_prompts_are_published_in_the_manifest(self) -> None:
        self.assertTrue(PROVENANCE["prompts_published"])
        provenance = self.manifest["provenance"]
        self.assertIn("You are writing text for an annotation dataset", provenance["generation_prompt"])
        self.assertIn("You are an annotator", provenance["annotation_prompt"])
        self.assertIn("risk categories", provenance["guide_digest_given_to_agents"])

    def test_the_manifest_records_the_benchmark_identity(self) -> None:
        self.assertEqual(self.manifest["id"], BENCHMARK_ID)
        self.assertEqual(self.manifest["version"], BENCHMARK_VERSION)
        self.assertEqual(self.manifest["case_count"], 300)
        self.assertEqual(self.manifest["status"], "frozen")

    def test_the_manifest_names_the_annotation_protocol(self) -> None:
        self.assertEqual(self.manifest["annotation_protocol"], ANNOTATION_PROTOCOL)
        self.assertEqual(self.manifest["annotation_version"], ANNOTATION_VERSION)

    def test_the_manifest_records_agreement_and_adjudication(self) -> None:
        self.assertIn("agreement", self.manifest)
        self.assertIn("adjudication", self.manifest)
        self.assertGreater(self.manifest["adjudication"]["rulings"], 0)

    def test_the_manifest_records_the_scored_case_count(self) -> None:
        adjudication = self.manifest["adjudication"]
        self.assertEqual(
            adjudication["scored_cases"]
            + adjudication["unresolved_cases"],
            adjudication["total"] if "total" in adjudication else 300,
        )

    def test_every_record_carries_its_frame_block(self) -> None:
        for item in self.records:
            frame = item["frame"]
            for key in ("language", "form", "source_type", "topic", "intended_group"):
                self.assertIn(key, frame, item["id"])

    def test_every_record_carries_a_resolved_flag(self) -> None:
        for item in self.records:
            self.assertIn("resolved", item, item["id"])

    def test_every_record_has_a_text_and_a_reason(self) -> None:
        for item in self.records:
            self.assertTrue(item["text"].strip(), item["id"])
            self.assertTrue(item["annotation_reason"].strip(), item["id"])

    def test_case_ids_are_unique(self) -> None:
        ids = [item["id"] for item in self.records]
        self.assertEqual(len(ids), len(set(ids)))

    def test_both_languages_are_present(self) -> None:
        languages = {item["frame"]["language"] for item in self.records}
        self.assertEqual(languages, {"en", "zh"})

    def test_the_files_the_protocol_requires_are_published(self) -> None:
        for name in (
            "cases.json",
            "labels.json",
            "manifest.json",
            "labels_a.json",
            "labels_b.json",
            "disagreements.json",
            "adjudication.json",
            "adjudicated.json",
        ):
            self.assertTrue((BENCHMARK_DIR / name).is_file(), name)

    def test_the_raw_label_sets_are_retained_and_distinct(self) -> None:
        left = json.loads((BENCHMARK_DIR / "labels_a.json").read_text(encoding="utf-8"))
        right = json.loads((BENCHMARK_DIR / "labels_b.json").read_text(encoding="utf-8"))
        self.assertEqual(left["annotator"], "A")
        self.assertEqual(right["annotator"], "B")
        self.assertEqual(len(left["labels"]), 300)
        self.assertEqual(len(right["labels"]), 300)
        differing = sum(
            1
            for a, b in zip(left["labels"], right["labels"])
            if a["decision"] != b["decision"]
        )
        self.assertGreater(differing, 0, "two annotators that never differ are one annotator")

    def test_the_label_index_covers_every_case(self) -> None:
        payload = label_payload(self.records)
        self.assertEqual(payload["case_count"], 300)
        self.assertEqual(len(payload["by_case"]), 300)

    def test_the_achieved_distribution_is_reported(self) -> None:
        achieved = achieved_distribution(self.records)
        self.assertEqual(
            achieved["with_a_category"] + achieved["without_a_category"], 300
        )
        self.assertEqual(sum(achieved["by_group"][k]["cases"] for k in achieved["by_group"]), 300)

    def test_the_manifest_and_the_records_agree_on_the_hash(self) -> None:
        from risk_evaluation.v3_independent.dataset import dataset_digest

        self.assertEqual(self.manifest["dataset_hash"], dataset_digest())

    def test_the_distribution_is_not_silently_the_frame_quota(self) -> None:
        """The achieved labels are the annotators' and need not match the frame."""

        achieved = achieved_distribution(self.records)
        self.assertNotEqual(achieved["by_group"], {"boundary": 75, "risk_positive": 150, "safe": 75})

    def test_a_record_without_a_label_is_rejected(self) -> None:
        from risk_evaluation.v3_independent.build import GeneratedCase

        case = GeneratedCase("IND-9999", "text", {"group": "safe"})
        with self.assertRaises(DatasetError):
            build_records((case,), ())


if __name__ == "__main__":
    unittest.main()
