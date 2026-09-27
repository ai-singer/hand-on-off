# Xiaolin Finance Plugin

Reference Creator distillation plugin for finance explainers. It contains no
collected corpus and writes no article. Its responsibilities are to recognize
finance-relevant value, expose prohibited claims, classify what each source
contributed, select a domain structure, and return domain evaluation evidence.

Contract: [`docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md`](../../docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md)
Interface: [`docs/PLUGIN_INTERFACE_COMPATIBILITY.md`](../../docs/PLUGIN_INTERFACE_COMPATIBILITY.md)

## Package boundaries

| Path | Owner of |
| --- | --- |
| `plugin.json` | Identity, contract version, declared sections and prohibitions, entry point, file locations |
| `plugin.py` | Protocol implementation and rule interpreter only |
| `rules/value_rules.json` | What finance content **should** distil, per section |
| `rules/filter_rules.json` | What finance content **must not** distil, per category |
| `rules/structure_templates.json` | Organization patterns, not generated prose |
| `schemas/domain_extension.schema.json` | Private extension shape (additive only) |
| `evaluation/rubric.json` | Scoring policy, inherited dimensions, finance checks |

`plugin.json` is authoritative for identity: `plugin.py` reads it instead of
duplicating the values, so declaration and behaviour cannot drift.

## What this plugin distils

Five sections, each backed by a value rule and surfaced as a
`domain_extension` field:

| Section | Question |
| --- | --- |
| `business_mechanism` | How does the business earn money, and how do value, cost and incentive connect? |
| `financial_structure` | Is the report organized as revenue, cost, growth sources and named risk factors? |
| `data_expression_pattern` | How are numbers expressed — comparison, trend, indicator interpretation? |
| `case_selection_logic` | Why this company case, and how does it support the claim? |
| `misconception_analysis` | Which common belief is wrong, and where does fact diverge from perception? |

## What this plugin refuses to distil

Four prohibited categories, each backed by a filter rule that emits an explicit
`risk_constraint` rather than silently dropping the claim:

| Category | Severity / action |
| --- | --- |
| `investment_advice` — buy/sell instructions, guaranteed returns | `block` / `block` |
| `market_prediction` — certainty forecasts, price targets | `warning` / `require_evidence` |
| `emotional_language` — incitement, panic framing, exaggeration | `warning` / `downrank` |
| `unverified_fact` — unconfirmed figures, unattributable claims | `warning` / `require_evidence` |

The plugin does not provide investment advice and writes no recommendation.

## Source classification

Each source is classified by the distillation role it actually played, derived
from where it is referenced in the common extraction:

| Artifact field | Role |
| --- | --- |
| `topic_candidate` | `topic_source` |
| `knowledge_unit` | `knowledge_source` |
| `content_template` | `structure_source` |
| `style_pattern` | `style_source` |

The result is returned as `domain_extension.source_classification`.

## Evaluation

Reported under `evaluation_result.domain`:

- inherited dimensions — `performance`, `structure_quality`, `transferability`;
- finance checks — `data_credibility`, `explanation_completeness`,
  `risk_boundary`.

Scoring parameters live in `evaluation/rubric.json`, not in code.

## Loading

```python
from core import load_plugin

plugin = load_plugin("plugins.xiaolin_finance")
```

`plugins/xiaolin_finance/__init__.py` exposes the zero-argument
`create_plugin()` factory required by `plugin_interface`.

Changing or removing this plugin requires no modification to `core/`,
`distillation_core/`, `evaluation/` or the shared artifact schema. Verification:
`python -m unittest tests.finance_plugin -v` from the workspace root.
