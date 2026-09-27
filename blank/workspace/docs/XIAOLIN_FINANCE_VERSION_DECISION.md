# xiaolin_finance Plugin Version Decision

Phase 6.3 Step 2. Records the plugin version audit and the semantic version
decision for the release candidate.

## 1. Version Audit (before this phase)

| Declaration | Location | Value | Assessment |
| --- | --- | --- | --- |
| Plugin version | `plugin.json` → `plugin.version` | `1.1.0` | **Stale** — Phase 6.2 changed behaviour without a bump |
| Domain contract | `plugin.json` → `domain_schema.version` | `1.1.0` | Correct — `domain_extension` shape unchanged in 6.2 |
| Evaluation contract | `plugin.json` → `evaluation.version` | `1.1.0` | Correct — matches `evaluation/rubric.json` `version` |
| Plugin specification | `plugin.json` → `contract.version` | `1.0` | Correct — matches `plugin_interface/creator_distillation_plugin_spec.md` |
| Value rules | `rules/value_rules.json` → `version` | `1.1.0` | Correct — changed in 6.1, untouched in 6.2 |
| Filter rules | `rules/filter_rules.json` → `version` | `1.1.0` | **Stale** — keyword coverage changed in 6.2 |
| Structure templates | `rules/structure_templates.json` → `version` | `1.0.0` | Correct — file never revised since creation |
| Rubric | `evaluation/rubric.json` → `version` | `1.1.0` | Correct — unchanged in 6.2 |
| Domain schema file | `schemas/domain_extension.schema.json` | *(no version field)* | By design — the schema version is declared once in `plugin.json` so it cannot drift |
| Artifact schema | `schemas/unified_distillation_artifact.json` → `artifact_version` | `1.0.0` | Unchanged |
| Runtime config contract | `runtime.SUPPORTED_CONFIG_VERSION` | `1.0.0` | Unchanged |

Two defects were found by the audit:

1. **A-01** — the plugin version stayed at `1.1.0` although Phase 6.2 changed
   both the produced output and the detection behaviour.
2. **A-02** — `rules/filter_rules.json` stayed at `1.1.0` although its content
   changed in Phase 6.2.

Per-file versions version *that file's own revisions*, so different values
across files are expected; `structure_templates.json` remaining at `1.0.0` is
correct rather than drift.

## 2. Changes Since 1.1.0

Phase 6.2 (commit `a5dec93`) introduced exactly two changes:

| # | Change | Kind |
| --- | --- | --- |
| C1 | `risk_constraints` items now carry `category` (the prohibited category from the filter rule) | Additive output field |
| C2 | `finance.investment-advice` keyword coverage extended with `guaranteed buy`, `guaranteed profit`, `guaranteed gain`, `must buy`, `稳赚不赔`, `必买` | Expanded detection |

Neither change removes or renames anything, and neither alters a required
field.

## 3. SemVer Judgement

### Why not MAJOR

- No field was removed, renamed or made required;
- the `PluginContribution` protocol in `plugin_interface/base.py` is untouched;
- the private `domain_extension` shape is unchanged, so the private schema
  version stays at `1.1.0`;
- the shared artifact schema is unchanged;
- every input that previously validated still validates, and every previously
  emitted field is still emitted.

### Why not PATCH

- **C1 adds a field consumers can now read.** A new output capability is
  functionality, not a fix.
- **C2 changes observable behaviour.** Inputs that previously produced no risk
  constraint can now produce a `block` constraint. A consumer relying on
  "this text is safe" sees a different result. That is a behavioural addition,
  and it must be visible in the version so a deployment can decide when to take
  it.

### Conclusion

```text
SemVer judgement : MINOR (backward compatible functionality added)
Plugin version   : 1.1.0 -> 1.2.0
```

## 4. Applied Changes

| File | Field | From | To | Reason |
| --- | --- | --- | --- | --- |
| `plugin.json` | `plugin.version` | `1.1.0` | `1.2.0` | C1 + C2 |
| `rules/filter_rules.json` | `version` | `1.1.0` | `1.2.0` | C2 |
| `release.json` | `version` | *(new)* | `1.2.0` | Release manifest, must agree with `plugin.json` |

Unchanged on purpose: `domain_schema.version` (`1.1.0`), `evaluation.version`
(`1.1.0`), `rules/value_rules.json` (`1.1.0`),
`rules/structure_templates.json` (`1.0.0`), `contract.version` (`1.0`), the
shared artifact schema, and the runtime config contract.

## 5. Compatibility Statement

```text
Plugin                 : xiaolin_finance 1.2.0
Plugin specification   : creator-distillation-plugin 1.0
Domain contract        : domain_extension 1.1.0
Artifact schema        : unified_distillation_artifact 1.0.0
Runtime config contract: 1.0.0
```

An instance running framework `creator-agent-template-v0.2.0-rc1` can load this
plugin without any framework change: the plugin is selected purely by
`config/runtime/default.json` `plugins.enabled` / `plugins.default`.

### Upgrading from 1.1.0

Artifacts produced by 1.1.0 remain valid — they simply lack `category` on their
risk constraints, and the shared schema does not require it. Consumers that want
the category can read it when present. No consumer change is required to accept
1.1.0 artifacts.

### Downgrading from 1.2.0

Consumers that persisted 1.2.0 artifacts and then downgrade to 1.1.0 will see
`category` disappear from newly produced risk constraints. No schema violation
results.

## 6. Enforcement

The version decision is enforced rather than documented only:
`tests/xiaolin_finance_release/test_release_manifest.py` asserts that
`release.json`, `plugin.json`, the private schema version the plugin actually
emits, and the rubric version all agree, and that the declared compatibility
strings match the framework's real contract values.
