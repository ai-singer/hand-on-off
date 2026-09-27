# Creator Agent Framework Phase 6.1 - Creator Specific Plugin Specification

```text
Phase 6.1 Creator Plugin Specification Status: PASS

Universal Distillation Framework
  -> Stable Plugin Contract
  -> xiaolin_finance Domain Plugin
  -> Unified Artifact Compatible          CLOSED
```

本阶段在不修改 `distillation_core`、`runtime`、`artifact`、`workflow`、`security`
的前提下，把 Creator 能力作为 Plugin Layer 接入，并建立 xiaolin_finance 的
Creator Specific Distillation Contract。

**没有**写文章、生成视频、训练模型或抓取真实财经素材。

## 1. Architecture

```text
Raw Source
   |
   v
Universal Distillation Framework        distillation_core / core / evaluation
   |  common_signals: topic_candidate, content_template, knowledge_unit, style_pattern
   v
Creator Specific Plugin                 plugins/xiaolin_finance
   |  PluginContribution: domain_extension, risk_constraints,
   |                      evaluation_result, field_enhancements
   v
Unified Distillation Artifact           schemas/unified_distillation_artifact.json
   v
Generation                              injected adapter, only after quality gate PASS
```

### 新增与修改文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `plugins/xiaolin_finance/plugin.json` | 新增 | 声明式插件清单（身份 / 契约 / 段落 / 禁止类别 / 文件位置）|
| `plugins/xiaolin_finance/plugin.py` | 修改 | 解释规则文件；读取 `plugin.json` 作为身份唯一来源 |
| `plugins/xiaolin_finance/rules/value_rules.json` | 修改 | 3 → 5 维度，每条规则声明其所属段落 |
| `plugins/xiaolin_finance/rules/filter_rules.json` | 修改 | 2 → 4 禁止类别 |
| `plugins/xiaolin_finance/schemas/domain_extension.schema.json` | 修改 | 增加 5 个段落字段 + `source_classification` |
| `plugins/xiaolin_finance/evaluation/rubric.json` | 修改 | 5 个评分维度 + 继承维度 + 财经检查 + 显式评分参数 |
| `plugins/xiaolin_finance/README.md` | 修改 | 插件边界、蒸馏/禁止清单、评价说明 |
| `tests/finance_plugin/` | 新增 | 16 项契约测试 |
| `docs/PLUGIN_INTERFACE_COMPATIBILITY.md` | 新增 | Step 1 产出 |
| `docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md` | 新增 | Step 2 产出 |

`plugin.json` 是身份的**唯一来源**：`plugin.py` 的 `identity` 从清单读取，而不是
重复硬编码。声明与行为因此不可能漂移，并由测试双向校验。

### 未修改（已核验）

`distillation_core/`、`runtime/`、`artifact/`、`workflows/`、`security/`、`core/`、
`plugin_interface/`、`evaluation/`、`schemas/unified_distillation_artifact.json`
均未改动。

## 2. Contract

### Input

来自 Unified Distillation Framework：原样 `RawSource` 记录 + 已分类的
`common_signals`（`topic_candidate` / `content_template` / `knowledge_unit` /
`style_pattern`）。`common_signals` 是深拷贝，插件可读不可写。

### Output

`PluginContribution`，四个字段全部有硬约束：

| 字段 | 约束 |
| --- | --- |
| `domain_extension` | 私有无覆盖语义；**只能新增字段**，须通过插件私有 Schema |
| `risk_constraints` | 每条必须含 `rule_id` / `severity` / `action` / `message` / `source_ids` |
| `evaluation_result` | 确定性证据；含继承维度与领域检查 |
| `field_enhancements` | 对四个通用族的**仅追加**增强 |

### 不可绕过

- `field_enhancements` 出现四个通用族以外的键 → 引擎抛 `ValueError`；
- 增强以 `extend` 追加，插件**无法删除或替换**通用信号；
- 合并后的 artifact 必须通过 `schemas/unified_distillation_artifact.json`；
- 私有 Schema 存在时，在共享 Schema 通过后立即生效，失败则**先于质量门**停止；
- 插件失败即运行失败，不得回退到通用结果。

完整说明见 `docs/PLUGIN_INTERFACE_COMPATIBILITY.md` 与
`docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md`。

## 3. Finance Rules

### 应该蒸馏（5 个段落）

| 段落 | 内容 | 规则 ID |
| --- | --- | --- |
| `business_mechanism` | 商业机制解释：公司如何赚钱、商业模式、成本与激励如何连接 | `finance.business-mechanism` |
| `financial_structure` | 财报分析结构：收入结构、成本结构、增长来源、风险因素 | `finance.financial-structure` |
| `data_expression_pattern` | 数据表达方式：对比、趋势、指标解释（含单位与期间）| `finance.data-interpretation` |
| `case_selection_logic` | 案例选择方式：为什么选这个公司、案例如何支撑观点 | `finance.company-case` |
| `misconception_analysis` | 认知误区拆解：常见误解，事实与认知的差异 | `finance.misconception-analysis` |

