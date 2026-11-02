---
name: gongkao-zhenti-knowledge
description: 公考真题知识库（国考 2000–2026、广东省考 2003–2026、湖北省考 2008–2026，行测 11393 题 + 申论 414 题，含答案与解析）。当用户需要「历年真题原题」「这道题哪年考过」「某考点出过哪些题」「真题+答案」「命题规律/高频考点/考情分析」「按年份/省份/题型检索真题」「多关键词模糊找题」时使用。考点体系完全对齐 gongkao-huasheng13（花生十三公考技巧）：资料分析 ABRX 九大题型、数量关系十二题型、言语理解、判断推理、常识判断、申论五大题型。检索到真题后自动联动 gongkao-huasheng13 输出对应解题技巧与速算方法。触发词：真题、原题、历年真题、题干、选项、答案、解析、命题规律、高频考点、考情、国考真题、广东省考真题、湖北省考真题、行测真题、申论真题、考点分布、哪年考过、还考过什么。
license: MIT
version: 1.5.3
---

# 公考真题知识库

本 skill 是「真题数据层」，与 `gongkao-huasheng13`（技巧层）构成 **考点 → 真题 → 技巧** 的配套闭环：

| 层 | skill | 回答的问题 |
|---|---|---|
| 技巧层 | `gongkao-huasheng13` | 这类题怎么想、怎么算、怎么提速 |
| 数据层 | **本 skill** | 这类题历年考过什么、原题长什么样、答案是什么、命题规律如何 |

**铁律：不自造考点体系。** 所有模块、题型、考点编码一律沿用 `gongkao-huasheng13` 的命名（见 `docs/kaodian-taxonomy.md`）。本库只在体系未覆盖的旧题型（数字推理、科学推理）上做「模块级对齐 + 显式标注」，不新造二级体系。

---

## 一、何时使用

**强信号（直接进入检索）**
- "这题哪年考的/哪套卷"、"给我找几道 XX 的真题"、"XX 考点历年真题"
- "国考/广东省考/湖北省考 XXXX 年行测/申论第 X 题"
- "整理一下资料分析/图形推理/申论单一题的命题规律"、"高频考点排行"
- "用真题举例说明 XX 技巧" → 先取真题，再联动技巧
- 用户粘贴一道题问"这是真题吗/考过吗" → 多关键词检索比对

**弱信号（先确认条件）**
- "怎么备考公考" → 问清目标省份、年份范围、薄弱模块，再给「规律 + 高频 + 真题清单」
- "帮我刷题" → 问清模块与难度，从对应考点文件抽样

---

## 二、数据地图（先看这里再读文件）

```
data/
  xingce.jsonl        行测全量题库，1 行 1 题，11 393 题（含答案/解析/考点/子考点/难度/关键词/同题折叠标记）
  shenlun.jsonl      申论题库，1 行 1 小题，419 题（含材料/答案/主题标签/难度）
  search-index.tsv    检索索引，1 行 1 题：id 年份 省份 卷别 模块 题型 关键词 题干摘要
  stats.json          全库统计（题量、年份、模块分布、考点分布）
references/
  00-index.md         总索引：考点 → 文件、试卷 → 文件（先读这个）
  01-命题规律总览.md   分省分年模块题量矩阵、高频考点 TOP20、题型变迁
  kaodian/<编码>-<名称>.md   48 个考点文件：命题规律 + 近年 12 题 + 分片索引
  kaodian/split/*.md        127 个年代分片（其余真题按 2000s/2010s/2020s 拆开，控制单次读取体积）
  juan/<省>-<年>-<卷别>.md   98 套行测原卷：题目 + 答案 + 考点 + 难度
  shenlun/<省>-<年>-<卷别>.md 106 套申论原卷：材料 + 题目 + 参考答案 + 主题标签
  images/<题目ID>.jpg        3 387 张原题配图（图形推理的图形、资料分析的图表材料）
docs/
  kaodian-taxonomy.md 考点体系全表（三级）+ 对齐花生十三的映射依据
  data-spec.md        字段说明与数据口径
  coverage.md         覆盖范围与已知缺口（扫描件缺答案等）
  eval.md             评测集与指标口径
  distribution.md     lite / full 发行包与 GitHub Release
scripts/
  search.py           检索 CLI（考点/子考点/年份/省份/多关键词/模糊/难度/主题）
  paper.py            组卷：按考点配比生成试卷 + 答案页
  wrongbook.py        错题本：记录、归因、复习报告
  make_release.py     打包 lite / full 发行版
  selfcheck.py        数据自检
tests/
  test_skill.py       检索与数据一致性冒烟测试
  test_tools.py       组卷 / 错题本测试
  eval.py             分类准确率评测（强标注/弱标注两档 gold）
```

