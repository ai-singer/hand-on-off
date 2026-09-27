# Creator Agent Framework Phase 5.2.1 - Credential Exposure Closure

```text
Repository-side Closure: COMPLETE
Credential Exposure Closure: NOT CLOSED
Blocking Item: exposed credentials are not rotated, and the purged archive
               is still retrievable from GitHub by direct SHA-1
```

本轮完成 Phase 5.2 遗留的仓库侧全部收尾动作：取消跟踪、历史重写、Tag 重建、远端
强制更新与部署入口修订。但**凭据暴露本身并未关闭**，原因是两项本阶段无法完成的工作：
服务端凭据轮换，以及 GitHub 侧对不可达对象的清理。第 4 节给出实测证据。

## 1. Actions Taken

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | `git rm --cached new/workspace.tar.gz` | 风险文件不再被跟踪 |
| 2 | 将本地归档移出仓库至隔离目录 | 工作树不再持有任何明文凭据 |
| 3 | `git filter-repo --path new/workspace.tar.gz --invert-paths` | 从全部 62 个可达提交中清除该 blob |
| 4 | 清理 `refs/codex/turn-diffs/checkpoints/*` 两个仅本地 tree ref | 消除 `push --mirror` 的再泄露通道 |
| 5 | `git reflog expire` + `git gc --prune=now` | 本地对象库中该 blob 已不可达 |
| 6 | 修订 `GITHUB_DEPLOYMENT_ENTRY.md` | 部署归档改为可部署子树导出；整树归档需先通过仓库根扫描 |
| 7 | 修订 `RELEASE_NOTES_v0.1.0.md` | Commit/Baseline 更新为重建后的真实 SHA |
| 8 | 为 Phase 5.2 报告加"已被取代"标注 | 保留原始证据，不改写历史结论 |
| 9 | `git push --force origin main` + `--force` Tag | 远端 `main` 与 Tag 指向清理后的历史 |

未改动：蒸馏核心、Plugin Interface、Workflow 架构、Runtime 逻辑、任何业务行为。
未执行：任何凭据的读取、复制、测试或轮换。

### 风险文件处置

```text
原路径   : new/workspace.tar.gz（blob e79e53188b8d86f19218b7191da2fb32b0fea780）
SHA-256  : e3513e29fcbbbdb43f31ff0a536e88c22fe22ac54fb2ec1a5a732ee7a4bf431d
现状     : 已从仓库工作树、Git 历史与远端 ref 中移除
隔离位置 : F:\Desktop\hand-on-off-pre-rewrite-backup\new-workspace.tar.gz
镜像备份 : F:\Desktop\hand-on-off-pre-rewrite-backup\repo.git（重写前完整镜像）
```

隔离副本与镜像备份**刻意保留**：它们是凭据所有者确认"哪一条凭据需要轮换"的唯一
依据。**轮换完成后必须安全销毁这两者。**

### 提交映射（重写前 → 重写后）

| 提交 | 重写前 | 重写后 |
| --- | --- | --- |
| `feat: build creator agent framework foundation` | `cfb38a8` | `a6111aefc4b7be9024be38207879ec91e9595c2f` |
| `fix: harden creator agent deployment runtime` | `033da3c` | `d3cf40faca4789796b60dbe2e9d81f454da7a780` |
| `docs: add release notes and github deployment entry` | `c3174cd` | `7b73035eebcb055e347bbad4a0526447e809f78d` |
| `fix: add plugin schema validation and credential audit` | `d810e01` | `ba70f7dfa198b021c0fd0510d9b9acbb2113c7b4` |
| `security: remediate credential exposure...` | `c2ee0e6` | `b4456d4a6a1d513334afe33ca020a6ce63d5e7ba` |
| `snapshot: workspace 2026-09-22` | `ac5f81a` | **已删除**（清除该文件后成为空提交） |
| Tag `creator-agent-template-v0.1.0` | 对象 `c9ad5b5` → `c3174cd` | 对象 `ca19e35` → `7b73035` |
| `main`（当前） | `c3174cd` | `0fcd02b7af361e8b025dd4ac563571c21420ddca` |

## 2. Verification Evidence

