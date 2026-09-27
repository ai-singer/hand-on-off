# Release Notes: creator-agent-template-v0.2.0-rc1

## 1. Version

```text
Release:      creator-agent-template-v0.2.0-rc1
Tag:          creator-agent-template-v0.2.0-rc1
Commit:       91ae6fca1cf89b53c1a0bba480c294a25e19699f
Baseline:     ed6a9241c8c4f9badd0405d8835cc263619ed611
Repository:   https://github.com/ai-singer/hand-on-off
Branch:       main
Package:      creator-agent-template 0.1.0 (pyproject.toml)
Deployable:   blank/workspace/
Status:       Release Candidate — NOT production ready
```

前序版本 `creator-agent-template-v0.1.0` 只包含基础 Framework 与 Security Gate。本
Release Candidate 在其之上补齐 Runtime Bootstrap、Runtime Integration 与 Artifact
Validation 三层能力。**v0.1.0 的历史与 Tag 未被修改。**

## 2. New Features

### 2.1 Runtime Bootstrap

新增 `runtime/` 层，提供唯一初始化入口 `bootstrap()`：

```text
Runtime Config -> bootstrap() -> RuntimeContext -> Component Loading
```

Runtime Config 现在真正驱动运行行为，而不只是被校验：

| Config 字段 | 结果 |
| --- | --- |
| `instance` | `RuntimeContext.instance` |
| `version` | `RuntimeContext.version`，并校验与运行时契约主版本兼容 |
| `plugins.enabled` | 只构造并加载被启用的插件；身份冲突与 `plugins.default` 缺失即失败 |
| `skills.enabled` | 只加载被启用的 Skill；缺少 `manifest.json` 即失败 |
| `workflow.default` | 解析并结构校验后绑定为 `RuntimeContext.workflow` |

同时为 3 个可部署 Skill 包补齐标准 `manifest.json`，并与其 `adapter.json`
交叉校验 name / version / entrypoint 漂移。

### 2.2 Lobster Runtime Integration

生产执行路径统一进入 bootstrap，消除双初始化路径：

```text
Runtime Config -> bootstrap() -> RuntimeContext -> Lobster Runtime Adapter
               -> Workflow Execution -> Artifact
```

- `workflows/lobster/runtime_adapter.py` 不再解析配置、不再自行加载插件；
- 新增 `resolve_context()`：注入的 context 原样复用，否则 bootstrap 恰好一次；
- Workflow Schema、`.lobster` 结构、Command 定义、Node 顺序、Input/Output 格式与
  Quality Gate 逻辑**均未改动**；
- 新增 fail-closed 绑定检查：配置绑定的 workflow 必须声明该命令实现的节点。

**行为变更（有意）**：全部 5 个命令现在都先 bootstrap，配置损坏时工作流在第一个
节点即失败，不再"带着默认值半跑"。

### 2.3 Artifact Validation Pipeline

部署制品获得可验证身份：

```text
Build -> Artifact Manifest -> Artifact Validation -> Deploy
```

- `artifact/manifest.py`：递归扫描制品，记录 `artifact_id` / `version` /
  `created_at` / `runtime_version` / `config_version` / `enabled_plugins` /
  `enabled_skills`，以及每个文件的 `path` / `sha256` / `size`（稳定排序）；
- `artifact/validator.py`：10 条规则一次收集全部问题，覆盖
  **文件完整性、Hash、Runtime 版本、Plugin 存在、Skill 存在、Config 存在**，
  另加 config 语义一致性与"夹带未声明文件"两项；
- `artifact/schema.json`：清单结构 Schema，复用既有 `core.schema_validation`；
- `scripts/package_workspace.ps1` 接入部署 Gate：打包 → 生成清单 → 解包制品并
  按清单验证 → 成功才输出。**失败时删除制品与清单并以非零码退出，绝不留下可部署包。**

清单从打包输入生成、对解包产物验证，因此 Gate 证明的是"实际发出的字节"，而不是
用同一份内容自证。

## 3. Validation Evidence

全部在 `blank/workspace/` 下执行，基线 `91ae6fc`：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **59** tests, OK |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| JSON 解析 | 全部 `*.json`（runtime config / skill manifest / schema / artifact manifest）| **PASS**，21/21 |
| Secret scan | `python security/secret_scan.py .` 与 `<repository-root>` | **PASS**，两范围 0 发现 |
| Deployment Gate — 成功路径 | `pwsh -File scripts/package_workspace.ps1` | **PASS**，输出制品 + 旁挂 manifest，exit 0 |
| Deployment Gate — 失败路径 | 受控破坏制品内 config | **FAIL 阻断**，exit 1，制品与 manifest 均已删除 |

测试构成（59 项）：

| 测试包 | 数量 | 归属 |
| --- | ---: | --- |
| `tests/runtime_bootstrap/test_bootstrap.py` | 12 | 本版本新增 |
| `tests/runtime_bootstrap/test_lobster_integration.py` | 9 | 本版本新增 |
| `tests/artifact_validation/test_artifact_validation.py` | 16 | 本版本新增 |
| `tests/deployment/`（4 个模块） | 8 | 0.1.0 起 |
| `tests/secret_scan/` | 6 | 0.1.0 起 |
| `tests/test_framework.py` | 5 | 0.1.0 起 |
| `tests/stabilization/` | 3 | 0.1.0 起 |

