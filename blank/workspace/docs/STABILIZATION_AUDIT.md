# Creator Agent Framework Phase 5 - Template Stabilization Audit

## 1. 审查摘要

| 项目 | 结论 |
| --- | --- |
| 审查对象 | `creator-agent-template-v0.1.0` |
| 仓库提交 | `c3174cd53a7b9ac7bfa8ddab07212eb76e258245` |
| 审查范围 | `blank/workspace/` 及与发布、打包直接相关的仓库根部制品 |
| 审查方式 | 静态引用链检查、配置/Schema/Workflow/Skill 定义检查、现有测试、内存诊断、Git/制品只读检查 |
| 代码或配置修改 | 无 |
| 新增内容 | 本审查报告 |
| 发现问题 | 10 项：高风险 4 / 中风险 5 / 低风险 1 |

```text
Deployment Stabilization Status: NOT READY
```

当前候选已经具备可运行的框架骨架，通用蒸馏、财经插件、质量门和 Lobster 映射的基础链路均有测试证据；但它尚不具备直接升级为模板 v1.0 的条件。阻塞原因是插件私有 Schema 没有进入运行时验证链、Runtime Config 的多个声明字段没有实际消费者、部署包排除了 Skill 元数据声明的测试，以及发布标签中跟踪的旧归档含有 `.env` 路径并携带完整嵌套 Git 仓库。前三项影响数据正确性和部署可靠性，最后一项需要立即做凭据暴露核查。

## 2. 当前架构状态

当前实现采用单次蒸馏架构：

```text
RawSource[]
  -> CommonExtractor
  -> CreatorDistillationPlugin.enhance(...)
  -> UnifiedDistillationArtifact
  -> QualityGateController
       | PASS -> GenerationRequest / injected GenerationAdapter
       | FAIL -> STOP / review_required
```

| 模块 | 位置 | 状态 | 审查结论 |
| --- | --- | --- | --- |
| 通用模型与加载 | `core/` | PASS | 输入模型、动态插件加载、共享 Schema 验证边界清晰。 |
| 单次蒸馏 | `distillation_core/` | PASS | 通用提取和插件增强在一次 `DistillationEngine` 调用中合并。 |
| 插件接口 | `plugin_interface/` | PASS | `PluginIdentity`、`PluginContribution`、runtime-checkable Protocol 和插件规范均存在。 |
| 财经插件 | `plugins/xiaolin_finance/` | PASS WITH GAP | 规则、rubric、私有 Schema 与代码隔离正确；私有 Schema 未被执行。 |
| 统一 Artifact | `schemas/` | PASS | 核心 Schema 保持领域无关，`domain_extension` 为开放对象。 |
| 质量门 | `evaluation/` | PASS WITH GAP | 风险阻断确实发生在生成前；评价器仍是最小确定性参考实现。 |
| Runtime Config | `config/runtime/` | NEED FIX | 五类字段均可解析，但只有插件选择进入实际 Python 运行链。 |
| Workflow | `workflows/` | PASS WITH DOC FIX | `.lobster` 是执行层，`workflow.json` 是描述层；缺少明确的双文件治理和漂移检查。 |
| OpenClaw Skill | `skills/openclaw/` | NEED FIX | 可发现、加载和读取版本/依赖声明；依赖未解析或强制执行。 |
| 测试 | `tests/` | NEED FIX | 13 项通过，但未覆盖若干 v1.0 稳定化 Gate。 |
| 打包 | `scripts/package_workspace.ps1` | NEED FIX | 基本安全检查存在，但排除 tests 后使已声明的 Skill 测试命令失效。 |

## 3. 已验证能力

本轮从 `blank/workspace/` 执行：

```text
python -m unittest discover -s tests -v
Ran 13 tests in 0.025s
OK
```

现有证据支持以下能力：

1. 普通文档素材可生成统一 Artifact，且保留来源引用。
2. `plugins.xiaolin_finance` 可被动态加载并产生财经领域增强。
3. 测试用教育插件可替换财经插件，不需要修改通用核心。
4. 高风险财经输入产生 `block`，质量门返回 `FAIL`，生成适配器调用次数为 0。
5. 默认 Runtime Config 可解析，未来插件模块路径可通过配置替换。
6. 三个 OpenClaw Skill Adapter 可由内部注册表发现和加载。
7. Lobster 五节点映射顺序、节点契约和安全路径的 Python 适配器测试通过。
8. Git `HEAD`、`origin/main` 与发布标签当前都对应 `c3174cd`；工作区在新增本报告前为 clean。

