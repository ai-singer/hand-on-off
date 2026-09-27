# Creator Specific Plugin Contract

Phase 6.1. The contract every Creator-specific distillation plugin satisfies.
`plugins/xiaolin_finance` is the reference implementation.

```text
Raw Source
   |
   v
Universal Distillation Framework          distillation_core (domain-neutral)
   |  common_signals: topic_candidate, content_template, knowledge_unit, style_pattern
   v
Creator Specific Plugin                   plugins/<name> (domain judgement)
   |  PluginContribution: domain_extension, risk_constraints,
   |                      evaluation_result, field_enhancements
   v
Unified Distillation Artifact             schemas/unified_distillation_artifact.json
   |
   v
Generation                                 injected adapter, only after quality gate PASS
```

## 1. Input contract

A Creator plugin receives what the Universal Distillation Framework produced. It
does not read raw storage, does not re-classify from scratch, and does not
perform a second distillation pass.

| Input | Content | Contract |
| --- | --- | --- |
| `raw_sources` | Original `RawSource` records | `source_type` is one of `video`, `document`, `data`, `image`; `source_id` is unique per run |
| `common_signals["topic_candidate"]` | Topic-level candidates | `label`, `rationale`, `source_ids`, `confidence`, `origin` |
| `common_signals["content_template"]` | Structure patterns | `name`, `sections`, `source_ids`, `origin` |
| `common_signals["knowledge_unit"]` | Evidence-bound statements | `statement`, `evidence_refs`, `confidence`, `origin` |
| `common_signals["style_pattern"]` | Expression patterns | `name`, `attributes`, `source_ids`, `origin` |

`common_signals` is a deep copy. A plugin reads it; it cannot change it.

## 2. Output contract

`enhance()` returns `PluginContribution`. The output must keep the artifact
compatible with `schemas/unified_distillation_artifact.json`.

| Output | Requirement |
| --- | --- |
| `domain_extension` | Plugin-owned object. Must validate against the plugin's `schemas/domain_extension.schema.json`. **May only add fields.** |
| `risk_constraints` | Every risk uses `rule_id`, `severity`, `action`, `message`, `source_ids`. A claim is never deleted silently. Additional fields are allowed; the reference plugin adds `category` so the prohibited category is readable directly from the artifact. |
| `evaluation_result` | Deterministic domain evidence, including the framework-inherited dimensions and the domain-specific checks. |
| `field_enhancements` | **Append-only additions** to the four common families. Replacing or removing a common signal is impossible by construction. |

### Forbidden output behaviour

- Overriding `topic_candidate`, `content_template`, `knowledge_unit`,
  `style_pattern`, `risk_constraints` or `evaluation_result`;
- returning enhancement keys outside the four common families;
- emitting a `domain_extension` that fails its own private schema;
- removing or rewriting a common signal;
- producing finished content, publishing, or mutating a production account;
- network or model calls without a separately injected adapter.

## 3. Domain rule declaration

Domain policy must be **inspectable data**, not code:

| File | Owns |
| --- | --- |
| `plugin.json` | Identity, contract version, declared sections and prohibited categories, entry point, file locations |
| `rules/value_rules.json` | What the domain should distil, and which extension section each rule feeds |
| `rules/filter_rules.json` | What the domain must not distil, and how each match is handled |
| `rules/structure_templates.json` | How content is organised (never finished prose) |
| `evaluation/rubric.json` | Deterministic scoring policy, inherited dimensions, domain checks |
| `schemas/domain_extension.schema.json` | The private extension shape |

`plugin.json` is authoritative for identity: the implementation reads it rather
than duplicating values, so declaration and behaviour cannot drift.

## 4. Evaluation contract

A Creator plugin reports two layers.

**Inherited from the Universal Distillation Framework:**

| Dimension | Question |
| --- | --- |
| `performance` | How much of the domain taxonomy did the material actually cover? |
| `structure_quality` | Was an explainable structure selected? |
| `transferability` | Does the extracted value hold across the supplied sources rather than one excerpt? |

**Domain-specific checks (finance):**

| Check | Question |
| --- | --- |
| `data_credibility` | Are figures attributable, or do they rest on unconfirmed claims? |
| `explanation_completeness` | Does the material explain a mechanism and interpret data, not only report events? |
| `risk_boundary` | Is the boundary between explanation and advice respected? |

The pass decision is the rubric score against `pass_score`, with blocking risks
capping the score. The reported checks are evidence for review, and the checks
that mirror risk rules also influence the score through those rules.

## 5. Capability matrix of the reference plugin

| Capability | Status |
| --- | --- |
| Input: reads common signals only | PASS |
| Output: append-only field enhancements | PASS |
| Output: private schema validated | PASS |
| Domain value rules | PASS — 5 sections |
| Domain prohibition rules | PASS — 4 categories |
| Domain evaluation | PASS — 3 inherited + 3 finance checks |
| Deterministic and side-effect free | PASS — identical output across runs |
| No core modification | PASS — verified behaviourally |
| Network required | No |
| Writes content | No |

## 6. Adding a new Creator plugin

1. Create `plugins/<name>/` with `__init__.py` exposing
   `create_plugin() -> CreatorDistillationPlugin`;
2. Add `plugin.json` declaring identity, contract version, sections and
   prohibitions;
3. Add `rules/` (value, filter, structure) and `evaluation/rubric.json`;
4. Add `schemas/domain_extension.schema.json` for the private extension;
5. Select it through `config/runtime/default.json` `plugins.enabled` and
   `plugins.default` — **no core change is required**;
6. Run `python -m unittest discover -s tests -v` from the workspace root.

Removing a plugin is symmetric: drop the package and the configuration entry.
The shared schema, engine, evaluator and runtime bootstrap are untouched.
