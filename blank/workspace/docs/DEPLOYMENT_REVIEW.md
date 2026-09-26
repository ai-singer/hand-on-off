# Creator Agent Framework Phase 2 部署前架构审查

## 审查摘要

- 审查对象：本地提交 `cfb38a8`（`feat: build creator agent framework foundation`）
- 审查日期：2026-09-26
- 审查范围：`blank/workspace/`
- 审查方式：静态架构审查、现有测试、只读配置/语法检查、两个内存诊断、当前 OpenClaw 官方约定对照
- 代码修改：无
- 测试修改：无
- 审查发现：9 项（高 4 / 中 4 / 低 1）

```text
Deployment Readiness: NOT READY
```

当前实现可以作为继续完善的框架基础，但不能直接进入空白龙虾实例部署。主要原因不是通用蒸馏核心或插件隔离失败，而是尚缺少可被当前 OpenClaw/Lobster 实际加载和执行的部署绑定；同时，风险质量门位于内容生成之后，已实证无法阻止带有 `block` 风险的内容进入生成适配器。

## 1. 当前架构状态

### 1.1 仓库结构

| 目标模块 | 实际位置 | 状态 | 说明 |
| --- | --- | --- | --- |
| `core/` | `core/` | PASS | 输入模型、插件加载、Schema 验证、Skill 发现边界清晰。 |
| `distillation/` | `distillation_core/` | NEED FIX | 能力存在且边界清晰，但目录名与任务约定不一致；属于低风险契约/命名偏差。 |
| `plugin_interface/` | `plugin_interface/` | PASS | 协议与具体插件分离。 |
| `plugins/` | `plugins/xiaolin_finance/` | PASS | 财经规则、私有 Schema、评价规则均位于插件内部。 |
| `skills/` | `skills/` | NEED FIX | 内部注册表可发现，但不满足当前 OpenClaw 原生 Skill 命名和依赖声明规范。 |
| `workflows/` | `workflows/content_distillation_pipeline/` | NEED FIX | Python 编排存在，但 `workflow.json` 只是描述文件，不是可直接运行的 Lobster 工作流。 |
| `schemas/` | `schemas/` | NEED FIX | 共享 Schema 存在；插件私有 Schema 没有被运行时验证。 |
| `evaluation/` | `evaluation/` | NEED FIX | 评价逻辑存在，但质量门执行顺序不符合部署要求。 |
| `tests/` | `tests/` | NEED FIX | 5 个基础测试通过，但未覆盖部署关键语义与龙虾集成。 |
| `docs/` | `docs/` | PASS | 架构、插件与部署说明齐全，但部分部署声明超过当前实现能力。 |

### 1.2 模块边界结论

**状态：NEED FIX**

正面结论：

- `core/` 与 `distillation_core/` 未包含财经规则或具体 Creator 插件导入。
- 具体领域逻辑全部位于 `plugins/xiaolin_finance/`。
- 内容生成通过 `GenerationAdapter` 注入，没有嵌入蒸馏核心。
- Skill、Workflow、Schema、Evaluation 和测试均有独立目录。
- 没有发现绝对路径写死；Schema 与插件资源均使用包相对路径。

需要修复的关键点是部署层而非领域隔离层：框架内部模块能组合，但还没有形成 OpenClaw/Lobster 可加载、可配置、可执行、可验证的运行单元。

## 2. 部署适配分析

### 2.1 工程能力到龙虾能力映射

| 工程模块对应龙虾能力状态 | 龙虾能力 | 当前状态与映射建议 |
| --- | --- | --- |
| 插件系统 | Skill / Plugin 工具能力 | **NEED FIX**。Python 插件协议可复用，但具体执行应由一个 OpenClaw Skill 调用稳定 CLI/工具；如果需要注册新工具，则应包装成 OpenClaw Plugin。当前只有 Python import，没有原生调用入口。 |
| Workflow | Lobster 工作流 | **NEED FIX**。应提供 `.lobster` 或符合 Lobster 字段约定的 YAML/JSON，步骤必须含可执行 `command`、输入传递、条件和审批；当前 `workflow.json` 仅有 `contract`/`contains` 元数据。 |
| 能力描述 | Skill 能力档案 | **NEED FIX**。`SKILL.md` 可作为能力说明，但名称使用下划线，且没有 OpenClaw `metadata.openclaw.requires` 依赖门控和实际调用命令。 |
| 实例配置 | Agent/Gateway 实例配置 | **NEED FIX**。`IDENTITY.md`、`USER.md`、`SOUL.md` 适合保留在实例；插件选择、工具 allowlist、Lobster 启用、工作区路径、密钥和适配器配置应由实例/Gateway 管理。当前 `CREATOR_*` 变量没有被代码消费。 |
| 版本管理 | GitHub 版本 / 发布制品 | **NEED FIX**。代码与规则应由 GitHub 管理，部署应绑定 commit/tag 与制品 SHA-256；当前本地分支比 `origin/main` 领先 1 个提交，远端不存在 `cfb38a8`。 |

