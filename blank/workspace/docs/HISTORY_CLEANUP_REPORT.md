# Creator Agent Framework Phase 5.2 - History Cleanup Report

## 1. 结论摘要

```text
History Rewrite Required: YES
Rewrite Executed This Round: NO (requires explicit authorization)
Precondition: credential rotation must complete first
```

`new/workspace.tar.gz` 已进入远端 `main` 与注解发布 Tag，并出现在 `ac5f81a` 起至
`HEAD` 的全部可达提交中（62 个可达提交中的 5 个）。删除当前文件或只做
`git rm --cached` 都**不能**消除历史暴露，因此需要历史重写。

本报告只给出判定、影响范围与操作建议。按 Phase 5.2 的边界约束，本轮**没有**执行
删除、`git rm --cached`、重写、`force push` 或 Tag 重建。

## 2. 为什么不能简单删除

| 做法 | 是否足够 | 原因 |
| --- | --- | --- |
| 只加 `.gitignore` | 否 | 对已跟踪文件完全无效（当前仓库就处于这个状态） |
| 只 `git rm --cached` | 否 | 只是从下一个提交的树里移除；`ac5f81a`..`HEAD` 的历史仍含该 blob，远端仍可检出 |
| 只删本地工作树文件 | 否 | 远端 `main` 与 Tag 已含该 blob，删除本地文件不改变远端 |
| 单点删除归档 | 否 | 归档内部还含两个嵌套 Git 仓库（`workspace/.git` 3 个提交、`workspace/ai-singer/hand-on-off/.git` 44 个提交），其内部历史仍可达敏感文件 |
| 重写历史 | 是（配合轮换） | 唯一能停止继续分发的仓库侧手段；但**不能**吊销已经泄露的凭据 |
| 轮换凭据 | 是（必须最先做） | 唯一能真正关闭凭据风险的手段 |

关键点：**历史清理不是轮换的替代品**。若只重写历史而不轮换，已泄露的凭据仍然有效。

## 3. 影响范围

### 3.1 受影响 ref

| ref | 当前值 | 是否受影响 |
| --- | --- | --- |
| `refs/heads/main` | `d810e01` | 是，需重写后 `force push` |
| `refs/remotes/origin/main` | `c3174cd` | 是，远端已被污染 |
| `refs/tags/creator-agent-template-v0.1.0` | 注解 Tag `c9ad5b5` → `c3174cd` | 是，需删除并重建 |
| `refs/codex/turn-diffs/checkpoints/...`（2 个，仅本地） | `617f5b3`、`0c7a00e` | 是，二者均可达含风险文件的提交，必须一并删除，否则对象仍可检出 |
| `refs/remotes/origin/HEAD` | `c3174cd` | 随远端 `main` 变化 |

### 3.2 受影响提交

- 加入提交：`ac5f81a`（`snapshot: workspace 2026-09-22`）。
- 含该 blob 的可达提交：`ac5f81a`、`cfb38a8`、`033da3c`、`c3174cd`、`d810e01`。
- 历史重写会改变 `ac5f81a` 及其后所有提交的 SHA，即 **5 个提交 SHA 全部变化**，
  连同 `refs/heads/main` 的提交身份。

### 3.3 连带影响（容易遗漏）

1. **发布文档中的 commit 引用会失效**：`docs/GITHUB_DEPLOYMENT_ENTRY.md` 与
   `docs/RELEASE_NOTES_v0.1.0.md` 引用 `033da3c76ddae7740afb7c51d56b4e12ce78378e`，
   重写后该 SHA 不再位于 `main` 上，文档必须同步更新。
2. **已有克隆与 fork 继续携带旧对象**：重写不会回溯清理他人副本；协作方必须
   重新克隆，不能 `pull`。
3. **GitHub 自动源码归档与 CDN 缓存**：`/archive/refs/tags/...` 生成的归档由平台
   生成并缓存，Tag 重建后旧归档可能在缓存中短期仍可取，部分场景需平台侧介入。
4. **`main` 上的既有引用**：任何指向旧 SHA 的 issue/PR/commit 链接、CI 记录、
   外部文档都会指向已重写的历史。

## 4. 操作建议

以下流程需在**明确授权**的维护窗口内、由仓库所有者执行。顺序不可颠倒。

### 阶段 0：先轮换（不依赖任何仓库操作）

在对应服务端 `revoke` + `rotate` `docs/EXPOSURE_SCOPE_REPORT.md` E-08 表列出的全部
凭据与会话。轮换完成后才进入阶段 1。

### 阶段 1：冻结与备份

