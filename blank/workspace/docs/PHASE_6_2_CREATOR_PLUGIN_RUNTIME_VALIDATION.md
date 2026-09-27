# Creator Agent Framework Phase 6.2 - Creator Plugin Runtime Validation

```text
Phase 6.2 Creator Plugin Runtime Validation Status: PASS

Universal Framework -> Creator Plugin -> Runtime Execution -> Validated Domain Artifact
```

本阶段证明 `xiaolin_finance` 不是静态规则包，而是可以被 Creator Agent Runtime 实际
调用的领域蒸馏插件。**未修改**核心 Framework、Runtime Bootstrap、Artifact Pipeline 与
Workflow 结构；**未**写真实文章、生成视频或抓取真实财经素材（全部测试素材为合成文本）。

## 1. Runtime Loading

Plugin 进入 Runtime 的完整链路：

```text
config/runtime/default.json  plugins.enabled = ["plugins.xiaolin_finance"]
        |
        v
runtime.bootstrap()  ->  _load_plugins()  ->  core.load_plugin()
        |                                        |-- importlib.import_module("plugins.xiaolin_finance")
        |                                        |-- plugins/xiaolin_finance/__init__.py :: create_plugin()
        |                                        |-- isinstance(plugin, CreatorDistillationPlugin)
        |                                        |-- identity completeness check
        v
RuntimeContext.plugins["plugins.xiaolin_finance"]  ==  RuntimeContext.default_plugin
```

注意：`plugin.json` **不**参与加载判定——它由 `plugin.py` 在构造/调用时读取，作为身份
的唯一来源。加载链本身仍由 `plugins.enabled` 决定。

| 验证 | 结果 |
| --- | --- |
| Runtime Config 启用 xiaolin_finance | **成功加载**；`context.plugins` 含该模块路径；`default_plugin.identity.name == "xiaolin_finance"`；`default_plugin` 与注册表项为**同一对象** |
| Runtime Config 未启用（改用探针插件） | `context.plugins` 中**不含** xiaolin_finance；`context.plugin(...)` 抛 `KeyError` |
| 三方身份一致 | `plugin.json` 的 name/version/domain/creator_target == `RuntimeContext` 中的实例 == 重新 `load_plugin()` 得到的实例；`domain_extension.schema_version` == `plugin.json` 声明的 `domain_schema.version` |

```text
plugin.json      : xiaolin_finance 1.1.0 / finance / xiaolin-style-finance-explainer
runtime identity : xiaolin_finance 1.1.0 / finance / xiaolin-style-finance-explainer
plugin instance  : xiaolin_finance 1.1.0 / finance / xiaolin-style-finance-explainer
```

## 2. Pipeline Flow

```text
RawSource (document, metadata={source: financial_report})
   |
   v
DistillationEngine.distill()
   |-- CommonExtractor.extract(sources)            -> common_signals（四族）
   |-- plugin.enhance(sources, deepcopy(signals))  -> PluginContribution
   |-- merge: field_enhancements 仅追加
   |-- evaluate_distillation_artifact(merged, sources)  -> evaluation_result.common
   |-- assemble artifact
   |-- validate_runtime_schemas()                  共享 Schema + 私有 Schema
   v
Unified Distillation Artifact
   |
   v
Lobster Runtime Adapter（distill -> plugin-check -> gate -> generation-handoff）
   v
Quality Gate PASS -> Generation Handoff (ready_for_generation)
```

| 验证 | 结果 |
| --- | --- |
| 引擎单次运行产出 artifact | `plugin.name == xiaolin_finance`，`artifact_version == 1.0.0`，`rubric_version` 与 rubric 文件一致 |
| 通用四族不被改写 | 与空领域插件对比：`knowledge_unit` / `content_template` / `style_pattern` **逐字节相同**；`topic_candidate` 前 N 项与原内容相同，仅在其后追加，且追加项 `origin` 全部为 `xiaolin_finance` |
| `domain_extension` 存在且合规 | 通过私有 Schema 与共享 Schema 两层校验（`validate_runtime_schemas` 返回 `PASS` 且 `domain_schema_applied=True`）|
| Runtime Adapter 全链 | `distill` → `plugin-check` → `gate` → `generation-handoff` 全部通过，终态 `ready_for_generation` |