### 2.2 GitHub 管理边界

以下内容应由 GitHub 作为不可变、可审查的源代码和版本事实管理：

- `core/`、`distillation_core/`、`plugin_interface/`；
- 插件代码、规则、私有 Schema 和评价 rubric；
- Skill 源文件与版本声明；
- Lobster 工作流定义和其调用的稳定 CLI/脚本；
- 共享 Schema、测试、文档、打包脚本；
- release tag、commit SHA、制品 SHA-256、兼容性矩阵。

### 2.3 龙虾实例管理边界

以下内容应由具体空白实例或 Gateway 配置管理，不应提交为通用框架默认值：

- 启用的 Creator/领域插件及版本；
- Creator 身份、受众、操作员偏好；
- Lobster 与其他工具的安装、启用和 allowlist；
- 模型、OCR、转写、搜索、存储、发布适配器；
- 密钥、账号权限、网络、超时、重试和成本限制；
- 工作流启用状态、审批人、定时任务、留存与日志策略；
- 当前部署制品、回滚制品和运行环境版本。

## 3. Skill 包规范审查

**状态：NEED FIX**

| 要求 | 当前实现 | 结论 |
| --- | --- | --- |
| metadata | `SKILL.md` frontmatter + `manifest.json` | 部分满足。OpenClaw 原生只识别 `SKILL.md` frontmatter；自定义 `manifest.json` 仅被内部注册表使用。 |
| version | 两处均声明 `1.0.0` | 满足内部版本记录，但缺少两处版本一致性校验。 |
| instructions | 每个 Skill 有 `SKILL.md` | 满足。 |
| dependencies | 未声明 | 不满足。没有 `metadata.openclaw.requires.bins/env/config`，`manifest.json` 也没有 `dependencies` 字段。 |
| tests | `test_command` 指向共享测试类 | 部分满足。没有 Skill 自包含测试；`source_ingestion` 的命令只测试注册表，未测试摄取行为。 |
| 独立发现 | `discover_skills()` 可发现三项 | 仅内部 PASS；OpenClaw 原生 NEED FIX。 |
| 独立加载 | 只加载 metadata，不加载执行能力 | NEED FIX。 |
| 独立升级 | 有版本字段，无安装/升级/兼容策略 | NEED FIX。 |
| 独立测试 | 有命令字符串，但测试粒度不独立 | NEED FIX。 |