**命题规律字段**：每题带 `sub`（三级子考点）、`diff`（1–5 难度，模块内等频）、申论另有 `theme`（1–3 个主题标签）。检索可用 `--sub` / `--diff 4-5` / `--theme 基层治理` 组合过滤；组卷可按考点轮转自动配难度分布。

**分片读取**：考点主文件现在只放「规律 + 近年 12 题」，其余题目在 `kaodian/split/<编码>-<年代>s.md`。**不要一次读完整个考点目录**：先读主文件判断趋势，需要更多例题再按年代读分片。

**同题折叠**：同一道题常在国考副省/地市/执法三卷、不同年份、联考各省重复出现。数据里 `canonical` 指向同题主记录、`dup_n` 是变体数；检索默认只出主记录（并提示"同题另有 N 个变体"），要看该题所有年份出处时加 `--all-variants`。回答"还考过什么"时，用变体年份作为佐证（例如"这题 2021 地市、2023 副省、2024 执法都出现过"）。

**配图**：`references/images/<题目ID>.jpg` 是按题号自动裁切的题区截图，`juan/` 与 `kaodian/` 的 Markdown 已内嵌引用，检索结果会给出配图路径。**图形推理、资料分析图表题必须先看图再讲**：图形题的文字层只有通用问法，资料分析的材料常常就是一张图表。

**ID 规则**：`省-年-卷别-题号`，如 `GK-2024-fs-X112`（2024 国考副省级第 112 题）、`GD-2023-xj-X045`、`HB-2024-ty-X088`、申论 `GK-2024-fs-S01`。
省：`GK` 国考 / `GD` 广东 / `HB` 湖北；卷别：`fs` 副省级、`ds` 地市级、`zf` 行政执法、`sj` 省级、`ty` 统一卷、`xj` 县级、`xz` 乡镇、`xx` 县乡、`ss` 省市、`a/b` A/B 卷、`xd` 选调。

---

## 三、检索协议（按问题类型选路径）

### 路径 A：按考点找真题（最常用）

1. 把用户说法映射成考点编码（对照 `docs/kaodian-taxonomy.md`，找不到就先用关键词路径）。
2. 读 `references/kaodian/<编码>-<名称>.md`：内含「命题规律」+「最多 30 道原题（按年份倒序）+ 答案 + 解析」。
3. 需要更多同类题时，跑检索脚本（见路径 C）或读 `references/juan/` 对应年份原卷。

> 例：用户问"资料分析基期量计算历年怎么考" → 读 `references/kaodian/ZL-BASE-基期量计算.md` → 给规律 + 3–5 道典型原题 → 联动 `gongkao-huasheng13` 的"假设分配法/截位直除"。

### 路径 B：按年份/省份/整卷找真题

- 精确到某套卷：直接读 `references/juan/<省>-<年>-<卷别>.md`（含全部题目、答案、考点标注）。
- 只要清单：读 `references/00-index.md` 的「按试卷检索」表，或 `search-index.tsv` 按年份过滤。
- 要对比多省：读 `references/01-命题规律总览.md` 的模块题量矩阵。

### 路径 C：多关键词全文检索（零散知识点组合定位）

用户常给不出考点名，只给零散词，例如"东北 粮仓 黑土地 保护 常识"或"基期 比重 百分点 陷阱"。

**方法 1（推荐，有 Python 环境）**

