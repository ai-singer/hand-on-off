# xiaolin_finance Creator Plugin

Creator distillation plugin for finance explainers.
Plugin version `1.2.0` · release candidate.

Contract: [`docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md`](../../docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md)
Interface: [`docs/PLUGIN_INTERFACE_COMPATIBILITY.md`](../../docs/PLUGIN_INTERFACE_COMPATIBILITY.md)
Version decision: [`docs/XIAOLIN_FINANCE_VERSION_DECISION.md`](../../docs/XIAOLIN_FINANCE_VERSION_DECISION.md)

## Purpose

A Creator-specific distillation plugin for the finance domain. It contributes
domain judgement to the framework's single distillation run: it recognizes which
finance material deserves amplification, surfaces prohibited claims as explicit
risks, classifies what each source contributed, selects an explanation
structure, and returns domain evaluation evidence.

It contains no collected corpus, downloads nothing, calls no model, and writes
no article. It does not provide investment advice.

## Input

Given by the Universal Distillation Framework, never read from storage:

| Input | Content |
| --- | --- |
| `RawSource[]` | Original records: `source_id`, `source_type` (`video` / `document` / `data` / `image`), `content`, `metadata` |
| `common_signals` | Deep copy of the common extraction: `topic_candidate`, `content_template`, `knowledge_unit`, `style_pattern` |

`common_signals` is read-only in effect. The plugin adds domain judgement on top
of the framework's classification; it never re-classifies from scratch and never
runs a second distillation pass.

## Output

A `PluginContribution`, merged by the engine into one
`UnifiedDistillationArtifact`:

| Output | Content |
| --- | --- |
| `domain_extension` | Finance extension validated against `schemas/domain_extension.schema.json` — additive only |
| `risk_constraints` | Explicit risk decisions, each with `rule_id`, `category`, `severity`, `action`, `message`, `source_ids` |
| `evaluation_result` | Three inherited dimensions and three finance checks |
| `field_enhancements` | **Append-only** additions to `topic_candidate` |

The common families are never rewritten: `knowledge_unit`, `content_template`
and `style_pattern` come out of the engine byte-identical to a domain-free run.

## Allowed Distillation

Five sections, each backed by a value rule and surfaced as a `domain_extension`
field:

| Section | Question |
| --- | --- |
| `business_mechanism` | How does the business earn money, and how do value, cost and incentive connect? |
| `financial_structure` | Is the report organized as revenue, cost, growth sources and named risk factors? |
| `data_expression_pattern` | How are numbers expressed — comparison, trend, indicator interpretation? |
| `case_selection_logic` | Why this company case, and how does it support the claim? |
| `misconception_analysis` | Which common belief is wrong, and where does fact diverge from perception? |

## Forbidden Behavior

Four prohibited categories. Each is backed by a filter rule that raises an
explicit `risk_constraint` rather than silently dropping the claim:

| Category | Severity / action |
| --- | --- |
| `investment_advice` — buy/sell instructions, guaranteed returns | `block` / `block` |
| `market_prediction` — certainty forecasts, price targets | `warning` / `require_evidence` |
| `emotional_language` — incitement, panic framing, exaggeration | `warning` / `downrank` |
| `unverified_fact` — unconfirmed figures, unattributable claims | `warning` / `require_evidence` |

A blocking constraint caps the domain score and forces the quality gate to
`review_required`, so no content reaches generation.

## Runtime Usage

The plugin is loaded through the runtime bootstrap, never imported directly by
the framework:

```text
config/runtime/default.json  plugins.enabled = ["plugins.xiaolin_finance"]
        |
        v
Runtime Bootstrap  ->  bootstrap()  ->  Plugin Registry
        |                core.load_plugin("plugins.xiaolin_finance")
        |                plugins/xiaolin_finance/__init__.py :: create_plugin()
        v
RuntimeContext.plugins["plugins.xiaolin_finance"] == RuntimeContext.default_plugin
        |
        v
Distillation Pipeline   RawSource -> DistillationEngine -> plugin.enhance()
        |                                             -> Unified Artifact
        v
Quality Gate -> Generation Handoff (only after PASS)
```

Switching or removing the plugin requires only a change to
`config/runtime/default.json`. No `core/`, `distillation_core/`, `evaluation/`
or schema change is needed.

```python
from runtime import bootstrap

context = bootstrap()
plugin = context.default_plugin          # xiaolin_finance 1.2.0
```

## Package boundaries

| Path | Owner of |
| --- | --- |
| `plugin.json` | Runtime-facing manifest: identity, contract, sections, prohibitions, file locations |
| `release.json` | Release-facing manifest: version, framework / artifact / runtime compatibility, capabilities |
| `plugin.py` | Protocol implementation and rule interpreter only |
| `rules/value_rules.json` | What finance content **should** distil, per section |
| `rules/filter_rules.json` | What finance content **must not** distil, per category |
| `rules/structure_templates.json` | Organization patterns, not generated prose |
| `schemas/domain_extension.schema.json` | Private extension shape (additive only) |
| `evaluation/rubric.json` | Scoring policy, inherited dimensions, finance checks |

`plugin.json` is authoritative for identity: `plugin.py` reads it instead of
duplicating values, so declaration and behaviour cannot drift.

## Source classification

Each source is classified by the distillation role it actually played, derived
from where it is referenced in the common extraction, and returned as
`domain_extension.source_classification`:

| Artifact field | Role |
| --- | --- |
| `topic_candidate` | `topic_source` |
| `knowledge_unit` | `knowledge_source` |
| `content_template` | `structure_source` |
| `style_pattern` | `style_source` |

## Evaluation

Reported under `evaluation_result.domain`:

- inherited dimensions — `performance`, `structure_quality`, `transferability`;
- finance checks — `data_credibility`, `explanation_completeness`,
  `risk_boundary`.

Scoring parameters live in `evaluation/rubric.json`, not in code.

## Verification

```bash
python -m unittest tests.finance_plugin tests.xiaolin_finance_runtime tests.xiaolin_finance_release -v
```
