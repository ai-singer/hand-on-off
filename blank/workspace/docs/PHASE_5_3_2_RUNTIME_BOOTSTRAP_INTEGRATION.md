# Creator Agent Framework Phase 5.3.2 - Runtime Bootstrap Production Integration

```text
Phase 5.3.2 Runtime Bootstrap Integration Status: PASS

Runtime Config -> bootstrap() -> RuntimeContext -> Lobster Runtime Adapter
                -> Workflow Execution -> Artifact        CLOSED (production path)
```

本轮让生产执行链真正由 Runtime Bootstrap 统一控制：`workflows/lobster/runtime_adapter.py`
不再解析配置、不再自行加载插件，全部组件从 `RuntimeContext` 读取，双初始化路径消除。

Lobster Workflow Schema、`.lobster` 文件结构、Command 定义、Input/Output 格式、Node
顺序与 Quality Gate 逻辑**均未改动**。

## 1. Before

存在两套并行初始化路径，配置与组件在两处各解析一次：

```text
经 Bootstrap（Phase 5.3.1 新增，但仅被测试覆盖）
  runtime config -> bootstrap() -> RuntimeContext -> (仅测试使用)

经 Adapter（生产实际路径，绕过 Bootstrap）
  runtime config -> load_runtime_config() -> RuntimeConfig
                 -> load_plugin(runtime.plugins.default) -> plugin
                 -> DistillationEngine(plugin)
```

后果：

- `plugins.enabled` / `skills.enabled` / `version` 的交叉校验只在 Bootstrap 中存在，
  生产路径上不生效；
- Skill 与 Workflow 绑定在生产路径上完全没有被解析；
- 两份初始化逻辑需要同步维护，任一处漂移都不会被测试发现。

实测（本轮修改前）：

```text
workflows/lobster/runtime_adapter.py
  from config.runtime import load_runtime_config     <-- 直接读配置
  from core import RawSource, load_plugin            <-- 直接加载插件
```

## 2. After

只有一条初始化路径：

```text
runtime config -> bootstrap() -> RuntimeContext -> Lobster Runtime Adapter
```

`runtime_adapter.py`：

- 移除 `load_runtime_config` 与 `load_plugin` 的导入，改为
  `from runtime import RuntimeBootstrapError, RuntimeContext, bootstrap`；
- 新增 `resolve_context(config_path, context)`：**传入 context 则原样使用；否则调用
  `bootstrap()`**。这是适配器获取组件的唯一入口；
- `distill_payload()` 与 `verify_plugin_checkpoint()` 接受可选 `context` 关键字参数，
  使用 `context.default_plugin` 而不是自行 `load_plugin(...)`；
- `main()` 在命令分发前调用一次 `bootstrap(config_path)`，并把同一个 context 传给需要
  组件的节点。

机械验证（全仓库 grep `load_runtime_config|load_plugin`）：

| 位置 | 结果 |
| --- | --- |
| `runtime/bootstrap.py` | 生产路径中**唯一**的消费者 |
| `workflows/lobster/runtime_adapter.py` | **0 命中**（双路径已消除） |
| `core/`、`config/` | 定义与导出，未变 |
| `tests/` | 测试直接使用底层 API，属正常单元级用法 |

## 3. Runtime Flow

```text
Runtime Config (config/runtime/default.json 或 LOBSTER_ARG_RUNTIME_CONFIG)
      |
      v
bootstrap(config_path)                      ~ 唯一初始化入口
      |-- load_runtime_config -> RuntimeConfig
      |-- validate version (主版本契约)
      |-- plugins.enabled -> 插件构造 + 身份冲突检测
      |-- skills.enabled  -> manifest 发现 + adapter 交叉校验
      |-- workflow.default -> 解析 + 结构校验
      v
RuntimeContext(instance, version, plugins, skills, workflow, config)
      |
      v
Lobster Runtime Adapter (workflows/lobster/runtime_adapter.py)
      |-- resolve_context()  使用注入的 context 或 bootstrap 一次
      |-- _verify_workflow_binding()  绑定的 workflow 必须声明该命令实现的节点
      |-- 组件全部取自 context
      v
Workflow Execution (5 个节点，命令与 I/O 格式未变)
      source_input -> unified_distillation -> creator_plugin_enhancement
                   -> quality_gate -> content_generation
      v
Artifact
```