```bash
python scripts/search.py --kw 黑土地 --kw 保护 --prov 国考 --limit 5
python scripts/search.py --kw 基期 --kw 比重 --year 2023      # 多关键词 AND
python scripts/search.py --kaodian ZL-BILI --prov 广东        # 考点 + 省份
python scripts/search.py --sub 两期比重差                     # 三级子考点（最精准）
python scripts/search.py --kw 占比 --kw 提高 --fuzzy          # 模糊：同义词 + 2-gram（换说法/错字也能中）
python scripts/search.py --any 新质生产力 未来产业 低空经济    # 任一词命中
python scripts/search.py --id GK-2025-fs-X010 --full          # 取完整题目
python scripts/paper.py --module 资料分析 --count 20 --prov 国考 --out out/套卷.md     # 组卷
python scripts/search.py --theme 基层治理 --diff 4-5          # 主题 + 难度
python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟                # 错题本
python scripts/make_release.py --version 1.3.0                # 打包 lite / full
```

**检索策略优先级**：`--sub`（子考点）> `--kaodian`（考点）> `--kw`（关键词 AND）> `--fuzzy`（模糊）> `--any`（OR）。先用最具体的；没结果就降一级，不要一上来就用 `--any`（噪声大）。

**方法 2（无 Python：文本检索降级）**

1. 先在 `data/search-index.tsv` 中检索关键词 → 得到候选 `id`（每题一行，短、易过滤）。
2. 多个关键词时逐个检索取交集（AND）；同一关键词的不同说法要都试（如"占比/比重/占"）。
3. 用 `id` 在 `data/xingce.jsonl` 或 `data/shenlun.jsonl` 中定位整行，得到题干、选项、答案、解析。
4. 如果 JSON 读取不便，直接读该题所属的 `references/juan/` 原卷文件。

> 关键词扩展规则：考点词 ↔ 同义说法（比重/占比/占…%；增长率/增速/增幅；平均数/人均/每…；中心理解/意在/主旨/主要说明）。检索不到时，去掉最"硬"的那个词，只保留 2 个词再试。

### 路径 D：申论真题

- 读 `references/shenlun/<省>-<年>-<卷别>.md`：给定材料 + 题目（含分值与字数要求）+ 参考答案。
- 按题型找：`references/kaodian/SN-*.md`（单一题 / 综合分析 / 提出对策 / 公文写作 / 大作文）。
- 申论答案多为「参考要点」，不是唯一标准答案；输出时按要点分层呈现，并提示"采分点导向，非唯一答案"。

---

## 四、输出规范

### 4.1 单题 / 少量原题

```
【检索结果】共命中 N 题（考点：判断推理·逻辑判断）
1. 【2024 国考 副省级 第 108 题】GK-2024-fs-X108
   题干：……
   A. …… B. …… C. …… D. ……
   【答案】C
   【解析】（节选）……
   【所属考点】判断推理·逻辑判断（花生十三 panduan-tuili.md#4.3 加强削弱）
```

### 4.2 考点命题规律

固定五段式：

```
一、题量趋势：总题量、年份跨度、近 5 年逐年题量
二、地区差异：国考 / 广东 / 湖北 的考法差异
三、高频子考点：从解析与题干中归纳的细粒度考点排行
四、典型原题：3–5 道，覆盖不同年份与省份，附答案
五、备考建议：结合 gongkao-huasheng13 的方法给出训练动作
```

### 4.3 与技巧联动（必须执行）

只要用户问"怎么做/怎么提速/为什么错"，在给出真题后**必须**同时给出技巧层内容：

1. 判定考点编码 → 从 `docs/kaodian-taxonomy.md` 查到对应的花生十三文件与章节；
2. 引用该章节的方法名（如"截位直除""415 份数法""假设分配法""要素法""翻译推理逆否"）；
3. 资料分析/数量关系必须给速算过程；言语/判断给识别标志 + 排除顺序；申论给采分点结构。

**联动映射速查**（与 `gongkao-huasheng13/references/` 对应）：

