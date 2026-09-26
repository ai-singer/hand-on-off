# Creator Plugin Development Guide

## 1. Create the package

Use a package under `plugins/`:

```text
plugins/example_creator/
├── __init__.py
├── plugin.py
├── rules/
├── schemas/
├── evaluation/
└── README.md
```

Do not copy another Creator's corpus or account configuration. Reuse the public
interface and create domain-owned rules.

## 2. Implement identity and contribution

```python
from plugin_interface import PluginContribution, PluginIdentity

class ExamplePlugin:
    @property
    def identity(self):
        return PluginIdentity(
            name="example_creator",
            version="1.0.0",
            domain="example",
            creator_target="example-audience",
        )

    def enhance(self, raw_sources, common_signals):
        return PluginContribution(
            domain_extension={"schema_version": "1.0.0"},
            risk_constraints=[],
            evaluation_result={"score": 1.0, "passed": True},
        )
```

Expose a factory from `plugins/example_creator/__init__.py`:

```python
def create_plugin():
    return ExamplePlugin()
```

## 3. Define policy as data

Keep inspectable, versioned definitions for:

- value signals to enhance;
- filtering/down-ranking and evidence rules;
- structure templates;
- domain evaluation dimensions and hard failures;
- the private `domain_extension` schema.

Risk decisions should preserve the source ID and explain the action. Filtering
must not silently erase a claim.

## 4. Respect the one-run rule

The plugin receives raw sources and common signals as inputs to one engine
invocation. It must not invoke another distillation workflow, persist a generic
artifact, or treat common output as replacement source material.

## 5. Load and test

```python
from core import load_plugin
from distillation_core import DistillationEngine

plugin = load_plugin("plugins.example_creator")
engine = DistillationEngine(plugin)
artifact = engine.distill(raw_sources)
```

Minimum plugin tests:

1. identity and factory conformance;
2. positive domain-value enhancement;
3. filtering and risk handling;
4. shared schema validation;
5. replacement of the previous plugin without a common-core edit.

Run the full local gate before packaging:

```bash
python -m unittest discover -s tests -v
```

## 6. Versioning

- Patch: rule correction without contract change.
- Minor: backward-compatible rule, evaluation, or extension additions.
- Major: incompatible `domain_extension` or behavior contract changes.

Shared artifact changes are governed separately by
`schemas/unified_distillation_artifact.json`.
