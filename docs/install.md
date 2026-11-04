# 安装与使用

> 适用版本：v1.11.0　｜　数据规模与口径见 [`docs/stats-snapshot.md`](stats-snapshot.md)（由 `pipeline/gen_docs.py` 生成、CI 校验）

本 skill 兼容三种安装方式：**豆包工作模式**、**通用 Agent Skills（SKILL.md 规范）**、**本地命令行**。

---

## 零、先选发行版

| 版本 | 体积 | 内容 | 用途 |
|---|---|---|---|
| **lite** | 6.6 MB | 全部 Markdown 题库 + 检索索引 | 豆包上传、只要查真题 |
| **full** | 41.0 MB | lite + JSONL 题库 + 3 536 张配图 + 工具链 | 本地刷题、组卷、错题本 |

> 体积为 `dist/` 现有 v1.4.0 打包产物的 zip 大小；v1.11.0 尚未重新打包，full 解压后约 106.8 MB，见 [distribution.md](distribution.md)。

打包命令与 GitHub Release 流程见 [distribution.md](distribution.md)。

## 一、安装到豆包工作模式

豆包（Doubao）的「技能 / 工作模式」按 Agent Skills 规范加载：一个目录 + `SKILL.md`（含 YAML frontmatter 的 `name` 与 `description`），其余文件作为按需读取的资源。

### 步骤

1. 下载本仓库（`Code → Download ZIP` 或 `git clone`），解压得到 `gongkao-zhenti-knowledge/` 目录。
2. 确认目录顶层直接包含 `SKILL.md`（不要多套一层文件夹）。
3. 在豆包智能体的「技能 / 工作模式」中上传或指定该目录（部分版本提供"导入 Skill / 添加技能包"，选择目录压缩包即可）。
4. 若平台要求填写名称与描述，直接复制 `SKILL.md` frontmatter 里的 `name` 与 `description`。
5. **同时安装 `gongkao-huasheng13`（花生十三技巧 skill）**，才能实现「真题 + 技巧」联动；未安装时本 skill 仍可独立输出真题与答案，只是技巧调用会降级为方法名提示。

### 验证

安装后在同一对话中问：

```
2024 年国考副省级资料分析考了哪些题？给我 2 道原题和答案。
```

预期：命中 `references/juan/国考-2024-副省级.md`，输出题干、选项、答案、考点，并联动花生十三的「截位直除 / 假设分配」讲解。

---

## 二、安装为通用 Agent Skill（Claude / 其他支持 SKILL.md 的宿主）

把整个目录放进宿主的 skills 目录，例如：

```bash
# Claude Code / 兼容宿主
cp -r gongkao-zhenti-knowledge ~/.claude/skills/
# 或本 harness（DSH）
cp -r gongkao-zhenti-knowledge ~/.dsh/skills/
```

宿主会读取 `SKILL.md` 的 `description` 决定何时加载，`.md` / `.jsonl` 作为按需资源被读取。

---

## 三、本地命令行使用（不需要任何宿主）

只依赖 Python 3.9+（标准库即可，无需 pip 安装）。

```bash
cd gongkao-zhenti-knowledge

# 1) 按考点 + 省份
python scripts/search.py --kaodian ZL-BASE --prov 国考 --limit 3

# 2) 多关键词组合定位（AND）
python scripts/search.py --kw 黑土地 --kw 保护 --kw 粮仓

# 3) 关键词任一命中（OR）
python scripts/search.py --any 新质生产力 低空经济 未来产业

# 4) 某年某省全部资料分析题
python scripts/search.py --year 2024 --prov 广东 --module 资料分析 --limit 20

# 5) 三级子考点（最精准）：两期比重差 / 最不利构造 / 翻译推理 …
python scripts/search.py --sub 两期比重差 --prov 国考 --limit 5

# 6) 模糊检索：同义词 + 2-gram，容忍换说法与错字
python scripts/search.py --kw 占比 --kw 提高 --fuzzy --limit 5

# 7) 按 ID 取完整题目（含解析）
python scripts/search.py --id GD-2023-xj-X045 --full

# 8) 展开同题变体（默认折叠，只出主记录）
python scripts/search.py --kaodian ZL-BILI --all-variants --limit 10

# 9) 列出所有考点与题量
python scripts/search.py --list-kaodian

# 10) 组卷（按考点轮转抽样，输出试卷 + 答案页）
python scripts/paper.py --module 资料分析 --count 20 --prov 国考 --years 2019-2026 --out out/套卷.md

# 11) 错题本
python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟 --note "比重差算成增长率"
python scripts/wrongbook.py list
python scripts/wrongbook.py report --out out/wrongbook.md

# 12) 数据自检 / 评测 / 测试
python scripts/selfcheck.py
python tests/eval.py
python tests/test_skill.py
```

Windows PowerShell 中把 `python` 换成 `py` 或实际解释器路径即可；若中文输出乱码，先执行 `$env:PYTHONIOENCODING='utf-8'`。

---

## 四、无 Python 环境的降级用法

纯文本即可完成检索，不依赖任何脚本：

1. 打开 `references/00-index.md`，按考点或试卷定位文件；
2. 或打开 `data/search-index.tsv`，用编辑器的"查找"搜关键词，得到 `id`；
3. 用 `id` 在 `data/xingce.jsonl` / `data/shenlun.jsonl` 中定位整行（或用 `id` 中的年份与题号直接打开 `references/juan/` 对应原卷）；
4. 结论输出遵循 `SKILL.md` 的「输出规范」。

---

## 五、目录约定（务必保持）

```
gongkao-zhenti-knowledge/
├── SKILL.md            ← 宿主加载入口，必须位于顶层
├── README.md
├── LICENSE
├── docs/               ← 体系、字段、覆盖、安装说明
├── references/         ← 人/模型可读的知识层（考点、原卷）
├── data/               ← 机器可读的数据层（jsonl + tsv）
├── scripts/            ← 检索与自检
└── tools/pipeline/     ← 采集流水线（复现用，可选）
```

`SKILL.md` 里写的相对路径全部相对于本目录，移动目录时保持结构不变即可。

---

## 六、常见问题

**Q：安装后模型没有调用它？**
A：检查 `SKILL.md` 的 `description` 是否被平台截断（部分平台限制 1024 字符）。可把 `description` 精简为第一句"公考真题知识库（国考/广东省考/湖北省考，行测 11393 题 + 申论 419 题，含答案与解析）"。

**Q：只有真题、没有技巧？**
A：需同时安装 `gongkao-huasheng13`。本 skill 的 `docs/kaodian-taxonomy.md` 已写好每个考点对应的花生十三文件与章节。

**Q：答案显示"暂缺"？**
A：该卷原答案 PDF 是扫描件（详见 `docs/coverage.md`）。不要编造答案，提示用户核对原卷。

**Q：能联网更新吗？**
A：本库是静态快照（截至 2026 年国考/省考）。新增年份时按 `docs/data-spec.md` 第六节重跑流水线。