用户提供的上阶段事实为 Runtime Validation PASS。本轮本机没有 `openclaw` 和 `lobster` CLI，因此没有重复执行原生 Skill discovery 或 Lobster dry-run；本报告将其视为既有外部证据，而不是本轮重新确认的结果。

## 4. 分项审查

### 4.1 Runtime Stub 审查

#### `plugin_interface.base`

**状态：PASS**

- 真实实现位于 `plugin_interface/base.py`。
- 定义了 `PluginIdentity`、`PluginContribution` 和 `CreatorDistillationPlugin` Protocol。
- `core/plugin_loader.py` 和 `distillation_core/engine.py` 直接导入并使用该模块。
- `pyproject.toml` 将 `plugin_interface` 列为 package；workspace tar 打包边界也会包含该源码。
- 未发现当前仓库运行链依赖外部同名 Stub 的证据。

结论：Runtime Validation 时创建过的外部 Stub 不应继续作为运行前提；仓库内接口实现已经能够作为唯一来源。

#### `evaluation.evaluator`

**状态：NEED FIX**

- 真实实现位于 `evaluation/evaluator.py`，不是空文件或 import shim。
- `DistillationEngine` 使用 `evaluate_distillation_artifact()`；Python Pipeline 和 Lobster Runtime Adapter 使用 `evaluate_pipeline_output()`。
- `QualityGateController` 根据该报告执行 PASS/FAIL，并已经有“FAIL 时不调用生成器”的回归测试。
- 未发现运行链依赖外部同名 Stub 的证据。

但当前实现明确是最小确定性参考评价器：公共评分仅使用信号族数量和来源覆盖率，领域评分由插件自行提供，缺少单独的 evaluator contract/version 和生产策略绑定。它可支撑当前模板 smoke flow，但不应在 v1.0 中被表述为已完成的生产评价系统。

修复建议：为公共 evaluator 定义稳定、可版本化的输入/输出契约和最低生产检查集；保留依赖注入边界；禁止通过部署时同名 Stub 覆盖仓库实现。

### 4.2 Creator Plugin Schema 链路审查

**状态：NEED FIX**

目标文件：`plugins/xiaolin_finance/schemas/domain_extension.schema.json`。

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 被生成 | 是 | 财经插件在 `plugin.py` 中生成 `domain_extension`。 |
| 被加载 | 否 | Python/JSON 引用搜索没有发现运行时加载该私有 Schema 的代码。 |
| 被验证 | 否 | `DistillationEngine` 只调用共享 `validate_unified_artifact()`。 |
| 被消费 | 部分 | Artifact 和 GenerationRequest 会携带它，但 Quality Gate 不检查其业务结构；模板内没有生产生成器消费字段。 |

本轮内存诊断将一个有效财经 Artifact 的扩展替换为：

```json
{"unexpected": "accepted"}
```

共享 Schema 验证仍然通过，输出为：

```text
SHARED_SCHEMA_ACCEPTED_INVALID_PRIVATE_EXTENSION
```

这证明当前链路允许不符合财经插件私有契约的数据进入 Quality Gate 和生成 handoff。

### 4.3 Unified Schema 扩展能力审查

**状态：PASS**

- `schemas/unified_distillation_artifact.json` 的核心字段不包含财经专属结构。
- `domain_extension` 只要求为对象，因此科技、教育、医疗插件可携带各自扩展，不需要修改核心 Schema。
- `test_replacing_plugin_does_not_change_common_core` 已用教育插件证明核心字段可保持不变。

边界条件：PASS 仅表示核心 Schema 的扩展设计正确，不代表插件私有结构已经安全；后者仍由 4.2 的 NEED FIX 阻塞。

### 4.4 Runtime Version Governance 审查

**状态：NEED FIX**

#### 版本矩阵

