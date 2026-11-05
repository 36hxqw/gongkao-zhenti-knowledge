# 公考真题知识库 Skill · gongkao-zhenti-knowledge

> 国考（2000–2026）· 广东省考（2003–2026）· 湖北省考（2008–2026）
> **行测 11 393 题 + 申论 419 题**，含答案与解析；考点体系与 **gongkao-huasheng13（花生十三技巧，配套 skill）** 完全对齐。

一个可按**考点 / 题型 / 年份 / 省份**精准检索、支持**多关键词全文匹配**的公考真题知识库，作为 Agent Skill 直接安装到豆包工作模式（或其他支持 `SKILL.md` 的宿主），与花生十三技巧 skill 组成 **考点 → 真题 → 技巧** 的闭环。

```
用户问「资料分析基期量怎么考」
        │
        ├── 本 skill：历年基期量真题 17 道（同题折叠后；全量 19 道）、命题规律、原题 + 答案 + 解析
        └── gongkao-huasheng13：ABRX 体系、假设分配法、截位直除的解题步骤
```

---

## 一、它解决什么问题

| 痛点 | 本库的做法 |
|---|---|
| 想按考点刷真题，但题库和考点体系对不上 | 每题都带 `模块/题型/考点编码`，考点命名 100% 沿用花生十三体系（不自定义）；另有 **197 个三级子考点**（两期比重差、折纸盒、三视图、最不利构造…） |
| 只记得几个零散词，找不到题 | `search.py` 支持多关键词 AND/OR、`--sub` 子考点、`--form` 设问形态/空数、`--fuzzy` 同义词+2-gram 模糊匹配，也可纯文本 grep |
| 需要"原题 + 答案 + 解析"一起给 | 每题保留题干、A–D 选项、正确答案、原解析节选、来源文件 |
| 同一道题在国考三卷、多年重复出现 | 同题折叠：默认只出主记录，并告诉你"这题还考过哪几年" |
| 图形推理、资料分析图表题看不到图 | 3 536 张按题号自动裁切的原题配图，Markdown 内嵌 + 检索结果给出路径 |
| 想知道"这个考点到底怎么考" | 48 个考点文件内含题量趋势、地区差异、近六年分布、典型原题 |
| 讲了真题却讲不了技巧 | 与花生十三 skill 联动映射表，精确到 `文件#章节` |
| 想直接刷一套 / 记错题 | `paper.py` 按考点配比组卷（含答案页），`wrongbook.py` 记录错题并按四类错因出复习报告 |

---

## 二、数据规模

> 下表数字与 [`docs/stats-snapshot.md`](docs/stats-snapshot.md) 一致：该文件由 `pipeline/gen_docs.py` 从 `data/*.jsonl` 复算生成，CI 用 `scripts/doc_check.py` 校验。改动数据后先重生成快照，再改本表。

| 维度 | 数值 |
|---|---|
| 行测试卷 | 98 套（国考 45 / 广东 35 / 湖北 18） |
| 行测题目 | 11 393 题（**有答案 8 478 题**；同题变体 1 095 条已折叠，折叠后 10 298 题） |
| 考试类型 | 国考 6 004 / 广东省考 3 437 / 湖北省考 2 371（行测 5 803 / 3 307 / 2 283 + 申论 201 / 130 / 88；按 `data/*.jsonl` 现算，非快照指标。列题展示统一用 `exam_label`：年份 + 考试类型（+卷别），如 `2024 广东省考（县级）`） |
| 申论试卷 | 106 套 |
| 申论小题 | 419 题（**287** 题有参考答案，**132** 题见原卷） |
| 考点 | 48 个有题考点（`--list-kaodian` 合计 11 812 题），覆盖 6 大模块；另有 3 个零题编码（ZL-PULL / YY-YJXH / YY-PZYD，无文件）；三级子考点 211 个标签（图形推理新增折纸盒 / 三视图 / 截面 / 立体拼合 4 个二级子考点） |
| 质量评测 | 规则集 189 条 + **人工盲标集 154 条**（3 个子代理盲标、主代理抽检 14 条一致率 100%）；模块 98.0% / 考点 82.2% |
| 原题配图 | 3 536 个文件（约 55.4MB）：题目图 3 148 + 材料图 225（表格/图表独立裁切、同组共享；按记录计 1 455 条）+ 跨页续图 163 |
| 难度 / 主题 | 11 393 + 419 题全部 1–5 难度分档；申论 419 题带主题标签（15 类） |
| 年份跨度 | 2000–2026（含 2026 国考、广东、湖北最新卷） |

