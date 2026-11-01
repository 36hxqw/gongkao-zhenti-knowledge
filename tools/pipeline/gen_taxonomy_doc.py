# -*- coding: utf-8 -*-
"""Emit docs/kaodian-taxonomy.md from the classifier taxonomy + live counts."""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import TAXONOMY  # noqa: E402

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MODULE_ORDER = ["资料分析", "数量关系", "言语理解", "判断推理", "常识判断", "申论"]
MODULE_REF = {
    "资料分析": "`references/ziliao-fenxi.md`、`ziliao-susuan.md`、`ziliao-zonghe.md`",
    "数量关系": "`references/shuliang-guanxi.md`、`shuliang-gongshi.md`",
    "言语理解": "`references/yanyu-lianjie.md`、`yanyu-ciyu.md`、`yanyu-zhuanxiang.md`",
    "判断推理": "`references/panduan-tuili.md`、`panduan-guilv.md`、`panduan-tuxing.md`",
    "常识判断": "`references/changshi-panduan.md`、`shizheng-redian.md`",
    "申论": "`references/shenlun.md`、`shenlun-biaoda.md`、`shenlun-sucai.md`",
}


def main():
    x = [json.loads(l) for l in open(os.path.join(REPO, "data", "xingce.jsonl"), encoding="utf-8")]
    s = [json.loads(l) for l in open(os.path.join(REPO, "data", "shenlun.jsonl"), encoding="utf-8")]
    cnt = collections.Counter(r["code"] for r in x + s)
    by_year = collections.defaultdict(set)
    for r in x + s:
        if r["year"]:
            by_year[r["code"]].add(r["year"])

    lines = ["# 考点体系（完全对齐 gongkao-huasheng13）", ""]
    lines.append("本表是本库唯一的考点字典：题目标注、检索键、`references/kaodian/` 文件名均由此表派生。")
    lines.append("")
    lines.append("**对齐原则**")
    lines.append("")
    lines.append("1. 模块名、题型名、子题型名一律沿用 `gongkao-huasheng13` 的表述，不改写、不合并、不新增二级体系。")
    lines.append("2. 体系未单列的旧题型（数字推理、科学推理）只做「模块级对齐 + 显式标注」，在表中标记为「体系外补充」。")
    lines.append("3. 一个考点 = 一个 `code`；`code` 只用于检索与文件命名，展示时始终用中文题型名。")
    lines.append("")
    lines.append("**编码规则**：`模块前缀-题型缩写`。ZL=资料分析，SL=数量关系，YY=言语理解，PD=判断推理，CS=常识判断，SN=申论。")
    lines.append("")
    total = sum(cnt.values())
    lines.append(f"**总题量**：{total} 题（行测 {len(x)} + 申论 {len(s)}）")
    lines.append("")

    for mod in MODULE_ORDER:
        codes = [c for c in TAXONOMY if TAXONOMY[c][0] == mod]
        codes.sort(key=lambda c: list(TAXONOMY).index(c))
        lines.append(f"## {mod}")
        lines.append("")
        lines.append(f"花生十三对应文件：{MODULE_REF.get(mod, '')}")
        lines.append("")
        lines.append("| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |")
        lines.append("|---|---|---:|---|---|")
        for c in codes:
            m, t, ref = TAXONOMY[c]
            ys = sorted(by_year.get(c, []))
            span = f"{ys[0]}–{ys[-1]}" if ys else "—"
            lines.append(f"| `{c}` | {t} | {cnt.get(c, 0)} | {span} | {ref} |")
        lines.append("")
        sub = [c for c in codes if cnt.get(c, 0) == 0]
        if sub:
            lines.append("> 本库未命中的题型（存量真题中未出现或抽取失败）：" +
                         "、".join(f"`{c}`" for c in sub))
            lines.append("")

    lines.append("## 体系外补充说明")
    lines.append("")
    lines.append("| 编码 | 题型 | 处理方式 |")
    lines.append("|---|---|---|")
    lines.append("| `SL-SZ` | 数字推理 | 花生十三数量关系体系未单列；国考 2000–2012、广东/湖北联考旧卷大量出现，"
                 "按语义归入数量关系模块，题名沿用真题叫法「数字推理」 |")
    lines.append("| `PD-KX` | 科学推理 | 广东特色题型（物理/化学/生物），花生十三判断推理体系未单列；"
                 "按语义归入判断推理模块 |")
    lines.append("")
    lines.append("## 与技巧层的调用契约")
    lines.append("")
    lines.append("```")
    lines.append("用户问题 → 判定考点 code → 本库取原题与答案")
    lines.append("                       ↘ 按上表 ref 读取 gongkao-huasheng13 对应章节 → 输出方法/速算/易错点")
    lines.append("```")
    lines.append("")
    lines.append("资料分析、数量关系的题必须给出速算过程（截位直除 / 415 份数 / 假设分配 / 代入排除）；")
    lines.append("言语、判断必须给「识别标志 + 排除顺序」；申论必须给「采分点结构」。")
    with open(os.path.join(REPO, "docs", "kaodian-taxonomy.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote taxonomy doc", total)


if __name__ == "__main__":
    main()
