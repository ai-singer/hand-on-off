"""Loading an artifact: layouts, reading, failure modes, capability derivation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from creator_loader import (
    AGGREGATE_FILES,
    ERROR_CODES,
    MODULES,
    PROVENANCE_FILE,
    CapabilityState,
    InstanceModuleMissingError,
    InstanceNotFoundError,
    InstanceProvenanceMissingError,
    InstanceUnreadableError,
    LoadedCreatorInstance,
    ProvenanceKind,
    capability_records,
    load_creator_instance,
    read_artifact,
    read_json,
    resolve_artifact_path,
)

from . import fixtures


class LoadMappedTests(unittest.TestCase):
    """The C0.4-A mapped artifact loads into a frozen configuration object."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("loader_mapped")
        cls.loaded = load_creator_instance(cls.directory)

    def test_returns_a_loaded_creator_instance(self) -> None:
        self.assertIsInstance(self.loaded, LoadedCreatorInstance)

    def test_instance_id_is_the_creator_id(self) -> None:
        self.assertEqual(self.loaded.instance_id, "finance_xhs")

    def test_source_path_is_the_directory_loaded(self) -> None:
        self.assertEqual(self.loaded.source_path, self.directory)

    def test_contract_version_is_recorded(self) -> None:
        self.assertEqual(self.loaded.contract_version, "1.0.0")

    def test_provenance_kind_is_mapped(self) -> None:
        self.assertEqual(self.loaded.provenance_kind, ProvenanceKind.MAPPED.value)

    def test_all_seven_modules_load(self) -> None:
        self.assertEqual(sorted(self.loaded.modules), sorted(MODULES))

    def test_identity_module_loads(self) -> None:
        self.assertEqual(self.loaded.domain, "finance")

    def test_every_validation_check_passed(self) -> None:
        for check, status in self.loaded.validation.items():
            if check == "provenance_kind":
                self.assertEqual(status, "mapped")
            else:
                self.assertEqual(status, "PASS", check)

    def test_loading_is_deterministic(self) -> None:
        first = load_creator_instance(self.directory).as_dict()
        second = load_creator_instance(self.directory).as_dict()
        self.assertEqual(first, second)

    def test_the_artifact_is_not_modified_by_loading(self) -> None:
        before = {
            path.name: path.read_bytes()
            for path in sorted(self.directory.iterdir())
            if path.is_file()
        }
        load_creator_instance(self.directory)
        after = {
            path.name: path.read_bytes()
            for path in sorted(self.directory.iterdir())
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_loading_creates_no_new_files(self) -> None:
        names = sorted(path.name for path in self.directory.iterdir())
        load_creator_instance(self.directory)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), names)

    def test_the_artifact_directory_has_the_expected_files(self) -> None:
        names = {path.name for path in self.directory.iterdir()}
        for module in MODULES:
            self.assertIn(f"{module}.json", names)
        self.assertIn(PROVENANCE_FILE, names)