模块分布：判断推理 29.4%、言语理解 25.0%、常识判断 18.8%、资料分析 14.9%、数量关系 11.9%。

> 答案缺失 **25.6%（2 915 题）**——全部集中在广东 2004–2021 等**原始答案 PDF 无文字层**的试卷，题目与考点照常可用，答案如实标"该题答案缺失，见原卷"，绝不编造（另有 15 条答案因越界被置空并写 `ans_note` 说明）。明细见 [`docs/coverage.md`](docs/coverage.md)。

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
│   ├── kaodian/                  # 48 个考点文件：规律 + 近年 12 题 + 分片索引
│   │   └── split/                # 128 个年代分片（控制单次读取体积）
│   ├── juan/                     # 98 套行测原卷（题目 + 答案 + 考点）
│   ├── shenlun/                  # 106 套申论原卷（材料 + 题目 + 参考答案）
│   └── images/                   # 3 536 张原题配图（题目图 / 材料图 / 跨页续图）
├── data/
│   ├── xingce.jsonl              # 行测题库
│   ├── shenlun.jsonl             # 申论题库
│   ├── search-index.tsv          # 检索索引（短行，适合 grep）
│   └── stats.json
├── scripts/
│   ├── search.py                 # 检索 CLI（考点/子考点/多关键词/模糊，零依赖）
│   ├── paper.py                  # 组卷：按考点轮转抽样，输出试卷 + 答案页
│   ├── wrongbook.py              # 错题本：记录 / 归因 / 复盘报告
│   ├── make_release.py           # 打包 lite / full 发行版
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
python scripts/search.py --kw 黑土地 --kw 保护   # 实测 3 题；3 词以上 0 命中会自动降级

# 任一词命中（OR）
python scripts/search.py --any 新质生产力 低空经济 未来产业

# 某年某省某模块（--year / --prov / --module 均可多值：空格或逗号分隔，年份还支持区间）
python scripts/search.py --year 2024 --prov 广东 --module 资料分析 --limit 10
python scripts/search.py --year 2024 2025 --module 资料分析 判断推理 --prov 国考 --limit 3
python scripts/search.py --year 2023-2025 --prov 广东 --limit 5

# 按维度分组看分布（年份 / 考点 / 省份 / 考试 / 年份+考点）
python scripts/search.py --module 资料分析 --group-by 年份 --limit 6
python scripts/search.py --module 资料分析 --group-by 考试 --limit 6   # 组头用 exam_label

# 按 ID 取完整题目（含解析；同题变体 id 也能命中，会先告诉你主记录）
python scripts/search.py --id GK-2025-fs-X010 --full

# 三级子考点（知识点，最精准）：两期比重差 / 最不利构造 / 翻译推理 / 折纸盒 / 三视图 …
python scripts/search.py --sub 两期比重差 --prov 国考
python scripts/search.py --sub 折纸盒 --full --limit 3     # 图形推理·立体图形二级子考点

# 按设问形态 / 空数（form，可与上面任一条件叠加）：选正确项/选错误项/判断个数/排序与图示/一空/两空/三空及以上
python scripts/search.py --form 两空 --limit 5
python scripts/search.py --form 一空 两空 --module 言语理解 --limit 3
python scripts/search.py --form 两空 --fields id,form,sub   # 字段裁剪，便于脚本消费

# 模糊检索：同义词 + 2-gram，换说法/错字也能中
python scripts/search.py --kw 占比 --kw 提高 --fuzzy

