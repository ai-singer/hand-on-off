# Creator Agent Framework Phase 5.3.1 - Runtime Bootstrap Implementation

```text
Phase 5.3.1 Runtime Bootstrap Status: PASS WITH ISSUES
Runtime Config -> Bootstrap -> Runtime Context -> Component Loading -> Execution: CLOSED (in the new layer)
Production wiring (workflows/lobster/runtime_adapter.py): NOT WIRED (see Remaining Issues)
```

本轮在不修改 Distillation Engine 核心逻辑、Creator Plugin Interface、Unified Artifact
Schema、Lobster Workflow 结构、Security Gate 与部署流程的前提下，新增 Runtime Bootstrap
层，使 Runtime Config 从"配置存在但不驱动运行"升级为"配置驱动的 Runtime 初始化系统"。

> **前置说明**：任务书引用的审计报告
> `blank/workspace/docs/PHASE_5_3_RUNTIME_CONFIGURATION_AUDIT.md` **在仓库与远端均不存在**
> （当前 `docs/` 下无任何 `PHASE_5_3*` 文件）。本轮按任务书正文描述的 S-03 与 Bootstrap
> 缺失问题实施，未依赖该报告。

## Completed

1. **新增 Runtime Bootstrap 层**（`runtime/`）：单一初始化入口 `bootstrap()`，一次完成
   配置加载、版本校验、插件构造、Skill 发现与筛选、Workflow 绑定、Context 创建。
2. **新增 RuntimeContext**（`runtime/context.py`）：Bootstrap 之后唯一运行入口，字段与
   运行时配置一一对应。
3. **补齐 Skill Manifest**：为 3 个可部署 OpenClaw Skill 包补 `manifest.json`，使用现有
   `core.skill_registry.discover_skills()` 接口，未重新设计 Skill 协议。
4. **新增测试** `tests/runtime_bootstrap/` 12 项，覆盖任务要求的 Test 1–5 及 6 项交叉校验。
5. **注册包**：`pyproject.toml` 增加 `runtime`。
6. **未改动**：`distillation_core/`、`plugin_interface/`、`schemas/`、
   `workflows/lobster/`、`security/`、`scripts/`、`config/runtime/`。`core/` 仅被只读引用
   （`CreatorFrameworkError`、`load_plugin`、`discover_skills`）。

## Runtime Flow

```text
bootstrap(config_path=None, workspace_root=None)
  |
  +-- _resolve_workspace_root()   工作区根，默认 runtime/ 的上一级
  +-- _load_config()              load_runtime_config() -> RuntimeConfig
  +-- _validate_version()         语义版本 + 与 SUPPORTED_CONFIG_VERSION 主版本兼容
  +-- _load_plugins()             plugins.enabled -> load_plugin() 逐个构造
  |                                + 身份冲突检测 + plugins.default 必须已加载
  +-- _load_skills()              skills.enabled -> manifest 发现 + adapter 交叉校验
  +-- _load_workflow()            workflow.default -> 解析 + 结构校验 -> WorkflowBinding
  |
  +-- RuntimeContext(instance, version, plugins, skills, workflow, config)
```

失败语义：任一步失败均抛出 `RuntimeBootstrapError`（`CreatorFrameworkError` +
`RuntimeError`），原始异常通过 `__cause__` 保留。调用方只需捕获一种错误类型。

`RuntimeContext` 是不可变 dataclass（`frozen=True, slots=True`），`plugins` / `skills` /
`workflow.payload` 以 `MappingProxyType` 暴露，避免下游改写初始化结果。

## Config Binding

| Config 字段 | 绑定结果 | 校验 |
| --- | --- | --- |
| `instance.name` | `RuntimeContext.instance` | 非空字符串（loader） |
| `version` | `RuntimeContext.version` | 语义版本 `X.Y.Z` + **主版本必须等于运行时契约主版本**（`SUPPORTED_CONFIG_VERSION = 1.0.0`） |
| `plugins.enabled` | `RuntimeContext.plugins` 的键（按模块路径）| 每个模块必须可导入、`create_plugin()` 可用、满足 `CreatorDistillationPlugin`；**身份 name 不得重复** |
| `plugins.default` | `RuntimeContext.default_plugin` | 必须属于 `plugins.enabled`（loader + bootstrap 双重） |
| `skills.enabled` | `RuntimeContext.skills` 的键（按 Skill 名）| 每个名字必须能在 `skills/openclaw/` 发现 `manifest.json`；与同包 `adapter.json` 交叉校验 name / version / entrypoint |
| `workflow.default` | `RuntimeContext.workflow`（`WorkflowBinding`）| 文件必须存在、为合法 JSON 对象、含非空 `name`、含非空 `steps`，每个 step 有唯一 `id` 与非空 `command` |
| — | `RuntimeContext.config` | 原始不可变 `RuntimeConfig`，便于审计来源 |