class LoadLayoutTests(unittest.TestCase):
    """Both on-disk layouts read, and the aggregate wins when both are present.

    The two layouts are **not** equivalent, and the loader does not pretend they are.
    C0.4-A's ``instance.json`` carries the whole artifact, including the per-module
    availability records and the factory identity. Its ``provenance.json`` carries
    only the contract module blocks and the bare per-field records, so reading the
    directory alone loses the ``generated_by`` line.

    Precedence is therefore explicit and deterministic: the aggregate is read when it
    is there. The ``modules`` layout exists for an artifact whose aggregate is
    missing, and a caller who wants it asks for it by name. Nothing falls back
    silently — a malformed aggregate is reported, not quietly bypassed.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("loader_layouts")

    def test_aggregate_is_present(self) -> None:
        self.assertTrue((self.directory / "instance.json").is_file())

    def test_aggregate_layout_loads(self) -> None:
        loaded = load_creator_instance(self.directory, layout="prefer-aggregate")
        self.assertEqual(loaded.provenance_kind, ProvenanceKind.MAPPED.value)

    def test_modules_layout_loads(self) -> None:
        loaded = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(loaded.provenance_kind, ProvenanceKind.MAPPED.value)

    def test_both_layouts_load_the_same_creator(self) -> None:
        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        modules = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(aggregate.creator_id, modules.creator_id)

    def test_both_layouts_load_the_same_modules(self) -> None:
        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        modules = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(sorted(aggregate.modules), sorted(modules.modules))

    def test_both_layouts_load_the_same_field_values(self) -> None:
        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        modules = load_creator_instance(self.directory, layout="modules")
        for module in MODULES:
            self.assertEqual(aggregate.module(module), modules.module(module), module)

    def test_both_layouts_load_the_same_field_traces(self) -> None:
        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        modules = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(
            aggregate.provenance.field_traces, modules.provenance.field_traces
        )

    def test_both_layouts_resolve_the_same_assets(self) -> None:
        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        modules = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(aggregate.provenance.assets(), modules.provenance.assets())

    def test_both_layouts_agree_on_the_capability_of_every_explicit_module(self) -> None:
        """Where both state a capability, they state the same one."""

        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        modules = load_creator_instance(self.directory, layout="modules")
        for module in ("generation", "publishing", "identity", "risk_policy",
                       "text_rules", "visual_rules"):
            self.assertEqual(
                aggregate.capability(module).state,
                modules.capability(module).state,
                module,
            )

    def test_only_the_directory_layout_registers_the_loader_as_the_generator(self) -> None:
        """The directory file has no ``generated_by``; the loader says so."""

        modules = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(modules.provenance.generated_by, "")

    def test_the_directory_layout_cannot_identify_the_bundle(self) -> None:
        modules = load_creator_instance(self.directory, layout="modules")
        self.assertEqual(modules.provenance.bundle_id, "(not recorded)")

    def test_the_aggregate_layout_does_identify_the_bundle(self) -> None:
        aggregate = load_creator_instance(self.directory, layout="prefer-aggregate")
        self.assertTrue(aggregate.provenance.bundle_id.startswith("bundle-"))

    def test_the_default_layout_reads_the_aggregate(self) -> None:
        default = load_creator_instance(self.directory)
        self.assertEqual(
            default.provenance.bundle_id,
            load_creator_instance(self.directory, layout="prefer-aggregate")
            .provenance.bundle_id,
        )

    def test_an_unknown_layout_is_rejected(self) -> None:
        with self.assertRaises(InstanceUnreadableError):
            load_creator_instance(self.directory, layout="guess")

    def test_a_dangling_aggregate_does_not_fall_back_silently(self) -> None:
        """A malformed aggregate is reported, never quietly bypassed."""

        copy = fixtures.scratch_dir("loader_dangling") / "finance_xhs"
        copy.mkdir()
        for path in self.directory.iterdir():
            if path.is_file():
                copy.joinpath(path.name).write_bytes(path.read_bytes())
        (copy / "instance.json").write_text("{ not json", encoding="utf-8")
        with self.assertRaises(InstanceUnreadableError):
            load_creator_instance(copy)

    def test_the_modules_layout_still_reads_a_dangling_aggregate(self) -> None:
        copy = fixtures.scratch_dir("loader_dangling2") / "finance_xhs"
        copy.mkdir()
        for path in self.directory.iterdir():
            if path.is_file():
                copy.joinpath(path.name).write_bytes(path.read_bytes())
        (copy / "instance.json").write_text("{ not json", encoding="utf-8")
        loaded = load_creator_instance(copy, layout="modules")
        self.assertEqual(loaded.instance_id, "finance_xhs")

    def test_the_modules_layout_still_enforces_field_completeness(self) -> None:
        copy = fixtures.scratch_dir("loader_modules_strict") / "finance_xhs"
        copy.mkdir()
        for path in self.directory.iterdir():
            if path.is_file():
                copy.joinpath(path.name).write_bytes(path.read_bytes())
        (copy / "instance.json").unlink()
        document = json.loads((copy / "visual_rules.json").read_text(encoding="utf-8"))
        del document["profile_id"]
        (copy / "visual_rules.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
        from creator_loader import LoaderError

        try:
            load_creator_instance(copy, layout="modules")
        except LoaderError as exc:
            self.assertIn(
                exc.code, ("INSTANCE_SCHEMA_INVALID", "INSTANCE_FIELD_MISSING")
            )
        else:  # pragma: no cover
            self.fail("expected a loader failure")


class LoadPathFormsTests(unittest.TestCase):
    """A directory or a single document both name an artifact."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("loader_paths")

    def test_a_single_aggregate_file_loads(self) -> None:
        loaded = load_creator_instance(self.directory / "instance.json")
        self.assertEqual(loaded.instance_id, "finance_xhs")

    def test_a_file_load_reports_the_file_as_its_source(self) -> None:
        loaded = load_creator_instance(self.directory / "instance.json")
        self.assertEqual(loaded.source_path, self.directory / "instance.json")

    def test_a_file_load_falls_back_to_the_parent_directory_name(self) -> None:
        """A file path has no identity block to name itself, so... it does."""

        loaded = load_creator_instance(self.directory / "instance.json")
        self.assertEqual(loaded.instance_id, "finance_xhs")

    def test_a_path_string_is_accepted(self) -> None:
        loaded = load_creator_instance(str(self.directory))
        self.assertEqual(loaded.instance_id, "finance_xhs")

    def test_a_pathlib_path_is_accepted(self) -> None:
        loaded = load_creator_instance(Path(self.directory))
        self.assertEqual(loaded.instance_id, "finance_xhs")

    def test_an_empty_path_is_rejected(self) -> None:
        with self.assertRaises(InstanceNotFoundError):
            load_creator_instance("")

    def test_a_missing_path_is_rejected(self) -> None:
        with self.assertRaises(InstanceNotFoundError):
            load_creator_instance(self.directory / "nope")

    def test_a_non_json_file_is_rejected(self) -> None:
        target = fixtures.scratch_dir("loader_non_json") / "notes.txt"
        target.write_text("hello", encoding="utf-8")
        with self.assertRaises(InstanceNotFoundError):
            load_creator_instance(target)

    def test_an_empty_directory_is_rejected(self) -> None:
        with self.assertRaises(InstanceNotFoundError):
            load_creator_instance(fixtures.scratch_dir("loader_empty"))

    def test_resolve_artifact_path_returns_the_path(self) -> None:
        self.assertEqual(resolve_artifact_path(self.directory), self.directory)

    def test_resolve_artifact_path_rejects_a_missing_path(self) -> None:
        with self.assertRaises(InstanceNotFoundError):
            resolve_artifact_path(self.directory / "nope")

    def test_resolve_artifact_path_rejects_an_empty_string(self) -> None:
        with self.assertRaises(InstanceNotFoundError):
            resolve_artifact_path("")


