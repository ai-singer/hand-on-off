# Creator Agent Framework Phase 6.3 - xiaolin_finance Plugin Release Preparation

## Plugin Release Status

```text
Plugin Release Status: READY
```

```text
Validated Plugin -> Versioned Plugin Release Candidate -> Ready for Lobster Plugin Deployment Validation
```

`xiaolin_finance` 1.2.0 已具备版本化插件候选的完整要素：一致的版本声明、发布清单、
完整的插件文档、专用的发布测试，以及全量回归通过。

**READY 的确切含义是"可用于目标实例的插件部署验证"，不是"生产就绪"。** 第 5 节列出的
已知问题未被修复（本阶段范围内不允许修改规则），必须在部署验证中实测。

本阶段**未修改** Universal Distillation Framework、Runtime Bootstrap、Artifact
Pipeline、Workflow、Security Gate；**未**修改任何历史 commit，**未**修改
`creator-agent-template-v0.2.0-rc1` Tag；**未**生成任何财经内容。

## 1. Version

| 项 | 值 |
| --- | --- |
| Plugin | `xiaolin_finance` **1.2.0** |
| Previous | `1.1.0` |
| Bump | **MINOR** |
| Release manifest | `plugins/xiaolin_finance/release.json` |
| Release status | `release-candidate` |

SemVer 判断依据见 [`XIAOLIN_FINANCE_VERSION_DECISION.md`](XIAOLIN_FINANCE_VERSION_DECISION.md)。

### 版本审计发现并修正的两项缺陷

| ID | 缺陷 | 修正 |
| --- | --- | --- |
| A-01 | Phase 6.2 改变了输出与检测行为，但 `plugin.json` 仍为 `1.1.0` | `1.1.0 → 1.2.0` |
| A-02 | `rules/filter_rules.json` 内容在 6.2 变更，版本仍为 `1.1.0` | `1.1.0 → 1.2.0` |

`rules/structure_templates.json` 保持 `1.0.0` 是**正确**的（该文件自创建以来未被修改），
并非漂移——每个文件版本化自身的修订。

## 2. Compatibility Matrix

| Component | Version |
| --- | --- |
| Framework (template) | `creator-agent-template-v0.2.0-rc1` (main `8c99f47`) |
| Plugin specification | `creator-distillation-plugin@1.0` |
| Runtime | `creator-agent-runtime-config@1.0.0` |
| Artifact Schema | `unified_distillation_artifact@1.0.0` |
| Domain contract | `domain_extension@1.1.0` |
| **Plugin** | **`xiaolin_finance@1.2.0`** |

三项兼容性声明**可机器校验**，由发布测试逐项比对到框架的真实契约值：

| 声明字段 | 校验对象 | 实测 |
| --- | --- | --- |
| `framework_compatibility` | `plugin_interface/creator_distillation_plugin_spec.md` 的 Specification version | `1.0` ✓ |
| `runtime_requirement` | `runtime.SUPPORTED_CONFIG_VERSION` | `1.0.0` ✓ |
| `artifact_schema_version` | 制品实际输出的 `artifact_version` | `1.0.0` ✓ |

### 升级 / 降级行为

- **从 1.1.0 升级**：1.1.0 产出的 artifact 仍然有效（只是 `risk_constraints` 缺少
  `category`，共享 Schema 不要求该字段）。消费方无需修改即可接受旧 artifact。
- **从 1.2.0 降级**：持久化过 1.2.0 artifact 的消费方降级后，新产出的风险约束不再携带
  `category`，不产生 Schema 违规。
- **实例侧**：插件仍完全由 `config/runtime/default.json` 的 `plugins.enabled` /
  `plugins.default` 选择，无需任何框架改动。

## 3. Release Manifest

`plugins/xiaolin_finance/release.json`：

| 字段 | 值 |
| --- | --- |
| `name` | `xiaolin_finance` |
| `version` | `1.2.0` |
| `framework_compatibility` | `creator-distillation-plugin@1.0` |
| `artifact_schema_version` | `1.0.0` |
| `runtime_requirement` | `creator-agent-runtime-config@1.0.0` |
| `capabilities` | 15 项，格式 `<kind>:<id>` |

`capabilities` 是三组能力的联合，并被测试逐组比对到真实来源：

