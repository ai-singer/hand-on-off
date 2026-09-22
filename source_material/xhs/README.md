# source_material/xhs/

XHS 数据采集层存储目录。

## 目录结构

```
source_material/xhs/
├── raw/                        原始采集结果（xhs-scraper-skill 直接输出）
├── {category}/
│   ├── video/                  视频笔记，每条独立存为 {note_id}.json
│   └── image_text/             图文笔记，每条独立存为 {note_id}.json
├── schema/
│   ├── xhs_normalized_schema.yaml   字段定义和来源映射（v2.0）
│   └── normalize.py                 Raw → 分类存储转换脚本（v2.0）
└── creator_registry/           博主注册表
```

当前已建立垂类目录：

- `finance/` — 商业财经
- `general/` — 通用/未分类

新增垂类时直接在 `xhs/` 下创建对应目录即可，normalize.py 会自动处理。

## 数据流

```
xhs-scraper-skill
  ↓ {raw_file}.json → raw/
  ↓
schema/normalize.py --category finance
  ↓
finance/video/{note_id}.json        → discovery_role: topic_discovery
finance/image_text/{note_id}.json   → discovery_role: knowledge_distillation
  ↓
source_collector / 内容生产流程
```

## 使用方法

```bash
cd /home/node/.openclaw/workspace/source_material/xhs/schema

# 将原始采集文件标准化并按垂类存储
python3 normalize.py ../raw/xhs_某博主_20260922.json finance

# 输出示例：
# ✓ 标准化完成
#   总计：50 条
#   video：12 条 → topic_discovery
#   image_text：38 条 → knowledge_distillation
#   评级：S=3 A=15 B=22 C=10
```

## 字段说明（v2.0 新增）

| 字段 | 说明 |
|------|------|
| `category` | 垂类标签，如 finance / travel / general |
| `content_type` | video 或 image_text |
| `discovery_role` | topic_discovery（视频）或 knowledge_distillation（图文） |
| `content_signal_score` | 素材价值评分 0–100（collected×0.35 + share×0.30 + comment×0.25 + liked×0.10） |
| `material_tier` | S/A/B/C 优先级分级 |
| `topic_candidate` | 由 Research Agent 填写（仅 video 类） |

## 素材优先级

| 级别 | 分数 | 处理方式 |
|------|------|----------|
| S | ≥ 75 | 优先生产池 |
| A | ≥ 50 | 研究池 |
| B | ≥ 25 | 趋势观察 |
| C | < 25 | 丢弃 |

## Schema 版本

当前: v2.0.0
定义: `schema/xhs_normalized_schema.yaml`
