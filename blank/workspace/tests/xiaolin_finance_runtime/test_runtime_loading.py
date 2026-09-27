from __future__ import annotations

import tempfile
import unittest

from core import load_plugin
from runtime import bootstrap

from ._fixtures import (
    DEFAULT_CONFIG,
    PLUGIN_MODULE_PATH,
    PLUGIN_NAME,
    STUB_MODULE_PATH,
    plugin_json,
    register_stub_plugin,
    unregister_stub_plugin,
    write_config,
)


class RuntimeLoadingTests(unittest.TestCase):
    """Step 1 - the plugin is loaded through Runtime Bootstrap."""

    def tearDown(self) -> None:
        unregister_stub_plugin()

    # Test 1 - runtime config enables the plugin
    def test_runtime_config_enables_the_finance_plugin(self) -> None:
        context = bootstrap(DEFAULT_CONFIG)

        self.assertIn(PLUGIN_MODULE_PATH, context.plugins)
        self.assertEqual(context.config.plugins.default, PLUGIN_MODULE_PATH)
        self.assertEqual(context.default_plugin.identity.name, PLUGIN_NAME)
        self.assertEqual(context.default_plugin.identity.domain, "finance")
        self.assertIs(context.default_plugin, context.plugins[PLUGIN_MODULE_PATH])

    # Test 2 - runtime config disables the plugin
    def test_plugin_is_absent_when_the_config_does_not_enable_it(self) -> None:
        register_stub_plugin()
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(directory, plugins=[STUB_MODULE_PATH])

            context = bootstrap(path)

        self.assertNotIn(PLUGIN_MODULE_PATH, context.plugins)
        self.assertEqual(set(context.plugins), {STUB_MODULE_PATH})
        with self.assertRaises(KeyError):
            context.plugin(PLUGIN_MODULE_PATH)

    # Test 3 - plugin.json == runtime identity == plugin instance
    def test_identity_is_consistent_across_manifest_context_and_instance(self) -> None:
        declared = plugin_json("plugin.json")["plugin"]
        context = bootstrap(DEFAULT_CONFIG)
        instance = context.default_plugin

        self.assertEqual(declared["name"], instance.identity.name)
        self.assertEqual(declared["version"], instance.identity.version)
        self.assertEqual(declared["domain"], instance.identity.domain)
        self.assertEqual(declared["creator_target"], instance.identity.creator_target)

        # The context holds the same object the loader produced, and a second
        # load agrees with it, so no layer invents its own identity.
        self.assertEqual(context.plugins[PLUGIN_MODULE_PATH].identity, instance.identity)
        self.assertEqual(load_plugin(PLUGIN_MODULE_PATH).identity, instance.identity)


if __name__ == "__main__":
    unittest.main()