```text
distill:business_mechanism          prohibit:investment_advice       evaluate:performance
distill:financial_structure         prohibit:market_prediction       evaluate:structure_quality
distill:data_expression_pattern     prohibit:emotional_language      evaluate:transferability
distill:case_selection_logic        prohibit:unverified_fact         evaluate:data_credibility
distill:misconception_analysis                                       evaluate:explanation_completeness
                                                                     evaluate:risk_boundary
```

补充字段：`domain_contract_version`、`python_requirement`、`entrypoint`、
`release_status`、`side_effects`、`network_required`、`writes_content`。

`release.json` 是**面向发布**的清单（版本 + 兼容性 + 能力），`plugin.json` 是**面向运行时**
的清单（身份 + 契约 + 段落 + 文件位置）。两者都声明版本，因此**版本一致性由测试强制**，
而不是靠人工维护。

## 4. Validation Evidence

### 4.1 新增发布测试 `tests/xiaolin_finance_release/`（8 项）

| 要求 | 测试方法 | 验证点 |
| --- | --- | --- |
| Test 1 `release.json` 合法 | `test_release_manifest_is_valid`、`test_capabilities_match_the_declared_taxonomy` | 6 个必填字段齐备；版本语义化；capabilities 非空、无重复、格式合法；三组能力逐一等于 `plugin.json` 的 distills / prohibits 与 rubric 的检查集 |
| Test 2 版本一致 | `test_versions_agree_across_declarations` | `release.version` == `plugin.json` == **运行时实例身份**；`domain_contract_version` == `domain_schema.version`；`plugin.json.evaluation.version` == rubric `version`；全部规则文件版本语义化合法 |
| Test 3 Schema 版本兼容 | `test_declared_schema_compatibility_matches_reality` | 三项兼容性声明逐一比对到规范文件 / `SUPPORTED_CONFIG_VERSION` / 实际 artifact 输出；双层 Schema 校验 `PASS` |
| Test 4 Runtime 可加载 | `test_runtime_loads_the_release_plugin` | `bootstrap()` 后插件在 `RuntimeContext` 中且为 default；实例身份版本 == 发布版本；产出的 artifact 与 domain_extension 均记录该版本 |
| Test 5 旧 Artifact 兼容 | `test_artifacts_predating_the_new_field_remain_valid`、`test_domain_extension_shape_is_unchanged_by_the_release` | 剥离 `category` 的 artifact 仍通过共享 Schema；共享 Schema 确实不要求该字段；domain 契约版本未变 |
| Test 6 风险字段兼容 | `test_risk_constraint_fields_stay_compatible` | 共享 Schema 的 `risk_constraints` 属性集与必填集**精确等于** 5 个必需字段；当前输出的每条风险既含 5 个必需字段又含合法 `category`；仅保留 5 个必需字段的最小风险仍通过 Schema |

### 4.2 历史阶段证据（未修改，继续通过）

| 阶段 | 测试位置 | 数量 |
| --- | --- | ---: |
| Phase 6.1 插件契约 | `tests/finance_plugin/` | 16 |
| Phase 6.2 运行时验证 | `tests/xiaolin_finance_runtime/` | 21 |
| Phase 6.3 发布测试 | `tests/xiaolin_finance_release/` | 8 |
| 框架既有 | `tests/` 其余 | 59 |
| **合计** | | **104** |

