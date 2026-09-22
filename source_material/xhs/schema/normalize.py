#!/usr/bin/env python3
"""
XHS Raw → Categorized Normalized Schema Converter v2.0
将 xhs-scraper-skill 的原始 JSON 转换为标准化格式，
按垂类和内容格式分类存储：
  source_material/xhs/{category}/{content_type}/{note_id}.json
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path


# ── 素材价值评分 ───────────────────────────────────────────────

def _to_int(val) -> int:
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def compute_signal_score(metrics: dict) -> float:
    """
    Content Signal Score（依据 source_strategy.md）：
      collected × 0.35 + share × 0.30 + comment × 0.25 + liked × 0.10
    使用 log1p 压缩原始计数，最终映射到 0–100。
    """
    collected = _to_int(metrics.get("collected_count", 0))
    share     = _to_int(metrics.get("share_count", 0))
    comment   = _to_int(metrics.get("comment_count", 0))
    liked     = _to_int(metrics.get("liked_count", 0))

    raw = (
        math.log1p(collected) * 0.35 +
        math.log1p(share)     * 0.30 +
        math.log1p(comment)   * 0.25 +
        math.log1p(liked)     * 0.10
    )
    # log1p(10000)*1.0 ≈ 9.21 作为满分基准
    score = min(raw / 9.21 * 100, 100.0)
    return round(score, 2)


def score_to_tier(score: float) -> str:
    """
    素材优先级分级（依据 source_strategy.md）：
    S ≥ 75 | A ≥ 50 | B ≥ 25 | C < 25
    """
    if score >= 75:
        return "S"
    elif score >= 50:
        return "A"
    elif score >= 25:
        return "B"
    else:
        return "C"


# ── 内容类型判断 ───────────────────────────────────────────────

def detect_content_type(note_card: dict) -> str:
    """
    判断笔记格式：
    - 含 video 字段且非空 → video
    - 否则 → image_text
    """
    if note_card.get("video") or note_card.get("type") == "video":
        return "video"
    return "image_text"


def content_type_to_role(content_type: str) -> str:
    """
    依据 source_strategy.md：
    - video → topic_discovery
    - image_text → knowledge_distillation
    """
    return "topic_discovery" if content_type == "video" else "knowledge_distillation"


# ── 单条标准化 ─────────────────────────────────────────────────

def normalize_note(note_card: dict, category: str, raw_ref: str = "") -> dict:
    """将 note_card 转换为 v2.0 标准化格式"""

    # 图片列表
    images = []
    for img in note_card.get("image_list", []):
        url = img.get("url_default") or img.get("url_pre") or ""
        if not url:
            for info in img.get("info_list", []):
                if info.get("image_scene") in ("WB_DFT", "WB_PRV"):
                    url = info.get("url", "")
                    break
        if url:
            images.append({
                "url": url,
                "width": img.get("width"),
                "height": img.get("height"),
                "file_id": img.get("file_id", ""),
            })

    post_id      = note_card.get("note_id", "")
    interact     = note_card.get("interact_info", {})
    user         = note_card.get("user", {})
    content_type = detect_content_type(note_card)
    role         = content_type_to_role(content_type)

    metrics = {
        "liked_count":     interact.get("liked_count", "0"),
        "collected_count": interact.get("collected_count", "0"),
        "comment_count":   interact.get("comment_count", "0"),
        "share_count":     interact.get("share_count", "0"),
    }

    score = compute_signal_score(metrics)
    tier  = score_to_tier(score)

    return {
        "platform":             "xiaohongshu",
        "category":             category,
        "content_type":         content_type,
        "discovery_role":       role,
        "creator": {
            "id":     user.get("user_id", ""),
            "name":   user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
        },
        "post_id":              post_id,
        "title":                note_card.get("title", ""),
        "text":                 note_card.get("desc", ""),
        "images":               images,
        "tags":                 [t.get("name", "") for t in note_card.get("tag_list", []) if t.get("name")],
        "metrics":              metrics,
        "content_signal_score": score,
        "material_tier":        tier,
        "topic_candidate":      None,   # 由后续 Research Agent 填写（video 类）
        "source_url":           f"https://www.xiaohongshu.com/explore/{post_id}",
        "collected_at":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raw_ref":              raw_ref,
    }


# ── 批量处理 ───────────────────────────────────────────────────

def normalize_batch(raw_file: Path, xhs_base: Path, category: str) -> dict:
    """
    批量转换一个 raw JSON 文件，按 category/content_type 分目录存储。
    每条笔记独立存为 {note_id}.json。

    返回统计信息。
    """
    with open(raw_file, encoding="utf-8") as f:
        raw_notes = json.load(f)

    stats = {"total": 0, "video": 0, "image_text": 0, "tiers": {"S": 0, "A": 0, "B": 0, "C": 0}}

    for note_card in raw_notes:
        normalized = normalize_note(
            note_card,
            category=category,
            raw_ref=f"raw/{raw_file.name}",
        )
        content_type = normalized["content_type"]
        post_id      = normalized["post_id"]
        tier         = normalized["material_tier"]

        out_dir = xhs_base / category / content_type
        out_dir.mkdir(parents=True, exist_ok=True)

        out_file = out_dir / f"{post_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)

        stats["total"]             += 1
        stats[content_type]        += 1
        stats["tiers"][tier]       += 1

    return stats


# ── CLI 入口 ───────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="XHS Normalizer v2.0")
    parser.add_argument("raw_file", help="原始 JSON 文件路径")
    parser.add_argument("category", help="垂类标签，如 finance / travel / general")
    parser.add_argument(
        "--xhs-base",
        default="/home/node/.openclaw/workspace/source_material/xhs",
        help="xhs 目录根路径",
    )
    args = parser.parse_args()

    raw_file = Path(args.raw_file)
    xhs_base = Path(args.xhs_base)

    print(f"处理文件：{raw_file}")
    print(f"垂类：{args.category}")
    print(f"输出根目录：{xhs_base}")
    print()

    stats = normalize_batch(raw_file, xhs_base, args.category)

    print(f"✓ 标准化完成")
    print(f"  总计：{stats['total']} 条")
    print(f"  video：{stats['video']} 条 → topic_discovery")
    print(f"  image_text：{stats['image_text']} 条 → knowledge_distillation")
    print(f"  评级：S={stats['tiers']['S']} A={stats['tiers']['A']} B={stats['tiers']['B']} C={stats['tiers']['C']}")
    print()
    print(f"输出目录：")
    print(f"  {xhs_base}/{args.category}/video/")
    print(f"  {xhs_base}/{args.category}/image_text/")
