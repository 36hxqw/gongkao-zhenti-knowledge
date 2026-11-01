# 采集流水线（复现用）

从原始真题 PDF 生成 `data/` 与 `references/` 的完整链路。**普通使用者不需要运行这些脚本**，仓库里已包含生成结果；只有在新增年份或更换数据源时才需要。

## 依赖

- Python 3.9+
- `pymupdf`（`pip install pymupdf`）
- 无需公网、无需 OCR

## 数据源约定

源目录结构如下（`ZHENTI_ROOT` 指向它）：

```
<ZHENTI_ROOT>/
├── 国考2000-2026真题pdf/
│   ├── 2000-2026国考行测PDF/{行测-真题, 行测-答案及解析}/
│   └── 2000-2026国考申论PDF/
├── 广东公务员考试真题pdf版/
│   ├── 广东公务员考试真题——行测04-26pdf版/{题目, 答案及解析}/
│   └── 广东公务员考试真题——申论03-26pdf版/
└── 湖北公务员考试真题pdf版/
    ├── 湖北公务员考试真题——行测08-26PDF版/{题目, 答案及解析}/
    └── 湖北公务员考试真题——申论07-25PDF版/
```

设置源目录：

```bash
# PowerShell
$env:ZHENTI_ROOT = "D:\公考真题"
# bash
export ZHENTI_ROOT=/data/gongkao
```

未设置时默认取本文件向上三级目录（即仓库根），仅适合数据源与仓库同级的场景。

## 执行顺序

```bash
cd tools/pipeline
python survey.py          # 1. 探测每个 PDF 的文字层（找出扫描件）
python build_xingce.py    # 2. 行测：题目解析 + 答案解析 + 配对 → out/xingce_raw.jsonl
python build_shenlun.py   # 3. 申论：材料/题目/参考答案 → out/shenlun_raw.jsonl
python finalize.py        # 4. 考点分类 + 关键词 + ID + 统计 → ../../data/
python make_images.py --all # 5. 生成题区配图（2300+ 张，约 30MB）
python gen_docs.py        # 6. 生成 references/kaodian、juan、shenlun、总索引、规律总览
python gen_taxonomy_doc.py# 7. 生成 docs/kaodian-taxonomy.md
cd ../.. && python scripts/selfcheck.py   # 8. 自检
```

## 各模块职责

| 文件 | 职责 |
|---|---|
| `survey.py` | 逐 PDF 抽样页统计中文字符数，输出 `survey.json`；`sample_cn < 30` 判定为无文字层（扫描件） |
| `textlib.py` | 按**内容流顺序**取行（本语料中字体宽度信息有损坏，坐标排序会把选项打乱）、合并被拆开的 `B`+`.①③`、丢弃页眉页脚、识别章节标题 |
| `parse_lib.py` | 题号锚定的结构化解析：容忍 `1.` `1、` `1．` `1` 空格 等编号；A–D 选项支持一行一个、一行四个、双栏交错（乱序字母也能还原）；答案支持「快速对答案表 / 第【N】题 正确答案 / 故正确答案为X / 因此选择X」 |
| `classify.py` | 考点分类：以章节标题定模块，再按题型关键词定考点；输出严格对齐花生十三体系的编码 |
| `manifest.py` | 题目 PDF ↔ 答案解析 PDF 配对（difflib 名称相似度 + 年份/卷别约束），并标记扫描件 |
| `build_xingce.py` / `build_shenlun.py` | 批量抽取与合并，带文本缓存（`cache/`） |
| `finalize.py` | 生成稳定 ID、关键词标签、`data/*.jsonl`、`search-index.tsv`、`stats.json` |
| `gen_docs.py` / `gen_taxonomy_doc.py` | 生成人/模型可读的 Markdown 知识层 |

## 已知边界

- 扫描版 PDF（无文字层）不做 OCR：实测 Windows OCR 对答案字母（A–D）识别率仅 60–70%，错误答案比无答案更糟。这类卷保留题目、答案标 `null`。
- 图形推理、图表题的图是位图，只能保留题号、答案与解析中的规律说明。
- 双栏回忆版卷存在少量文字粘连，详见 `docs/coverage.md`。
