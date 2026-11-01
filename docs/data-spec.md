# 数据说明与字段规范

本库所有检索能力都建立在两份 JSONL 上，加一份 TSV 检索索引。文件均为 UTF-8，一行一条 JSON，可直接 `grep` / `jq` / Python 读取。

## 一、文件清单

| 文件 | 内容 | 体量 |
|---|---|---|
| `data/xingce.jsonl` | 行测题目（1 行 1 题） | 11 393 行 |
| `data/shenlun.jsonl` | 申论小题（1 行 1 小题，含材料） | 414 行 |
| `data/search-index.tsv` | 检索索引（1 行 1 题，短行，适合 grep） | 11 807 行 |
| `data/stats.json` | 全库统计 | — |

## 二、`data/xingce.jsonl` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 唯一编号，`省-年-卷别-X题号`，如 `GK-2024-fs-X112`、`GD-2023-xj-X045` |
| `prov` | string | `国考` / `广东` / `湖北` |
| `year` | int | 考试年份 |
| `vol` | string | 卷别：`副省级`/`地市级`/`行政执法`/`省级`/`统一卷`/`县级`/`乡镇`/`县乡`/`省市`/`A卷`/`B卷`/`一卷`/`二卷`/`三卷`/`选调`/`思维能力测验`/`综合行政能力测验`/`公安` |
| `num` | int | 原卷题号 |
| `module` | string | 模块：资料分析 / 数量关系 / 言语理解 / 判断推理 / 常识判断 |
| `type` | string | 题型名（对齐花生十三）：如 `基期量计算`、`逻辑填空`、`图形推理`、`政治常识` |
| `code` | string | 考点编码，见 `docs/kaodian-taxonomy.md` |
| `stem` | string | 题干（已去除选项；资料分析题的材料见 `ctx`） |
| `opts` | object | 选项，键为 `A/B/C/D`；图形题为空对象 |
| `ans` | string\|null | 正确答案字母；`null` 表示原卷为扫描版、未提取到答案 |
| `expl` | string | 原解析文本（节选，最长约 4000 字）；可能为空 |
| `ctx` | string | 资料分析的给定材料 / 篇章阅读的材料原文 |
| `kw` | array | 关键词标签（领域词典 + 高频 bigram），最长 12 个，用于快速过滤 |
| `fig` | bool | `true` 表示图形题（选项为图片，图见原卷） |
| `src` | string | 来源文件名（题目 PDF \| 答案 PDF），便于溯源核对 |

## 三、`data/shenlun.jsonl` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `省-年-卷别-S小题号`，如 `GK-2024-fs-S01` |
| `prov` / `year` / `vol` | — | 同上 |
| `paper` | string | 试卷编号，同一套卷的多道小题共享 |
| `no` | string | 原卷题号（如"一""问题三""1"） |
| `module` | string | 固定 `申论` |
| `type` | string | `单一题（归纳概括）`/`综合分析题`/`提出对策题`/`公文写作题`/`大作文` |
| `code` | string | `SN-DY`/`SN-ZH`/`SN-DC`/`SN-GW`/`SN-DZW` |
| `stem` | string | 题干 + 作答要求（分值、字数限制） |
| `ans` | string | 参考答案 / 参考要点（可能为空） |
| `material` | string | 本题所属申论材料全文（同学同卷的几道小题重复存放，便于单独使用） |
| `kw` | array | 关键词标签 |
| `src` | string | 来源文件名 |

## 四、`data/search-index.tsv` 字段

`#id	year	prov	vol	module	type	kw	stem60`，制表符分隔，首行是注释。`kw` 用空格连接，`stem60` 是题干前 60 字（已去换行）。用于「无 Python 环境」时的文本检索：先在此文件搜关键词拿 `id`，再回 JSONL 取整条。

## 五、数据口径

1. **答案来源**：只取原卷/原解析中明确写出的「正确答案 X / 故正确答案为 X / 故选 X」；多条解析给出不同答案时取首个。不做人工改判、不推测。
2. **题干清洗**：去除页眉页脚（`第 X 页 共 Y 页`）、重复卷名；合并被字库拆开的选项标记（如 `B`+`.①③`→`B.①③`）。
3. **选项顺序**：多栏排版的原卷按字母还原为 A/B/C/D，不按视觉位置。
4. **图表题**：图形推理、资料分析的图表本身是图片，文本层只有题干与答案；此类题 `fig=true`，题干标注"图形题，图见原卷"。
5. **完整性**：极小比例题目（<0.3%）因原 PDF 分栏/公式出现文字粘连，`stem` 中可能混入选项碎片；输出时如发现明显异常，换同考点其他题举例。
6. **答案缺失**：26 套卷（主要为广东 2004–2021 行测、国考 2021 副省级、国考 2002 B 卷）的原答案 PDF 是扫描件、无文字层，`ans` 为 `null`，输出时必须如实说明，**不得编造答案**。

## 六、复现与再生成

`tools/pipeline/` 保留了从原始 PDF 到本库的完整流水线（PyMuPDF 文本抽取 → 题目结构化 → 考点分类 → 索引与文档生成）。重新采集时：

```bash
python tools/pipeline/survey.py        # 先探测 PDF 文本层可用性
python tools/pipeline/build_xingce.py  # 行测抽取
python tools/pipeline/build_shenlun.py # 申论抽取
python tools/pipeline/finalize.py      # 生成 data/
python tools/pipeline/gen_docs.py      # 生成 references/
```

流水线不依赖公网，只依赖 `pymupdf`。