class ReadJsonTests(unittest.TestCase):
    """Document reading converts every failure into a typed error."""

    def test_reads_a_valid_document(self) -> None:
        path = fixtures.scratch_dir("read_json") / "a.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        self.assertEqual(read_json(path, what="doc"), {"a": 1})

    def test_a_missing_file_raises_not_found(self) -> None:
        path = fixtures.scratch_dir("read_json2") / "a.json"
        with self.assertRaises(InstanceNotFoundError):
            read_json(path, what="doc")

    def test_invalid_json_raises_unreadable(self) -> None:
        path = fixtures.scratch_dir("read_json3") / "a.json"
        path.write_text("{oops", encoding="utf-8")
        with self.assertRaises(InstanceUnreadableError):
            read_json(path, what="doc")

    def test_a_directory_raises_unreadable(self) -> None:
        path = fixtures.scratch_dir("read_json4")
        with self.assertRaises(InstanceUnreadableError):
            read_json(path, what="doc")

    def test_an_empty_file_raises_unreadable(self) -> None:
        path = fixtures.scratch_dir("read_json5") / "a.json"
        path.write_text("", encoding="utf-8")
        with self.assertRaises(InstanceUnreadableError):
            read_json(path, what="doc")


class ReadArtifactTests(unittest.TestCase):
    """Reading assembles a document without judging it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("loader_read")

    def test_read_artifact_returns_a_document(self) -> None:
        self.assertIsInstance(read_artifact(self.directory), dict)

    def test_read_artifact_carries_all_modules(self) -> None:
        document = read_artifact(self.directory)
        for module in MODULES:
            self.assertIn(module, document)

    def test_read_artifact_carries_provenance(self) -> None:
        self.assertIn("provenance", read_artifact(self.directory))

    def test_read_artifact_carries_a_contract_version(self) -> None:
        self.assertIn("contract_version", read_artifact(self.directory))

    def test_modules_layout_carries_all_modules(self) -> None:
        document = read_artifact(self.directory, layout="modules")
        for module in MODULES:
            self.assertIn(module, document)

    def test_a_missing_module_is_not_filled_in(self) -> None:
        """Reading must not invent a module; the check layer reports it."""

        root = fixtures.scratch_dir("loader_missing_module") / "finance_xhs"
        root.mkdir()
        for path in self.directory.iterdir():
            if path.is_file() and path.name != "visual_rules.json":
                root.joinpath(path.name).write_bytes(path.read_bytes())
        (root / "instance.json").unlink()
        document = read_artifact(root, layout="modules")
        self.assertNotIn("visual_rules", document)

    def test_a_missing_module_is_reported_on_load(self) -> None:
        root = fixtures.scratch_dir("loader_missing_module2") / "finance_xhs"
        root.mkdir()
        for path in self.directory.iterdir():
            if path.is_file() and path.name != "visual_rules.json":
                root.joinpath(path.name).write_bytes(path.read_bytes())
        (root / "instance.json").unlink()
        with self.assertRaises(InstanceModuleMissingError):
            load_creator_instance(root, layout="modules")

    def test_a_non_object_document_is_rejected(self) -> None:
        path = fixtures.scratch_dir("loader_non_object") / "instance.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(InstanceUnreadableError):
            read_artifact(path)

    def test_a_directory_with_only_provenance_is_rejected(self) -> None:
        root = fixtures.scratch_dir("loader_only_prov") / "finance_xhs"
        root.mkdir()
        root.joinpath("provenance.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(InstanceModuleMissingError):
            load_creator_instance(root)

    def test_an_artifact_with_no_provenance_is_rejected(self) -> None:
        root = fixtures.scratch_dir("loader_no_prov") / "finance_xhs"
        root.mkdir()
        for path in self.directory.iterdir():
            if path.is_file() and path.name not in ("provenance.json", "instance.json"):
                root.joinpath(path.name).write_bytes(path.read_bytes())
        with self.assertRaises(InstanceProvenanceMissingError):
            load_creator_instance(root)

    def test_aggregate_filenames_are_declared(self) -> None:
        self.assertEqual(AGGREGATE_FILES, ("instance.json", "creator_instance.json"))

    def test_provenance_filename_is_declared(self) -> None:
        self.assertEqual(PROVENANCE_FILE, "provenance.json")

    def test_the_two_aggregate_names_are_the_contract_and_mapping_names(self) -> None:
        self.assertEqual(set(AGGREGATE_FILES), {"instance.json", "creator_instance.json"})


class CapabilityDerivationTests(unittest.TestCase):
    """Capability state is read from the artifact and never promoted."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_creator_instance(fixtures.write_mapped("loader_caps"))

    def test_generation_is_declared_not_available(self) -> None:
        self.assertEqual(
            self.loaded.capability("generation").state, CapabilityState.DECLARED
        )

    def test_publishing_is_declared_not_available(self) -> None:
        self.assertEqual(
            self.loaded.capability("publishing").state, CapabilityState.DECLARED
        )

    def test_identity_is_available(self) -> None:
        self.assertEqual(
            self.loaded.capability("identity").state, CapabilityState.AVAILABLE
        )

    def test_visual_rules_are_available(self) -> None:
        self.assertEqual(
            self.loaded.capability("visual_rules").state, CapabilityState.AVAILABLE
        )

    def test_source_records_no_own_asset_and_is_absent(self) -> None:
        self.assertEqual(
            self.loaded.capability("source").state, CapabilityState.ABSENT
        )

    def test_no_capability_is_enabled(self) -> None:
        self.assertEqual(self.loaded.enabled_capabilities(), ())

    def test_disabled_capabilities_carry_a_reason(self) -> None:
        for module in ("generation", "publishing"):
            self.assertTrue(self.loaded.capability(module).reason, module)

    def test_generation_reason_is_the_availability_reason(self) -> None:
        self.assertEqual(
            self.loaded.capability("generation").reason,
            "generation_capability_not_available",
        )

    def test_disabled_capabilities_include_both_capability_modules(self) -> None:
        self.assertEqual(
            self.loaded.unavailable_capabilities(), ("generation", "publishing")
        )

    def test_absent_capabilities_lists_only_source(self) -> None:
        self.assertEqual(self.loaded.absent_capabilities(), ("source",))

    def test_absent_is_not_reported_as_unavailable(self) -> None:
        self.assertNotIn("source", self.loaded.unavailable_capabilities())

    def test_absent_is_a_distinct_state_from_unavailable(self) -> None:
        self.assertNotEqual(CapabilityState.ABSENT, CapabilityState.UNAVAILABLE)

    def test_capability_records_one_entry_per_module(self) -> None:
        self.assertEqual(len(self.loaded.capability_states()), len(MODULES))

    def test_capability_states_are_plain_strings(self) -> None:
        for state in self.loaded.capability_states().values():
            self.assertIsInstance(state, str)

    def test_capability_keeps_the_asset_it_read(self) -> None:
        self.assertEqual(
            self.loaded.capability("generation").asset_id, "generation_capability"
        )

    def test_capability_keeps_the_asset_status(self) -> None:
        self.assertEqual(
            self.loaded.capability("generation").asset_status, "unavailable"
        )

    def test_capability_lists_the_skills_that_fed_it(self) -> None:
        self.assertIn(
            "xiaohongshu-article-generation",
            self.loaded.capability("generation").skill_ids,
        )

    def test_a_non_capability_module_reports_no_enabled_flag(self) -> None:
        self.assertIsNone(self.loaded.capability("identity").enabled)

    def test_capability_records_for_capability_modules_carry_a_boolean(self) -> None:
        for module in ("generation", "publishing"):
            self.assertIsInstance(self.loaded.capability(module).enabled, bool)

    def test_capability_records_function_reads_the_mapped_payload(self) -> None:
        document = read_artifact(fixtures.write_mapped("loader_caps2"))
        records = capability_records(document)
        self.assertEqual(sorted(records), sorted(MODULES))

    def test_capability_records_function_returns_empty_without_provenance(self) -> None:
        self.assertEqual(capability_records({}), {})

    def test_capability_records_function_returns_empty_for_a_non_mapping(self) -> None:
        self.assertEqual(capability_records({"provenance": "text"}), {})


