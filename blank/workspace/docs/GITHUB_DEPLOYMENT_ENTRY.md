# GitHub Deployment Entry: Blank Lobster Instance

本文件是空白龙虾实例（OpenClaw workspace）从 GitHub 拉取并部署 Creator Agent
Framework 的唯一入口说明。

## 1. 仓库与版本

| 项目 | 值 |
| --- | --- |
| 仓库 | https://github.com/ai-singer/hand-on-off |
| 使用版本 | `creator-agent-template-v0.1.0` |
| 版本对应 commit | `033da3c76ddae7740afb7c51d56b4e12ce78378e` |
| 分支 | `main` |
| 可部署目录 | 仓库内 `blank/workspace/` |
| 发布说明 | [`RELEASE_NOTES_v0.1.0.md`](RELEASE_NOTES_v0.1.0.md) |

```text
Release Status: Deployment Candidate
Runtime Validation: Pending
```

必须固定使用 tag `creator-agent-template-v0.1.0`，不要跟踪 `main` 的漂移提交。
本版本是部署候选：可以拉取、加载并验证，但在运行时验证通过前不得用于生产
生成或对外发布链路。

## 2. 部署流程

### 步骤 1：拉取指定版本

```bash
git clone https://github.com/ai-singer/hand-on-off.git
cd hand-on-off
git fetch --tags
git checkout tags/creator-agent-template-v0.1.0 -b release/creator-agent-template-v0.1.0

# 校验拉取到的正是候选版本
git rev-parse HEAD
# 期望：033da3c76ddae7740afb7c51d56b4e12ce78378e
```

也可直接下载该 tag 的源码归档：

```text
https://github.com/ai-singer/hand-on-off/archive/refs/tags/creator-agent-template-v0.1.0.tar.gz
```

部署根目录为 `blank/workspace/`。以下步骤均在该目录下执行。如需打包成交付
制品，使用 `scripts/package_workspace.ps1`，并记录输出的 SHA-256。

### 步骤 2：加载 Runtime 配置

```bash
python -c "from config.runtime import load_runtime_config; print(load_runtime_config())"
```

- 默认 profile：`config/runtime/default.json`；
- 实例自有 profile 通过环境变量 `CREATOR_RUNTIME_CONFIG` 或 Lobster 参数
  `runtime_config` 选择；
- profile 负责 `instance.name`、`workflow.default`、`plugins.enabled`、
  `plugins.default`、`skills.enabled` 与 profile `version`；
- 非法 profile（缺段、默认插件未启用、名称重复、版本非法、Skill 命名不合规）
  必须启动即失败，不要绕过。

模型、搜索、OCR、转写、存储与发布凭据属于实例密钥存储，不进入本仓库，也不写入
profile。

### 步骤 3：加载 OpenClaw Skill

```bash
python -c "from skills.openclaw import discover_openclaw_skills; print(sorted(discover_openclaw_skills()))"
# 目标实例原生校验
openclaw skills list
```

- 可部署包装位于 `skills/openclaw/`：`source-ingestion`、
  `unified-distillation`、`quality-review`；
- 内部 Skill 由 `skills/internal/catalog.json` 映射，保持不变；
- 只加载当前 workflow 实际需要的 Skill；
- 原生发现结果必须与 profile 的 `skills.enabled` 一致。

### 步骤 4：加载 Creator 插件

```bash
python -c "from core import load_plugin; print(load_plugin('plugins.xiaolin_finance').identity)"
```

- 插件模块路径是数据：更换 Creator/领域插件只需安装插件并修改 profile，不需要
  修改 `core/` 或 `distillation_core/`；
- 插件私有 Schema 目前没有运行时消费者（见发布说明第 5 节第 1 条），部署时不要
  假定 `domain_extension` 已被私有 Schema 校验；
- 领域规则、rubric 与私有 Schema 必须留在 `plugins/<plugin_name>/` 内。

### 步骤 5：加载 Lobster Workflow

```bash
cat workflows/lobster/content_distillation.lobster
```

节点顺序：`source_input` → `unified_distillation` → `creator_plugin_enhancement`
checkpoint → `quality_gate` → `content_generation` handoff。节点契约、输入输出
与失败语义见 `workflows/lobster/node_contracts.json`。

- 蒸馏只调用一次引擎（通用提取与插件增强在同一次运行内完成），
  `creator_plugin_enhancement` 只是校验 checkpoint，不得触发第二次蒸馏；
- 最后一步受 `$quality_gate.json.can_continue` 约束，只有 PASS 才进入生成交接；
- 最终节点只产出 `GenerationRequest` 交接，框架不提供模型与发布实现；
- 对外发布、账号写入、付费调用等外部副作用需要显式授权，并应使用 Lobster
  approval 保护。

### 步骤 6：执行 Runtime Validation

```bash
python -m unittest discover -s tests -v
python -m compileall .
```

除单元测试与编译检查外，必须在目标实例执行以下运行时验证，并保存证据：

| 验证项 | 期望结果 |
| --- | --- |
| 版本绑定 | `git rev-parse HEAD` 等于 tag `creator-agent-template-v0.1.0` 指向的 commit |
| Skill 原生发现 | `openclaw skills list` 能列出三个连字符命名 Skill |
| Skill 最小调用 | 每个 Skill 的测试命令可执行且通过 |
| Lobster 解析/dry-run | 工作流可解析，五个节点可按序执行 |
| 安全输入 | 通过质量门并到达生成交接 |
| 阻断输入 | `block` 风险产生 `review_required`，且生成步骤未执行（生成适配器调用次数为 0） |
| 插件/配置不匹配 | 在插件 checkpoint 停止，不进入质量门 |
| 制品导入与回滚 | 归档可导入，可回滚到上一版本，不回混插件私有 Schema |
| 记录 | commit SHA、tag、制品 SHA-256、插件/profile 版本写入发布记录 |

任一验证项失败时停止部署，不要用放宽配置或跳过步骤的方式继续。

## 3. 边界

- 本模板不包含模型调用、发布、凭据或账号变更；
- 生成实现与发布适配器由实例注入，并保留既有的外部副作用授权要求；
- 实例配置与密钥不得提交回本仓库；
- 本版本为 Deployment Candidate，Runtime Validation 未完成。
