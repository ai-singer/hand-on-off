"""Step 3: the adapter layer - uniform interface, delegation, no copied logic."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3.adapters import AdapterError, AdapterResult, require_adapters
from risk_evaluation.v3.adapters import attribution as attribution_adapter
from risk_evaluation.v3.adapters import intent_pattern as intent_adapter
from risk_evaluation.v3.adapters import semantic as semantic_adapter
from risk_evaluation.v3.model import ClaimInput, ModelError
from risk_evaluation.v3.patterns import PATTERNS


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE_ROOT / "risk_evaluation" / "v3"

GUARANTEE_TEXT = "This return is guaranteed."


def _input(text: str, *, claim_id: str = "claim-001", span=(0, 0)) -> ClaimInput:
    return ClaimInput(claim_id, text, span or (0, len(text)), text)


class AdapterResultTests(unittest.TestCase):
    def test_a_result_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            AdapterResult(adapter="x", claim_id="c-1", evidence=())

    def test_a_result_needs_an_adapter_name(self) -> None:
        with self.assertRaises(ModelError):
            AdapterResult(adapter="", claim_id="c-1", evidence=("x",))

    def test_a_result_needs_a_claim_id(self) -> None:
        with self.assertRaises(ModelError):
            AdapterResult(adapter="x", claim_id="", evidence=("x",))

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(
            AdapterResult(adapter="x", claim_id="c-1", evidence=("x",)).as_dict()
        )


class AdapterRegistryTests(unittest.TestCase):
    def test_an_empty_adapter_list_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            require_adapters(())

    def test_duplicate_names_are_rejected(self) -> None:
        adapter = semantic_adapter.SemanticAdapter()

        with self.assertRaises(AdapterError):
            require_adapters((adapter, adapter))

    def test_an_object_without_evaluate_is_rejected(self) -> None:
        class NotAnAdapter:
            name = "nope"

        with self.assertRaises(AdapterError):
            require_adapters((NotAnAdapter(),))

    def test_the_three_adapters_have_unique_names(self) -> None:
        names = [
            attribution_adapter.AttributionAdapter().name,
            intent_adapter.IntentPatternAdapter().name,
            semantic_adapter.SemanticAdapter().name,
        ]

        self.assertEqual(names, ["attribution", "intent_pattern", "semantic"])


class AttributionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = attribution_adapter.AttributionAdapter()

    def test_it_extracts_claims_with_spans(self) -> None:
        claims = self.adapter.extract("Analysts expect growth. However, we disagree.")

        self.assertEqual(len(claims), 2)
        self.assertTrue(all(item.span[1] > item.span[0] for item in claims))

    def test_it_returns_a_speaker_and_a_stance(self) -> None:
        result = self.adapter.evaluate(_input("We believe the fund is safe."))

        self.assertEqual(result.speaker, "author")
        self.assertIn(result.stance, ("endorsed", "quoted", "rejected", "uncertain"))

    def test_it_carries_evidence(self) -> None:
        result = self.adapter.evaluate(_input("We believe the fund is safe."))

        self.assertTrue(result.evidence)

    def test_stance_uses_the_source_text_not_the_claim_alone(self) -> None:
        """The backward rejection needs the next sentence to be visible."""

        text = "Analysts expect growth. However, we disagree."
        first = self.adapter.extract(text)[0]
        result = self.adapter.evaluate(first)

        self.assertEqual(result.stance, "rejected")

    def test_it_reports_a_claim_the_layer_did_not_produce(self) -> None:
        stranded = ClaimInput("claim-999", "x", (0, 1), "nothing here", index=99)
        result = self.adapter.evaluate(stranded)

        self.assertFalse(result.available)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.adapter.evaluate(_input(GUARANTEE_TEXT)).as_dict())


class IntentPatternAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = intent_adapter.IntentPatternAdapter()

    def test_it_finds_the_guarantee_relation(self) -> None:
        result = self.adapter.evaluate(_input(GUARANTEE_TEXT))
        relations = {item.relation for item in result.intents}

        self.assertIn("GUARANTEE", relations)

    def test_it_binds_the_entity_type(self) -> None:
        result = self.adapter.evaluate(_input(GUARANTEE_TEXT))
        guarantee = [i for i in result.intents if i.relation == "GUARANTEE"][0]

        self.assertEqual(guarantee.entity, "RETURN")

    def test_it_reports_the_frame_kind(self) -> None:
        result = self.adapter.evaluate(_input(GUARANTEE_TEXT))
        guarantee = [i for i in result.intents if i.relation == "GUARANTEE"][0]

        self.assertEqual(guarantee.frame, "copular")

    def test_the_evidence_marker_names_the_frame(self) -> None:
        result = self.adapter.evaluate(_input(GUARANTEE_TEXT))

        self.assertTrue(any("copular_guarantee_pattern" in e for e in result.evidence))

    def test_a_silent_claim_records_the_absence(self) -> None:
        result = self.adapter.evaluate(_input("The company reports its results in March."))

        self.assertEqual(result.intents, ())
        self.assertIn("rule:intent_pattern.no-relation", result.evidence)

    def test_it_uses_the_v3_pattern_set(self) -> None:
        self.assertEqual(self.adapter.matcher.patterns.name, PATTERNS.name)

    def test_it_does_not_hold_its_own_matcher_logic(self) -> None:
        """The matcher is Phase 8.4's class, not a copy."""

        from risk_evaluation.intent_patterns.matcher import RelationMatcher

        self.assertIsInstance(self.adapter.matcher, RelationMatcher)

    def test_a_non_claim_input_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            self.adapter.evaluate("not a claim")  # type: ignore[arg-type]

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.adapter.evaluate(_input(GUARANTEE_TEXT)).as_dict())


class SemanticAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = semantic_adapter.SemanticAdapter()

    def test_it_returns_categories(self) -> None:
        result = self.adapter.evaluate(_input("This is a guaranteed return."))

        self.assertEqual(result.categories, ("financial_guarantee",))

    def test_it_names_the_evaluator_it_delegates_to(self) -> None:
        self.assertEqual(self.adapter.evaluator_name, "semantic-intent-v2")

    def test_it_records_why_it_was_asked(self) -> None:
        result = self.adapter.evaluate(
            _input("This is a guaranteed return."), searched_because="test"
        )

        self.assertEqual(result.detail["searched_because"], "test")
        self.assertTrue(any("test" in e for e in result.evidence))

    def test_raw_returns_the_evaluators_own_results(self) -> None:
        raw = self.adapter.raw("This is a guaranteed return.")

        self.assertTrue(raw)
        self.assertEqual(raw[0].evaluator, "semantic-intent-v2")

    def test_a_silent_claim_records_the_absence(self) -> None:
        result = self.adapter.evaluate(_input("The company reports its results in March."))

        self.assertEqual(result.categories, ())
        self.assertTrue(any("rule:semantic.no-category" in e for e in result.evidence))

    def test_the_blind_spot_is_still_the_evaluators(self) -> None:
        """The adapter reports what v2 says; it does not repair it.

        `This return is guaranteed.` is a Phase 8.1 defect of the evaluator. The
        adapter must not paper over it, or the pipeline would have no way to
        show that the intent layer is what closes it.
        """

        result = self.adapter.evaluate(_input(GUARANTEE_TEXT))

        self.assertEqual(result.categories, ())

    def test_a_non_claim_input_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            self.adapter.evaluate("nope")  # type: ignore[arg-type]

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.adapter.evaluate(_input(GUARANTEE_TEXT)).as_dict())


class NoCopiedImplementationTests(unittest.TestCase):
    """The adapters convert protocols; they do not reimplement anything."""

    def _sources(self):
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in (PACKAGE / "adapters").rglob("*.py")
        }

    def test_the_adapters_do_not_redefine_the_signal_patterns(self) -> None:
        for name, text in self._sources().items():
            for token in ("SIGNAL_PATTERNS", "INTENT_PATTERNS", "HEDGE_MARKERS ="):
                self.assertNotIn(token, text, name)

    def test_the_adapters_do_not_redefine_the_entity_lexicon(self) -> None:
        """The lexicon lives in patterns.py, once."""

        for name, text in self._sources().items():
            self.assertNotIn("EntityLexicon(", text, name)

    def test_the_adapters_import_the_layers_they_wrap(self) -> None:
        sources = self._sources()
        combined = "\n".join(sources.values())

        self.assertIn("risk_evaluation.attribution", combined.replace("...", "risk_evaluation."))
        self.assertIn("intent_patterns", combined)

    def test_the_adapters_do_not_patch_anything(self) -> None:
        for name, text in self._sources().items():
            for token in ("setattr(", "monkeypatch"):
                self.assertNotIn(token, text, name)


if __name__ == "__main__":
    unittest.main()