`common_signal_counts` 实测：`content_template` / `knowledge_unit` / `style_pattern`
的计数与最终 artifact 一致，只有 `topic_candidate` 因插件增强而增加——**这正是"只追加"的
结构化证据**。

## 3. Finance Enhancement Evidence

五类财经增强，每类一个独立合成输入（Step 3 Test A–E）：

| # | 输入（合成）| 命中段落 | 触发词 | matched |
| --- | --- | --- | --- | --- |
| A | The company business model connects subscription revenue with service cost. | `business_mechanism` | business model, revenue, cost | **true** |
| B | The income statement and balance sheet describe the cost structure. | `financial_structure` | income statement, balance sheet, cost structure | **true** |
| C | The growth rate ratio compares this quarter with the previous one. | `data_expression_pattern` | growth rate, ratio | **true** |
| D | This enterprise is used as the case because its earnings are traceable. | `case_selection_logic` | enterprise, earnings | **true** |
| E | A common misunderstanding is that revenue equals profit. | `misconception_analysis` | misunderstanding | **true** |

每项断言除 `matched=true` 外，还校验：`signals` 非空、每个 signal 的 `section` 与
`source_ids` 正确、`matched_terms` 非空。另有一项独立性测试确认：只触发 E 的输入不会
误点亮 `financial_structure` 或 `data_expression_pattern`。

`source_classification` 按来源在通用抽取中**实际被引用的位置**推导（例如只进入
`knowledge_unit` 的来源被标记为 `knowledge_source`）。

## 4. Risk Boundary Evidence

| 输入（合成）| category | severity | action | domain score | passed | risk_boundary | 生成适配器调用 |
| --- | --- | --- | --- | ---: | --- | ---: | ---: |
| This stock is a guaranteed buy. | `investment_advice` | **block** | **block** | 0.20 | false | **0.0** | **0** |
| Company price will definitely rise. | `market_prediction` | warning | require_evidence | 0.42 | false | 0.75 | **0** |
| 据说不具名的消息人士透露，该公司收入翻倍。 | `unverified_fact` | warning | require_evidence | 0.54 | false | 0.75 | **0** |

- 三类输入均使管线返回 `review_required` 且**生成适配器调用次数为 0**；
- 投资建议触发 `block`，评分被上限压到 0.2 且 `risk_boundary = 0.0`；
- 风险项同时携带 `category`（本次为验证新增），因此"禁止类别"在 artifact 中直接可见，
  无需反查 rule id。

### 本阶段修复的 Plugin 问题（任务允许）

任务 Step 4 指定的输入 **"This stock is a guaranteed buy."** 在 Phase 6.1 的规则下
**不产生任何风险**——`finance.investment-advice` 只包含 `guaranteed return` 等词形，
不含 `guaranteed buy`。这是真实的召回缺口，因此本轮：

1. 为 `finance.investment-advice` 补充 `guaranteed buy` / `guaranteed profit` /
   `guaranteed gain` / `must buy` / `稳赚不赔` / `必买`；
2. 在 `risk_constraints` 中增加 `category` 字段（取自过滤规则的 `category`）。

修复后任务指定输入正确产生 `block`。既有 75 项测试全部未修改即通过。

## 5. Evaluation Integration

`evaluation_result.domain` 报告两层共 6 个维度，全部进入质量评估：

| 层 | 维度 | 实测（report 形状输入）|
| --- | --- | ---: |
| 继承通用框架 | `performance` | 0.4 |
| 继承通用框架 | `structure_quality` | 1.0 |
| 继承通用框架 | `transferability` | 1.0 |
| 财经检查 | `data_credibility` | 1.0 |
| 财经检查 | `explanation_completeness` | 0.5 |
| 财经检查 | `risk_boundary` | 1.0 |

```text
domain score = 0.64   pass_score = 0.6   passed = true
matched_sections = [business_mechanism, financial_structure]
```

`explanation_completeness = 0.5` 是因为该输入解释了机制但未包含数据解释维度
（rubric 要求 `business_mechanism` + `data_interpretation`）——评分如实反映证据，未
被放宽。

### 评分来自 rubric 而非硬编码（实测）

