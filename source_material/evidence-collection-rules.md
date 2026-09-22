# 证据层采集规则 v1.1

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

来源分为两类：**知识来源**（机制解释、案例、研究）和**数据来源**（统计数字、财务指标）。

---

### 知识来源

用于：商业机制解释、企业案例、行业逻辑、管理研究

#### 企业一手资料

| 来源 | 网址 |
|------|------|
| 巨潮资讯网（A股法定信披） | https://www.cninfo.com.cn/ |
| 上交所信息披露 | http://www.sse.org.cn/disclosure/listed/notice/index.html |
| 深交所信息披露 | https://www.szse.cn/disclosure/ |
| 中国证监会 | https://www.csrc.gov.cn/ |
| 港交所披露易（简体） | https://sc.hkexnews.hk/TuniS/www.hkexnews.hk/index_c.htm |
| SEC 官网（美股/中概股） | https://sec.gov/ |

#### 研究与学术

| 来源 | 网址 |
|------|------|
| 麦肯锡全球研究院（中文） | https://www.mckinsey.com.cn/McKinsey/ |
| 哈佛商业评论中文版 | https://www.hbrchina.org/ |
| 中国知网 CNKI | https://www.cnki.net/ |
| Google Scholar | https://scholar.google.com/ |
| SSRN（金融经济学预印本） | https://www.ssrn.com/ |

---

### 数据来源

用于：统计数字、财务指标、行业规模、宏观经济数据

#### 国内政府统计

| 来源 | 网址 | 核心数据 |
|------|------|----------|
| 国家统计局 | https://www.stats.gov.cn/ | GDP、CPI、工业产值、零售、人口 |
| 国家统计局数据发布 | https://www.stats.gov.cn/sj/zxfb/index.html | 最新统计数据发布入口 |
| 中国人民银行 | https://www.pbc.gov.cn/ | 货币政策、社融、利率、金融数据 |
| 央行支付统计数据 | https://www.pbc.gov.cn/zhifujiesuansi/128525/128545/128643/index.html | 支付体系运行数据 |
| 商务部开放数据平台 | https://opendata.mofcom.gov.cn/front/data/topic?type=2 | 进出口、外资、消费、电商 |
| 工信数据 | https://www.miit.gov.cn/gxsj/ | 工业产业统计数据 |
| 财政部 | https://www.mof.gov.cn/ | 财政收支、债务、税收 |
| 国家发展改革委 | https://www.ndrc.gov.cn/ | 产业政策、价格监测 |
| 国家外汇管理局 | https://www.safe.gov.cn/ | 外汇储备、跨境资金流动 |
| 国家金融监督管理总局 | https://www.nfra.gov.cn/ | 银行保险业数据 |

#### 国际机构

| 来源 | 网址 | 核心数据 |
|------|------|----------|
| 世界银行 Open Data | https://data.worldbank.org/ | 全球发展指标、产业数据 |

#### 行业数据

| 来源 | 网址 | 用途 |
|------|------|------|
| Wind 经济数据库 | https://www.wind.com.cn/mobile/EDB/zh.html | 宏观经济数据库（部分免费） |

---

## 四、采集规则

### 优先采集内容

- 企业年报、季报中的财务数据和经营描述
- 政府统计局发布的行业数据
- 研究机构发布的行业报告核心结论
- 学术论文中的机制解释和实证结论

### 禁止采集

- 社交平台内容（小红书、微博、抖音等）
- 个人博主观点和预测
- 未注明来源的行业数据
- 投资建议、买卖推荐

### 引用要求

每条核心数据或事实陈述必须标注：

- 来源名称
- 来源网址
- 发布时间（如可获取）

---

## 五、验证规则

进入内容生产前必须满足：

- [ ] 来源存在且可追溯
- [ ] 数据有明确发布机构
- [ ] 关键数字有原始来源
- [ ] 未使用社交平台内容作为事实依据

### 失败路由

| 情况 | 处理 |
|------|------|
| 来源缺失 | 停止生产，返回 Research 流程 |
| 数据无法追溯 | 标记 pending，等待补充来源 |
| 来源质量不足 | 降级为参考，不作为核心依据 |
