# Release Validation: creator-agent-template-v0.2.0-rc1

## 1. Release Status

```text
Release Status: SUCCESS
Release Candidate — NOT Production Ready
```

`creator-agent-template-v0.2.0-rc1` 已建立、推送并通过全新克隆验证。

## 2. Git 信息

### 2.1 Commit

| 项 | 值 |
| --- | --- |
| Release commit | `666f8b053b54867506c6ba8966eac636f04ceeb8` |
| Release commit message | `docs: add creator agent v0.2.0-rc1 release notes` |
| Phase 5.3.3 baseline | `91ae6fca1cf89b53c1a0bba480c294a25e19699f`（`feat: add artifact validation pipeline`）|
| 前序远端基线 | `ed6a9241c8c4f9badd0405d8835cc263619ed611` |

Baseline 审计在 `91ae6fc` 上执行：working tree clean，提交链完整。

```text
ed6a924  security: finalize credential exposure closure
   |
f8f9174  feat: add runtime bootstrap layer
   |
a5abda9  feat: integrate runtime bootstrap with lobster adapter
   |
91ae6fc  feat: add artifact validation pipeline
   |
666f8b0  docs: add creator agent v0.2.0-rc1 release notes   <-- release commit / tag target
```

> **与任务书 Step 10.1 的差异说明**：任务书写"确认 GitHub main = `91ae6fc`"。实际
> `main` 位于 `666f8b0`。原因是 Step 3 要求新增 `RELEASE_NOTES_v0.2.0_RC1.md`，而
> Release Tag 必须包含自身的 release notes（否则 Tag 内无发布说明）。`91ae6fc` 是
> `666f8b0` 的直接父提交，已完整包含在发布内容中。

### 2.2 Tag

| 项 | 值 |
| --- | --- |
| Tag | `creator-agent-template-v0.2.0-rc1`（annotated）|
| Tag object | `b715e9c24ed278d2a380df058e8e90588a6c1239` |
| Tag target | `666f8b053b54867506c6ba8966eac636f04ceeb8` |

Tag message：

```text
Creator Agent Framework v0.2.0 Release Candidate 1
Includes Runtime Bootstrap,
Lobster Integration,
Artifact Validation Pipeline.
```

**v0.1.0 未被修改**：`creator-agent-template-v0.1.0` 仍为 Tag 对象 `ca19e350c4408210baa9d7f0f68c101ad5315a90`
→ commit `7b73035eebcb055e347bbad4a0526447e809f78d`。

### 2.3 Remote 状态

推送结果：

```text
main : ed6a924..666f8b0  (fast-forward)
tag  : [new tag] creator-agent-template-v0.2.0-rc1
```

GitHub 实时 `ls-remote`：

```text
666f8b053b54867506c6ba8966eac636f04ceeb8   refs/heads/main
ca19e350c4408210baa9d7f0f68c101ad5315a90   refs/tags/creator-agent-template-v0.1.0
7b73035eebcb055e347bbad4a0526447e809f78d   refs/tags/creator-agent-template-v0.1.0^{}
b715e9c24ed278d2a380df058e8e90588a6c1239   refs/tags/creator-agent-template-v0.2.0-rc1
666f8b053b54867506c6ba8966eac636f04ceeb8   refs/tags/creator-agent-template-v0.2.0-rc1^{}
```

```text
local main == origin/main   (ahead 0, behind 0)
```

## 3. Clean Clone 验证

从 GitHub 全新克隆并 checkout 本 RC Tag（不依赖本地对象库）：

| 检查 | 结果 |
| --- | --- |
| `git clone https://github.com/ai-singer/hand-on-off.git` | **成功** |
| `git checkout tags/creator-agent-template-v0.2.0-rc1` | **成功**，HEAD = `666f8b0` |
| 目录 `blank/workspace/runtime/` | **PRESENT** |
| 目录 `blank/workspace/artifact/` | **PRESENT** |
| 目录 `blank/workspace/tests/runtime_bootstrap/` | **PRESENT** |
| 目录 `blank/workspace/tests/artifact_validation/` | **PRESENT** |
| 目录 `blank/workspace/security/` | **PRESENT** |
| `blank/workspace/docs/RELEASE_NOTES_v0.2.0_RC1.md` | **PRESENT** |

在**该全新克隆的 Tag 检出**上重跑全部能力验证：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran **59** tests, OK |
| 编译检查 | `python -m compileall .` | **PASS**，exit 0 |
| Secret scan | `python security/secret_scan.py .` / `..\..` | **PASS**，两范围 0 发现 |
| Deployment Gate | `pwsh -File scripts/package_workspace.ps1` | **PASS**，111 文件入清单，制品验证通过，exit 0 |

Gate 输出：

```text
Files: 111
Artifact validation PASS: <temp>\workspace
Package:  <clone>\blank\dist\creator-agent-workspace-20260927-142322.tar.gz
SHA256:   AA0B2A04D5B76DCA15B6708097F1D86CD67DC9E5EE1D3307695C2CB57B53CB01
Manifest: <clone>\blank\dist\creator-agent-workspace-20260927-142322.tar.gz.manifest.json
```