| 位置 | 版本 | 状态 |
| --- | --- | --- |
| package：`pyproject.toml` | `0.1.0` | PASS，与候选模板版本一致。 |
| Git tag | `creator-agent-template-v0.1.0` -> `c3174cd` | PASS。 |
| runtime profile：`config/runtime/default.json` | `1.0.0` | NEED FIX，字段名未说明它是 profile contract 版本还是模板运行时版本。 |
| Artifact：`DistillationEngine` | `1.0.0` | PASS WITH DOC，属于 Artifact contract 版本，应明确命名空间。 |
| Creator Plugin | `1.0.0` | PASS，插件独立版本。 |
| Skill / OpenClaw Adapter | `1.0.0` | PASS WITH GAP，版本存在但依赖兼容性未验证。 |
| Workflow description | `1.0.0` | PASS WITH DOC，独立 Workflow contract 版本。 |
| release docs | `creator-agent-template-v0.1.0` | NEED FIX，`RELEASE_NOTES_v0.1.0.md` 内嵌 Commit 仍写 `033da3c`，实际 tag 指向 `c3174cd`；文档还写着 Runtime Validation Pending。 |

结论：`0.1.0` 与多个 `1.0.0` 并非必然冲突，但当前没有统一说明版本命名空间、兼容规则和谁负责升级。版本字面一致性不足，发布记录还存在已确认的提交和状态漂移。

### 4.5 Workflow 定义审查

**状态：NEED FIX（文档/治理）**

当前职责实际上已经分离：

- `workflows/content_distillation_pipeline/workflow.json`：描述逻辑步骤、契约和输出。
- `workflows/lobster/content_distillation.lobster`：提供实际 command、stdin 和 condition。
- `workflows/lobster/node_contracts.json`：补充节点目的、依赖和失败语义。

`.lobster` 的执行职责在 `workflows/lobster/README.md` 与部署文档中已经说明；但 `workflow.json` 没有显式标记 `kind=description`，其 README 也没有说明该文件不能直接执行。现有测试只检查 `.lobster` 与 `node_contracts.json`，不检查 `workflow.json` 是否与执行层同步。

需要文档补充：明确 `workflow.json` 是描述层、`.lobster` 是唯一执行层，并定义两者的字段映射和版本/漂移检查。

### 4.6 Runtime Configuration 审查

**状态：NEED FIX**

| 能力 | 声明/解析 | 实际消费 |
| --- | --- | --- |
| instance | 是 | 否，仅测试读取。 |
| plugin | 是 | 是，`distill_payload()` 和 plugin checkpoint 使用。 |
| skill | 是 | 否，Runtime Adapter 不按 `skills.enabled` 发现、加载或拒绝 Skill。 |
| workflow | 是 | 否，没有 launcher 使用 `workflow.default` 选择执行文件。 |
| version | 是 | 否，仅做 semver 格式校验。 |

引用搜索显示，`runtime.instance`、`runtime.workflow`、`runtime.skills` 和 `runtime.version` 只在测试中被读取。当前 Runtime Config 是“完整声明、部分生效”。

新增领域插件可通过安装模块并更换实例自有 profile 实现，无需修改核心 loader 或 engine；这一扩展方向 PASS。但在 v1.0 前必须确保启动入口真正消费并交叉验证 workflow、skill 和 version，而不是只解析后忽略。

### 4.7 OpenClaw Skill Adapter 审查

**状态：NEED FIX**

| 要求 | 结果 |
| --- | --- |
| discovery | PASS，扫描 `*/adapter.json`。 |
| loading | PASS，按名称加载元数据并可读取 `SKILL.md`。 |
| versioning | 部分 PASS，检查 semver，但不与内部 Skill 版本或依赖范围核对。 |
| dependency declaration | 部分 PASS，JSON 中有依赖，但注册表只转成字符串 tuple，不解析、排序、检测缺失/循环/版本冲突。 |

另外，Runtime Config 的 `skills.enabled` 没有与 Adapter Registry 连接；配置声明一个不存在的 Skill 仍可通过 Runtime Config loader，只要名称格式合法。

### 4.8 测试覆盖审查

**状态：NEED FIX**

#### 已覆盖

| 流程 | 测试证据 | 评价 |
| --- | --- | --- |
| 普通素材输入 | `test_ordinary_material_produces_unified_artifact` | PASS |
| 财经增强 | `test_finance_plugin_applies_domain_enhancement` | PASS |
| 插件替换 | `test_replacing_plugin_does_not_change_common_core` | PASS |
| 风险阻断 | `test_fail_stops_before_generation` | PASS，明确断言适配器调用为 0。 |
| Runtime Config 解析 | `test_runtime_config.py` | PASS，但只验证解析。 |
| Skill Adapter | `test_skill_adapters.py` | PASS，但只验证元数据层。 |
| Workflow | `test_workflow_mapping.py` | PASS，覆盖 Python 安全路径和静态映射。 |