实测（同一份 `default.json` 派生变体）：

```text
default.json (as shipped)          -> instance='creator-agent-template' skills=['quality-review','source-ingestion','unified-distillation']
skills trimmed to quality-review   -> instance='creator-agent-template' skills=['quality-review']
instance renamed                   -> instance='my-creator-instance'        skills=[...3...]
version 2.0.0                      -> REJECTED: RuntimeBootstrapError: runtime config version '2.0.0'
                                      is not compatible with runtime config contract '1.0.0'
```

对应任务书要求的四项绑定：`instance` → `RuntimeContext.instance`；`version` →
`RuntimeContext.version` 且经版本校验；`plugins` → 只加载 `plugins.enabled` 指定的插件；
`skills` → 只加载 `skills.enabled` 指定的 Skill；`workflow` → `RuntimeContext.workflow`。

## Skill Manifest

新增 3 个文件，字段与既有 `discover_skills()` 契约一致
（`name` / `version` / `entrypoint` / `capabilities` / `test_command`）：

| 文件 | name | capabilities |
| --- | --- | --- |
| `skills/openclaw/source-ingestion/manifest.json` | `source-ingestion` | normalize-video, normalize-document, normalize-data, normalize-image |
| `skills/openclaw/unified-distillation/manifest.json` | `unified-distillation` | classify-material, extract-common-signals, apply-creator-plugin, validate-artifact |
| `skills/openclaw/quality-review/manifest.json` | `quality-review` | evaluate-coverage, apply-domain-rubric, enforce-risk-gate |

设计说明：

- 配置中的 `skills.enabled` 使用连字符名（`source-ingestion`），与 `skills/openclaw/` 下
  的可部署包同名，因此 bootstrap 以 `skills/openclaw/` 作为 Skill 包根。
- 内部 Skill（`skills/source_ingestion/` 等下划线命名）**未改动**，其既有 manifest 与
  `SkillRegistryTests` 保持原状；新增文件位于 `skills/openclaw/<name>/`，不进入
  `skills/*/manifest.json` 通配，因此不影响既有发现结果（已实测 34 项测试全绿）。
- 当同包存在 `adapter.json` 时执行交叉校验；缺失则不强制（Skill 可以只有 manifest）。

## Tests

新增 `tests/runtime_bootstrap/`（12 项），任务要求的 Test 1–5 全部覆盖：

| 任务要求 | 测试方法 | 验证点 |
| --- | --- | --- |
| Test 1 Runtime Config Loading | `test_runtime_config_enters_runtime_context` | instance / version / workflow 名称与 5 个 step 顺序进入 Context |
| Test 2 Plugin Selection | `test_plugin_selection_follows_config` | 只加载配置指定的插件；未配置的插件不出现；default 生效 |
| Test 3 Skill Selection | `test_skill_selection_follows_config` | 配置 1 个 / 2 个 / 全部时的选择结果互斥正确 |
| Test 4 Missing Skill Manifest | `test_configured_skill_without_manifest_fails_bootstrap`、`test_removed_manifest_file_fails_bootstrap` | 配置未知名失败；真实 Skill 包删除 `manifest.json` 后失败 |
| Test 5 Version Validation | `test_incompatible_version_fails_bootstrap` | `2.0.0` 失败、非法版本失败、同主版本 `1.4.7` 通过 |

补充交叉校验测试：插件身份冲突、插件模块不存在、Workflow 定义缺失、manifest 与 adapter
漂移、以及端到端 `Config -> bootstrap -> Context -> 组件加载 -> 执行`（用
`context.default_plugin` 实际跑通 `ContentDistillationPipeline` 并校验 artifact 中的
插件身份与质量门结果）。