同时交叉验证本地工作区与 Tag 检出的制品文件集完全一致（两处均为 111 个文件，
差异集合为空），确认发布内容与本地开发内容一致。

## 4. Capability Matrix

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Runtime Bootstrap | **PASS** | `runtime/` 层；`tests/runtime_bootstrap/test_bootstrap.py` 12 项；Config 驱动 instance / plugin / skill / workflow |
| Lobster Integration | **PASS** | `tests/runtime_bootstrap/test_lobster_integration.py` 9 项，含 5 进程真实工作流链路；适配器不再解析配置或加载插件 |
| Artifact Validation | **PASS** | `artifact/` 层 + `artifact/schema.json`；`tests/artifact_validation/` 16 项；部署 Gate 成功/失败双向实测 |
| Security Gate | **PASS** | `security/secret_scan.py` 6 项测试；工作区与仓库根扫描 0 发现；打包前/后双次扫描 |

发布事实：

```text
Tests:        59 PASS (本版本新增 37)
Compile:      PASS
JSON:         21/21 PASS
Secret scan:  PASS (workspace + repository root)
Deploy gate:  PASS (artifact + manifest emitted, fail-closed verified)
```

## 5. Known Issues（未隐藏）

完整清单见 `RELEASE_NOTES_v0.2.0_RC1.md` 第 4 节。发布时仍未关闭的高优先级项：

| ID | 问题 | 状态 |
| --- | --- | --- |
| SEC-1 | Credential rotation pending：6 类已泄露凭据尚未轮换 | **OPEN** |
| SEC-2 | GitHub cache exposure pending：已清除归档仍可按旧 SHA 从 GitHub 下载 | **OPEN** |
| SEC-3 | 本机隔离副本与重写前镜像仍持有同一份材料 | **OPEN** |
| ART-1 | Manifest unsigned | OPEN（已记录）|
| VER-1 | 版本命名空间不一致（pyproject 0.1.0 / config 1.0.0 / tag v0.2.0-rc1）| OPEN（已记录）|

上述问题**不在本阶段修复**（本阶段只做 Release Engineering），仅如实记录。

## 6. Deployment Recommendation

```text
Release Candidate
NOT Production Ready
```

**可以**：供目标实例（小龙虾）拉取、加载、执行部署与运行时验证。

**不可以**：在真实部署验证通过前用于生产生成或对外发布链路。

建议的验证范围：

| # | 验证项 | 期望 |
| --- | --- | --- |
| 1 | 按 `GITHUB_DEPLOYMENT_ENTRY.md` 拉取并校验 commit/tag | HEAD = `666f8b0` |
| 2 | `bootstrap()` 加载实例自有 runtime profile | instance / plugins / skills / workflow 与配置一致 |
| 3 | Lobster 五节点链路执行 | 产出 artifact，质量门 PASS，生成交接 ready |
| 4 | 配置阻断行为 | 插件未启用 / 版本不兼容时启动即失败 |
| 5 | 制品导入与回滚 | 归档可导入，manifest 自验通过，可回滚 |
| 6 | 质量门阻断 | block 风险产生 `review_required` 且生成步骤未执行 |
| 7 | 安全现状确认 | 确认 SEC-1/SEC-2 仍未关闭，并推动凭据轮换 |

## 7. 本阶段边界

- **未修改**：核心代码、Runtime 逻辑、Workflow、Plugin、Skill 协议（已用 `git status`
  与提交内容核验，本阶段只新增两份 docs）；
- **未修复**：本阶段发现或沿用的任何问题，只记录（见第 5 节）；
- **未修改 v0.1.0**：其历史与 Tag 保持原状。

## 8. 最终状态

```text
main pushed      : YES   (666f8b0)
tag pushed       : YES   (creator-agent-template-v0.2.0-rc1 -> 666f8b0)
working tree     : clean
```

## 9. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

1. **Release Tag 必须包含自身发布说明**。任务书 Step 10.1 期望 `main = 91ae6fc`，
   但新增 release notes 必然产生新提交。二者不可同时成立，本轮选择"Tag 内含发布说明"
   并在第 2.1 节显式记录差异，而不是让 Tag 指向缺少发布说明的提交。
2. **发布验证必须在全新克隆上重跑能力检查**，而不是复用本地环境。本轮 59 项测试、
   编译、扫描与部署 Gate 全部在 Tag 检出的干净克隆上复验，并对两处制品文件集做了
   集合比对（差异为空），这是"发布内容 = 开发内容"的唯一硬证据。
3. **验证脚本中的 Shell 引号是真实风险**：`git rev-parse 'tag^{commit}'` 中 `{...}`
   在 PowerShell 下会被当作脚本块解析并静默改变参数。命令要加引号，且结论要由
   独立路径（全新克隆 checkout）交叉确认，不能只信一次 `rev-parse` 输出。