| 检查 | 命令 / 方式 | 结果 |
| --- | --- | --- |
| 本地 blob 已消失 | `git cat-file -t e79e5318…` | `fatal: could not get object info` |
| 本地无 ref 持有归档 | 遍历全部 ref 的 `git ls-tree -r` | 0 命中 |
| 本地历史已清除 | `git log --all -- new/workspace.tar.gz` | 空 |
| 工作区扫描 | `python security/secret_scan.py .` | **PASS**，0 发现 |
| 单元测试 | `python -m unittest discover -s tests -v` | **PASS**，Ran 21 tests, OK |
| 编译检查 | `python -m compileall .` | **PASS** |
| 远端分支 | 全新 `git clone` 后 `git ls-files` | 无 `new/workspace.tar.gz` |
| 远端历史 | 全新 clone 后 `git log --all -- new/workspace.tar.gz` | 空 |
| **发布分发面** | 下载 GitHub Tag 源码归档并用扫描器检查 | **归档从约 39 MB 降至 0.4 MB**，成员中只剩 3 个已确认干净的归档；扫描 **PASS** |
| 旧 commit 是否仍可达 | GitHub API `GET /commits/c3174cd…` | **仍可达**（见第 4 节） |
| 旧 blob 是否仍可达 | GitHub API `GET /git/blobs/e79e5318…` | **仍可达，size=20123338**（见第 4 节） |

结论：**分支与 Tag 视图、以及发布用 Tag 源码归档都已干净**；但按 SHA 直取仍然可行。

## 3. Rotation Checklist（凭据所有者执行）

以下凭据全部已被判定为"已泄露"（曾位于公开仓库 `main` 与 Tag 中）。仓库清理**不能**
替代轮换。标识信息仅为定位用，不含任何凭据值。

| ID | 类型 | 归档内定位（隔离副本中） | 服务端动作 | 完成后如何验证 |
| --- | --- | --- | --- | --- |
| R1 | `sk-` 形式 API Token（2 处同值） | `workspace/phanthy_poller.py`、`workspace/memory/2026-09-22-phanthy-publish-debug.md` | 在签发方 revoke 并重新签发 | 旧值调用返回 401/403 |
| R2 | API Key A | `workspace/credentials.json` → `$.agents[0].api_key` | 轮换 | 旧值鉴权失败 |
| R3 | API Key B | `workspace/credentials.json` → `$.agents[1].api_key` | 轮换 | 旧值鉴权失败 |
| R4 | GitHub 凭据 | `workspace/.env` → `GITHUB_KEY` | 在 GitHub Settings 撤销该 token 并重新签发 | 旧 token 调 API 返回 401 |
| R5 | Cookie / 会话材料 | `workspace/xiaohongshu_cookies.txt` | 目标账号退出全部会话（或改密）后重新登录 | 旧 Cookie 请求返回登录页或 401 |
| R6 | 未分类敏感赋值 | `agent_package/tools/source_collector/collectors/bilibili/auth.py`（2 处）、`agent_package/tools/source_collector/secrets` | 先人工确认服务归属，再按所属服务轮换 | 按具体服务确认旧值失效 |

执行顺序与注意事项：

1. **R4 优先注意副作用**：`GITHUB_KEY` 可能是本机 `git` 推送使用的同一凭据。撤销后
   本机必须重新认证才能继续 `push`，请先确认已掌握重新签发的途径。
2. 其余凭据彼此独立，可并行轮换。
3. 每条凭据轮换后立即执行"验证"列，确认旧值确实失效；仅删除文件不算完成。
4. 全部轮换完成后，安全销毁以下位置：
   - `F:\Desktop\hand-on-off-pre-rewrite-backup\new-workspace.tar.gz`
   - `F:\Desktop\hand-on-off-pre-rewrite-backup\repo.git`（重写前镜像）
   - 任何其他克隆副本
5. 轮换完成后重新执行 `python security/secret_scan.py <repo-root>` 作为收尾确认。

## 4. Critical Residual: GitHub 按 SHA 仍可取得已清除的归档

强制推送**没有**让不可达对象立刻消失。实测（`2026-09-27`，公开仓库）：

```text
GET https://api.github.com/repos/ai-singer/hand-on-off/commits/c3174cd…   -> 200 可达
GET https://api.github.com/repos/ai-singer/hand-on-off/git/blobs/e79e5318… -> 200 size=20123338
HEAD https://github.com/ai-singer/hand-on-off/raw/c3174cd…/new/workspace.tar.gz               -> 200 len=20123338
HEAD https://raw.githubusercontent.com/ai-singer/hand-on-off/c3174cd…/new/workspace.tar.gz    -> 200 len=20123338
git fetch origin c3174cd53a7b9ac7bfa8ddab07212eb76e258245                                     -> 成功
```

即：**该归档目前仍可通过旧 SHA 直接下载**。这是 GitHub 的既定行为，不是本轮操作
失误——GitHub 官方文档明确说明，重写历史只能让提交"从分支与 Tag 不可达"，而这些
提交"可能仍可通过其 SHA-1 在缓存视图中访问"，并且"只有联系 GitHub Support 才能永久
移除缓存视图"。

仓库现状对该问题的处置很有利：

```text
forks=0  pull requests=0  issues=0  stars=0  watchers=0  branches=1 (main)
```

没有任何 `refs/pull/*` 引用阻止垃圾回收，也没有 fork 需要清理。

