# 证据层采集规则与存储结构 v1.0

更新时间：2026-09-22

---

## 一、定位

证据层（Evidence Layer）是内容生产的事实基础。

职责：

- 为选题提供可验证的事实、数据和机制解释
- 不负责发现用户需求（由 Discovery Layer 负责）
- 所有进入内容生产的事实必须追溯至本层来源

---

## 二、来源优先级

```
企业官方披露（年报/公告/招股书）
> 政府统计数据
> 国际权威机构数据
> 专业研究机构报告
> 学术论文
> 媒体报道（仅用于线索发现，不作为事实依据）
```

社交平台内容禁止进入证据层。

---

## 三、已验证官方数据源

### 3.1 企业一手资料

| 来源 | 网址 | 用途 |
|------|------|------|
| 巨潮资讯网 | https://www.cninfo.com.cn/ | A股法定信披平台，年报/季报/公告 |
| 上海证券交易所 | https://www.sse.com.cn/ | 沪市公告、财报披露 |
| 上交所信息披露 | http://www.sse.org.cn/disclosure/listed/notice/index.html | 上市公司公告直接入口 |
| 深圳证券交易所 | https://www.szse.cn/ | 深市公告、财报披露 |
| 深交所信息披露 | https://www.szse.cn/disclosure/ | 深市信披直接入口 |
| 证监会 | https://www.csrc.gov.cn/ | 监管文件、问询函、行政处罚 |
| 港交所披露易（简体） | https://sc.hkexnews.hk/TuniS/www.hkexnews.hk/index_c.htm | 港股年报、招股书、公告 |
| 港交所官网 | https://www.hkex.com.hk/ | 上市规则、市场数据 |
| SEC 官网 | https://sec.gov/ | 美股及中概股全部披露文件（10-K / 20-F） |

### 3.2 宏观经济与政府统计

| 来源 | 网址 | 核心数据 |
|------|------|----------|
| 国家统计局 | https://www.stats.gov.cn/ | GDP、CPI、工业产值、零售、人口 |
| 国家统计局数据发布 | https://www.stats.gov.cn/sj/zxfb/index.html | 最新统计数据发布入口 |
| 中国人民银行 | https://www.pbc.gov.cn/ | 货币政策、社融、利率、金融数据 |
| 央行支付统计数据 | https://www.pbc.gov.cn/zhifujiesuansi/128525/128545/128643/index.html | 支付体系运行数据 |
| 商务部 | https://www.mofcom.gov.cn/ | 进出口、外资、消费、电商 |
| 商务部开放数据平台 | https://opendata.mofcom.gov.cn/front/data/topic?type=2 | 结构化统计数据 |
| 工业和信息化部 | https://www.miit.gov.cn/ | 工业产业政策 |
| 工信数据 | https://www.miit.gov.cn/gxsj/ | 工信部统计数据直接入口 |
| 财政部 | https://www.mof.gov.cn/ | 财政收支、债务、税收数据 |
| 国家发展改革委 | https://www.ndrc.gov.cn/ | 产业政策、价格监测 |
| 国家外汇管理局 | https://www.safe.gov.cn/ | 外汇储备、跨境资金流动 |
| 国家金融监督管理总局 | https://www.nfra.gov.cn/ | 银行保险业数据、监管政策 |

### 3.3 国际权威数据

| 来源 | 网址 | 核心数据 |
|------|------|----------|
| 世界银行 Open Data | https://data.worldbank.org/ | 全球发展指标、产业数据 |

### 3.4 行业研究与专业机构

| 来源 | 网址 | 用途 |
|------|------|------|
| Wind 金融数据 | https://www.wind.com.cn/portal/zh/WFT/index.html | 行业研报、金融终端（需账号） |
| Wind 经济数据库 | https://www.wind.com.cn/mobile/EDB/zh.html | 宏观经济数据库（部分免费） |
| 麦肯锡全球研究院（中文） | https://www.mckinsey.com.cn/McKinsey/ | 行业趋势、商业模式研究 |

### 3.5 学术与商业研究

| 来源 | 网址 | 用途 |
|------|------|------|
| 中国知网 CNKI | https://www.cnki.net/ | 中文学术论文、行业研究 |
| 哈佛商业评论中文版 | https://www.hbrchina.org/ | 商业管理案例与分析 |
| Google Scholar | https://scholar.google.com/ | 全球学术论文 |
| SSRN | https://www.ssrn.com/ | 金融经济学预印本论文 |

---

## 四、采集规则

### 4.1 采集对象

优先采集：

- 企业年报、季报中的财务数据和经营描述
- 政府统计局发布的行业数据
- 研究机构发布的行业报告摘要和核心结论
- 学术论文中的机制解释和实证结论

### 4.2 禁止采集

- 社交平台内容（小红书、微博、抖音等）
- 个人博主观点和预测
- 未注明来源的行业数据
- 投资建议、买卖推荐

### 4.3 引用要求

每条核心数据或事实陈述必须标注：

- 来源名称
- 来源网址
- 发布时间（如可获取）

---

## 五、存储结构

```
source_material/
├── evidence/
│   ├── finance/
│   │   ├── company/        企业年报、公告、招股书摘要
│   │   ├── macro/          宏观经济数据
│   │   ├── industry/       行业研究报告
│   │   └── academic/       学术论文和商业研究
│   └── {other_category}/
│       └── ...
```

### 单条证据文件格式

```json
{
  "evidence_id": "唯一ID",
  "category": "finance",
  "sub_category": "company | macro | industry | academic",
  "source_name": "来源名称",
  "source_url": "来源网址",
  "published_at": "发布时间（ISO8601）",
  "collected_at": "采集时间（ISO8601）",
  "title": "文档标题",
  "key_facts": ["核心事实1", "核心事实2"],
  "data_points": [
    {
      "metric": "指标名称",
      "value": "数值",
      "unit": "单位",
      "period": "统计周期"
    }
  ],
  "related_topics": ["关联选题ID"],
  "verification_status": "verified | pending | rejected"
}
```

---

## 六、使用规则

### 进入内容生产前必须满足

- [ ] 来源存在且可追溯
- [ ] 数据有明确发布机构
- [ ] 关键数字有原始来源
- [ ] 未使用社交平台内容作为事实依据
- [ ] verification_status = verified

### 失败路由

| 情况 | 处理 |
|------|------|
| 来源缺失 | 停止生产，返回 Research 流程 |
| 数据无法追溯 | 标记为 pending，等待补充来源 |
| 来源质量不足 | 降级为参考，不作为核心依据 |