### 4.3 全量验证

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 全量单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **104** tests, OK（6.2 的 96 + 新 8） |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json`（含新增 `release.json`） | **PASS**，**23/23** |
| Secret scan — 工作区 / 仓库根 | `python security/secret_scan.py .` / `..\..` | **PASS**，两范围 0 发现 |

## 5. Known Issues

以下问题**保留未修复**。本阶段的允许范围是版本升级、文档更新、测试补充与发布文档，
**不包含修改插件规则**，因此仅记录并给出实测证据。

### 5.1 关键词匹配假阳性（fail-closed 方向）

```
"This is not a guaranteed return."   ->  investment_advice / block        (误报)
```

子串匹配不做否定处理。方向是**保守的**（多阻断而非漏放），但会让合法内容进入人工复核。

### 5.2 关键词匹配假阴性（**更严重**，本轮实测）

```
"I would put my entire savings into this company."        ->  NO RISK
"This is the best investment you can make right now."     ->  NO RISK
"You should move your money here before it is too late."  ->  NO RISK
"Analysts are certain the price target will be reached."  ->  NO RISK
```

五条投资建议/预测表述中**四条完全绕过风险边界**。这不是保守方向的误报，而是**风险边界
的真实缺口**：规则集的英文覆盖不足（例如规则含中文 `目标价`、`价格预测`，但没有英文
`price target`），且不做语义判断。

**必须由部署验证专门探测**：建议在目标实例用对抗性表述集实测风险边界召回率，而不是只
验证已收录的关键词。

### 5.3 无语料校准

财经规则为手工设计的通用示例，从未在真实素材上评估召回率与精确率。本阶段（以及 6.1/6.2）
均禁止抓取真实财经素材，因此**准确率指标未知**。

### 5.4 语义风险理解能力有限

插件是确定性的关键词规则解释器，不具备语义理解：

- 无法识别未含关键词的建议、暗示性表述或讽刺；
- 无法判断"解释机制"与"给出建议"之间更细的语用差别；
- 多语言覆盖不完整（中英混排尚可，其他语言未设计）。

这是规则式插件的架构边界，不是待修缺陷。若要实质改善，应在插件边界内引入可注入的
评估适配器，而不是继续扩充关键词。

### 5.5 其他已记录项

| ID | 问题 | 影响 |
| --- | --- | --- |
| V-01 | `release.json` 与 `plugin.json` 都声明 version | 属有意的双清单设计，一致性由 Test 2 强制 |
| V-02 | `domain_extension.schema.json` 自身不含版本字段 | 版本只在 `plugin.json` 声明一次，避免漂移；代价是该 schema 文件无法独立标识版本 |
| V-03 | 模板版本命名空间仍不统一（`pyproject` 0.1.0 / runtime config 1.0.0 / tag v0.2.0-rc1） | 沿用 Phase 5.4 的 VER-1，未在本阶段处理 |
| V-04 | 规则为关键词匹配，同义表达漏检 | 见 5.2 |

## 6. Release Artifacts

| 文件 | 类型 |
| --- | --- |
| `plugins/xiaolin_finance/release.json` | 新增 — 发布清单 |
| `plugins/xiaolin_finance/plugin.json` | 修改 — plugin.version `1.2.0` |
| `plugins/xiaolin_finance/rules/filter_rules.json` | 修改 — version `1.2.0` |
| `plugins/xiaolin_finance/README.md` | 修改 — Purpose / Input / Output / Allowed Distillation / Forbidden Behavior / Runtime Usage |
| `tests/xiaolin_finance_release/` | 新增 — 8 项发布测试 |
| `docs/XIAOLIN_FINANCE_VERSION_DECISION.md` | 新增 |
| `docs/PHASE_6_3_XIAOLIN_FINANCE_PLUGIN_RELEASE.md` | 新增（本文件） |

未修改：`plugin.py`、`rules/value_rules.json`、`rules/structure_templates.json`、
`schemas/domain_extension.schema.json`、`evaluation/rubric.json`、共享 Schema，以及全部
框架与运行时目录。

## 7. Next Step

1. 在目标实例（小龙虾）执行**插件部署验证**：按 `config/runtime/default.json` 加载
   1.2.0、跑通 Lobster 五节点链路、确认风险阻断与生成交接行为；
2. **专项探测风险边界召回率**（第 5.2 节），用对抗性表述集而不是已收录关键词；
3. 依据实测结果决定是否在下一阶段扩充规则或引入可注入评估适配器；
4. 若验证通过，再考虑版本晋升（脱离 `release-candidate`）并同步远端。

## 8. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

1. **版本声明必须被测试强制**。`release.json` 与 `plugin.json` 都写 version，靠人工同步
   必然漂移；本轮用一条 "release == manifest == 运行时实例身份" 的断言把漂移变成测试
   失败。
2. **发布前必须做版本审计，而不是假定版本正确**。审计立刻发现两处陈旧版本：
   行为已变但插件版本未升、规则文件内容已变但版本未升。二者都不会被功能测试发现。
3. **已知问题要测出方向，而不是只写"可能不准"**。本轮实测出 4/5 假阴性，
   与"假阳性是保守的"这一常见假设相反——风险边界的主要失效方向是**漏放**。
   发布文档中把这一点写成可复现的证据，比写"规则可能不完善"有用得多。