### 新增：Workflow 绑定一致性检查

`main()` 在分发前校验“运行时配置绑定的 workflow 是否声明了该命令实现的节点”：

| 适配器命令 | 要求 workflow 声明的节点 |
| --- | --- |
| `source-input` | `source_input` |
| `distill` | `unified_distillation` |
| `plugin-check` | `creator_plugin_enhancement` |
| `gate` | `quality_gate` |
| `generation-handoff` | `content_generation` |

不匹配时 fail-closed（错误信息含 `instance` 与 workflow 名称），避免在运行时选定的
workflow 之外执行节点。这是 `context.workflow` 与 `context.instance` 在适配器中的实际
用途。

### 行为变更（有意）

`main()` 现在**对全部 5 个命令**先 bootstrap，再执行。修改前 `source-input`、`gate`、
`generation-handoff` 不读取配置。

- 收益：配置损坏时工作流在**第一个节点**即失败，不再“带着默认值半跑”；
  与"统一初始化入口"一致。
- 代价：这三个命令现在要求运行时配置可用（配置路径默认 `config/runtime/default.json`，
  相对 CWD，与原行为一致；workflow 与 skills 相对工作区根解析，不受 CWD 影响）。

## 4. Compatibility

| 旧调用方式 | 现状 |
| --- | --- |
| `distill_payload(payload)` | **保持**，内部 `bootstrap(None)` 使用默认配置 |
| `distill_payload(payload, config_path)` | **保持**，内部 `bootstrap(config_path)` |
| `verify_plugin_checkpoint(payload)` / `(payload, config_path)` | **保持** |
| `normalize_source_input(payload)` | **未改动** |
| `evaluate_gate(payload)` | **未改动** |
| `build_generation_handoff(payload, format_name)` | **未改动** |
| `main(argv)` 命令集与退出码 | **保持**：参数个数错误 → 2；未知命令 → 1；执行失败 → 1 |
| stdout JSON / stderr `{"error": ...}` | **格式未变** |
| `.lobster` 与 `node_contracts.json` | **未改动** |

新增能力（向后兼容，不破坏旧调用）：

```python
context = bootstrap(config_path)                 # 初始化一次
distill_payload(payload, context=context)        # 复用，不再重读配置
verify_plugin_checkpoint(payload, context=context)
```

已测试：注入 context 时 `bootstrap` **零调用**（`test_supplied_context_is_not_re_bootstrapped`）。

既有回归测试 `tests/deployment/test_workflow_mapping.py`（使用旧的两参数调用方式）
未作任何修改即继续通过。

## 5. Tests

新增 `tests/runtime_bootstrap/test_lobster_integration.py`（9 项，含任务要求的 Test 1–5）：

| 任务要求 | 测试方法 | 验证点 |
| --- | --- | --- |
| Test 1 Bootstrap → Lobster Adapter | `test_adapter_initializes_through_bootstrap` | 适配器模块**不存在** `load_runtime_config` / `load_plugin`；`distill_payload` 恰好触发 1 次 `bootstrap` |
| Test 1（补） | `test_supplied_context_is_not_re_bootstrapped` | 注入 context 时不再重读配置（`bootstrap` 零调用） |
| Test 2 Runtime Config Plugin Selection | `test_configured_plugin_is_the_one_the_workflow_uses` | 只启用探针插件时 artifact 的 plugin 为探针；同一 artifact 在默认配置下被 checkpoint 拒绝 → 选择确实来自配置 |
| Test 3 Runtime Config Skill Selection | `test_configured_skill_registry_matches_config` | 只启用 `quality-review` 时 skill registry 恰为该项 |
| Test 4 Bootstrap Failure Propagation | `test_invalid_config_propagates_without_fallback`、`test_cli_reports_bootstrap_failure_instead_of_running` | 非法版本在 API 与 CLI 两条路径都抛/报 `RuntimeBootstrapError`，**无 fallback 到旧 loader** |
| Test 4（补） | `test_workflow_binding_mismatch_fails_closed` | 绑定不含该节点的 workflow 时 fail-closed |
| Test 5 End-to-End Dry Run | `test_end_to_end_dry_run_shares_one_context` | 5 个节点共享同一 context，产出 artifact 且 gate PASS → handoff ready |
| Test 5（补，最强证据） | `test_workflow_commands_run_as_separate_processes` | 用 `python -m workflows.lobster.runtime_adapter <cmd>` **真实起 5 个进程**串起完整链条，全部退出码 0，最终 `status=ready_for_generation` |