另含 1 项**回归护栏** `test_test_packages_do_not_shadow_workspace_packages`。

### 验证结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **34** tests, OK（原 22 + 新 12） |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json`（含 runtime config、manifest、schema） | **PASS**，**20/20**（原 17 + 新 3） |
| Secret scan — 工作区 | `python security/secret_scan.py .` | **PASS** |
| Secret scan — 仓库根 | `python security/secret_scan.py ..\..` | **PASS** |
| Secret scan — 被跟踪文件 | `git archive HEAD` → 扫描 | **PASS** |

### 测试包命名（重要）

测试目录命名为 `tests/runtime_bootstrap/` 而非任务书建议的 `tests/runtime/`：
`python -m unittest discover -s tests` 会把 `tests/` 置于 `sys.path[0]`，因此
`tests/runtime/` 会**遮蔽工作区根的同名 `runtime/` 包**，使目录内
`from runtime import ...` 解析到测试包自身而导入失败（Phase 5.2.2 曾发生同类问题并
导致安全测试整体无法加载）。命名已避开该冲突，并新增上述护栏测试防止复发。

## Remaining Issues

| ID | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| R-01 | **生产路径尚未接入 bootstrap**：`workflows/lobster/runtime_adapter.py` 仍直接调用 `load_runtime_config()` + `load_plugin()`，未经过 `bootstrap()` | 新的 Context 层在真实工作流中尚未生效；"配置驱动"目前由 `runtime_adapter` 的既有逻辑部分承担 | 在获准修改 Lobster 适配器后，将其改为 `bootstrap()` + `context.default_plugin`，使闭环在生产路径成立 |
| R-02 | 任务书引用的 `PHASE_5_3_RUNTIME_CONFIGURATION_AUDIT.md` 不存在 | 无法与审计条目逐条对账 | 补齐该报告或确认以任务书正文为准 |
| R-03 | 版本命名空间仍不统一：`pyproject.toml` = `0.1.0`、runtime config = `1.0.0`、tag = `v0.1.0`、`SUPPORTED_CONFIG_VERSION` = `1.0.0` | 语义不同但字面易混（原审计 S-06） | 统一命名空间或明确区分"配置契约版本"与"包版本" |
| R-04 | Skill 仍存在两套并行注册：内部下划线 Skill（`discover_skills`）与可部署连字符 Skill（`discover_openclaw_skills` + 新 manifest） | 概念重叠，使用者需知道用哪一套 | 明确内外部 Skill 的职责边界并写入文档 |
| R-05 | 新 manifest 的 `test_command` 指向 `tests.deployment.test_skill_adapters`，而部署打包脚本排除 `tests/` | 继承既有矛盾（原审计 S-03）：制品内无法执行声明的测试命令 | 明确测试命令的适用环境，或调整打包排除策略 |
| R-06 | 无 bootstrap 命令行入口（如 `python -m runtime`） | 运维无法直接检视初始化结果 | 需要时再补；本轮未新增 |
| R-07 | `bootstrap()` 每次调用重新构造插件与重新读取文件，无缓存 | 重复初始化有开销 | 单例/缓存属调用方职责，暂不引入 |

### 未完成项说明

任务的成功标准把闭环定义为
`Runtime Config -> Bootstrap -> Runtime Context -> Component Loading -> Execution`。
本轮该链路**在新层内已实测闭环**（见上表端到端测试）。但**生产工作流路径未接入**，
原因是任务书禁止修改 Lobster Workflow 结构，而 `runtime_adapter.py` 位于
`workflows/lobster/` 内；在不明确授权的情况下未改动该文件。这是本轮判定为
`PASS WITH ISSUES` 而非 `PASS` 的唯一实质原因。

## Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

两条应下沉为验证规则的教训：

1. **测试包命名冲突是可验证的**：`tests/<pkg>/` 与工作区顶层包同名会在
   `unittest discover -s tests` 下静默破坏导入。已固化为护栏测试，建议纳入发布 Gate 1。
2. **"新增层"不等于"接入运行链"**：新层自带单元测试全部通过，仍可能在生产路径上
   完全未被调用。验收时应区分"层内闭环"与"生产闭环"，并显式记录未接入点。