| 考点 | 花生十三文件·章节 |
|---|---|
| ZL-BASE 基期量计算 | `ziliao-fenxi.md#题型1` + `ziliao-susuan.md#三`（假设分配法） |
| ZL-GROW 增长量计算 | `ziliao-fenxi.md#题型2` + `ziliao-susuan.md#二`（415 份数法） |
| ZL-RATE 增长率计算与比较 | `ziliao-fenxi.md#题型3` |
| ZL-BILI 比重计算与比较 | `ziliao-fenxi.md#题型4` |
| ZL-AVG 平均数计算 | `ziliao-fenxi.md#题型5` |
| ZL-BEI 倍数计算 / ZL-YEAR 年均增长率 / ZL-PULL 拉动贡献率 | `ziliao-fenxi.md#题型6/7/8` |
| ZL-COMP 综合分析 | `ziliao-zonghe.md` 全篇 |
| SL-* 数量关系 | `shuliang-guanxi.md#题型1–12` + `shuliang-gongshi.md` |
| YY-LJTK 逻辑填空 | `yanyu-lianjie.md#二` + `yanyu-ciyu.md` |
| YY-ZXJL/XJPD/BTTR/YJTR/XWTD | `yanyu-lianjie.md#三` |
| YY-YJPX/YJXH | `yanyu-lianjie.md#四` |
| YY-PZYD 篇章阅读 | `yanyu-lianjie.md#五` |
| PD-TX 图形推理 | `panduan-tuili.md#一` + `panduan-tuxing.md` |
| PD-DY 定义判断 | `panduan-tuili.md#二`（要素法） |
| PD-LB 类比推理 | `panduan-tuili.md#三`（关系层级法） |
| PD-LJ 逻辑判断 | `panduan-tuili.md#四` + `panduan-guilv.md#四` |
| CS-* 常识判断 | `changshi-panduan.md#2.x` + `shizheng-redian.md` |
| SN-DY/ZH/DC/GW/DZW | `shenlun.md#二/三/四/五/六` + `shenlun-biaoda.md` |

**若 `gongkao-huasheng13` 未安装**：仍要给出方法名与解题步骤（本 skill 的 `docs/kaodian-taxonomy.md` 记录了方法归属），并提示"完整方法体系见花生十三技巧 skill"。

---

## 五、数据口径与免责

- **来源**：用户提供的国考（2000–2026）、广东省考（2003–2026）、湖北省考（2008–2026）真题 PDF，逐页抽取文本后结构化。
- **答案**：一律取原卷/原解析中的"正确答案/故正确答案为 X"，不做人工改判。**答案缺失**的原卷（扫描版无文字层）在题目里标注"暂缺"，不得臆造答案，须提示用户核对原卷。
- **图形推理**：图形本身为图片，本库保留题号、答案与「解析中说明的规律」，题干处标注"图形题，图见原卷"。
- **抽取噪声**：极少数题目因原 PDF 版式（分栏、公式、表格）出现文字粘连或缺失，输出时如发现题干明显不完整，应提示并改用同考点其他题目举例。
- **覆盖面**：详见 `docs/coverage.md`（含未收录年份与原因）。回答"是否考过"时，只能表述为"在本库覆盖的 X 套卷中未检索到"，不能断言"从未考过"。

---

## 六、快速响应模板

**"资料分析怎么提速"**
→ 读 `references/kaodian/ZL-*.md` 统计高频题型 → 给 3 道近年真题（附速算）→ 联动 `ziliao-susuan.md` 三大速算。

**"广东省考判断推理爱考什么"**
→ 读 `references/01-命题规律总览.md` 广东模块矩阵 → 读 `references/kaodian/PD-*.md` 的广东题量与例题 → 给结论 + 3 道广东原题。

**"2024 国考副省级第 108 题"**
→ 读 `references/juan/国考-2024-副省级.md` 定位 → 输出题干/选项/答案/解析 → 联动考点技巧。

**"这几个词能搜到什么题：黑土地 保护 粮仓"**
→ 路径 C：`scripts/search.py --kw 黑土地 --kw 保护` 或 tsv 交集 → 输出命中题目与考点。

**"帮我出一套资料分析专项练习"**
→ 从 `references/kaodian/ZL-*.md` 各抽 2 题，按「基期→增长量→增长率→比重→平均数→综合分析」组卷，附答案页，并给时间建议（20 题 25 分钟）。