本版本新增 **37** 项，0.1.0 既有 **22** 项。

其中 `tests/runtime_bootstrap/test_lobster_integration.py` 含一项真实进程链路验证：
以 `python -m workflows.lobster.runtime_adapter <command>` 起 5 个子进程，经
stdin/stdout 串联完整工作流，终态 `status=ready_for_generation`。

对比 v0.1.0：测试数 13 → 59。

## 4. Known Issues

以下问题**未隐藏**，且**不在本阶段修复**（本阶段只做 Release Engineering）。
完整清单见各阶段报告。

### 4.1 安全（沿用 Phase 5.2 结论，仍未关闭）

| ID | 问题 | 状态 |
| --- | --- | --- |
| SEC-1 | **Credential rotation pending**：Phase 5.2 识别出的 6 类已泄露凭据（API Token / API Key ×2 / GitHub Token / Cookie-Session / 未分类敏感赋值）尚未轮换，仍未失效 | **OPEN — 需凭据所有者执行** |
| SEC-2 | **GitHub cache exposure pending**：已从历史清除的含凭据归档仍可按旧 commit/blob SHA 从 GitHub 完整下载 | **OPEN — 需轮换优先，必要时 Support purge 或删除重建仓库** |
| SEC-3 | 本机隔离副本与重写前镜像仍持有同一份材料 | **OPEN — 轮换后须销毁** |

仓库侧与发布链侧已关闭：当前树、历史与 Tag 均已清理；部署入口不再分发整树源码
归档；Release Security Gate 已建立。

### 4.2 制品与发布

| ID | 问题 | 影响 |
| --- | --- | --- |
| ART-1 | **Manifest unsigned**：清单未签名 | 可防无意损坏，不可防"清单与制品被同时替换"的主动篡改 |
| ART-2 | 打包排除项在两处声明（tar `--exclude` 与脚本 `$artifactExcludes`） | 不一致时 Gate fail-closed 误报，不会漏放 |
| ART-3 | 清单为旁挂文件（`<artifact>.manifest.json`） | 消费方需另行获取清单才能自验 |
| ART-4 | `created_at` 使清单非字节复现 | 复现构建需另行设计 |

### 4.3 版本命名空间

| ID | 问题 | 影响 |
| --- | --- | --- |
| VER-1 | **Version namespace inconsistency**：`pyproject.toml` = `0.1.0`、runtime config `version` = `1.0.0`、Tag = `v0.2.0-rc1`、`SUPPORTED_CONFIG_VERSION` = `1.0.0` | 四者语义不同但字面易混；本版本未统一 |

### 4.4 运行时代码质量（已记录，未修复）

| ID | 问题 | 影响 |
| --- | --- | --- |
| RT-1 | **潜在循环导入**：`plugin_interface` 无法先于 `core` 导入 | 任何"先 import plugin_interface"的模块会 ImportError；因"禁止修改 Plugin Interface"未修 |
| RT-2 | `context.skills` 未被任何适配器命令消费 | Skill 选择已经 bootstrap 校验，但节点未直接使用 skill 元数据 |
| RT-3 | 命令↔节点映射硬编码为常量表 | workflow 改名节点时会 fail-closed，需同步维护 |
| RT-4 | 每个命令各 bootstrap 一次 | Lobster 每步一个进程，重复初始化开销非零 |
| RT-5 | 验证器不检查 config 引用的 workflow 文件是否存在 | 该问题由 `bootstrap()` 在运行时暴露 |
| RT-6 | 仅在 Windows + Python 3.13 实测 | tar 排除语义与大小写敏感性未在 Linux 验证 |

## 5. Compatibility

- **v0.1.0 未受影响**：历史与 Tag `creator-agent-template-v0.1.0` 未被修改；
- **API 兼容**：`distill_payload(payload)`、`distill_payload(payload, config_path)`、
  `verify_plugin_checkpoint(...)`、`normalize_source_input`、`evaluate_gate`、
  `build_generation_handoff` 的签名与输出格式全部保持；既有
  `tests/deployment/test_workflow_mapping.py` 未作修改即通过；
- **配置兼容**：`config/runtime/default.json` 未改动，实例自有 profile 继续可用；
- **部署兼容**：打包脚本输出格式不变，新增旁挂 manifest 与 Gate 校验；失败时不再输出制品。

## 6. Deployment Recommendation

```text
Release Candidate
NOT Production Ready
```

可用于：目标实例拉取、加载、运行 Runtime Validation 与部署演练。

**在目标实例（小龙虾）完成真实部署验证之前，不得用于生产生成或对外发布链路。**
验证至少应覆盖：Runtime Config 加载与选择生效、Lobster 五节点链路、制品导入与回滚、
Artifact Manifest 自验、Quality Gate 阻断行为、以及已声明 Known Issues 的现状确认。

部署入口见 [`GITHUB_DEPLOYMENT_ENTRY.md`](GITHUB_DEPLOYMENT_ENTRY.md)。

## 7. 本阶段边界

本阶段只做 Release Engineering：

- 未修改核心代码、Runtime 逻辑、Workflow、Plugin、Skill 协议；
- 未修复任何新发现的问题，仅记录（见第 4 节）；
- 未修改 v0.1.0 历史与 Tag。