| 实验 | 结果 |
| --- | --- |
| 基线（真实 rubric） | score 0.64，passed true |
| 将 rubric `scoring.base` 改为 0.95 | score **上升**（符合 `base + coverage × weight − penalty`）|
| 将 rubric `pass_score` 改为 0.99 | score **不变**（0.64），`passed` 变为 **false** |

第一项证明评分公式读取 rubric 参数；第二项证明通过阈值同样来自 rubric。既有
`checks`、`inherited_checks`、`finance_checks` 在两种改动下其余数值不变。

## 6. Remaining Issues

| ID | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| R-01 | 关键词为**子串匹配**，不做否定/词形处理 | `"This is not a guaranteed return."` 仍会命中 `block`（本轮实测）| 属 fail-closed 方向的误报；精确化需引入规则表达式而非继续堆关键词 |
| R-02 | 本轮为通过任务指定输入而扩充了 `investment-advice` 关键词 | 规则集仍非穷举，同义表达可能漏检 | 规则集应在目标实例用真实素材校准（本阶段禁止抓取素材）|
| R-03 | `risk_constraints.category` 为本轮新增字段 | 共享 Schema 的 `risk_constraints` 未声明 `additionalProperties: false`，因此新增字段合法；但消费方若做严格字段白名单需同步 | 已在 Phase 6.1 的契约文档中记录 `risk_constraints` 的最小形状；如需固定应升级共享 Schema |
| R-04 | `explanation_completeness` 对"只有机制、没有数据"的输入给 0.5 | 该维度只报告、不直接决定 `passed` | 若要让其参与门槛，应在 rubric 中显式声明权重并单独评审 |
| R-05 | 单来源输入的 `transferability` 恒为 1.0 | 单来源无法体现迁移性 | 多来源用例才能真正区分；本轮未构造多来源财经素材 |
| R-06 | 插件版本仍为 `1.1.0`，但本轮修改了规则与输出字段 | 按语义化版本，规则扩充与新字段属向后兼容增量；仍需决定是否升到 `1.2.0` | 建议随下一阶段一并升版并在 release notes 记录 |
| R-07 | 财经规则未与真实语料校准 | 召回率/精确率未知 | 留待目标实例运行时校准 |

## 7. 测试与验证

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 全量单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **96** tests, OK |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | `plugin.json` / domain schema / rubric / 全部 `*.json` | **PASS**，22/22 |
| Secret scan — 工作区 / 仓库根 | `python security/secret_scan.py .` / `..\..` | **PASS**，两范围 0 发现 |

### 新增 `tests/xiaolin_finance_runtime/`（21 项）

| 分组 | 任务要求 | 实际 | 说明 |
| --- | ---: | ---: | --- |
| Runtime Loading | 3 | **3** | 启用 / 未启用 / 三方身份一致 |
| Pipeline Integration | 3 | **4** | 引擎产 artifact、通用四族只追加、domain_extension 两层合规、Runtime Adapter 全链 |
| Domain Enhancement | 5 | **6** | Test A–E + 段落独立性 |
| Risk Blocking | 3 | **6** | 三类风险 × (风险形状 + 生成阻断) + 类别完整性 |
| Evaluation | 2 | **2** | 六维度齐备 / 评分由 rubric 驱动 |
| **合计** | 16 | **21** | |

测试总数 75 → **96**。

## 8. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

1. **"规则集存在"不等于"规则集命中"**。任务给出的标准输入
   `"This stock is a guaranteed buy."` 在既有规则下**零命中**——如果只写"投资建议会被
   阻断"的断言并换一个能过的输入，这个缺口会被永久掩盖。验收应当**使用任务/需求原文
   提供的输入**，而不是为了让测试通过而挑选输入。
2. **评分策略必须可被外部改动证明**。断言"分数在 0–1 之间"证明不了策略来自 rubric；
   本轮通过改写 rubric 参数观察分数与阈值随之变化，才真正证明"非硬编码"。这类
   "参数注入实验"建议作为配置驱动能力的通用验收手法。
3. **只追加语义需要结构化证据**。比较最终列表长度只能说明"变多了"；比较
   `common_signal_counts` 与最终 artifact 的逐字段计数，才能定位到"只有
   topic_candidate 被扩展"这一事实。
