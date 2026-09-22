# source_material/xhs/

XHS 数据采集层存储目录。

## 目录结构

```
source_material/xhs/
├── raw/                        原始采集结果（xhs-scraper-skill 直接输出）
├── {category}/
│   ├── image_text/
│   │   └── {note_id}.json      图文笔记（元数据 + 正文 + 图片 + 流量数据）
│   └── video/
│       └── {note_id}/
│           ├── meta.json        笔记元数据 + 流量数据
│           ├── transcript.json  完整字幕（含时间戳）
│           └── frames/
│               └── {timestamp}/
│                   ├── frame.jpg         静态图片帧
│                   └── transcript.json   该时间段对应字幕
├── schema/
│   ├── xhs_normalized_schema.yaml   字段定义（v2.1）
│   └── normalize.py                 Raw → 分类存储转换脚本
└── creator_registry/           博主注册表
```

当前垂类目录：

- `finance/` — 商业财经
- `general/` — 通用/未分类

## 数据流

```
xhs-scraper-skill
  ↓ {raw_file}.json → raw/
  ↓
schema/normalize.py --category finance
  ↓
finance/image_text/{note_id}.json     → discovery_role: knowledge_distillation
finance/video/{note_id}/meta.json     → discovery_role: topic_discovery
  ↓ （视频需进一步处理）
finance/video/{note_id}/transcript.json   ← ASR / 内嵌字幕
finance/video/{note_id}/frames/{ts}/      ← 静态帧截取
  ↓
Research Agent / 内容生产流程
```

## 使用方法

### 标准化原始数据

```bash
cd /home/node/.openclaw/workspace/source_material/xhs/schema
python3 normalize.py ../raw/xhs_某博主_20260922.json finance
```

### 视频处理规则

| 项目 | 规则 |
|------|------|
| 字幕来源 | 优先内嵌字幕（.srt/.vtt），无则使用 Whisper base 模型 ASR |
| 语言 | 中文（zh） |
| 静态帧检测阈值 | 连续 ≥ 3 秒相同画面 |
| 截取时机 | 静态段中间帧 |
| 图片格式 | JPEG，最宽 1280px |

### frames/{timestamp}/transcript.json 格式

```json
{
  "frame_time": "00:00:32",
  "segment_start": "00:00:30",
  "segment_end": "00:00:45",
  "segments": [
    { "index": 12, "start": "00:00:30", "end": "00:00:34", "text": "..." }
  ],
  "full_text": "拼接后的完整文本段落"
}
```

## 字段说明（v2.1）

| 字段 | 说明 |
|------|------|
| `category` | 垂类标签，如 finance / travel / general |
| `content_type` | video 或 image_text |
| `discovery_role` | topic_discovery（视频）或 knowledge_distillation（图文） |
| `content_signal_score` | 素材价值评分 0–100 |
| `material_tier` | S/A/B/C 优先级（S≥75 / A≥50 / B≥25 / C<25） |
| `video_processing.status` | pending / transcribed / frames_extracted / complete |

## Schema 版本

当前: v2.1.0
定义: `schema/xhs_normalized_schema.yaml`
