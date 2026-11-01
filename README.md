# 公考真题知识库 Skill · gongkao-zhenti-knowledge

> 国考（2000–2026）· 广东省考（2003–2026）· 湖北省考（2008–2026）
> **行测 11 393 题 + 申论 414 题**，含答案与解析；考点体系与 [gongkao-huasheng13（花生十三技巧）](../) 完全对齐。

一个可按**考点 / 题型 / 年份 / 省份**精准检索、支持**多关键词全文匹配**的公考真题知识库，作为 Agent Skill 直接安装到豆包工作模式（或其他支持 `SKILL.md` 的宿主），与花生十三技巧 skill 组成 **考点 → 真题 → 技巧** 的闭环。

```
用户问「资料分析基期量怎么考」
        │
        ├── 本 skill：历年基期量真题 436 道、命题规律、原题 + 答案 + 解析
        └── gongkao-huasheng13：ABRX 体系、假设分配法、截位直除的解题步骤
```

---

## 一、它解决什么问题

| 痛点 | 本库的做法 |
|---|---|
| 想按考点刷真题，但题库和考点体系对不上 | 每题都带 `模块/题型/考点编码`，考点命名 100% 沿用花生十三体系（不自定义）；另有 **185 个三级子考点**（两期比重差、最不利构造、翻译推理…） |
| 只记得几个零散词，找不到题 | `search.py` 支持多关键词 AND/OR、`--sub` 子考点、`--fuzzy` 同义词+2-gram 模糊匹配，也可纯文本 grep |
| 需要"原题 + 答案 + 解析"一起给 | 每题保留题干、A–D 选项、正确答案、原解析节选、来源文件 |
| 同一道题在国考三卷、多年重复出现 | 同题折叠：默认只出主记录，并告诉你"这题还考过哪几年" |
| 图形推理、资料分析图表题看不到图 | 2 332 张按题号自动裁切的原题配图，Markdown 内嵌 + 检索结果给出路径 |
| 想知道"这个考点到底怎么考" | 48 个考点文件内含题量趋势、地区差异、近六年分布、典型原题 |
| 讲了真题却讲不了技巧 | 与花生十三 skill 联动映射表，精确到 `文件#章节` |
| 想直接刷一套 / 记错题 | `paper.py` 按考点配比组卷（含答案页），`wrongbook.py` 记录错题并按四类错因出复习报告 |

---

## 二、数据规模

| 维度 | 数值 |
|---|---|
| 行测试卷 | 98 套（国考 47 / 广东 32 / 湖北 19） |
| 行测题目 | 11 393 题（含答案 8 497 题；同题变体 1 136 条已折叠） |
| 申论试卷 | 105 套 |
| 申论小题 | 419 题（含参考答案） |
| 考点 | 48 个有题考点，覆盖 6 大模块、49 个编码；三级子考点 193 个标签 |
| 原题配图 | 2 332 张（图形推理的图形、图表型资料分析材料） |
| 年份跨度 | 2000–2026（含 2026 国考、广东、湖北最新卷） |

模块分布：判断推理 29.2%、言语理解 24.2%、常识判断 19.5%、资料分析 14.9%、数量关系 12.2%。

> 答案缺失 25.4%（2 896 题）——全部集中在广东 2004–2021 等**原答案 PDF 为扫描件无文字层**的试卷，题目与考点照常可用，答案如实标"暂缺"，绝不编造。明细见 [`docs/coverage.md`](docs/coverage.md)。

---

## 三、目录结构

