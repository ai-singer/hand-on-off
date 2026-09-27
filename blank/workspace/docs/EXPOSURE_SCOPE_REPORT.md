# Creator Agent Framework Phase 5.2 - Exposure Scope Report

> **状态：已被 Phase 5.2.1 取代，保留为历史记录。**
> 本报告描述的是历史重写**之前**的事实：当时 `new/workspace.tar.gz` 仍被跟踪，并
> 存在于 `main` 与发布 Tag 中。Phase 5.2.1 已完成取消跟踪、历史重写、Tag 重建与
> 远端更新，因此本报告中的 commit / blob SHA 已不再存在。原始结论与证据未作改写；
> 当前状态见 [`PHASE_5_2_1_CREDENTIAL_EXPOSURE_CLOSURE.md`](PHASE_5_2_1_CREDENTIAL_EXPOSURE_CLOSURE.md)。

## 1. 检查范围

本轮目标是关闭 `docs/CREDENTIAL_AUDIT_REPORT.md` 遗留的“暴露范围未知”缺口。执行
过程中不修改 Git 历史、不删除文件、不重写或推送远端、不读取或复制任何凭据原文。

| 检查面 | 方法 | 结论 |
| --- | --- | --- |
| 当前 HEAD 工作树 | `git ls-files`、`git ls-tree -r HEAD` | 风险文件被 Git 跟踪 |
| 完整本地历史 | `git log --all -- <path>`、`--diff-filter=DM` | 加入点明确，从未被删除或修改 |
| 本地 Tag | `git cat-file -p`、`git ls-tree -r <tag>` | 注解 Tag 指向的 commit 树含风险文件 |
| 远端分支 | `git ls-tree -r origin/main`、`git merge-base --is-ancestor` | 远端 `main` 已含风险文件 |
| 远端 Tag ref | `git ls-remote --tags origin` | 未完成，见第 5 节 |
| 发布入口文档 | `docs/GITHUB_DEPLOYMENT_ENTRY.md`、`docs/RELEASE_NOTES_v0.1.0.md` | 文档公开了包含风险文件的 Tag 源码归档地址 |
| 部署制品 | `scripts/package_workspace.ps1` 打包范围、本地 `dist/` 搜索 | 制品不含风险文件 |
| 归档内容实测 | `python security/secret_scan.py <repo-root>` | 15 项发现，全部位于 `new/workspace.tar.gz` 内 |

凭据类型与数量沿用 `docs/CREDENTIAL_AUDIT_REPORT.md` 的脱敏结论。本报告只记录类型、
位置与是否需要轮换，不含任何凭据原文、片段或明文指纹。

## 2. 发现结果

### E-01：风险文件仍在当前 HEAD 中被跟踪

```text
path   : new/workspace.tar.gz
blob   : e79e53188b8d86f19218b7191da2fb32b0fea780
size   : 20123338 bytes
sha256 : e3513e29fcbbbdb43f31ff0a536e88c22fe22ac54fb2ec1a5a732ee7a4bf431d
```

`git ls-files` 返回该路径，说明它处于已跟踪状态。仓库根 `.gitignore` 已包含
`new/workspace.tar.gz`，但 **`.gitignore` 对已跟踪文件无效**：该条目当前不提供任何
保护，容易被误读为“已处理”。

### E-02：风险文件已进入 Git 历史

- 加入提交：`ac5f81a`（`snapshot: workspace 2026-09-22`）。
- `git log --all --diff-filter=DM -- new/workspace.tar.gz` 为空，说明该 blob 自加入后
  从未被删除或修改。
- 因此它存在于 `ac5f81a` 起至 `HEAD` 的全部可达提交中：`ac5f81a`、`cfb38a8`、
  `033da3c`、`c3174cd`、`d810e01`，即 **62 个可达提交中的 5 个**。
- 该归档内部还含两个嵌套 Git 仓库（`workspace/.git` 与
  `workspace/ai-singer/hand-on-off/.git`）。因此即使只替换归档外的单个 blob，
  归档内部历史中的敏感文件仍然可达。

### E-03：风险文件已进入 GitHub 远端 main（已分发）

- `git ls-tree -r origin/main` 列出 `new/workspace.tar.gz`。
- `git merge-base --is-ancestor ac5f81a origin/main` 成立。
- 本地 `origin/main` = `c3174cd53a7b9ac7bfa8ddab07212eb76e258245`，`HEAD` 仅领先 1 个
  未推送提交（`d810e01`）。

结论：**风险文件内容已经到达 GitHub `main`**。按“凭据已经泄露”处理，不能按本地
误提交处理。

### E-04：风险文件已进入发布 Tag

- `creator-agent-template-v0.1.0` 是注解 Tag（对象 `c9ad5b5`），指向 commit
  `c3174cd`，即与 `origin/main` 相同的提交。
- `git ls-tree -r creator-agent-template-v0.1.0` 含 `new/workspace.tar.gz`。
- 发布文档记载的 commit 为 `033da3c`；该提交同样是 `c3174cd` 的祖先且同样含风险
  文件。即 **文档记载版本与实际 Tag 指向版本都受影响**。

### E-05：发布入口文档把 Tag 源码归档作为公开分发渠道

`docs/GITHUB_DEPLOYMENT_ENTRY.md` 第 44 行公开给出：

```text
https://github.com/ai-singer/hand-on-off/archive/refs/tags/creator-agent-template-v0.1.0.tar.gz
```

该地址是 GitHub 自动生成的**整树源码归档**，会包含仓库根下的 `new/workspace.tar.gz`。
因此“按文档部署”的任一实例都会下载到含明文凭据的归档。这是本轮新确认的**主动分发
路径**，风险高于单纯的仓库历史暴露。

