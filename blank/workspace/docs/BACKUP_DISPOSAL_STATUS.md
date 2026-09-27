# Backup Disposal Status

```text
Sensitive Copies On Disk: 2 locations (1 file copy + 1 git mirror)
Securely Destroyed: NO
Reason: retained deliberately as the only evidence for identifying which
        credentials must be rotated. Must be destroyed AFTER rotation.
```

本文件记录 Phase 5.2.2 时点磁盘上仍持有已泄露材料的副本。为遵守"不输出敏感内容"的
约束，本文件只记录**路径、类型与体积**，不记录任何凭据内容、片段或 hash。

## 1. Inventory

### 1.1 隔离目录（存在）

```text
F:\Desktop\hand-on-off-pre-rewrite-backup\
```

| 条目 | 类型 | 体积 | 是否含敏感文件 | 是否已销毁 |
| --- | --- | ---: | --- | --- |
| `new-workspace.tar.gz` | 归档文件 | 20,123,338 B | **是** —— 即 Phase 5.1 审计确认含明文凭据、会话材料与嵌套 Git 历史的原始归档，由仓库工作树移出后存放于此 | **否** |
| `repo.git` | bare 镜像仓库 | 38.6 MB | **是** —— 重写前完整镜像；其 `main`、注解 Tag、远端跟踪 ref 以及 2 个 checkpoint tree ref 均可达同一敏感归档 | **否** |
| `strip_checkpoint_trees.py` | 脚本 | 3,325 B | 否 —— 仅含路径常量与 tree 处理逻辑，不含凭据 | 不适用 |

### 1.2 主工作仓库（干净）

```text
F:\Desktop\workspace_audit_handoff\
```

- 工作树中不存在 `new/workspace.tar.gz`；
- Git 历史、索引与全部 ref 均不可达该 blob（已在 Phase 5.2.1 验证并 GC）；
- 仓库根 secret scan：**PASS**。

### 1.3 其他副本（未发现）

| 检查 | 结果 |
| --- | --- |
| `F:\Desktop` 下 `hand-on-off*` 目录（深度 3） | 仅命中隔离目录本身，无其他克隆 |
| `F:\Desktop` 下 `*workspace.tar.gz` 文件（深度 5） | 仅命中隔离目录内的那一份 |
| 临时验证目录 | Phase 5.2.1/5.2.2 期间创建的探测目录已删除 |

无法核查的范围：本机其他磁盘路径、云同步目录、备份软件快照、外部主机，以及**任何
第三方克隆**（GitHub 仓库 `forks = 0`，因此平台侧无 fork 副本）。

## 2. Disposal Plan

**顺序要求：先轮换，后销毁。** 隔离副本与镜像镜像存在的唯一理由是让凭据所有者能够
确认"哪一条凭据对应哪个服务"，从而完成轮换。提前销毁会使轮换失去定位依据。

### 轮换完成后执行

| # | 目标 | 建议方式 |
| --- | --- | --- |
| 1 | `new-workspace.tar.gz` | 先覆盖写入再删除；若磁盘为 SSD 且要求严格，使用平台提供的安全擦除。不要只是移到回收站。 |
| 2 | `repo.git` | 整目录删除；不要保留 bundle。 |
| 3 | `strip_checkpoint_trees.py` | 可一并删除（已无用途）。 |
| 4 | 回收站 / 临时目录 | 清空，确认无残留副本。 |
| 5 | 本地工作仓库 | 执行一次 `git gc --prune=now` 作为收尾（当前已无可达敏感对象）。 |

### 销毁后复核

```powershell
# 1) 磁盘上不应再存在该归档
Get-ChildItem -Path F:\Desktop -Recurse -Depth 5 -Filter '*workspace.tar.gz' -File

# 2) 工作仓库对象库不应可达该 blob
git -C F:\Desktop\workspace_audit_handoff cat-file -t <旧blob>   # 期望报错

# 3) 仓库与仓库根均通过扫描
cd F:\Desktop\workspace_audit_handoff\blank\workspace
python security/secret_scan.py .
python security/secret_scan.py ..\..
```

## 3. Status

```text
Local Sensitive Copies: 2 (both in the quarantine directory)
Disposal: PENDING (blocked on credential rotation, by design)
```

磁盘侧风险在完成第 2 节之前保持 OPEN。与 GitHub 缓存暴露不同，这一项**完全由本机
所有者可控**，且不需要任何平台支持介入。
