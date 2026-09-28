"""Artifact integration, layer-boundary, and benchmark tests (Phase M2)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from multimodal_creator import (
    LAYER_UNIVERSAL,
    MULTIMODAL_FAMILIES,
    PLUGIN_MAY_NOT_REDEFINE,
    MultimodalContractError,
    integrate_samples,
    validate_integrated_artifact,
    validate_multimodal_artifact,
)
from multimodal_creator.benchmark import (
    BenchmarkSuite,
    discovery_agreement,
    render_report,
    run_benchmark,
)
from multimodal_creator.benchmark.cases import (
    cross_modal_cases,
    layout_cases,
    similarity_cases,
)
from multimodal_creator.extraction import RegionSpec, SampleProvenance, SubjectSpec, VisualSample

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
BASELINE_SCHEMA = WORKSPACE_ROOT / "schemas" / "unified_distillation_artifact.json"
MULTIMODAL_SCHEMA = WORKSPACE_ROOT / "schemas" / "multimodal_artifact.schema.json"


def text_core() -> dict:
    return {
        "artifact_version": "1.0.0",
        "plugin": {
            "name": "fixture_creator",
            "version": "1.0.0",
            "domain": "general",
            "creator_target": "short_form_cards",
        },
        "topic_candidate": [
            {
                "label": "3 mistakes investors make",
                "rationale": "Repeated framing across the sample set.",
                "source_ids": ["L01"],
                "confidence": 0.7,
                "origin": "common",
            }
        ],
        "content_template": [
            {
                "name": "three-card-listicle",
                "sections": ["hook", "one", "two", "three"],
                "source_ids": ["L01"],
                "origin": "common",
            }
        ],
        "knowledge_unit": [
            {
                "statement": "Fees compound against long-horizon returns.",
                "evidence_refs": [{"source_id": "L01", "source_type": "image"}],
                "confidence": 0.65,
                "origin": "common",
            }
        ],
        "style_pattern": [
            {
                "name": "direct-address",
                "attributes": ["second-person"],
                "source_ids": ["L01"],
                "origin": "common",
            }
        ],
        "domain_extension": {},
        "risk_constraints": [],
        "evaluation_result": {
            "common": {"score": 0.8, "checks": {"shape": True}, "passed": True},
            "domain": {},
        },
    }


def region(region_id, role, x, y, w, h, layer=0):
    return RegionSpec(region_id, role, {"x": x, "y": y, "w": w, "h": h}, layer)


def sample(sample_id, creator, *, regions=None, layout="image_left_text_right", **kw):
    return VisualSample(
        sample_id=sample_id,
        regions=regions
        or (
            region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
            region("title", "title", 0.06, 0.10, 0.40, 0.20, 1),
            region("img", "subject", 0.55, 0.10, 0.40, 0.60, 1),
        ),
        color_family=kw.get("color", "warm_red"),
        subject=SubjectSpec(kw.get("subject", "human_figure"), "subject_dominant"),
        provenance=SampleProvenance(creator),
        layout_template_class=layout,
        alignment=kw.get("alignment", "left"),
        palette_relation="high_contrast_accent",
        placement="side_panel",
    )


def small_batch():
    return [
        sample("F1", "creator-1"),
        sample("F2", "creator-2"),
        sample("F3", "creator-3"),
    ]


class ArtifactIntegrationTests(unittest.TestCase):
    """Observation → Pattern → Artifact must hold end to end."""

    def test_integration_produces_a_multimodal_artifact(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        for family in MULTIMODAL_FAMILIES:
            self.assertIn(family, result.artifact)

    def test_integration_produces_all_three_record_kinds(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        counts = result.family_summary()
        self.assertGreater(counts["visual_patterns"], 0)
        self.assertGreater(counts["layout_patterns"], 0)
        self.assertGreater(counts["cross_modal_patterns"], 0)

    def test_integrated_artifact_validates(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        validate_integrated_artifact(result)

    def test_integrated_artifact_has_no_keys_outside_the_schema(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        schema = json.loads(MULTIMODAL_SCHEMA.read_text(encoding="utf-8"))
        extra = set(result.artifact) - set(schema["properties"])
        self.assertEqual(extra, set())

    def test_text_core_is_preserved(self) -> None:
        base = text_core()
        result = integrate_samples(base, small_batch())
        for field in (
            "topic_candidate",
            "content_template",
            "knowledge_unit",
            "style_pattern",
            "risk_constraints",
            "evaluation_result",
        ):
            self.assertEqual(result.artifact[field], base[field], field)

    def test_text_core_projection_matches_the_base_field_set(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        self.assertEqual(set(result.text_core_projection), set(text_core()))

    def test_projection_validates_against_the_unmodified_baseline(self) -> None:
        from core.schema_validation import validate_schema_instance

        result = integrate_samples(text_core(), small_batch())
        validate_schema_instance(
            result.text_core_projection, BASELINE_SCHEMA, root_name="artifact"
        )

    def test_discovery_is_reachable_from_the_result(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        self.assertGreaterEqual(len(result.discovery.clusters), 1)
        self.assertEqual(result.observations_count, 3)

    def test_discovery_output_is_not_inside_the_artifact(self) -> None:
        """The M1 schema is closed; discovery must not be smuggled into it."""

        result = integrate_samples(text_core(), small_batch())
        self.assertNotIn("template_discovery", result.artifact)
        self.assertIn("discovery", result.as_dict())

    def test_empty_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            integrate_samples(text_core(), [])

    def test_summary_renders(self) -> None:
        self.assertIn("observations", integrate_samples(text_core(), small_batch()).summarise())


class LayerBoundaryTests(unittest.TestCase):
    """Structure stays universal; plugins only interpret."""

    def test_every_structural_record_is_universal(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        for family in MULTIMODAL_FAMILIES:
            for record in result.artifact[family]:
                self.assertEqual(record["layer"], LAYER_UNIVERSAL, family)

    def test_every_structural_record_originates_commonly(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        for family in MULTIMODAL_FAMILIES:
            for record in result.artifact[family]:
                self.assertIn(record["origin"], {"common", "framework"}, family)

    def test_plugin_extension_cannot_originate_structure(self) -> None:
        result = integrate_samples(
            text_core(), small_batch(), plugin="xiaolin_finance"
        )
        self.assertEqual(result.artifact["creator_extension"]["plugin"], "xiaolin_finance")
        for family in MULTIMODAL_FAMILIES:
            for record in result.artifact[family]:
                self.assertNotEqual(record["origin"], "xiaolin_finance")

    def test_plugin_acknowledges_the_universal_vocabulary(self) -> None:
        result = integrate_samples(text_core(), small_batch(), plugin="xiaolin_finance")
        declared = set(result.artifact["creator_extension"]["may_not_redefine"])
        self.assertTrue(set(PLUGIN_MAY_NOT_REDEFINE).issubset(declared))

    def test_plugin_binding_naming_a_fake_family_is_rejected(self) -> None:
        with self.assertRaises(MultimodalContractError):
            integrate_samples(
                text_core(),
                small_batch(),
                plugin="xiaolin_finance",
                pattern_bindings=[
                    {
                        "pattern_id": "p",
                        "family": "plugin_invented_family",
                        "domain_meaning": "nope",
                    }
                ],
            )

    def test_plugin_domain_vocabulary_is_stored_but_inert(self) -> None:
        result = integrate_samples(
            text_core(),
            small_batch(),
            plugin="xiaolin_finance",
            domain_vocabulary={"attention": ["earnings_surprise"]},
        )
        self.assertIn(
            "earnings_surprise",
            result.artifact["creator_extension"]["domain_vocabulary"]["attention"],
        )
        # The universal region vocabulary is untouched, so an invented role in a
        # record is still rejected.
        mutated = json.loads(json.dumps(result.artifact))
        mutated["visual_patterns"][0]["regions"] = [
            {
                "region_id": "banner",
                "role": "earnings_banner",
                "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.1},
                "layer_order": 0,
            }
        ]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(mutated)

    def test_default_plugin_bindings_name_discovered_families(self) -> None:
        result = integrate_samples(text_core(), small_batch(), plugin="xiaolin_finance")
        bindings = result.artifact["creator_extension"]["pattern_bindings"]
        self.assertTrue(bindings)
        for binding in bindings:
            self.assertTrue(binding["domain_meaning"].strip())


class AntiOcrIntegrationTests(unittest.TestCase):
    """No integration output may be grounded in transcription."""

    def test_no_structural_record_is_ocr_only(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        for family in MULTIMODAL_FAMILIES:
            for record in result.artifact[family]:
                evidence = record.get("evidence_kinds") or record.get(
                    "visual_anchor", {}
                ).get("evidence_kinds", [])
                self.assertTrue(evidence, family)
                self.assertNotEqual(list(evidence), ["ocr_text"], family)

    def test_cross_modal_records_anchor_both_sides(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        for record in result.artifact["cross_modal_patterns"]:
            self.assertTrue(record["text_anchor"]["text_signal"])
            self.assertTrue(record["visual_anchor"]["evidence_kinds"])

    def test_source_structures_mark_image_text_as_transcribed(self) -> None:
        result = integrate_samples(text_core(), small_batch())
        entries = result.artifact["multimodal_envelope"]["source_roles"]
        self.assertTrue(entries)
        for entry in entries:
            self.assertEqual(entry["source_type"], "image")
            self.assertIn("visual", entry["modalities"])


class BenchmarkSuiteTests(unittest.TestCase):
    """The benchmark must contain 30 cases in the required groups."""

    def test_suite_has_thirty_cases(self) -> None:
        self.assertEqual(BenchmarkSuite().case_count, 30)

    def test_layout_group_has_ten_cases(self) -> None:
        self.assertEqual(len(layout_cases()), 10)

    def test_similarity_group_has_ten_cases(self) -> None:
        self.assertEqual(len(similarity_cases()), 10)

    def test_cross_modal_group_has_ten_cases(self) -> None:
        self.assertEqual(len(cross_modal_cases()), 10)

    def test_all_cases_pass(self) -> None:
        report = run_benchmark()
        self.assertTrue(report.ok, report.render())

    def test_report_counts_match(self) -> None:
        report = run_benchmark()
        self.assertEqual(report.total, 30)
        self.assertEqual(report.passed, 30)
        self.assertEqual(report.failed, 0)

    def test_every_group_is_reported(self) -> None:
        groups = run_benchmark().by_group()
        self.assertEqual(set(groups), {"layout", "template_similarity", "cross_modal_alignment"})
        for passed, total in groups.values():
            self.assertEqual(passed, total)

    def test_benchmark_is_deterministic(self) -> None:
        first = run_benchmark().as_dict()
        second = run_benchmark().as_dict()
        self.assertEqual(first["passed"], second["passed"])
        self.assertEqual(first["total"], second["total"])

    def test_similarity_benchmark_labels_are_balanced(self) -> None:
        cases = similarity_cases()
        same = [c for c in cases if c.same_family]
        different = [c for c in cases if not c.same_family]
        self.assertGreaterEqual(len(same), 4)
        self.assertGreaterEqual(len(different), 4)

    def test_discovery_recovers_labeled_groupings(self) -> None:
        suite = BenchmarkSuite()
        agreement = discovery_agreement(run_benchmark(suite), suite)
        self.assertEqual(agreement["same_family_pairs"], agreement["same_family_grouped"])
        self.assertEqual(agreement["different_family_merged"], 0)

    def test_discovery_is_never_shown_the_labels(self) -> None:
        """Discovery must run on samples alone; labels only score it afterwards."""

        import inspect

        from multimodal_creator.clustering import template_discovery

        source = inspect.getsource(template_discovery.discover_templates)
        self.assertNotIn("same_family", source)
        self.assertNotIn("expected_", source)

    def test_report_renders_with_agreement(self) -> None:
        text = render_report(run_benchmark())
        self.assertIn("30/30", text)
        self.assertIn("agreement", text)

    def test_report_serialises(self) -> None:
        payload = run_benchmark().as_dict()
        self.assertIn("cases", payload)
        self.assertIn("discovery", payload)
        self.assertEqual(payload["total"], 30)

    def test_cross_modal_cases_declare_expected_relations(self) -> None:
        for case in cross_modal_cases():
            self.assertTrue(case.expected_geometric_relation)
            self.assertTrue(case.expected_semantic_relation)

    def test_layout_cases_declare_expected_roles(self) -> None:
        for case in layout_cases():
            self.assertTrue(case.expected_region_roles)
            self.assertIsNotNone(case.expected_layout_class)

    def test_benchmark_artifacts_validate_end_to_end(self) -> None:
        suite = BenchmarkSuite()
        result = integrate_samples(text_core(), suite.all_samples())
        validate_integrated_artifact(result)
        self.assertEqual(result.observations_count, len(suite.all_samples()))


if __name__ == "__main__":
    unittest.main()
