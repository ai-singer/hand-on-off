# Cache Exposure Status

```text
Old SHA accessible: YES
Content downloadable: YES (full archive, not just metadata)
Repository State: CLEAN
Distribution State: NOT CLEAN
```

本文件记录 Phase 5.2.2 时点对 GitHub 侧"不可达对象仍可按 SHA 访问"问题的复核结果。
所有测试均为只读探测：下载类操作只发送 `HEAD` 请求或仅取对象元数据，未下载任何
凭据内容。

> 说明：本文档需要引用旧 commit SHA 才能记录探测过程。commit SHA 是公开的对象标识，
> 不是凭据；但仓库为公开仓库，**对外发布本文档前应评估是否需要脱敏**。

## 1. Test Method

| # | 测试 | 命令 / 请求 |
| --- | --- | --- |
| 1 | raw URL 直取 | `HEAD https://github.com/ai-singer/hand-on-off/raw/<旧commit>/new/workspace.tar.gz` 与 `HEAD https://raw.githubusercontent.com/ai-singer/hand-on-off/<旧commit>/new/workspace.tar.gz` |
| 2 | GitHub blob API | `GET https://api.github.com/repos/ai-singer/hand-on-off/git/blobs/<旧blob>` |
| 3 | 旧 commit API | `GET https://api.github.com/repos/ai-singer/hand-on-off/commits/<旧commit>` |
| 4 | clone / fetch 行为 | 空仓库 `git fetch origin <旧commit>`，随后对 blob 执行 `git cat-file -t` / `-s` |

## 2. Current Result

| # | 测试 | 结果 | 判定 |
| --- | --- | --- | --- |
| 1 | raw URL（`github.com/.../raw/`） | `200`，`Content-Length: 20123338` | **可下载** |
| 1 | raw URL（`raw.githubusercontent.com`） | `200`，`Content-Length: 20123338` | **可下载** |
| 2 | blob API | `200`，`size: 20123338`，`encoding: base64` | **内容可取得** |
| 3 | 旧 commit API | `200` | **对象存在** |
| 4 | `git fetch origin <旧commit>` | 退出码 0，抓取成功 | **可按 SHA 取回** |
| 4 | `git cat-file -t <旧blob>` | `blob` | **对象可实体化** |
| 4 | `git cat-file -s <旧blob>` | `20123338` | **内容完整** |

结论：强制推送使该提交从**分支与 Tag 视图**消失（全新 `git clone` 已看不到它），
但它**仍然可以从 GitHub 按 SHA 完整下载**，包括内含的明文凭据归档。GitHub 尚未对
这些不可达对象执行垃圾回收，缓存视图也仍然有效。

这与 Phase 5.2.1 的观测一致，说明**时间流逝没有自动解决该问题**：不能假定"过一段
时间就好了"。

## 3. Why a Force-Push Cannot Fix This

GitHub 官方文档（Removing sensitive data from a repository）说明：重写历史只能让提交
"从分支与 Tag 不可达"，而这些提交"可能仍可通过其 SHA-1 在缓存视图中访问"，并且
"只有联系 GitHub Support 才能永久移除缓存视图"。因此这是平台行为，不是本轮操作
失误。

同一文档还说明了一条对本事件最关键的政策：**GitHub Support 不会移除非敏感数据，
并且仅在判定"风险无法通过轮换受影响凭据来缓解"时，才协助移除敏感数据。**

也就是说：**轮换是官方预期的首要缓解手段**，Support purge 是兜底，不是第一步。

## 4. Recommended Action

| 优先级 | 动作 | 说明 |
| --- | --- | --- |
| 1 | **完成凭据轮换** | 见 `CREDENTIAL_ROTATION_FINAL_STATUS.md`。轮换完成后，即使旧归档仍可下载，其中凭据也已失效——这是唯一由所有者可控且必然有效的缓解。 |
| 2 | **联系 GitHub Support 清除缓存视图** | 请其失效缓存视图并执行站点侧 GC。按上述政策，需说明这些凭据无法或不宜仅靠轮换缓解（例如会话类材料已经泄露、或存在无法轮换的长期凭据）。请求文本模板见 `PHASE_5_2_1_CREDENTIAL_EXPOSURE_CLOSURE.md` 第 4 节。 |
| 3 | **删除并重建仓库** | 唯一能由所有者自行彻底清除缓存视图的方式，且是**破坏性操作**。 |

### 方案 3 可行性评估

```text
forks = 0    pull requests = 0    issues = 0
stars = 0    watchers = 0         branches = 1 (main)
```

没有任何 PR / issue / star / watcher / fork 需要保留，也没有 `refs/pull/*` 引用阻止
垃圾回收。因此"删除并重建"在当前仓库状态下的代价极低：重建后重新推送当前
`main` 与重建后的 Tag 即可。

**本任务不自行执行删除仓库**（按任务约束）。是否执行由仓库所有者决定。

## 5. Status

```text
Cache Exposure: OPEN
Blocking: GitHub 侧不可达对象仍可按 SHA 下载
Owner Action: 轮换优先；必要时 Support purge 或删除重建
```

该风险在仓库所有者完成第 4 节第 1–3 项之前不会被关闭。本轮只能确认并记录它。