```
gongkao-zhenti-knowledge/
├── SKILL.md                      # 宿主加载入口（frontmatter: name/description）
├── README.md
├── LICENSE                       # MIT
├── CHANGELOG.md
├── skill.json                    # 元数据镜像（部分平台读取）
├── docs/
│   ├── kaodian-taxonomy.md       # 考点体系全表（三级）+ 与花生十三的对齐映射
│   ├── data-spec.md              # 字段规范与数据口径
│   ├── coverage.md               # 覆盖范围与已知缺口
│   ├── install.md                # 豆包 / 通用宿主 / 本地 CLI 安装
│   └── eval.md                   # 评测集与指标口径
├── references/
│   ├── 00-index.md               # 总索引（考点→文件、试卷→文件）
│   ├── 01-命题规律总览.md         # 分省分年模块矩阵、高频考点 TOP20、题型变迁
│   ├── kaodian/                  # 48 个考点文件：规律 + 原题 + 答案 + 解析
│   ├── juan/                     # 98 套行测原卷（题目 + 答案 + 考点）
│   ├── shenlun/                  # 106 套申论原卷（材料 + 题目 + 参考答案）
│   └── images/                   # 2 332 张原题配图（自动裁切）
├── data/
│   ├── xingce.jsonl              # 行测题库
│   ├── shenlun.jsonl             # 申论题库
│   ├── search-index.tsv          # 检索索引（短行，适合 grep）
│   └── stats.json
├── scripts/
│   ├── search.py                 # 检索 CLI（考点/子考点/多关键词/模糊，零依赖）
│   ├── paper.py                  # 组卷：按考点轮转抽样，输出试卷 + 答案页
│   ├── wrongbook.py              # 错题本：记录 / 归因 / 复盘报告
│   └── selfcheck.py              # 数据自检
├── tests/
│   ├── test_skill.py             # 检索与数据一致性冒烟测试
│   ├── test_tools.py             # 组卷 / 错题本测试
│   ├── eval.py                   # 分类准确率评测
│   └── gold*.jsonl               # 评测集（强标注 / 弱标注两档）
├── .github/workflows/ci.yml      # CI：自检 + 测试 + 评测
└── tools/pipeline/               # 从原始 PDF 复现本库的采集流水线
```

---

## 四、快速开始

### 1) 安装

- **豆包工作模式**：上传整个目录（或压缩包），平台读取 `SKILL.md` 的 `name` / `description` 完成注册；建议同时安装 `gongkao-huasheng13`。详见 [`docs/install.md`](docs/install.md)。
- **Claude / DSH 等**：`cp -r gongkao-zhenti-knowledge ~/.claude/skills/`（或 `~/.dsh/skills/`）。

### 2) 命令行检索（仅需 Python 3.9+ 标准库）

```bash
# 按考点 + 省份
python scripts/search.py --kaodian ZL-BASE --prov 国考 --limit 3

# 多关键词组合定位（AND）——"零散知识点"场景
python scripts/search.py --kw 黑土地 --kw 保护 --kw 粮仓

# 任一词命中（OR）
python scripts/search.py --any 新质生产力 低空经济 未来产业

# 某年某省某模块
python scripts/search.py --year 2024 --prov 广东 --module 资料分析 --limit 10

# 按 ID 取完整题目（含解析）
python scripts/search.py --id GK-2025-fs-X010 --full

# 三级子考点（最精准）：两期比重差 / 最不利构造 / 翻译推理 …
python scripts/search.py --sub 两期比重差 --prov 国考

# 模糊检索：同义词 + 2-gram，换说法/错字也能中
python scripts/search.py --kw 占比 --kw 提高 --fuzzy

# 组卷：按考点轮转抽样，输出试卷 + 答案页
python scripts/paper.py --module 资料分析 --count 20 --prov 国考 --years 2019-2026 --out out/套卷.md

# 错题本：记录 → 归因 → 复盘报告
python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟 --note "两期比重差算成增长率"
python scripts/wrongbook.py stats
python scripts/wrongbook.py report --out out/wrongbook.md

# 列出全部考点与题量
python scripts/search.py --list-kaodian

# 自检 / 测试 / 评测
python scripts/selfcheck.py && python tests/test_skill.py && python tests/eval.py
```

真实输出示例：