### 禁止蒸馏（4 个类别）

| 类别 | 内容 | severity / action |
| --- | --- | --- |
| `investment_advice` | 买入 / 卖出 / 推荐 / 稳赚承诺 | `block` / `block` |
| `market_prediction` | 无依据预测、价格预测、目标价 | `warning` / `require_evidence` |
| `emotional_language` | 煽动、恐慌、夸张判断 | `warning` / `downrank` |
| `unverified_fact` | 未确认数据、来源不明、传闻 | `warning` / `require_evidence` |

禁止规则**不会静默删除**内容：每次命中都产生一条显式 `risk_constraint`，由质量门
决定后续动作。

### Source Classification

按来源在通用抽取中**实际被引用的位置**判定其蒸馏角色，而不是按配置猜测：

| artifact 字段 | 角色 |
| --- | --- |
| `topic_candidate` | `topic_source` |
| `knowledge_unit` | `knowledge_source` |
| `content_template` | `structure_source` |
| `style_pattern` | `style_source` |

结果写入 `domain_extension.source_classification`。

### 质量评价

`evaluation_result.domain` 报告两层：

- **继承通用框架**：`performance`、`structure_quality`、`transferability`
- **财经检查**：`data_credibility`、`explanation_completeness`、`risk_boundary`

评分参数（`base` / `coverage_weight` / `warning_penalty` / `blocking_score_cap` 等）
位于 `evaluation/rubric.json`，由代码读取而非硬编码，策略因此可审阅。

## 4. Schema

`plugins/xiaolin_finance/schemas/domain_extension.schema.json` 版本 `1.1.0`，
`additionalProperties: false`，**只扩展不覆盖**：

```text
必填：schema_version, plugin_identity, value_signals, filtered_claims,
      recommended_structure, common_signal_counts,
      business_mechanism, financial_structure, data_expression_pattern,
      case_selection_logic, misconception_analysis, source_classification
```

每个段落字段形状一致：`{matched: boolean, signals: array, source_ids: array}`。

共享 artifact Schema 中 `domain_extension` 为开放对象（`{"type": "object"}`），
因此私有扩展**在结构上不可能覆盖** `topic_candidate`、`content_template`、
`knowledge_unit`、`style_pattern`、`risk_constraints` 或 `evaluation_result`。
私有 Schema 与共享 Schema 由既有的 `schema_validation` 层顺序执行。

## 5. Validation

### 测试结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **75** tests, OK（6.0 的 59 + 新 16） |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json` | **PASS**，**22/22**（原 21 + 新 `plugin.json`）|
| Secret scan — 工作区 / 仓库根 | `python security/secret_scan.py .` / `..\..` | **PASS**，两范围 0 发现 |

### 任务要求的 6 项测试

| 要求 | 测试方法 | 验证点 |
| --- | --- | --- |
| Test 1 Plugin schema 合法 | `test_domain_extension_matches_private_schema`、`test_manifest_agrees_with_runtime_identity`、`test_manifest_declared_files_exist` | 私有 Schema 通过；清单与运行时身份逐字段一致；声明的规则/Schema/评估文件均存在 |
| Test 2 财经输入增强成功 | `test_finance_input_produces_domain_enhancement` | 段落命中；`topic_candidate` 出现 `origin=xiaolin_finance`；领域评分通过；结构模板被选中 |
| Test 3 投资建议被阻断 | `test_investment_advice_is_blocked`、`test_investment_advice_stops_before_generation` | `block` 风险产生；`risk_boundary=0.0`；管线 `review_required` 且生成适配器调用次数为 **0** |
| Test 4 无依据预测被阻断 | `test_unsupported_prediction_requires_evidence`、`test_unsupported_prediction_stops_before_generation` | `require_evidence` 风险产生；管线 `review_required` 且生成适配器调用次数为 **0** |
| Test 5 通用 Artifact 兼容 | `test_artifact_remains_compatible_with_the_shared_schema` | artifact 通过共享 Schema 与 `validate_runtime_schemas`（`PASS` + 私有 Schema 已应用）|
| Test 6 Creator Plugin 不修改 Core | `test_plugin_only_appends_and_never_rewrites_common_output`、`test_replacing_the_plugin_changes_only_the_domain_layer` | 与无领域插件对比：`knowledge_unit` / `content_template` / `style_pattern` **逐字节相同**；`topic_candidate` 仅在原内容之后追加 |

