# Release Notes: creator-agent-template-v0.1.0

## 1. 版本

```text
Release:      creator-agent-template-v0.1.0
Tag:          creator-agent-template-v0.1.0
Commit:       033da3c76ddae7740afb7c51d56b4e12ce78378e
Baseline:     cfb38a8cc97bb146f1445ebdd02850e47f5b2736
Repository:   https://github.com/ai-singer/hand-on-off
Branch:       main
Package:      creator-agent-template 0.1.0 (pyproject.toml)
Deployable:   blank/workspace/
Date:         2026-09-26
```

本版本是 Creator Agent Framework 的第一个可部署候选模板，用于空白龙虾实例
（OpenClaw workspace）拉取部署。发布源为 GitHub；实例配置、密钥与生产副作用
仍由目标实例自己管理。

## 2. 已完成能力

| # | 能力 | 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | 通用蒸馏框架 | `core/`, `distillation_core/` | 输入为 `RawSource[]`，一次引擎调用完成分类、通用理解与插件增强，输出唯一 `UnifiedDistillationArtifact`。核心不含任何领域规则。 |
| 2 | Creator 插件体系 | `plugin_interface/`, `plugins/` | `CreatorDistillationPlugin` 协议与具体插件分离；插件返回 `PluginContribution`，由引擎合并，避免二次蒸馏与核心字段复制。 |
| 3 | 财经示例插件 | `plugins/xiaolin_finance/` | 示例领域插件，携带关键词、风险规则、结构模板、私有 Schema 与评价 rubric。替换插件不需要修改通用核心。 |
| 4 | 统一蒸馏结果 Schema | `schemas/unified_distillation_artifact.json` | 覆盖 `topic_candidate`、`content_template`、`knowledge_unit`、`style_pattern`、`domain_extension`、`risk_constraints` 与 `evaluation_result`；`domain_extension` 为开放对象，新增领域不需要改共享 Schema。 |
| 5 | 质量门控制 | `evaluation/quality_gate_controller.py` | `QualityGateController` 是唯一允许调用注入式生成适配器的组件；FAIL 返回 `review_required` 且不调用生成适配器（`generation_adapter_invoked=false`）。质量门位于内容生成之前。 |
| 6 | Lobster 工作流适配 | `workflows/lobster/` | `content_distillation.lobster` 为可执行映射（source_input → unified_distillation → plugin checkpoint → quality_gate → generation handoff），`node_contracts.json` 记录五个节点的输入/输出/依赖/失败语义，`runtime_adapter.py` 提供 JSON 命令入口。 |
| 7 | OpenClaw Skill 适配 | `skills/openclaw/`, `skills/internal/catalog.json` | 内部 Skill 保持不变，由 `catalog.json` 映射；`skills/openclaw/` 提供符合连字符命名约定的可部署包装（`source-ingestion`、`unified-distillation`、`quality-review`），含 metadata、version、entrypoint、dependencies、runtime_requirements 与测试命令。 |
| 8 | Runtime 配置 | `config/runtime/` | `config/runtime/default.json` 选择 workflow、插件与 Skill；`load_runtime_config()` 做显式校验，非法配置启动即失败；`CREATOR_RUNTIME_CONFIG` 由 `workflows/lobster/runtime_adapter.py` 消费。 |

## 3. 当前状态

```text
Deployment Candidate

Runtime Validation Pending
```

本版本是**部署候选**，不是生产版本。

- 已完成：本地单元测试、编译检查、JSON 解析检查、Git 同步与版本标记。
- 未完成：在真实空白龙虾实例上的运行时验证（`openclaw skills list/check`、
  Lobster 解析/dry-run、制品导入/回滚、适配器连通性、密钥与可观测性）。
- 因此本版本可用于实例拉取与验证，但不得在运行时验证通过前用于生产生成或
  对外发布链路。

## 4. 本次发布验证证据

在本仓库 `blank/workspace/` 下执行：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | PASS，13/13，耗时 0.019s，Python 3.13.14 |
| 编译检查 | `python -m compileall .` | PASS，退出码 0 |
| JSON 解析 | 全部 `*.json`（17 个）逐个 `json.load` | PASS，0 失败 |
| Lobster 工作流配置 | `workflows/lobster/content_distillation.lobster` | PASS（JSON 可解析，5 个节点含 command/stdin/condition） |
| Runtime 配置 | `config/runtime/default.json` | PASS |
| Schema 文件 | `schemas/unified_distillation_artifact.json`、`plugins/xiaolin_finance/schemas/domain_extension.schema.json` | PASS |
| 工作区状态 | `git status` | clean |

测试分布：`tests/test_framework.py` 5 项，`tests/deployment/` 8 项
（quality gate、runtime config、skill adapters、workflow mapping）。

## 5. 已知限制与待验证项（本轮仅记录，未修改代码）

以下条目在本版本中保持原状，未做任何修复，供下一阶段 Runtime Validation 使用：

1. **插件私有 Schema 无运行时消费者**：`plugins/xiaolin_finance/schemas/domain_extension.schema.json`
   存在，但代码中没有加载或执行它的路径（`core/schema_validation.py` 与
   `distillation_core/engine.py` 只验证共享 Schema）。对应部署审查中的 R-05。
2. **`workflows/content_distillation_pipeline/workflow.json` 仍是描述性元数据**
   （仅 `contract`/`contains`），不是可执行工作流。可执行映射是
   `workflows/lobster/content_distillation.lobster`；两个文件同时存在。
3. **版本字符串不一致**：`pyproject.toml` 为 `0.1.0`，`config/runtime/default.json`
   的 profile `version` 为 `1.0.0`。二者语义不同但字面易混淆。
4. **`docs/DEPLOYMENT_REVIEW.md` 的 `NOT READY` 结论基于 `cfb38a8`**，早于本次
   加固提交 `033da3c`；该文档为历史审查记录，未随本版本重写，也不代表本版本的
   运行时验证结论。
5. **原生运行时未验证**：本机未安装 `openclaw` 与 `lobster` CLI，Skill 原生发现、
   Lobster dry-run、审批/恢复与回滚演练均未执行。对应 R-06、R-08。

## 6. 本任务的边界

本次发布只做发布检查、Git 同步、版本标记与发布文档。

- 未修改代码；
- 未修改架构；
- 未重构目录；
- 未修改测试；
- 未修改插件；
- 未修改 Skill；
- 未修改 Workflow。

## 7. 下一阶段

下一阶段由空白龙虾实例执行：拉取 `creator-agent-template-v0.1.0`、部署、
加载 Runtime 配置 / OpenClaw Skill / Creator 插件 / Lobster Workflow，
并执行 Runtime Validation。部署入口见
[`GITHUB_DEPLOYMENT_ENTRY.md`](GITHUB_DEPLOYMENT_ENTRY.md)。