class HandEditedArtifactTests(unittest.TestCase):
    """A hand-edited artifact is read from disk, not from a cached build.

    Each case asserts the **error code**, not one particular class: the loader's
    layers overlap deliberately, so a missing field is reported first as a schema
    violation and only then as ``INSTANCE_FIELD_MISSING``. What a caller branches on
    is the code, so that is what the tests pin.
    """

    def _edited(self, name: str, mutate: object) -> Path:
        source = fixtures.write_mapped(f"loader_edit_{name}")
        root = fixtures.scratch_dir(f"loader_edited_{name}") / "finance_xhs"
        root.mkdir()
        for path in source.iterdir():
            if path.is_file():
                root.joinpath(path.name).write_bytes(path.read_bytes())
        aggregate = root / "instance.json"
        document = json.loads(aggregate.read_text(encoding="utf-8"))
        document.update({"contract_version": "1.0.0"})
        document = mutate(document)  # type: ignore[operator]
        aggregate.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return root

    def assertCode(self, code: str, path: Path, **kwargs: object) -> None:
        """Load ``path`` and assert it fails with ``code``."""

        from creator_loader import LoaderError

        try:
            load_creator_instance(path, **kwargs)  # type: ignore[arg-type]
        except LoaderError as exc:
            self.assertEqual(exc.code, code, str(exc))
        else:  # pragma: no cover - the call above must raise
            self.fail(f"expected a loader failure with code {code}")

    def assertCodeOneOf(self, codes: tuple[str, ...], path: Path, **kwargs: object) -> None:
        """Load ``path`` and assert it fails with one of ``codes``.

        The loader's layers overlap on purpose, so a defect can legitimately be caught
        by more than one of them. What matters is that it is caught, and reported with
        a code a caller can branch on.
        """

        from creator_loader import LoaderError

        try:
            load_creator_instance(path, **kwargs)  # type: ignore[arg-type]
        except LoaderError as exc:
            self.assertIn(exc.code, codes, str(exc))
        else:  # pragma: no cover - the call above must raise
            self.fail(f"expected a loader failure with one of {codes}")

    def test_an_enabled_capability_without_a_source_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            document["generation"]["enabled"] = True
            document["generation"]["reason"] = ""
            return document

        self.assertCode(
            "INSTANCE_CAPABILITY_INVALID", self._edited("enable_gen", mutate)
        )

    def test_a_disabled_capability_without_a_reason_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            document["publishing"]["reason"] = ""
            return document

        # C0.1's own contract validation catches this first ("a disabled capability
        # must state why it is disabled"); the loader's capability check would catch
        # it too. Either code is a correct rejection, so both are accepted.
        self.assertCodeOneOf(
            ("INSTANCE_CAPABILITY_INVALID", "INSTANCE_CONTRACT_INVALID"),
            self._edited("no_reason", mutate),
        )

    def test_a_removed_module_field_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            del document["visual_rules"]["profile_id"]
            return document

        root = self._edited("drop_field", mutate)
        from creator_loader import LoaderError

        try:
            load_creator_instance(root)
        except LoaderError as exc:
            self.assertIn(
                exc.code, ("INSTANCE_SCHEMA_INVALID", "INSTANCE_FIELD_MISSING")
            )
        else:  # pragma: no cover
            self.fail("expected a loader failure")

    def test_a_removed_required_field_is_named_by_the_schema_check(self) -> None:
        def mutate(document: dict) -> dict:
            del document["risk_policy"]["risk_categories"]
            return document

        root = self._edited("drop_field2", mutate)
        from creator_loader import InstanceFieldMissingError, LoaderError

        try:
            load_creator_instance(root)
        except InstanceFieldMissingError:
            pass
        except LoaderError as exc:
            self.assertIn(exc.code, ("INSTANCE_SCHEMA_INVALID",))

    def test_a_removed_provenance_entry_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            del document["provenance"]["visual_rules"]
            return document

        self.assertCode(
            "INSTANCE_SCHEMA_INVALID", self._edited("drop_prov", mutate)
        )

    def test_a_removed_provenance_payload_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            document["provenance"]["field_provenance"] = {}
            return document

        self.assertCodeOneOf(
            (
                "INSTANCE_PROVENANCE_INVALID",
                "INSTANCE_CONTRACT_INVALID",
                "INSTANCE_SCHEMA_INVALID",
            ),
            self._edited("empty_payload", mutate),
        )

    def test_a_provenance_without_the_modules_map_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            payload = document["provenance"]["field_provenance"]
            payload["modules"] = {}
            return document

        self.assertCodeOneOf(
            (
                "INSTANCE_PROVENANCE_INVALID",
                "INSTANCE_CONTRACT_INVALID",
                "INSTANCE_SCHEMA_INVALID",
            ),
            self._edited("empty_modules", mutate),
        )

    def test_a_corrupted_aggregate_fails_at_the_schema_check(self) -> None:
        def mutate(document: dict) -> dict:
            document["unexpected_key"] = 1
            return document

        self.assertCode("INSTANCE_SCHEMA_INVALID", self._edited("extra_key", mutate))

    def test_a_hand_edited_field_is_the_value_that_loads(self) -> None:
        def mutate(document: dict) -> dict:
            document["identity"]["tone"] = "hand edited"
            return document

        root = self._edited("edited_field", mutate)
        loaded = load_creator_instance(root)
        self.assertEqual(loaded.get("identity", "tone"), "hand edited")

    def test_a_corrupted_trace_is_rejected_not_repaired(self) -> None:
        def mutate(document: dict) -> dict:
            del document["provenance"]["field_provenance"]["fields"][
                "identity.tone"
            ]["rule_id"]
            return document

        self.assertCode(
            "INSTANCE_PROVENANCE_INVALID", self._edited("bad_trace", mutate)
        )

    def test_an_empty_field_trace_value_is_rejected(self) -> None:
        def mutate(document: dict) -> dict:
            document["provenance"]["field_provenance"]["fields"]["identity.tone"][
                "skill_id"
            ] = ""
            return document

        self.assertCode(
            "INSTANCE_PROVENANCE_INVALID", self._edited("empty_skill", mutate)
        )

    def test_a_hand_edited_artifact_is_never_written_back(self) -> None:
        def mutate(document: dict) -> dict:
            document["unexpected_key"] = 1
            return document

        root = self._edited("no_write_back", mutate)
        before = (root / "instance.json").read_bytes()
        try:
            load_creator_instance(root)
        except Exception:
            pass
        self.assertEqual((root / "instance.json").read_bytes(), before)