#### 未覆盖

- 错误 `domain_extension` 必须被私有 Schema 拒绝。
- Runtime Config 的 workflow/skills/version/instance 必须被真实启动链消费。
- Skill 依赖缺失、循环和版本冲突。
- `workflow.json` 与 `.lobster` 的描述/执行漂移。
- 实际发布 tar 的必需文件、敏感文件和 smoke-test 可用性。
- package/runtime/docs/tag 的版本一致性 Gate。
- wheel/sdist 中插件 JSON、共享 Schema、Workflow 和 Skill 数据文件的完整性。
- 原生 OpenClaw discovery 与 Lobster parse/dry-run 的可重复自动化证据。

## 5. 发现问题与风险等级

| ID | 风险 | 问题 | 影响 | 修复建议 |
| --- | --- | --- | --- | --- |
| S-01 | 高 | 财经私有 `domain_extension` Schema 未加载、未验证 | 畸形领域数据可通过共享 Schema，影响数据正确性和下游兼容性 | 让插件声明私有 Schema 路径/版本；在共享验证后执行私有验证；增加拒绝型回归测试。 |
| S-02 | 高 | Runtime Config 只有 plugin 进入运行链，instance/workflow/skills/version 被解析后忽略 | 配置可能产生“已选择/已启用”的假象，影响部署可靠性 | 建立唯一 runtime bootstrap/launcher，并对所有字段完成消费和交叉验证。 |
| S-03 | 高 | 打包脚本排除 `workspace/tests`，但三个 Skill Adapter 的 `test` 都指向被排除的测试 | 部署制品内的声明测试命令必然不可执行，破坏部署 preflight | 在制品中保留最小 smoke tests，或将 Adapter test 改为制品内自包含校验命令。 |
| S-04 | 高 | Git 跟踪的 `new/workspace.tar.gz`（约 20 MB）包含 `.env` 路径、完整嵌套 `.git` 和业务素材 | 可能暴露凭据/历史并造成公开 release 污染；实际内容未读取，敏感性尚待确认 | 立即做受控 secret scan；若包含真实凭据则轮换并清理 Git 历史/release；后续禁止跟踪不透明运行快照。 |
| S-05 | 中 | `evaluation.evaluator` 是真实但最小的参考评价器，缺少独立生产 contract/version | 生产质量语义和升级边界不清，长期可维护性不足 | 定义公共评价契约、版本、最小检查集和替换策略；禁止外部同名 Stub。 |
| S-06 | 中 | 版本命名空间与发布文档漂移 | package `0.1.0`、runtime/artifact/plugin/skill/workflow `1.0.0` 容易混淆；Release Notes commit 和 Runtime Validation 状态已过期 | 建立版本矩阵、兼容规则和自动校验；发布记录使用 tag 解析出的完整 SHA。 |
| S-07 | 中 | Skill 依赖仅声明，不解析或强制执行 | 缺失/不兼容 Skill 可能直到运行时才失败 | 增加依赖解析、存在性、循环和版本兼容验证，并与 `skills.enabled` 联动。 |
| S-08 | 中 | `pyproject.toml` 声明 Python package，但没有 package-data 配置 | wheel/sdist 可能遗漏插件规则、rubric、Schema、Workflow 和 Skill 文件；workspace tar 路径暂不受影响 | 明确唯一支持的分发方式；若支持 Python 包，加入 package-data 并验证 wheel 内容。 |
| S-09 | 中 | 现有 13 项测试没有覆盖稳定化关键 Gate | 问题可在单测全绿时进入发布制品 | 增加私有 Schema、配置消费、依赖解析、制品、版本和原生运行时 Gate。 |
| S-10 | 低 | `workflow.json` 描述层身份与双文件同步规则不够明确 | 文档维护者可能误把它当可执行定义，或让两层长期漂移 | 在 Workflow README 明确职责，增加描述层到执行层的映射说明和漂移检查。 |

## 6. 部署长期维护风险