# 组卷：按考点轮转抽样，输出试卷 + 答案页（默认 seed=20260101，dry-run 与成卷一致）
python scripts/paper.py --module 资料分析 --count 20 --prov 国考 --years 2019-2026 --out out/套卷.md
python scripts/paper.py --quota 资料分析=10 --quota 判断推理=10 --dry-run   # 不给 --count 时取配额之和 = 20 题

# 错题本：记录 → 归因 → 复盘报告
python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟 --note "两期比重差算成增长率"
python scripts/wrongbook.py stats
python scripts/wrongbook.py report --out out/wrongbook.md

# 难度 / 主题过滤
python scripts/search.py --diff 4-5 --module 资料分析
python scripts/search.py --theme 基层治理 --limit 5

# 打包发行版（lite zip 约 7 MB / full zip 约 62 MB）
python scripts/make_release.py --version 1.12.0

# 列出全部考点与题量
python scripts/search.py --list-kaodian

# 自检 / 测试 / 评测
python scripts/selfcheck.py && python tests/test_skill.py && python tests/eval.py
```

真实输出示例：

```
命中 41 题，显示前 1 题：

[GK-2024-ds-X111] 2024 国考（地市级）·第 111 题　| 资料分析·综合分析（ZL-COMP）　子考点：增长率　形式：排序与图示　难度：★★★★☆
  材料：2022年,S省各级12315工作机构共接收诉求220.4万件,同比增长21.41%。其中,投诉55.6万件、举报26.3万件、咨询138.5万件,比上一年分别增加14.0万件、8.9万件、16.0万件。
  题干：将S省各级12315工作机构接收的投诉、举报和咨询三类诉求量按2022年同比增速从高到低排序,以下正确的是:
  A. 投诉量、举报量、咨询量　B. 咨询量、投诉量、举报量　C. 举报量、咨询量、投诉量　D. 举报量、投诉量、咨询量
  材料图：references/images/GK-2024-ds-X111-m.jpg
  【答案】D
  【解析】根据题干"······按2022 年同比增速从高到低排序······",可判定本题为一般增长率比较问题。……
```

> 每题首行固定为 `[id] 年份 考试类型（卷别）·第 N 题`（`exam_label` + 题号）：**列题一律带「年份 + 考试类型（+卷别）」**，统一卷不带卷别后缀（如 `2024 广东省考`）。

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
- 答案以原卷答案表/解析结论为准；两者冲突时按原卷订正，并在 `ans_note` 记录原值与依据（如「答案按原卷解析订正（原 ans=A 与解析结论不一致）」）。

---

## 九、自检与维护

```bash
python scripts/selfcheck.py
# 行测 11393 题 / 申论 419 题 / 考点文件 49 个
# 答案缺失 2915 题（25.6%），逐卷见 docs/coverage.md
# ✅ 自检通过：字段、ID、考点编码、索引、统计、考点文件全部一致
```

新增年份时按 [`docs/data-spec.md`](docs/data-spec.md) 第六节重跑 `tools/pipeline/`。

---

## 十一、发布到 GitHub

```bash
cd gongkao-zhenti-knowledge
git init -b main                    # 已有 .git 可跳过
git add .
git commit -m "feat: 公考真题知识库 v1.12.0（行测 11393 + 申论 419，含答案/解析/配图）"
git remote add origin https://github.com/<你的账号>/gongkao-zhenti-knowledge.git
git push -u origin main
```

- 仓库体积约 106 MB（配图 55 MB），单文件最大 20 MB，均在 GitHub 限制内；
- 发行包（`dist/*.zip`）已加入 `.gitignore`，请作为 **Release 资产**上传，不要提交进仓库；
- 建议在仓库 **About** 里填描述（见本文件开头一句话），Topics 建议 `gongkao` `gongkao-zhenti` `agent-skill` `llm` `exam` `chinese`；
- 打 tag：`git tag -a v1.12.0 -m "v1.12.0" && git push origin v1.12.0`，再在 GitHub 页面 New release。

## 十、License

MIT © 2025 gongkao-zhenti-knowledge contributors