### E-06：实际部署制品不受影响

- `scripts/package_workspace.ps1` 只在 `blank/` 目录下打包 `workspace` 子目录，产物为
  `blank/dist/creator-agent-workspace-<timestamp>.tar.gz`。
- `new/workspace.tar.gz`、`new/skills.tar.gz`、`old/skills_backup_*.tar.gz` 位于仓库根，
  `blank/openclaw-backup-20260922.tar.gz` 位于 `blank/` 但不在 `workspace/` 内，
  四者均不进入制品。
- 本地搜索未发现任何已生成的 `dist/` 目录或历史制品文件。

结论：**可部署制品 `blank/workspace/` 及其打包产物不含风险文件**，作者声明的部署面
本身是干净的；污染来自仓库根的历史快照目录。

### E-07：归档内容实测结果（新增发现）

`python security/secret_scan.py <repo-root>` 报告 15 项发现，**全部位于
`new/workspace.tar.gz` 内**；`new/skills.tar.gz`、`old/skills_backup_20260922_072844.tar.gz`、
`blank/openclaw-backup-20260922.tar.gz` 均无内容级发现。

| 规则 | 数量 | 归档内位置 |
| --- | ---: | --- |
| `nested-git` | 2 | `workspace/.git`、`workspace/ai-singer/hand-on-off/.git` |
| `forbidden-filename` | 5 | `workspace/.env`、`workspace/environment_resources/.env`、`workspace/credentials.json`、`workspace/xiaohongshu_cookies.txt`、`workspace/agent_package/tools/source_collector/secrets` |
| `openai-style-token` | 2 | `workspace/memory/2026-09-22-phanthy-publish-debug.md:40`、`workspace/phanthy_poller.py:62` |
| `sensitive-assignment` | 6 | `workspace/.env:1`、`workspace/credentials.json:5,13`、`workspace/phanthy_poller.py:22`、`workspace/agent_package/tools/source_collector/collectors/bilibili/auth.py:13,29` |

与 Phase 5.1 审计相比，本轮新增确认两类此前未记录的位置：
`agent_package/tools/source_collector/secrets` 和
`collectors/bilibili/auth.py` 的敏感赋值。差异原因是本轮扫描器覆盖了更宽的文件名与
赋值规则，属于**扩大发现**，不是新增暴露。

### E-08：凭据类型与轮换要求

| 类型 | 归档内位置 | 需要轮换 |
| --- | --- | --- |
| API Token（`sk-` 形式） | `workspace/memory/2026-09-22-phanthy-publish-debug.md`、`workspace/phanthy_poller.py` | 是 |
| API Key ×2 | `workspace/credentials.json`（`agents[0]`、`agents[1]`） | 是 |
| GitHub 凭据 | `workspace/.env` | 是 |
| Cookie / 会话材料 | `workspace/xiaohongshu_cookies.txt` | 是 |
| 未分类敏感赋值 | `collectors/bilibili/auth.py`、`source_collector/secrets` | 是（需人工确认服务归属） |
| 空值声明 | `workspace/environment_resources/.env` | 否 |

所有条目均为已进入远端 `main` 与 Tag 分发面的内容，**按已泄露处理**。轮换由对应
凭据所有者在其服务端执行 `revoke` + `rotate`，本仓库不保存、不复现任何明文。

## 3. 风险等级

```text
Exposure Scope Confirmed: YES
Distribution Surface: GitHub main + annotated tag + tag source archive
Overall Risk Level: HIGH
```

判定理由：风险文件不只是本地误提交，而是已经进入远端 `main`、注解 Tag，并通过发布
入口文档公开的 Tag 源码归档地址对外分发。凭据与可重放会话材料的暴露不可撤销，
只能通过轮换与服务端吊销关闭。

## 4. 建议动作

1. **先轮换，后清理**：在对应服务端 `revoke` + `rotate` 第 2.8 节全部凭据与会话，
   （E-08 表）轮换优先于任何仓库清理动作。
2. 按 `docs/HISTORY_CLEANUP_REPORT.md` 的协调流程，在**单独授权**下移除风险文件、
   删除本地专用 ref、重建 Tag 并强制更新远端 ref；不要只做单点删除。
3. 修订 `docs/GITHUB_DEPLOYMENT_ENTRY.md`，把部署入口从“Tag 源码归档”改为
   `blank/workspace/` 子目录导出或经 secret scan 通过的制品，并记录制品 SHA-256。
4. 把 `python security/secret_scan.py <repo-root>` 纳入发布 Gate，与 `blank/workspace/`
   范围扫描同时执行；仅扫描工作区不足以发现仓库根快照风险。
5. 清理文档或仓库中所有“不透明运行快照”入口，禁止再次跟踪 `*.tar.gz` 运行快照。
6. 轮换完成后重跑同范围扫描，确认旧值已失效且发布入口已清理。

## 5. 检查限制

- 远端 Tag ref 未被验证：`git ls-remote --tags origin` 因本机无可用凭据失败
  （`SEC_E_NO_CREDENTIALS`），本轮为离线检查。由于 Tag 指向的 commit 与
  `origin/main` 相同，该 blob 已在远端这一点不依赖远端 Tag 的验证结果。
- 未检查 GitHub Release assets、Actions artifacts、缓存、镜像、fork 与第三方克隆。
  这些属远端平台侧核查，需在有凭据的授权环境中执行。
- 未调用任何外部服务验证凭据是否仍然有效，也未执行任何轮换。
- 本地存在两个仅本地可达的 ref `refs/codex/turn-diffs/checkpoints/...`（`617f5b3`、
  `0c7a00e`），二者同样可达含风险文件的提交；历史清理时必须一并清理，否则对象
  仍可通过这些 ref 检出。
