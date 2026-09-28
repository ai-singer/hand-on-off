"""Negative tests: the contract must reject the four named defect classes.

The phase brief names four mandatory rejections:

1. an instance that contains code (``python:``) — rejected;
2. visual rules that contain a generation prompt (``prompt: create image``) —
   rejected;
3. an empty risk policy — rejected;
4. an instance with no provenance — rejected.

Each is covered here explicitly and by name, then extended with adjacent cases
so the boundary is tested rather than the example.
"""

from __future__ import annotations

import copy
import unittest

from creator_contract import (
    CreatorContractDependencyError,
    CreatorContractError,
    CreatorContractIsolationError,
    assert_no_generation_prompt,
    assert_no_runtime_code,
    assert_risk_policy_not_empty,
    minimal_instance,
    validate,
)


class Negative1InstanceContainsCodeTests(unittest.TestCase):
    """Req 1: ``python:`` in an instance must be rejected."""

    def test_literal_python_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["python"] = "print('hello')"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_python_key_nested_in_text_rules_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["python"] = "def render(): pass"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_python_key_nested_in_identity_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["persona"]["python"] = "import os"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_code_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["generation"]["code"] = "requests.get(url)"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_script_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["source"]["script"] = "scrape_two_stage.py"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_subprocess_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["subprocess"] = "ffmpeg"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_a_model_call_declaration_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["generation"]["model_call"] = "openai.chat"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_crawler_code_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["source"]["crawler"] = "aiohttp"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_a_python_def_in_a_string_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["tone"]["voice"] = "def build_prompt(): return 'x'"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_an_import_in_a_string_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["persona"]["identity_card"] = "import subprocess"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_runtime_module_import_path_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["generation"]["adapter_ref"] = "distillation_core.engine"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_code_is_rejected_however_deeply_nested(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["review_rules"][0]["code"] = "x = 1"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)


class Negative2VisualContainsGenerationPromptTests(unittest.TestCase):
    """Req 2: ``prompt: create image`` in visual rules must be rejected."""

    def test_literal_prompt_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["prompt"] = "create image"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_prompt_key_with_an_image_instruction_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["prompt"] = "create image of a rocket"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_system_prompt_key_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["system_prompt"] = "you are a designer"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_negative_prompt_key_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["negative_prompt"] = "no text"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_model_reference_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["model"] = "sdxl"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_diffusion_settings_are_rejected(self) -> None:
        for key in ("diffusion", "checkpoint", "lora", "seed", "steps", "cfg_scale", "sampler"):
            with self.subTest(key=key):
                visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
                visual_rules[key] = 1
                with self.assertRaises(CreatorContractIsolationError):
                    assert_no_generation_prompt(visual_rules)

    def test_image_data_is_rejected(self) -> None:
        for key in ("image", "images", "image_data", "image_bytes", "pixels", "base64"):
            with self.subTest(key=key):
                visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
                visual_rules[key] = "AAAA"
                with self.assertRaises(CreatorContractIsolationError):
                    assert_no_generation_prompt(visual_rules)

    def test_publish_target_inside_visual_rules_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["publish_target"] = "xiaohongshu"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_api_key_inside_visual_rules_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["api_key"] = "sk-xxx"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_a_prompt_phrase_under_an_innocent_key_is_rejected(self) -> None:
        """Key-name checks alone are not enough; content is checked too."""

        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["visual_language"] = "generate image of a factory"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_midjourney_phrase_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["visual_language"] = "midjourney style"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_stable_diffusion_phrase_is_rejected(self) -> None:
        visual_rules = minimal_instance()["visual_rules"]
        visual_rules["visual_language"] = "stable diffusion aesthetic"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_a_clean_reference_only_visual_block_passes(self) -> None:
        assert_no_generation_prompt(minimal_instance()["visual_rules"])


class Negative3EmptyRiskPolicyTests(unittest.TestCase):
    """Req 3: an instance without risk rules must be rejected."""

    def test_empty_risk_rules_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_rules"] = {}
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_empty_risk_categories_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["risk_categories"] = []
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_empty_review_rules_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["review_rules"] = []
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_empty_blocked_patterns_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["blocked_patterns"] = []
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_risk_policy_emptied_of_all_content_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"] = {
            "risk_categories": [],
            "review_rules": [],
            "blocked_patterns": [],
            "evidence_requirement": {
                "require_source_ids": True,
                "min_first_party_ratio": 0.5,
            },
        }
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_risk_policy_helper_rejects_empty_categories(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["risk_categories"] = []
        with self.assertRaises(CreatorContractDependencyError):
            assert_risk_policy_not_empty(instance)

    def test_missing_risk_policy_helper_input_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractDependencyError):
            assert_risk_policy_not_empty({})


class Negative4NoProvenanceTests(unittest.TestCase):
    """Req 4: an instance with no provenance must be rejected."""

    def test_missing_provenance_block_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["provenance"]
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_empty_provenance_block_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["provenance"] = {}
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_partial_provenance_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["provenance"] = {"identity": {"source": "nuwa_skill"}}
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_a_single_missing_provenance_entry_is_rejected(self) -> None:
        for module in (
            "identity",
            "source",
            "text_rules",
            "visual_rules",
            "risk_policy",
            "generation",
            "publishing",
        ):
            with self.subTest(module=module):
                instance = minimal_instance()
                del instance["provenance"][module]
                with self.assertRaises(CreatorContractError):
                    validate(instance)

    def test_provenance_entry_without_a_source_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["provenance"]["visual_rules"] = {"derivation": "referenced"}
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_provenance_entry_with_a_blank_source_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["provenance"]["visual_rules"]["source"] = ""
        with self.assertRaises(CreatorContractError):
            validate(instance)


class NegativeCrossCuttingTests(unittest.TestCase):
    """Defects that combine two classes must still be reported."""

    def test_code_and_empty_risk_are_both_rejected(self) -> None:
        instance = minimal_instance()
        instance["python"] = "x = 1"
        instance["risk_policy"]["risk_categories"] = []
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_prompt_and_missing_provenance_are_both_rejected(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["prompt"] = "create image"
        del instance["provenance"]["visual_rules"]
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_an_instance_that_is_entirely_empty_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractError):
            validate({})

    def test_a_valid_instance_is_not_rejected(self) -> None:
        """The negative suite must not be passing for the wrong reason."""

        self.assertTrue(validate(minimal_instance()).passed)


if __name__ == "__main__":
    unittest.main()