### 验证结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **43** tests, OK（5.3.1 的 34 + 新 9） |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json`（runtime config / workflow / manifest / schema） | **PASS**，20/20 |
| Secret scan — 工作区 | `python security/secret_scan.py .` | **PASS** |
| Secret scan — 仓库根 | `python security/secret_scan.py ..\..` | **PASS** |

## 6. Remaining Issues

| ID | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| R-01 | **潜在循环导入**：`plugin_interface` 无法先于 `core` 导入（`plugin_interface.base` → `core.models` → `core.__init__` → `core.plugin_loader` → `plugin_interface.base`） | 任何"先 import plugin_interface"的模块都会 ImportError；本轮集成测试最初即因此失败 | 在 `plugin_interface/base.py` 用 `if TYPE_CHECKING:` 收窄 `RawSource` 导入（该类仅用于注解，文件已有 `from __future__ import annotations`）。**因"禁止修改 Creator Plugin Interface"未在本轮执行**，仅在新测试中以导入顺序规避并注释说明 |
| R-02 | `context.skills` 未被任何适配器命令消费 | Skill 选择虽经 bootstrap 校验，但生产节点未直接使用 skill 元数据 | 若需将节点与 Skill 关联（如 `quality_gate` ↔ `quality-review`），需先定义该策略；本轮未自行发明 |
| R-03 | 命令↔节点映射以常量表硬编码在适配器中 | workflow 若改名节点，适配器会 fail-closed（有意），但需同步维护 | 可将映射移入 `node_contracts.json` 或由 workflow 自身声明 |
| R-04 | `main()` 每个命令各 bootstrap 一次（Lobster 每步一个进程） | 每个节点重复读取配置与发现 Skill；单次开销小但非零 | 属进程模型固有；如需可加缓存，但会引入陈旧配置风险 |
| R-05 | `gate` / `source-input` / `generation-handoff` 现在也要求配置可用 | 属有意的 fail-fast 行为变更，已在第 3 节记录 | 若某实例需要"无配置运行门禁"，需显式提供只读配置 |

### 成功标准核对

```text
Runtime Config  ->  PASS
bootstrap()     ->  PASS
RuntimeContext  ->  PASS
Lobster Runtime Adapter  ->  PASS（不再解析配置/加载插件，全部取自 context）
Workflow Execution       ->  PASS（5 进程真实链路实测通过）
Artifact                 ->  PASS
```

生产路径已完全接入 Bootstrap，无 R-01 之外的阻塞项，故判定 **PASS**。

## 7. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

1. **"新增层"必须验证"生产接入"**：5.3.1 新层自带测试全绿，但生产路径一次都没调用它。
   验收应显式检查生产模块是否仍持有旧依赖——本轮用一次 grep
   （`load_runtime_config|load_plugin` 在适配器中 0 命中）即为可执行的准入证据，建议
   下沉为发布 Gate 检查项。
2. **端到端应以真实进程验证**：同进程共享 context 的测试无法发现"命令注册/CLI 分派"
   层面的断裂。5 次 `python -m` 子进程链路是本轮唯一能证明"工作流真的能跑"的证据，
   值得作为后续阶段的默认验收方式。
3. **导入顺序依赖是隐藏的契约**：循环导入让"import 顺序"变成未文档化的隐式依赖，
   测试通过与否取决于导入先后。发现后应记录而非静默规避。
