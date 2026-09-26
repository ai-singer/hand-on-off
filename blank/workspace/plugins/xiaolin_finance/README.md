# Xiaolin Finance Plugin

This is a reference Creator distillation plugin for finance explainers. It
contains no collected corpus and writes no article. Its only responsibilities
are to recognize finance-relevant value, expose risky claims, select a domain
structure, and return domain evaluation evidence.

## Package boundaries

- `rules/value_rules.json`: signals to enhance, including business mechanisms,
  data interpretation, and company cases.
- `rules/filter_rules.json`: investment-advice and unsupported-prediction risk
  handling.
- `rules/structure_templates.json`: organization patterns, not generated prose.
- `schemas/domain_extension.schema.json`: private extension shape.
- `evaluation/rubric.json`: deterministic domain evaluation policy.
- `plugin.py`: protocol implementation and rule interpreter.

The common engine loads this package by module path:

```python
from core import load_plugin

plugin = load_plugin("plugins.xiaolin_finance")
```

Changing or removing this plugin does not require modifying the common core.