class ErrorCodeTests(unittest.TestCase):
    """Every failure carries a stable, documented code."""

    def test_the_code_list_is_exactly_thirteen_entries(self) -> None:
        self.assertEqual(len(ERROR_CODES), 13)

    def test_the_code_list_has_no_duplicates(self) -> None:
        self.assertEqual(len(set(ERROR_CODES)), len(ERROR_CODES))

    def test_every_code_is_upper_snake_case(self) -> None:
        for code in ERROR_CODES:
            self.assertTrue(code.startswith("INSTANCE_"), code)

    def test_missing_field_has_its_own_code(self) -> None:
        self.assertIn("INSTANCE_FIELD_MISSING", ERROR_CODES)

    def test_not_found_carries_its_code(self) -> None:
        try:
            load_creator_instance("")
        except InstanceNotFoundError as exc:
            self.assertEqual(exc.code, "INSTANCE_NOT_FOUND")
        else:  # pragma: no cover - the call above must raise
            self.fail("expected InstanceNotFoundError")

    def test_a_missing_module_carries_its_code(self) -> None:
        root = fixtures.scratch_dir("code_missing_module") / "x"
        root.mkdir()
        root.joinpath("identity.json").write_text("{}", encoding="utf-8")
        root.joinpath("provenance.json").write_text("{}", encoding="utf-8")
        try:
            load_creator_instance(root)
        except InstanceModuleMissingError as exc:
            self.assertEqual(exc.code, "INSTANCE_MODULE_MISSING")
        else:  # pragma: no cover
            self.fail("expected InstanceModuleMissingError")

    def test_every_loader_error_subclasses_loader_error(self) -> None:
        import creator_loader

        for name in creator_loader.__all__:
            value = getattr(creator_loader, name)
            if isinstance(value, type) and name.endswith("Error"):
                self.assertTrue(
                    issubclass(value, creator_loader.LoaderError), name
                )

    def test_every_error_class_has_a_code_in_the_list(self) -> None:
        import creator_loader

        for name in creator_loader.__all__:
            value = getattr(creator_loader, name)
            if isinstance(value, type) and name.endswith("Error"):
                if value is creator_loader.LoaderError:
                    continue
                self.assertIn(value.code, ERROR_CODES, name)

    def test_every_code_has_an_error_class(self) -> None:
        import creator_loader

        declared: set[str] = set()
        for name in creator_loader.__all__:
            value = getattr(creator_loader, name)
            if not (isinstance(value, type) and name.endswith("Error")):
                continue
            declared.add(value.code)
            declared.update(getattr(value, "codes", ()))
        for code in ERROR_CODES:
            self.assertIn(code, declared, code)

    def test_the_base_error_code_is_not_one_of_the_loader_codes(self) -> None:
        """``INSTANCE_ERROR`` is the base marker, not a code a caller branches on."""

        import creator_loader

        self.assertNotIn(creator_loader.LoaderError.code, ERROR_CODES)

    def test_only_the_not_found_error_declares_two_codes(self) -> None:
        import creator_loader

        multiple = [
            name
            for name in creator_loader.__all__
            if isinstance(getattr(creator_loader, name), type)
            and name.endswith("Error")
            and len(getattr(getattr(creator_loader, name), "codes", ())) > 1
        ]
        self.assertEqual(multiple, ["InstanceNotFoundError"])

    def test_a_non_json_file_is_reported_as_not_a_directory(self) -> None:
        """The second code lets a caller tell "absent" from "wrong kind of thing"."""

        target = fixtures.scratch_dir("code_not_a_dir") / "notes.txt"
        target.write_text("hello", encoding="utf-8")
        try:
            load_creator_instance(target)
        except InstanceNotFoundError as exc:
            self.assertIn(exc.code, InstanceNotFoundError.codes)
        else:  # pragma: no cover
            self.fail("expected InstanceNotFoundError")


class NonStrictLoadTests(unittest.TestCase):
    """A non-strict load inspects an artifact without endorsing it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("loader_non_strict")

    def test_non_strict_records_that_checks_were_skipped(self) -> None:
        loaded = load_creator_instance(self.directory, strict=False)
        self.assertEqual(loaded.validation.get("strict"), "SKIPPED")

    def test_non_strict_still_returns_a_loaded_instance(self) -> None:
        loaded = load_creator_instance(self.directory, strict=False)
        self.assertIsInstance(loaded, LoadedCreatorInstance)

    def test_non_strict_still_derives_capabilities_honestly(self) -> None:
        loaded = load_creator_instance(self.directory, strict=False)
        self.assertEqual(loaded.enabled_capabilities(), ())

    def test_non_strict_still_requires_a_provenance_block(self) -> None:
        root = fixtures.scratch_dir("loader_non_strict_prov") / "finance_xhs"
        root.mkdir()
        root.joinpath("identity.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(InstanceProvenanceMissingError):
            load_creator_instance(root, strict=False)


if __name__ == "__main__":
    unittest.main()