当前 OpenClaw 官方规范要求 Skill 名称只使用小写字母、数字和连字符，并建议目录名与 frontmatter 名称一致。现有 `source_ingestion`、`unified_distillation`、`quality_review` 均使用下划线，因此内部测试通过不能证明它们能被 OpenClaw 正确发现和加载。参见 [OpenClaw Creating skills](https://docs.openclaw.ai/tools/creating-skills)。

另外，OpenClaw Skill 是给 Agent 的指令，不会自动注册 Python API 为工具。当前三个 `SKILL.md` 都没有给出可执行 CLI/工具调用，也没有 `command-dispatch` 或 `{baseDir}` 脚本入口，所以“读取了 Skill”不等于“能够执行框架”。

## 4. Creator Plugin 接口审查

**状态：PASS（私有 Schema 验证除外，见第 5 节）**

实际调用链为：

```text
RawSource[]
  -> CommonExtractor
  -> CreatorDistillationPlugin.enhance(raw_sources, common_signals)
  -> PluginContribution
  -> DistillationEngine 合并与共享 Schema 验证
  -> UnifiedDistillationArtifact
```

结论：

- 端到端输入是 `RawSource[]`，端到端输出是唯一的 `UnifiedDistillationArtifact`。
- 插件本身返回 `PluginContribution`，而不是独立构造完整 Artifact。这与任务描述的字面形式不同，但能避免插件复制核心字段和二次蒸馏，架构上更安全。
- 核心仅依赖 `CreatorDistillationPlugin` 协议，不依赖 `xiaolin_finance` 具体实现。
- 财经关键词、风险规则、结构模板和领域评分均位于插件包。
- 没有发现绝对路径或单账号密钥写死。
- `creator_target="xiaolin-style-finance-explainer"` 位于示例插件身份中，未污染通用核心；部署时仍应由选定插件/实例身份共同约束。

## 5. Unified Distillation Artifact 审查

**状态：NEED FIX**

共享 Schema 已覆盖：

- 四类通用蒸馏结果：`topic_candidate`、`content_template`、`knowledge_unit`、`style_pattern`；
- Creator/领域扩展：`domain_extension`；
- 风险约束：`risk_constraints`；
- 通用与领域质量评价：`evaluation_result.common/domain`；
- Artifact 与插件版本身份。

`domain_extension` 被设计为开放对象，因此科技、教育、医疗等新增领域原则上不需要修改共享 Schema；这是正确的扩展方向。

但插件私有 Schema `plugins/xiaolin_finance/schemas/domain_extension.schema.json` 从未被加载或验证。内存诊断使用一个缺少所有必填字段的 `{"unexpected": "accepted"}` 作为 `domain_extension`，仍成功生成并通过共享 Schema。该缺口会使插件版本漂移或错误结构延迟到生成、存储或下游消费阶段才暴露。

结论是：共享扩展机制可用，但当前缺少“按插件身份选择并执行私有 Schema”的闭环，因此不能判定为部署就绪。

## 6. Workflow 部署适配审查

**状态：NEED FIX**

### 6.1 当前 Python 流程

当前代码实际顺序为：

```text
素材输入
  -> 分类 + 通用蒸馏 + Creator 插件增强（一次引擎调用）
  -> Unified Distillation Artifact
  -> 内容生成适配器（如已配置）
  -> Quality Gate
```

这与部署目标要求的“质量门 -> 内容生成”相反。`pipeline.py:43` 调用生成适配器，`pipeline.py:50` 才调用 `evaluate_pipeline_output()`。内存诊断结果为：

```text
adapter_calls=['generated']
quality_status='review_required'
blocking_risk_count=1
```

因此 `block` 风险只能把最终报告标记为需要复核，不能阻止生成适配器实际执行。这是硬阻塞。

### 6.2 建议的龙虾 Workflow 结构

```text
Agent/Tool 节点：ingest
  输入：外部素材
  输出：RawSource[]
        |
Skill + CLI 节点：distill
  内部一次完成分类、通用提取和 Creator 插件增强
  输出：UnifiedDistillationArtifact
        |
Skill + 确定性节点：pre_generation_quality_gate
  验证共享 Schema、插件私有 Schema、风险和评分
        |
        +-- block/review_required --> 停止或 Lobster approval
        |
        +-- pass --> Agent/Tool 节点：generate
                         |
                  可选后置内容质量检查
                         |
                  输出/存储/发布审批
```

职责建议：

- Agent/工具节点：需要 I/O、模型、OCR、转写、外部存储或内容生成的步骤。
- Skill：输入规范化、统一蒸馏操作规程、质量审查规则。
- 确定性 CLI/库：Schema 验证、插件加载、风险阻断、格式转换。
- Lobster approval：生成后发布、账号写入或其他外部副作用。

当前 `workflow.json` 只有 `id`、`contract`、`contains` 和 `output`，没有 Lobster 需要的 `command`、`stdin`、`condition` 或 `approval`，因此不能直接作为 Lobster 工作流运行。当前 Lobster 规范参见 [OpenClaw Lobster workflow files](https://docs.openclaw.ai/tools/lobster)。

## 7. 配置隔离审查

**状态：NEED FIX**

代码层面的隔离基本正确：

```text
核心能力：core/ + distillation_core/
插件能力：plugins/<plugin>/
运行配置：实例/Gateway 环境（设计目标）
```

但运行配置仍停留在文档层。`.env.example` 和部署指南声明了 `CREATOR_PLUGIN`、`CREATOR_SCHEMA_PATH`、`CREATOR_LOG_LEVEL`，源码、脚本和测试中没有任何 `os.environ`/`getenv` 或等效配置加载逻辑。也没有 CLI/服务入口把这些配置传给 `load_plugin()` 和 `DistillationEngine()`。

因此：

- 通用核心没有写死 Creator 或财经规则：PASS；
- 财经规则只在财经插件内：PASS；
- 单账号配置未污染框架：PASS；
- 实例能够仅靠运行配置选择插件、Schema 和日志：NEED FIX；
- `CREATOR_PLUGIN` 的文档承诺与实际运行行为一致：NEED FIX。

## 8. 测试覆盖审查

**状态：NEED FIX**

### 8.1 已覆盖

| 能力 | 测试 | 结果 |
| --- | --- | --- |
| 普通素材输入 | `test_ordinary_material_produces_unified_artifact` | PASS |
| 财经增强 | `test_finance_plugin_applies_domain_enhancement` | PASS |
| 插件替换 | `test_replacing_plugin_does_not_change_common_core` | PASS |
| 风险识别与最终状态 | `test_finance_risk_blocks_automatic_progression` | 部分 PASS |
| Skill 内部发现 | `SkillRegistryTests` | PASS |

项目声明的测试命令结果：5 个测试全部通过，耗时约 0.007 秒。

### 8.2 未覆盖或覆盖不足

- 风险测试没有注入生成适配器，因此未断言阻断风险时“生成适配器不得被调用”。
- 未验证插件私有 `domain_extension` Schema。
- 未执行 OpenClaw `skills list/check` 或实际 Agent 调用，内部注册表测试不能替代原生加载验证。
- 未执行 Lobster 工作流解析、dry-run、审批/恢复或节点输入输出验证。
- 未测试 `CREATOR_*` 配置驱动的启动路径，因为该启动路径不存在。
- 未测试打包制品在目标实例的导入、启动、回滚和健康检查。
- 未验证 GitHub tag/commit 与制品哈希的发布绑定。

本机未安装 `openclaw` 和 `lobster` CLI，因此本轮无法执行原生运行时检查；这属于验证环境限制，但也说明当前证据不足以宣告可部署。

## 9. Deployment Risks

| ID | 等级 | 风险 | 证据与影响 | 是否阻塞 |
| --- | --- | --- | --- | --- |
| R-01 | 高 | 质量门位于生成之后 | 已复现 `block` 风险存在时生成适配器仍被调用；可能让不合规内容进入昂贵或有副作用的生成链路。 | 是 |
| R-02 | 高 | 没有可执行的 Lobster 工作流绑定 | `workflow.json` 是架构描述，不含可执行命令、条件、审批或输入传递；空白实例无法直接运行端到端流程。 | 是 |
| R-03 | 高 | Skill 不符合当前 OpenClaw 原生包约定 | 三个 Skill 名称和目录均使用下划线；依赖门控、执行命令和原生加载验证缺失。 | 是 |
| R-04 | 高 | 实例配置未接入运行时 | 文档声明 `CREATOR_*`，但代码不读取；实例不能通过配置选择插件/Schema 并启动流程。 | 是 |
| R-05 | 中 | 插件私有 Schema 未执行 | 错误的 `domain_extension` 仍通过共享验证，可能造成下游兼容性故障。 | 部署前应修复 |
| R-06 | 中 | 当前 OpenClaw 工作区兼容性未验证 | 当前 OpenClaw 使用 SQLite 保存 workspace attestation，并不读取旧式 workspace JSON；现有 `.openclaw/workspace-state.json` 不能作为兼容性证据。 | 需目标环境 preflight |
| R-07 | 中 | 目标提交未进入远端版本事实 | 本地 `main` 比 `origin/main` 领先 1；GitHub API 无法取得 `cfb38a8`。无法按 GitHub commit/tag 重建或审计部署。 | 发布前阻塞 |
| R-08 | 中 | 部署关键回归与集成门缺失 | 现有 5 个测试未覆盖 R-01、R-02、R-03、R-04、R-05，也未验证制品导入/回滚。 | 需补充后复审 |
| R-09 | 低 | 目录契约命名偏差 | 任务目标写 `distillation/`，实现为 `distillation_core/`；功能边界清晰，但外部脚本若按固定目录寻找会失败。 | 否 |

关于 R-06：当前 OpenClaw 文档说明工作区 setup/attestation 已存入共享 SQLite，旧式 workspace JSON 不再由运行时读取；参见 [OpenClaw Agent workspace](https://docs.openclaw.ai/agent-workspace) 和 [Agent runtime workspace](https://docs.openclaw.ai/concepts/agent)。

## 10. 阻塞问题

部署前至少必须关闭以下阻塞项：

1. 将风险/质量门移动到生成调用之前，并用测试证明 `block` 时生成适配器调用次数为 0。
2. 提供可由 Lobster 执行的工作流文件及其稳定 CLI/工具入口；完成解析或 dry-run。
3. 将 Skill 名称、目录、依赖门控和执行说明调整为当前 OpenClaw 原生规范，并在目标实例执行 `openclaw skills list/check` 和最小调用测试。
4. 提供读取实例配置并构建插件、Schema、Workflow 的唯一启动入口；消除“文档配置存在但运行时忽略”的假配置。
5. 在获准发布时把经审查提交推送到 GitHub，并用 tag/完整 SHA 与部署制品哈希绑定。此项本轮按禁止事项未执行。

R-05、R-06、R-08 也应在正式部署 Gate 前关闭；否则即使上述入口可运行，仍缺少足够证据支持安全升级与回滚。

## 11. 修复建议

以下仅为建议，本次审查未实施任何修复：

1. 把 `evaluate_pipeline_output()` 或一个专门的 pre-generation gate 放在 `GenerationAdapter.generate()` 之前；`review_required` 和 `block` 必须短路。
2. 新增稳定、JSON 输入输出的 CLI，例如 `creator-agent ingest/distill/gate/generate`，让 Lobster 调用确定性命令，而不是要求 Agent 即兴 import Python。
3. 用 `.lobster` 或符合 Lobster 规范的 YAML/JSON 表达真实步骤，显式设置 `stdin`、`condition`、`approval`、超时和输出上限。
4. 按 OpenClaw 规则把 Skill 改为连字符命名，并在 frontmatter 中声明依赖；每个 Skill 提供独立的测试入口。
5. 让插件声明私有 Schema 路径/版本，由引擎在共享 Schema 之后执行插件私有验证；失败必须显式终止。
6. 增加一个唯一 runtime bootstrap，读取并校验 `CREATOR_PLUGIN`、`CREATOR_SCHEMA_PATH`、日志级别及适配器配置；无效值启动失败。
7. 在目标 OpenClaw 版本执行 setup/doctor、Skill 检查、Lobster dry-run、阻断场景、制品导入和回滚演练。
8. 增加部署 Gate：单元测试、风险短路回归、私有 Schema 合规、Skill 原生加载、Lobster dry-run、包导入 smoke test、GitHub SHA/制品哈希核对。
9. 明确 `distillation_core/` 是正式公共目录名，或在发布契约中统一为 `distillation/`，避免自动化按错误路径查找。

## 12. 部署建议

当前不建议进入空白实例部署阶段，也不建议生成可用于生产导入的正式 release 制品。

建议下一阶段顺序：

1. 先关闭 R-01 至 R-05 的代码/契约问题；
2. 在与目标空白实例相同版本的 OpenClaw 上完成 Skill 与 Lobster preflight；
3. 执行最小真实部署演练，但保持生成/发布副作用禁用；
4. 验证阻断、审批、恢复、回滚和日志；
5. 将完整 commit SHA、tag、制品 SHA-256 和运行时版本写入发布记录；
6. 再进行一次 Deployment Review。

## 13. 最终结论

```text
Deployment Readiness: NOT READY
```

原因：

- 框架核心、插件隔离和统一 Artifact 的方向正确，已有测试也证明了基础能力、财经增强和插件替换。
- 但质量门无法阻止生成，属于直接安全语义错误。
- 当前 Skill 与 Workflow 不是可直接由当前 OpenClaw/Lobster 发现并执行的部署单元。
- 实例配置没有运行时消费者，插件选择和工作流启动无法由部署配置完成。
- 插件私有 Schema、目标运行时兼容性、远端版本可追溯性和部署集成测试仍不完整。

因此，`cfb38a8` 适合作为 Phase 2 基础架构开发基线，不适合作为空白龙虾实例的新架构正式部署基线。

## 14. 验证记录

已执行：

- `git status --short`：审查开始时为空；本地 `HEAD` 为 `cfb38a8`。
- `python --version`：Python 3.13.14，满足项目 `>=3.11` 要求。
- `python -m unittest discover -s tests -v`：5/5 PASS。
- 财经插件加载烟测：PASS。
- 全部 JSON 文件解析：PASS。
- `scripts/package_workspace.ps1` PowerShell AST 语法解析：PASS。
- `tar --version`：bsdtar 3.8.8 可用。
- `git diff cfb38a8^ cfb38a8 --check`：PASS。
- 风险短路内存诊断：FAIL，生成适配器在 `review_required`/`block` 场景仍被调用。
- 插件私有 Schema 内存诊断：FAIL，不符合私有 Schema 的对象仍被接受。
- Git 分支检查：本地 `main` 相对 `origin/main` ahead 1。
- GitHub 远端检查：`cfb38a8` 不存在于远端提交历史。

未执行：

- 正式打包：本次任务只允许审查和报告，避免生成额外部署制品。
- OpenClaw Skill 原生检查：本机无 `openclaw` CLI。
- Lobster 解析/dry-run：本机无 `lobster` CLI，且当前文件不含可执行步骤。
- 空白实例导入、启动、部署或发布：任务明确禁止。

## 15. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

本 Phase 暴露的问题不是缺少更多文字规则，而是验证器只检查最终 `review_required` 状态，没有检查被禁止的生成调用是否已经发生。后续应把“阻断时适配器调用次数为 0”、插件私有 Schema 合规、OpenClaw Skill 原生发现和 Lobster dry-run 固化为发布 Gate。