### 可选的彻底清理路径

| 方案 | 说明 | 代价 |
| --- | --- | --- |
| A. 依赖轮换（GitHub 官方推荐的首要缓解） | GitHub 政策明确：**仅当风险无法通过轮换受影响凭据缓解时**，Support 才协助移除敏感数据。因此轮换是预期的主路径 | 旧归档理论上仍可下载，但其中凭据已失效 |
| B. 联系 GitHub Support 清除缓存视图 | 请其移除缓存视图与 PR 引用并执行站点侧 GC | 需 Support 判定轮换无法缓解；无时效保证 |
| C. 删除并重建仓库 | 当前无 PR / issue / star / watcher / fork，**实质上没有需要保留的仓库侧协作数据**，这是唯一能由仓库所有者自行彻底清除缓存视图的方式 | 仓库创建时间、star 等元数据重置；所有协作者需重新克隆 |

建议顺序：**先完成第 3 节轮换（A）**，再视残余要求决定是否执行 B 或 C。轮换完成后，
即使旧归档仍可下载，其中的凭据也已无法使用。

### B 方案可直接使用的 Support 请求文本

```text
Subject: Request to purge cached views and unreachable objects for
         ai-singer/hand-on-off

Repository: https://github.com/ai-singer/hand-on-off (public)

A workspace snapshot containing plaintext API tokens, API keys, a GitHub
credential and session cookies was committed in error and has since been
purged from all branches and tags using git filter-repo followed by a
forced push. The credential values in question have been revoked and
rotated.

The following objects are now unreachable from any branch or tag but are
still retrievable by their SHA-1 hashes:

  commit: c3174cd53a7b9ac7bfa8ddab07212eb76e258245
  blob:   e79e53188b8d86f19218b7191da2fb32b0fea780
          (new/workspace.tar.gz, 20123338 bytes)

Please invalidate any cached views for these objects and run garbage
collection on the repository. The repository has no forks, no pull
requests and no issues.
```

## 5. Remaining Risk

| ID | 风险 | 等级 | 状态 |
| --- | --- | --- | --- |
| R-01 | 已识别凭据与会话**尚未轮换**，其中部分可能仍然有效 | **HIGH** | OPEN — 需凭据所有者执行第 3 节 |
| R-02 | 已清除的归档仍可按旧 SHA 从 GitHub 下载（含明文凭据） | **HIGH** | OPEN — 见第 4 节 A/B/C |
| R-03 | 本机隔离副本与重写前镜像仍持有同一份明文凭据 | MEDIUM | OPEN — 轮换后须销毁 |
| R-04 | 扫描器基于规则，未知格式秘密与二进制内嵌凭据可能漏检 | LOW | ACCEPTED |
| R-05 | 仓库根的其余三个历史快照归档经扫描干净，但仍属"不透明运行快照"，是否符合长期跟踪策略未决 | LOW | DOCUMENTED |

已关闭：

- ~~风险文件被跟踪~~ → 已取消跟踪并移出工作树；
- ~~风险文件存在于 Git 历史~~ → 已从全部本地与远端可达提交中清除；
- ~~风险文件存在于发布 Tag~~ → Tag 已重建，远端已更新；
- ~~发布入口持续分发含凭据的整树归档~~ → 入口已改为可部署子树导出，整树归档需先扫描；
- ~~仅本地 checkpoint ref 保留该 blob~~ → 已清除并 GC。
- ~~远端 Tag 是否存在未验证~~ → 已确认存在并已更新为重建后的 Tag。

## 6. Next Step

1. **（凭据所有者，最高优先）** 执行第 3 节轮换清单，并逐条验证旧值失效。
2. 轮换完成后销毁隔离副本与重写前镜像（第 3 节第 4 步）。
3. 视残余要求决定第 4 节方案 B（联系 Support）或 C（删除并重建仓库）。
4. 通知所有协作方**重新克隆**：历史已重写，旧克隆不得 `pull`，否则会回混旧历史。
5. 回到 **Phase 5.3 Runtime Configuration Stabilization**：S-02（配置交叉验证）、
   S-03（部署包与测试声明矛盾），以及 S-05~S-08、S-10。

## 7. Harness / Rule Distillation Review

```text
PROMOTE_TO_VERIFIER
```

本轮再次验证了一个应当下沉为发布验证器的教训：**"重写历史"不等于"数据已消失"**。
secret scan 只能证明当前树干净，无法证明分发面干净。建议把两项检查固化为发布 Gate：

1. 发布前对**整树 Tag 归档**范围执行扫描，而不只是工作区；
2. 发布后用**旧 SHA 可达性探测**（`raw.githubusercontent.com/<owner>/<repo>/<old-sha>/<path>`）
   确认前一次发布的敏感对象确实不可取得，而不是假定重写已生效。