1. **配置真值分裂**：Runtime Config、Lobster 文件、Skill Adapter 和插件自身都有版本与选择字段，但没有单一 bootstrap 负责组合和验证。
2. **Schema 真值分裂**：共享 Schema 被执行，插件私有 Schema 只作为文件存在。
3. **制品不可自证**：发布脚本排除 tests，而 Adapter 仍宣称可执行这些测试。
4. **分发路径分裂**：文档定义 workspace tar 为部署单元，`pyproject.toml` 又呈现为可打包 Python 项目，但二者包含文件的规则不同。
5. **发布记录漂移**：tag、文档内 SHA、Runtime Validation 状态没有自动绑定。
6. **不透明历史快照**：大型 tar 被直接提交，内容不能由常规 Git diff 审查，并且当前已观察到 `.env` 和嵌套 `.git` 路径。

## 7. 修复建议与后续执行顺序

本轮只给出建议，没有实施修复。

### 第一优先级：安全与数据正确性

1. 对 `new/workspace.tar.gz` 做受控 secret scan；若发现真实凭据，先轮换，再处理 Git 历史和已发布制品。
2. 将插件私有 Schema 纳入引擎或插件 checkpoint 的强制验证，并增加失败回归。

### 第二优先级：部署链闭环

3. 建立唯一 Runtime Bootstrap，使 instance/workflow/plugin/skill/version 全部生效并相互校验。
4. 使部署制品内的 Skill test 命令可执行；增加 tar 内容与敏感路径 Gate。
5. 将 Skill 依赖声明升级为真实依赖解析和版本兼容检查。

### 第三优先级：版本和分发治理

6. 区分 template、runtime profile、artifact contract、plugin、skill、workflow 六类版本；定义兼容矩阵。
7. 修正发布文档中的 commit 与 Runtime Validation 状态，并让 CI 从 Git/tag 自动生成或核对。
8. 明确 workspace tar 是唯一部署制品，或补齐 wheel/sdist 的 package-data 和制品测试。

### 第四优先级：v1.0 Gate

9. 补齐私有 Schema、Runtime Config 消费、Skill 依赖、Workflow 漂移、制品完整性和版本一致性测试。
10. 在目标 OpenClaw/Lobster 环境重新执行 native discovery、parse/dry-run、风险阻断、导入和回滚演练，并保存可追溯结果。
11. 关闭所有高风险项后再进行一次只读 Stabilization Re-audit；中风险项必须有明确关闭证据或经批准的 v1.0 风险接受记录。

## 8. 最终结论

```text
Deployment Stabilization Status: NOT READY
```

原因：

- 当前核心流程和风险短路已通过测试，基础架构不是阻塞点。
- 插件私有 Schema 未进入运行链，仍存在明确的数据正确性缺口。
- Runtime Config 和 Skill dependency 目前是“可声明但未完整生效”的治理层，存在部署假配置风险。
- 部署包排除其自身声明的测试，无法作为自证稳定的 v1.0 制品。
- 发布标签包含一个带 `.env` 路径和嵌套 Git 仓库的不透明旧快照，必须先完成敏感性核查。
- 版本与 Runtime Validation 文档记录没有和实际 tag/状态保持一致。

因此，`creator-agent-template-v0.1.0` 可继续作为已通过基础 Runtime Validation 的候选模板，但在关闭 S-01 至 S-04 前，不具备升级为 `creator-agent-template-v1.0` 的条件。

## 9. Verification Record

已执行：

- `git rev-parse HEAD`：`c3174cd53a7b9ac7bfa8ddab07212eb76e258245`。
- `git rev-list -n 1 creator-agent-template-v0.1.0`：`c3174cd53a7b9ac7bfa8ddab07212eb76e258245`。
- `python -m unittest discover -s tests -v`：13/13 PASS。
- 关键 import、版本、私有 Schema、Runtime Config 消费者和 Skill 元数据引用搜索。
- 私有 Schema 缺口内存诊断：共享 Schema 接受不符合财经私有 Schema 的扩展。
- 仓库 tar 只读目录检查与 Git tracking/size 检查；未读取 `.env` 内容。
- `openclaw` / `lobster` 可用性检查：本机未安装。

未执行：

- 未修改代码、架构、插件、Skill、Workflow 或配置。
- 未创建新的部署制品。
- 未读取或展示任何 `.env` 内容。
- 未重复目标实例上的 OpenClaw/Lobster Runtime Validation。
- 未执行网络、生产账号、发布、部署或凭据操作。

## 10. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

本 Phase 的主要缺口不是需要增加更多文字规则，而是发布验证器没有强制检查插件私有 Schema、Runtime Config 字段消费、Skill 依赖解析、制品内测试可执行性、版本一致性和不透明归档中的敏感路径。下一阶段应把这些检查固化为 v1.0 release gate。
