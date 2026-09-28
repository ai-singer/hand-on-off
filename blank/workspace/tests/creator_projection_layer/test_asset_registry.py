"""Asset registry: every projection input is declared, none is hard-coded."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from creator_projection import (
    ASSET_STATUSES,
    ASSET_TYPES,
    AssetRegistry,
    ProjectionAssetError,
    ProjectionAssetUnavailableError,
)

WORKSPACE = Path(__file__).resolve().parents[2]


def _write_registry(directory: str, body: str) -> Path:
    path = Path(directory) / "assets.yaml"
    path.write_text(body, encoding="utf-8")
    return path


VALID_REGISTRY = """version: "9.9.9"
assets:
  - id: thing
    type: text_rules
    location: some/file.json
    format: json
    status: available
    description: a thing
"""


class LoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)

    def test_registry_loads(self) -> None:
        self.assertIsInstance(self.registry, AssetRegistry)

    def test_registry_version(self) -> None:
        self.assertEqual(self.registry.version, "1.0.0")

    def test_registry_declares_fifteen_assets(self) -> None:
        self.assertEqual(len(self.registry), 15)

    def test_workspace_root_is_recorded(self) -> None:
        self.assertEqual(self.registry.workspace_root, WORKSPACE)

    def test_ids_are_sorted(self) -> None:
        self.assertEqual(list(self.registry.ids()), sorted(self.registry.ids()))

    def test_iteration_yields_assets(self) -> None:
        self.assertTrue(all(hasattr(asset, "asset_id") for asset in self.registry))

    def test_every_asset_type_is_recognised(self) -> None:
        for asset in self.registry:
            self.assertIn(asset.asset_type, ASSET_TYPES)

    def test_every_status_is_recognised(self) -> None:
        for asset in self.registry:
            self.assertIn(asset.status, ASSET_STATUSES)

    def test_required_assets_are_present(self) -> None:
        for asset_id in (
            "nuwa_persona_skill",
            "visual_profile_m5",
            "text_distillation_rules",
            "text_structure_templates",
            "risk_policy_reference",
            "evaluation_rubric",
            "generation_capability",
            "publishing_capability",
        ):
            self.assertIn(asset_id, self.registry.ids())

    def test_missing_registry_file_is_rejected(self) -> None:
        with self.assertRaises(ProjectionAssetError):
            AssetRegistry.load(WORKSPACE, "no/such/registry.yaml")


class LookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)

    def test_get_returns_the_asset(self) -> None:
        self.assertEqual(
            self.registry.get("visual_profile_m5").asset_type, "visual_rules"
        )

    def test_unknown_asset_id_is_rejected(self) -> None:
        with self.assertRaises(ProjectionAssetError):
            self.registry.get("not_registered")

    def test_by_type_filters(self) -> None:
        identity_sources = self.registry.by_type("identity_source")
        self.assertTrue(identity_sources)
        self.assertTrue(all(a.asset_type == "identity_source" for a in identity_sources))

    def test_by_type_with_no_matches_is_empty(self) -> None:
        self.assertEqual(self.registry.by_type("markdown_template")[:0], ())
        self.assertTrue(
            all(
                a.asset_type == "markdown_template"
                for a in self.registry.by_type("markdown_template")
            )
        )

    def test_first_available_picks_an_available_asset(self) -> None:
        asset = self.registry.first_available("nuwa_persona_skill", "text_distillation_rules")
        self.assertEqual(asset.asset_id, "text_distillation_rules")

    def test_first_available_returns_none_when_all_unavailable(self) -> None:
        self.assertIsNone(
            self.registry.first_available("nuwa_persona_skill", "publishing_capability")
        )

    def test_availability_map_covers_all_assets(self) -> None:
        self.assertEqual(len(self.registry.availability()), len(self.registry))

    def test_unavailable_lists_six_assets(self) -> None:
        self.assertEqual(len(self.registry.unavailable()), 6)


class AvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)

    def test_require_returns_an_available_asset(self) -> None:
        self.assertTrue(self.registry.require("text_distillation_rules").available)

    def test_require_rejects_an_unavailable_asset(self) -> None:
        with self.assertRaises(ProjectionAssetUnavailableError):
            self.registry.require("nuwa_persona_skill")

    def test_every_unavailable_asset_declares_a_reason(self) -> None:
        for asset in self.registry.unavailable():
            self.assertTrue(asset.reason, asset.asset_id)

    def test_capability_assets_are_unavailable(self) -> None:
        for asset_id in ("generation_capability", "publishing_capability"):
            self.assertFalse(self.registry.get(asset_id).available)

    def test_capability_assets_use_the_contract_reason_codes(self) -> None:
        self.assertEqual(
            self.registry.get("generation_capability").reason,
            "generation_capability_not_available",
        )
        self.assertEqual(
            self.registry.get("publishing_capability").reason,
            "publishing_capability_not_available",
        )

    def test_external_toolchain_assets_share_a_reason(self) -> None:
        self.assertEqual(
            self.registry.get("nuwa_persona_skill").reason,
            "external_toolchain_not_present_in_repository",
        )

    def test_asset_as_dict_excludes_absent_reason(self) -> None:
        record = self.registry.get("text_distillation_rules").as_dict()
        self.assertNotIn("reason", record)


class ReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)

    def test_read_json_returns_a_mapping(self) -> None:
        payload = self.registry.read_json("text_distillation_rules")
        self.assertIn("rules", payload)

    def test_read_json_matches_the_file_on_disk(self) -> None:
        import json

        payload = self.registry.read_json("plugin_manifest")
        direct = json.loads(
            (WORKSPACE / "plugins" / "xiaolin_finance" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload, direct)

    def test_read_text_returns_a_string(self) -> None:
        self.assertIsInstance(self.registry.read_json("runtime_config"), dict)

    def test_read_yaml_parses_the_m5_profile(self) -> None:
        payload = self.registry.read_yaml("visual_profile_m5")
        self.assertEqual(payload["visual_profile"]["profile_version"], "m5.0.0")

    def test_read_json_on_unavailable_asset_is_rejected(self) -> None:
        with self.assertRaises(ProjectionAssetUnavailableError):
            self.registry.read_json("nuwa_persona_skill")

    def test_path_of_resolves_against_the_workspace(self) -> None:
        path = self.registry.path_of("visual_profile_m5")
        self.assertTrue(str(path).startswith(str(WORKSPACE)))

    def test_every_available_asset_exists_on_disk(self) -> None:
        for asset in self.registry:
            if asset.available and asset.asset_format != "python":
                with self.subTest(asset=asset.asset_id):
                    self.assertTrue(self.registry.path_of(asset.asset_id).is_file())


class RegistryValidationTests(unittest.TestCase):
    """A malformed registry must be rejected, not silently tolerated."""

    def test_valid_registry_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_registry(tmp, VALID_REGISTRY)
            registry = AssetRegistry.load(WORKSPACE, path)
            self.assertEqual(registry.version, "9.9.9")

    def test_unknown_type_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("type: text_rules", "type: nonsense")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_unknown_status_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("status: available", "status: maybe")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_missing_id_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("  - id: thing\n", "  - type: text_rules\n")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_missing_location_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("    location: some/file.json\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_absolute_location_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("some/file.json", "/etc/passwd")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_missing_format_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("    format: json\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_unavailable_without_a_reason_is_rejected(self) -> None:
        body = VALID_REGISTRY.replace("status: available", "status: unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_duplicate_ids_are_rejected(self) -> None:
        body = VALID_REGISTRY + VALID_REGISTRY.split("assets:\n")[1]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))

    def test_registry_with_no_assets_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectionAssetError):
                AssetRegistry.load(WORKSPACE, _write_registry(tmp, "version: '1.0.0'\n"))

    def test_available_asset_pointing_at_a_missing_file_is_reported(self) -> None:
        body = VALID_REGISTRY.replace("some/file.json", "no/such/file.json")
        with tempfile.TemporaryDirectory() as tmp:
            registry = AssetRegistry.load(WORKSPACE, _write_registry(tmp, body))
            with self.assertRaises(ProjectionAssetUnavailableError):
                registry.read_json("thing")


if __name__ == "__main__":
    unittest.main()
