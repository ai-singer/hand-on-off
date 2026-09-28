"""Observer contract, pixel codec, backend isolation, and evidence tests."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from pathlib import Path

from multimodal_creator.observation import (
    EVIDENCE_FAMILIES,
    EVIDENCE_SOURCES,
    EvidenceRecord,
    FrameObserver,
    ManualAnnotationBackend,
    MockDescriptorBackend,
    ObservationResult,
    ObserverError,
    StdlibPixelBackend,
    VideoSequenceObserver,
    VisionBackend,
    VisualSource,
)
from multimodal_creator.observation.corpus import (
    Canvas,
    build_templates,
    validate_templates,
)
from multimodal_creator.observation.pixel.png_codec import (
    PngCodecError,
    RgbImage,
    decode_png,
    encode_png,
)
from multimodal_creator.observation.pixel.primitives import (
    build_grid,
    classify_color_family,
    contrast_role_of,
    count_alternations,
    detect_text_bands,
    dominant_colors,
    high_frequency_energy,
    label_components,
    luminance,
    palette_relation_of,
    rgb_to_hsv,
)
from multimodal_creator.observation.image_observer import (
    RegionEvidence,
    count_grid_lines,
)


def make_image(width=64, height=64, paint=None) -> RgbImage:
    canvas = Canvas(width, height)
    canvas.fill_rect(0, 0, width, height, (250, 250, 250))
    if paint:
        paint(canvas)
    import random

    return canvas.to_image(random.Random(7), grain=0)


class PngCodecTests(unittest.TestCase):
    """The codec must round-trip exactly, or observations are meaningless."""

    def test_round_trip_is_lossless(self) -> None:
        image = make_image(48, 32, lambda c: c.fill_rect(4, 4, 20, 20, (200, 40, 40)))
        restored = decode_png(encode_png(image))
        self.assertEqual(restored.pixels, image.pixels)
        self.assertEqual((restored.width, restored.height), (48, 32))

    def test_signature_is_checked(self) -> None:
        with self.assertRaises(PngCodecError):
            decode_png(b"not a png at all")

    def test_truncated_data_is_rejected(self) -> None:
        data = encode_png(make_image(8, 8))
        with self.assertRaises(PngCodecError):
            decode_png(data[: len(data) // 2])

    def test_pixel_out_of_range_is_rejected(self) -> None:
        image = make_image(4, 4)
        with self.assertRaises(PngCodecError):
            image.pixel(9, 9)

    def test_bad_buffer_length_is_rejected(self) -> None:
        with self.assertRaises(PngCodecError):
            RgbImage(4, 4, 3, b"\x00" * 10)

    def test_zero_dimension_is_rejected(self) -> None:
        with self.assertRaises(PngCodecError):
            RgbImage(0, 4, 3, b"")

    def test_downscale_preserves_dominant_colour(self) -> None:
        image = make_image(40, 40, lambda c: c.fill_rect(0, 0, 40, 40, (30, 90, 200)))
        small = image.downscale(4)
        self.assertEqual((small.width, small.height), (10, 10))
        r, g, b = small.pixel(5, 5)
        self.assertGreater(b, r)

    def test_downscale_factor_one_is_identity(self) -> None:
        image = make_image(6, 6)
        self.assertIs(image.downscale(1), image)


class PixelPrimitiveTests(unittest.TestCase):
    """Primitives must be deterministic and structurally meaningful."""

    def test_colour_classification_is_stable(self) -> None:
        self.assertEqual(classify_color_family(206, 58, 48), "warm_red")
        self.assertEqual(classify_color_family(44, 92, 168), "cool_blue")
        self.assertEqual(classify_color_family(20, 20, 20), "dark_monochrome")
        self.assertEqual(classify_color_family(250, 250, 250), "light_monochrome")

    def test_hsv_bounds(self) -> None:
        hue, saturation, value = rgb_to_hsv(255, 0, 0)
        self.assertAlmostEqual(hue, 0.0, places=3)
        self.assertAlmostEqual(saturation, 1.0, places=3)
        self.assertAlmostEqual(value, 1.0, places=3)

    def test_luminance_ordering(self) -> None:
        self.assertLess(luminance(0, 0, 0), luminance(255, 255, 255))

    def test_count_alternations_ignores_a_single_step(self) -> None:
        monotonic = [0.9, 0.9, 0.9, 0.3, 0.3, 0.3]
        oscillating = [0.9, 0.2, 0.9, 0.2, 0.9, 0.2]
        self.assertEqual(count_alternations(monotonic), 0)
        self.assertGreaterEqual(count_alternations(oscillating), 3)

    def test_grid_is_normalized_boxes(self) -> None:
        grid = build_grid(make_image(60, 60), target=30)
        box = grid.box_norm(0, 0, grid.width - 1, grid.height - 1)
        self.assertAlmostEqual(box["x"], 0.0, places=6)
        self.assertAlmostEqual(box["y"], 0.0, places=6)
        self.assertAlmostEqual(box["w"], 1.0, places=6)
        self.assertAlmostEqual(box["h"], 1.0, places=6)

    def test_components_are_deterministic(self) -> None:
        grid = build_grid(make_image(64, 64, lambda c: c.fill_rect(8, 8, 40, 40, (200, 40, 40))))
        first = [(c.component_id, c.x0, c.y0) for c in label_components(grid)]
        second = [(c.component_id, c.x0, c.y0) for c in label_components(grid)]
        self.assertEqual(first, second)

    def test_text_band_needs_alternation(self) -> None:
        """A flat two-tone image has no alternation and must yield no band."""

        grid = build_grid(make_image(80, 80, lambda c: c.fill_rect(0, 0, 40, 80, (30, 30, 30))))
        self.assertEqual(detect_text_bands(grid), [])

    def test_high_frequency_energy_separates_flat_from_busy(self) -> None:
        flat = build_grid(make_image(64, 64))
        busy = build_grid(
            make_image(
                64,
                64,
                lambda c: [
                    c.fill_rect(x, 10, x + 1, 50, (20, 20, 20)) for x in range(0, 64, 3)
                ],
            )
        )
        self.assertLess(high_frequency_energy(flat), high_frequency_energy(busy))

    def test_dominant_colors_shares_sum_to_one(self) -> None:
        grid = build_grid(make_image(40, 40))
        shares = [share for _family, share in dominant_colors(grid, top=4)]
        self.assertAlmostEqual(sum(shares), 1.0, places=5)

    def test_palette_relation_detects_complementary(self) -> None:
        self.assertEqual(
            palette_relation_of(["warm_red", "cool_blue"], [0.4, 0.3]),
            "complementary",
        )

    def test_palette_relation_detects_monochrome(self) -> None:
        self.assertEqual(
            palette_relation_of(["dark_monochrome"], [0.8]), "monochrome"
        )

    def test_contrast_role_of_flat_frame_is_ground(self) -> None:
        self.assertEqual(
            contrast_role_of(top_luma=0.5, bottom_luma=0.48, palette_relation="mixed"),
            "ground",
        )

    def test_grid_line_counting_finds_rules(self) -> None:
        def paint(canvas):
            for row in range(1, 5):
                y = 10 + row * 10
                canvas.fill_rect(5, y, 55, y + 1, (20, 20, 20))

        grid = build_grid(make_image(64, 64, paint))
        horizontal, _vertical = count_grid_lines(grid, 2, 2, 60, 60)
        self.assertGreaterEqual(horizontal, 2)


class VisualSourceTests(unittest.TestCase):
    """The input envelope must reject anything ambiguous."""

    def test_valid_source(self) -> None:
        source = VisualSource("s1", "image", "a.png")
        self.assertEqual(source.source_id, "s1")

    def test_empty_source_id_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            VisualSource("  ", "image", "a.png")

    def test_unknown_source_type_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            VisualSource("s1", "audio", "a.mp3")

    def test_empty_asset_reference_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            VisualSource("s1", "image", "   ")

    def test_source_has_no_structure_fields(self) -> None:
        """A source must not be able to pre-declare structure."""

        source = VisualSource("s1", "image", "a.png", {"note": "x"})
        payload = source.as_dict()
        for forbidden in ("regions", "layout_template_class", "palette_relation"):
            self.assertNotIn(forbidden, payload)


class EvidenceRecordTests(unittest.TestCase):
    """Evidence records must be well formed and OCR-free."""

    def test_valid_record(self) -> None:
        record = EvidenceRecord("layout_evidence", ("pixel_analysis",), 0.9)
        self.assertEqual(record.strength, 0.9)

    def test_unknown_family_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            EvidenceRecord("vibes_evidence", ("pixel_analysis",), 0.5)

    def test_empty_sources_are_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            EvidenceRecord("layout_evidence", (), 0.5)

    def test_unknown_source_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            EvidenceRecord("layout_evidence", ("telepathy",), 0.5)

    def test_ocr_is_not_an_admissible_evidence_source(self) -> None:
        """Transcription must be unrepresentable as evidence provenance."""

        self.assertNotIn("ocr", EVIDENCE_SOURCES)
        self.assertNotIn("ocr_text", EVIDENCE_SOURCES)
        with self.assertRaises(ObserverError):
            EvidenceRecord("layout_evidence", ("ocr",), 0.5)

    def test_strength_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            EvidenceRecord("layout_evidence", ("pixel_analysis",), 1.5)

    def test_four_families_are_required_by_the_contract(self) -> None:
        self.assertEqual(
            set(EVIDENCE_FAMILIES),
            {
                "layout_evidence",
                "visual_evidence",
                "asset_evidence",
                "cross_modal_evidence",
            },
        )


class BackendIsolationTests(unittest.TestCase):
    """The observer must not depend on a particular backend."""

    def test_pixel_backend_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(StdlibPixelBackend(), VisionBackend)

    def test_manual_backend_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(ManualAnnotationBackend(), VisionBackend)

    def test_mock_backend_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(MockDescriptorBackend(), VisionBackend)

    def test_observer_rejects_a_non_backend(self) -> None:
        class NotABackend:
            pass

        with self.assertRaises(ObserverError):
            FrameObserver(NotABackend())

    def test_all_backends_expose_an_evidence_source(self) -> None:
        for backend in (StdlibPixelBackend(), ManualAnnotationBackend(), MockDescriptorBackend()):
            self.assertIn(backend.evidence_source, EVIDENCE_SOURCES)

    def test_all_backends_expose_a_stable_id(self) -> None:
        for backend in (StdlibPixelBackend(), ManualAnnotationBackend(), MockDescriptorBackend()):
            self.assertTrue(backend.backend_id.strip())

    def test_observer_has_no_backend_specific_branching(self) -> None:
        """The frame observer must not name a concrete backend."""

        import inspect

        from multimodal_creator.observation import frame_observer

        source = inspect.getsource(frame_observer)
        for concrete in ("StdlibPixelBackend", "ManualAnnotationBackend", "MockDescriptorBackend"):
            self.assertNotIn(concrete, source, f"{concrete} is named in the observer")

    def test_no_perception_library_is_imported(self) -> None:
        package = Path(__file__).resolve().parents[2] / "multimodal_creator"
        forbidden = ("PIL", "cv2", "pytesseract", "easyocr", "numpy", "torch", "requests", "urllib")
        offenders: list[str] = []
        for path in sorted(package.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if f"import {token}" in text or f"from {token}" in text:
                    offenders.append(f"{path.name}:{token}")
        self.assertEqual(offenders, [], f"perception or network imports found: {offenders}")

    def test_no_ocr_or_character_recognition_exists(self) -> None:
        """No glyph matching, no character tables, anywhere in the package."""

        package = Path(__file__).resolve().parents[2] / "multimodal_creator"
        offenders: list[str] = []
        for path in sorted(package.rglob("*.py")):
            text = path.read_text(encoding="utf-8").lower()
            for token in ("pytesseract", "easyocr", "recognize_text", "read_text_from_image", "glyph_match"):
                if token in text:
                    offenders.append(f"{path.name}:{token}")
        self.assertEqual(offenders, [], f"OCR-like code found: {offenders}")


class ManualBackendTests(unittest.TestCase):
    """The annotation path must work without any perception at all."""

    def _annotation(self) -> dict:
        return {
            "regions": [
                {"region_id": "bg", "role": "background", "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "layer_order": 0},
                {"region_id": "t", "role": "title", "box": {"x": 0.05, "y": 0.1, "w": 0.9, "h": 0.15}, "layer_order": 1},
                {"region_id": "s", "role": "subject", "box": {"x": 0.55, "y": 0.1, "w": 0.4, "h": 0.6}, "layer_order": 1},
            ],
            "palette_relation": "complementary",
            "density": "balanced",
            "type_scale_relation": "two_level",
            "alignment": "left",
        }

    def test_manual_observation_is_produced(self) -> None:
        source = VisualSource("a1", "image", "unused.png", {"annotation": self._annotation()})
        result = FrameObserver(ManualAnnotationBackend()).observe(source)
        result.assert_complete()
        self.assertEqual(result.evidence_source, "manual_annotation")
        self.assertEqual(len(result.observation.regions), 3)

    def test_manual_backend_needs_an_annotation(self) -> None:
        source = VisualSource("a1", "image", "unused.png")
        with self.assertRaises(ObserverError):
            ManualAnnotationBackend().detect_regions(source)

    def test_annotation_missing_regions_is_rejected(self) -> None:
        source = VisualSource("a1", "image", "x.png", {"annotation": {"palette_relation": "muted"}})
        with self.assertRaises(ObserverError):
            ManualAnnotationBackend().detect_regions(source)

    def test_annotation_region_missing_fields_is_rejected(self) -> None:
        source = VisualSource(
            "a1", "image", "x.png", {"annotation": {"regions": [{"region_id": "r"}]}}
        )
        with self.assertRaises(ObserverError):
            ManualAnnotationBackend().detect_regions(source)

    def test_annotation_path_is_read_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "annotation.json"
            path.write_text(json.dumps(self._annotation()), encoding="utf-8")
            source = VisualSource("a1", "image", "unused.png", {"annotation_path": str(path)})
            result = FrameObserver(ManualAnnotationBackend()).observe(source)
            self.assertEqual(len(result.observation.regions), 3)

    def test_missing_annotation_file_is_reported(self) -> None:
        source = VisualSource("a1", "image", "x.png", {"annotation_path": "does-not-exist.json"})
        with self.assertRaises(ObserverError):
            ManualAnnotationBackend().detect_regions(source)

    def test_invalid_annotation_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            source = VisualSource("a1", "image", "x.png", {"annotation_path": str(path)})
            with self.assertRaises(ObserverError):
                ManualAnnotationBackend().detect_regions(source)

    def test_annotation_format_cannot_express_text(self) -> None:
        """A format that could carry text would invite an OCR shortcut."""

        from multimodal_creator.observation.manual_backend import ANNOTATION_KEYS

        for forbidden in ("text", "text_content", "ocr", "transcript", "words"):
            self.assertNotIn(forbidden, ANNOTATION_KEYS)


class CorpusValidationTests(unittest.TestCase):
    """Corpus defects must fail loudly, not quietly depress measured rates."""

    def test_shipped_templates_validate(self) -> None:
        validate_templates(build_templates())

    def test_ten_templates_exist(self) -> None:
        self.assertEqual(len(build_templates()), 10)

    def test_every_template_declares_an_expected_layout_class(self) -> None:
        for template_id, template in build_templates().items():
            self.assertTrue(
                template.expected_layout_class,
                f"{template_id} has no expected_layout_class",
            )

    def test_text_over_a_partial_block_is_rejected(self) -> None:
        from multimodal_creator.observation.corpus import RegionSpec, TemplateSpec

        broken = TemplateSpec(
            "broken",
            "broken",
            (
                RegionSpec("ground", "ground", 0.0, 0.0, 1.0, 1.0, layer=0),
                RegionSpec("title", "text", 0.1, 0.1, 0.5, 0.2),
                RegionSpec("img", "block", 0.3, 0.05, 0.5, 0.6),
            ),
        )
        with self.assertRaises(ValueError):
            validate_templates({"broken": broken})

    def test_text_over_a_full_bleed_block_is_allowed(self) -> None:
        from multimodal_creator.observation.corpus import RegionSpec, TemplateSpec

        overlay = TemplateSpec(
            "overlay",
            "overlay",
            (
                RegionSpec("img", "block", 0.0, 0.0, 1.0, 1.0, layer=0),
                RegionSpec("title", "text", 0.1, 0.4, 0.8, 0.2, layer=1),
            ),
        )
        validate_templates({"overlay": overlay})

    def test_region_outside_frame_is_rejected(self) -> None:
        from multimodal_creator.observation.corpus import RegionSpec, TemplateSpec

        out_of_frame = TemplateSpec(
            "oob",
            "oob",
            (RegionSpec("r", "block", 0.9, 0.9, 0.5, 0.5),),
        )
        with self.assertRaises(ValueError):
            validate_templates({"oob": out_of_frame})


class FrameObserverBehaviourTests(unittest.TestCase):
    """The observer must behave predictably on real rendered assets."""

    @classmethod
    def setUpClass(cls) -> None:
        from multimodal_creator.observation.corpus import (
            build_corpus,
            render_corpus,
        )

        cls._tmp = tempfile.TemporaryDirectory()
        samples, templates = build_corpus(only_hero=True)
        cls.written = render_corpus(
            cls._tmp.name, samples=samples[:6], templates=templates
        )
        cls.backend = StdlibPixelBackend()
        cls.observer = FrameObserver(cls.backend)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_observation_is_complete(self) -> None:
        for sample_id, path in self.written:
            result = self.observer.observe(VisualSource(sample_id, "image", path))
            self.assertTrue(result.is_complete(), sample_id)

    def test_observation_reports_all_four_families(self) -> None:
        sample_id, path = self.written[0]
        result = self.observer.observe(VisualSource(sample_id, "image", path))
        for family in EVIDENCE_FAMILIES:
            self.assertIn(family, result.evidence)

    def test_observation_carries_structural_evidence_only(self) -> None:
        from multimodal_creator.taxonomy import STRUCTURAL_EVIDENCE

        sample_id, path = self.written[0]
        result = self.observer.observe(VisualSource(sample_id, "image", path))
        self.assertNotIn("ocr_text", result.observation.evidence_kinds)
        for kind in result.observation.evidence_kinds:
            self.assertIn(kind, STRUCTURAL_EVIDENCE)

    def test_observation_is_deterministic(self) -> None:
        sample_id, path = self.written[0]
        first = self.observer.observe(VisualSource(sample_id, "image", path))
        second = self.observer.observe(VisualSource(sample_id, "image", path))
        self.assertEqual(first.observation, second.observation)

    def test_observation_regions_are_contract_valid(self) -> None:
        from multimodal_creator.taxonomy import REGION_ROLES

        sample_id, path = self.written[0]
        result = self.observer.observe(VisualSource(sample_id, "image", path))
        self.assertTrue(result.observation.regions)
        for region in result.observation.regions:
            self.assertIn(region["role"], REGION_ROLES)
            for key in ("x", "y", "w", "h"):
                self.assertGreaterEqual(region["box"][key], 0.0)
                self.assertLessEqual(region["box"][key], 1.0)

    def test_missing_asset_is_reported(self) -> None:
        with self.assertRaises(ObserverError):
            self.observer.observe(VisualSource("gone", "image", "missing.png"))

    def test_non_png_asset_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.png"
            path.write_bytes(b"definitely not a png")
            with self.assertRaises(ObserverError):
                self.observer.observe(VisualSource("fake", "image", str(path)))

    def test_duplicate_source_ids_are_rejected(self) -> None:
        sample_id, path = self.written[0]
        sources = [
            VisualSource("dup", "image", path),
            VisualSource("dup", "image", path),
        ]
        with self.assertRaises(ObserverError):
            self.observer.observe_all(sources)

    def test_result_serialises(self) -> None:
        sample_id, path = self.written[0]
        payload = self.observer.observe(
            VisualSource(sample_id, "image", path)
        ).as_dict()
        self.assertIn("evidence", payload)
        self.assertIn("observation", payload)


class VideoSequenceObserverTests(unittest.TestCase):
    """Frame sequences must observe consistently and record rhythm."""

    @classmethod
    def setUpClass(cls) -> None:
        from multimodal_creator.observation.corpus import build_corpus, render_corpus

        cls._tmp = tempfile.TemporaryDirectory()
        samples, templates = build_corpus(only_hero=True)
        cls.written = render_corpus(
            cls._tmp.name, samples=samples[:2], templates=templates
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_sequence_observation_runs(self) -> None:
        sources = [
            VisualSource(f"{sid}:f{index}", "video_frame", path)
            for index, (sid, path) in enumerate(self.written)
        ]
        results = VideoSequenceObserver(StdlibPixelBackend()).observe_sequence(sources)
        self.assertEqual(len(results), len(sources))

    def test_sequence_records_position_and_length(self) -> None:
        sources = [
            VisualSource(f"{sid}:f{index}", "video_frame", path)
            for index, (sid, path) in enumerate(self.written)
        ]
        results = VideoSequenceObserver(StdlibPixelBackend()).observe_sequence(sources)
        for index, result in enumerate(results):
            detail = result.evidence["cross_modal_evidence"].detail
            self.assertEqual(detail["sequence_index"], index)
            self.assertEqual(detail["sequence_length"], len(sources))

    def test_empty_sequence_is_rejected(self) -> None:
        with self.assertRaises(ObserverError):
            VideoSequenceObserver(StdlibPixelBackend()).observe_sequence([])

    def test_video_frames_may_claim_temporal_rhythm(self) -> None:
        source = VisualSource("f1", "video_frame", self.written[0][1])
        result = FrameObserver(StdlibPixelBackend()).observe(source)
        self.assertEqual(result.observation.medium, "video")


if __name__ == "__main__":
    unittest.main()
