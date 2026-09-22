# hand-on-off

小林说 Phanthy Creator Agent 的素材采集与内容生产基础设施。

## 定位

小林说是商业财经知识型虚拟博主。

内容生产不依赖热门内容搬运，而是基于：

```
用户真实问题（Discovery）
+ 专业可靠证据（Evidence）
+ 商业机制解释
↓
可验证的知识内容
```

## 仓库结构

```
source_material/
├── evidence-collection-rules.md   证据层采集规则与官方数据源分类
└── xhs/
    ├── README.md                   小红书素材采集说明
    ├── schema/
    │   ├── xhs_normalized_schema.yaml   数据字段定义（v2.0）
    │   └── normalize.py                 原始数据标准化脚本
    ├── finance/
    │   ├── video/                  财经视频笔记（→ 选题发现）
    │   └── image_text/             财经图文笔记（→ 知识蒸馏）
    └── general/
        ├── video/
        └── image_text/
```

## 素材双层架构

| 层 | 来源 | 作用 |
|----|------|------|
| Discovery Layer | 小红书等社交平台 | 发现用户真实问题，不作为事实依据 |
| Evidence Layer | 企业年报、政府统计、学术研究 | 提供可验证的事实与数据 |

具体来源清单见 [evidence-collection-rules.md](source_material/evidence-collection-rules.md)。