```
命中 240 题，显示前 1 题：

[GK-2024-fs-X112] 2024 国考·副省级 第 112 题　| 资料分析·比重计算与比较（ZL-BILI）
  材料：2023 年，全国规模以上工业企业实现营业收入 159.4 万亿元……
  题干：2023 年私营企业营业收入占规模以上工业企业营业收入的比重，比上年同期：
  A. 上升约 0.4 个百分点　B. 下降约 0.4 个百分点　C. 上升约 4 个百分点　D. 下降约 4 个百分点
  【答案】A
  【解析】……
```

### 3) 对话中直接提问

```
2023 年广东省考县级卷资料分析考了什么？给我两道原题和答案。
图形推理的「一笔画」最近几年还考吗？举两道真题。
帮我找几道涉及「新质生产力」的国考常识真题。
申论单一题（归纳概括）近三年国考怎么问？给参考答案要点。
```

---

## 五、考点体系对齐说明

本库**不自造体系**。模块名、题型名、考点编码全部派生自 `gongkao-huasheng13`：

| 模块 | 来源文件 | 题型 |
|---|---|---|
| 资料分析 | `ziliao-fenxi.md` 题型 1–9 | 基期量、增长量、增长率、比重、平均数、倍数、年均增长率、拉动贡献率、综合分析 |
| 数量关系 | `shuliang-guanxi.md` 题型 1–12 | 工程、行程、利润、排列组合、概率、容斥、最值、年龄、几何、溶液、牛吃草、鸡兔同笼 |
| 言语理解 | `yanyu-lianjie.md` | 逻辑填空、中心理解、细节判断、标题填入、语句填入、下文推断、语句衔接、语句排序、篇章阅读 |
| 判断推理 | `panduan-tuili.md` | 图形推理、定义判断、类比推理、逻辑判断 |
| 常识判断 | `changshi-panduan.md` 2.1–2.8 | 政治、经济、法律、历史人文、地理、科技、时政、生活 |
| 申论 | `shenlun.md` | 单一题、综合分析、提出对策、公文写作、大作文 |

**体系外补充（显式标注，不新增二级体系）**：`SL-SZ 数字推理`（旧国考/广东题型）、`PD-KX 科学推理`（广东特色），仅做模块级归入，题名沿用真题叫法。完整映射见 [`docs/kaodian-taxonomy.md`](docs/kaodian-taxonomy.md)。

---

## 六、命题规律能力

- [`references/01-命题规律总览.md`](references/01-命题规律总览.md)：分省分年模块题量矩阵、高频考点 TOP20、题型变迁（如「政治理论」2025 年起在国考单列、数字推理的退场）。
- 每个考点文件首段即「命题规律」：总量、年份跨度、地区分布、近六年逐年题量、覆盖试卷数。
- 结论均可回溯到具体题目：报告里的数字与 `data/*.jsonl` 一一对应，可用 `search.py` 复算。

---

## 七、与 gongkao-huasheng13 的联动契约

1. 命中真题后，按 `docs/kaodian-taxonomy.md` 的映射取花生十三对应章节；
2. 资料分析 / 数量关系必须给速算过程（截位直除、415 份数、假设分配、代入排除）；
3. 言语 / 判断给「识别标志 + 排除顺序」；申论给「采分点结构」；
4. 未安装技巧 skill 时降级为"方法名 + 步骤"提示，并说明完整体系见花生十三。

---

## 八、数据来源与合规

- 数据来自使用者提供的历年真题 PDF（含官方/机构解析），仅做**文本抽取与结构化**，不改编题目内容；
- 每题保留 `src`（来源文件名），便于溯源核对；
- 解析文本为原文节选（≤4000 字），用于学习研究；如涉及版权问题，请联系删除对应条目；
- 答案一律以原卷/原解析为准，库内不做人工改判。

---

## 九、自检与维护

```bash
python scripts/selfcheck.py
# 行测 11393 题 / 申论 414 题 / 考点文件 47 个
# ✅ 自检通过：字段、ID、考点编码、索引、统计、考点文件全部一致
```

新增年份时按 [`docs/data-spec.md`](docs/data-spec.md) 第六节重跑 `tools/pipeline/`。

---

## 十、License

MIT © 2025 gongkao-zhenti-knowledge contributors