### 补充测试

- `test_declared_taxonomy_matches_the_rule_files`：`plugin.json` 声明的段落/禁止类别与规则文件**完全一致**；
- `test_every_prohibited_category_has_a_rule`：4 个禁止类别均有规则，severity/action 取值合法；
- `test_sources_are_classified_by_the_role_they_played`：来源角色来自真实引用位置；
- `test_evaluation_reports_inherited_and_finance_checks`：3 + 3 检查齐备且分值在 [0,1]；
- `test_plugin_is_deterministic`：两次运行输出完全一致（无副作用）。

### 关键实测数据

```text
identity        : xiaolin_finance 1.1.0 / finance / xiaolin-style-finance-explainer
schema_version  : 1.1.0
fixture 命中段落 : business_mechanism, data_expression_pattern, case_selection_logic
domain score    : 0.76 (pass_score 0.6) -> passed True
inherited       : performance 0.6, structure_quality 1.0, transferability 1.0
finance         : data_credibility 1.0, explanation_completeness 1.0, risk_boundary 1.0
"Buy now for a guaranteed return."  -> block / risk_boundary 0.0 / review_required / 生成 0 次
"…will definitely rise…"            -> require_evidence / review_required / 生成 0 次
```

## 6. 与既有框架的兼容性

- **既有 59 项测试全部未修改即通过**，包括断言
  `business_mechanism` / `data_interpretation` / `company_case` 三个维度存在的
  `test_finance_plugin_applies_domain_enhancement`：本阶段采用**纯增量**方式扩展
  分类法，未重命名既有维度；
- 插件版本 `1.0.0 → 1.1.0`，私有 Schema 版本 `1.0.0 → 1.1.0`（向后兼容的增量）；
- `config/runtime/default.json` 未改动，插件选择路径不变；
- Runtime Bootstrap、Lobster 集成、Artifact Validation 全部保持通过。

## 7. Remaining Issues

| ID | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| R-01 | 测试目录使用 `tests/finance_plugin/` 而非任务建议的 `tests/plugins/` | `plugins` 是工作区顶层包，`tests/plugins/` 会在 `unittest discover -s tests` 下**遮蔽**它（`tests/` 位于 `sys.path[0]`），插件导入将失败；Phase 5.2.2 与 5.3.1 已两次遇到同类问题并新增了护栏测试 | 保持现名；护栏测试 `test_test_packages_do_not_shadow_workspace_packages` 会阻止复发 |
| R-02 | 关键词匹配为子串匹配，未做词形/否定处理 | "not a guaranteed return" 仍会命中 `guaranteed return` | 属保守方向的误报（fail-closed）；如需精确化应引入规则表达式而不是继续堆关键词 |
| R-03 | `value_rules.json` 的 `weight` 参与 `topic_candidate.confidence`，不参与评分 | 权重语义仅部分生效（评分用等权覆盖率），已在 rubric 中显式声明 `scoring.method` | 若要让权重影响评分，应在 rubric 增加加权公式并单独评审 |
| R-04 | `source_classification` 由通用抽取的引用位置推导 | 通用抽取未引用的来源会得到空角色列表 | 属如实反映；如需强制覆盖应新增规则而非推断 |
| R-05 | 私有 Schema 使用 `additionalProperties: false` | 未来新增段落字段必须同时更新 Schema 与 `plugin.json` | 由 `test_declared_taxonomy_matches_the_rule_files` 兜住声明侧漂移 |
| R-06 | 财经规则为通用示例，未与真实素材校准 | 关键词召回率未在真实语料上验证（本阶段禁止抓取素材）| 留待目标实例用真实素材校准，属 Phase 6 后续 |

### 本阶段限制遵守

未写文章、未生成视频、未训练模型、未抓取真实财经素材；只建立 Creator Specific
Layer 的规范、声明式规则与契约测试。

## 8. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

1. **声明文件必须被代码消费，否则必然漂移**。`plugin.json` 若只是文档，就会与
   `plugin.py` 逐渐不一致。本轮让它成为身份的**唯一来源**，并加一条
   "清单 ↔ 规则文件 ↔ 运行时身份" 三方一致性测试，把漂移变成测试失败。
2. **"不修改 Core" 需要行为证明，而不是声明**。用同一个输入分别跑领域插件与空插件，
   断言三个通用字段逐字节相同、第四个字段仅追加——这比"插件里没有 import core"
   强得多，建议作为所有插件准入的固定验收项。
3. **增量优先于重命名**。既有测试断言了旧维度名，重命名会迫使修改框架测试；
   改为新增维度 + 段落映射，既实现新分类法，又让既有 59 项测试零改动通过。