```bash
git clone --mirror https://github.com/ai-singer/hand-on-off.git repo-backup.git
git -C repo-backup.git bundle create ../hand-on-off-before-rewrite.bundle --all
```

备份用于审计与回滚，**不得**再分发。

### 阶段 2：重写历史

使用 `git filter-repo`（推荐，需先安装）或 BFG：

```bash
git clone https://github.com/ai-singer/hand-on-off.git hand-on-off-clean
cd hand-on-off-clean
git filter-repo --path new/workspace.tar.gz --invert-paths --force
```

若同一策略也覆盖其余不透明运行快照（三者当前扫描干净，非必需，但符合禁止跟踪
运行快照的策略），追加：

```bash
git filter-repo \
  --path new/workspace.tar.gz \
  --path new/skills.tar.gz \
  --path old/skills_backup_20260922_072844.tar.gz \
  --path blank/openclaw-backup-20260922.tar.gz \
  --invert-paths --force
```

### 阶段 3：清理仅本地 ref 与不可达对象

```bash
git update-ref -d refs/codex/turn-diffs/checkpoints/0fda25ae4040d0996372f12b0d9ff76c/58c618862bf9612dfdb24e83554f10ce/1790429318432/6d164448-52b5-4eed-bd62-50ada9e2959d
git update-ref -d refs/codex/turn-diffs/checkpoints/379f088b00ab0366e76f1f120385c5ee/8289d4019fc2ca6a01226351a90b7ed9/1790482854606/4c5da8b8-a70b-493e-8fe3-26da265ef493
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### 阶段 4：重建 Tag

注解 Tag 必须在新历史上重建，并同步更新发布文档中的 commit 引用：

```bash
git tag -d creator-agent-template-v0.1.0
git tag -a creator-agent-template-v0.1.0 -m "First deployable Creator Agent Framework template candidate"
git rev-parse HEAD          # 记录新 SHA，并写回发布文档
```

### 阶段 5：更新远端

```bash
git push --force-with-lease origin main
git push --force origin refs/tags/creator-agent-template-v0.1.0
```

### 阶段 6：验证与收尾

```bash
# 历史中不应再有任何运行快照
git log --all --oneline -- '*.tar.gz'

# 全仓库范围 secret scan 必须通过
python security/secret_scan.py <repo-root>

# 确认旧 blob 不可达
git cat-file -t e79e53188b8d86f19218b7191da2fb32b0fea780   # 期望报错
```

同时：更新 `GITHUB_DEPLOYMENT_ENTRY.md` 与 `RELEASE_NOTES_v0.1.0.md` 的 commit
引用；通知所有协作方重新克隆；核查并失效平台侧缓存与旧归档；把新 commit、Tag 与
制品 SHA-256 记入发布记录。

## 5. 风险与副作用

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 凭据仍然有效 | 历史重写不吊销凭据 | 阶段 0 必须先完成轮换 |
| 协作方历史分叉 | 强制更新远端后，旧克隆 `pull` 会产生分叉与回混 | 通知重新克隆；重写后禁止直接 `pull` |
| 旧 SHA 引用失效 | 文档、issue、CI 中的 commit 链接指向旧历史 | 阶段 4/6 同步更新文档与发布记录 |
| 平台侧副本残留 | fork、镜像、缓存、自动归档可能仍含旧对象 | 平台侧逐项核查；必要时联系平台支持 |
| 重写误伤 | `filter-repo` 会重写全部相关提交与 Tag | 阶段 1 先做 mirror 备份与 bundle |
| 不可逆 | 重写后本地回滚需依赖备份 | 备份保留至验证完成 |

## 6. 本轮未执行与授权要求

本轮**未执行**以下任一操作，且不得在未获授权时执行：

- 未删除 `new/workspace.tar.gz`（工作树与索引均保留原状）；
- 未 `git rm --cached`，未提交任何取消跟踪的变更；
- 未重写历史，未 `force push`，未触碰任何远端 ref；
- 未重建或删除 Tag。

历史重写是破坏性、需协调的操作，会改变公开 commit 身份并影响所有协作方，因此按
Phase 5.2 的边界要求，仅生成本报告供授权决策，不在本轮自行执行。

**立即可以安全执行、且建议优先执行的最小步骤**（不重写历史、可回退）：在授权后
先执行 `git rm --cached new/workspace.tar.gz` 并提交，使新克隆不再携带该文件；这
只是增量缓解，`ac5f81a`..`HEAD` 的历史与远端 Tag 仍然含该 blob，不能视为风险关闭。
