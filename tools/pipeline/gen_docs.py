# -*- coding: utf-8 -*-
"""Generate markdown reference files for the skill."""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import TAXONOMY  # noqa: E402

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REF = os.path.join(REPO, "references")

MODULE_ORDER = ["资料分析", "数量关系", "言语理解", "判断推理", "常识判断", "申论"]
CODE_ORDER = {c: i for i, c in enumerate(TAXONOMY)}
PROV_ORDER = {"国考": 0, "广东": 1, "湖北": 2}


def load(name):
    with open(os.path.join(REPO, "data", name), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "-", s)


def md_opts(opts):
    if not opts:
        return "> （本题为图形题，选项为图片，见原卷）\n"
    lines = []
    for k in "ABCD":
        if k in opts:
            lines.append(f"- **{k}.** {opts[k]}")
    return "\n".join(lines) + "\n"


def year_span(recs):
    ys = sorted({r["year"] for r in recs if r["year"]})
    if not ys:
        return "—"
    return f"{ys[0]}–{ys[-1]}" if ys[0] != ys[-1] else str(ys[0])


def prov_line(recs):
    c = collections.Counter(r["prov"] for r in recs)
    return " / ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: PROV_ORDER.get(kv[0], 9)))


def gen_kaodian(x, s):
    d = os.path.join(REF, "kaodian")
    os.makedirs(d, exist_ok=True)
    by_code = collections.defaultdict(list)
    for r in x:
        by_code[r["code"]].append(r)
    for r in s:
        by_code[r["code"]].append(r)
    index_rows = []
    for code in sorted(by_code, key=lambda c: (MODULE_ORDER.index(TAXONOMY[c][0]) if TAXONOMY[c][0] in MODULE_ORDER else 9, CODE_ORDER[c])):
        recs = by_code[code]
        mod, typ, ref = TAXONOMY[code]
        recs.sort(key=lambda r: (r["year"], PROV_ORDER.get(r["prov"], 9)), reverse=True)
        yrs = collections.Counter(r["year"] for r in recs)
        fname = f"{code}-{safe_name(typ)}.md"
        body = [f"# {mod} · {typ}", ""]
        body.append(f"> 考点编码：`{code}`　｜　体系对齐：花生十三 `{ref}`")
        body.append("")
        body.append("## 一、命题规律")
        body.append("")
        body.append(f"- **本题型真题总量**：{len(recs)} 题（{year_span(recs)}）")
        body.append(f"- **地区分布**：{prov_line(recs)}")
        top_years = ", ".join(f"{y}年{int(c)}题" for y, c in sorted(yrs.items(), reverse=True)[:6])
        body.append(f"- **近六年题量**：{top_years}")
        papers = len({(r["prov"], r["year"], r["vol"]) for r in recs})
        body.append(f"- **覆盖试卷**：{papers} 套")
        if code.startswith("ZL-") or code.startswith("SL-"):
            body.append(f"- **速算/速解提示**：见花生十三 `references/ziliao-susuan.md` 与 "
                        f"`references/shuliang-gongshi.md` 对应章节")
        body.append("")
        body.append("## 二、真题与答案（按年份倒序，最多 30 题）")
        body.append("")
        for r in recs[:30]:
            body.append(f"### {r['year']} {r['prov']}·{r['vol']}　第 {r['num'] if 'num' in r else r.get('no','')} 题")
            if r.get("ctx"):
                ctx = r["ctx"][:300].replace("\n", " ")
                body.append(f"> 材料：{ctx[:300]}…")
            body.append("")
            body.append(r["stem"])
            body.append("")
            body.append(md_opts(r.get("opts") or {}))
            body.append(f"**答案：{r.get('ans') or '暂缺（原始文件为扫描版）'}**")
            body.append("")
            expl = (r.get("expl") or "").strip()
            if code.startswith("SN-"):
                expl = (r.get("ans") or "").strip()
            if expl:
                body.append(f"**解析/参考要点**：{expl[:700]}")
                body.append("")
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        index_rows.append((mod, typ, code, len(recs), year_span(recs), prov_line(recs), fname))
    return index_rows


def gen_juan(x):
    d = os.path.join(REF, "juan")
    os.makedirs(d, exist_ok=True)
    groups = collections.defaultdict(list)
    for r in x:
        groups[(r["prov"], r["year"], r["vol"])].append(r)
    rows = []
    for key in sorted(groups, key=lambda k: (PROV_ORDER.get(k[0], 9), k[1], k[2])):
        recs = sorted(groups[key], key=lambda r: r["num"])
        prov, year, vol = key
        fname = f"{prov}-{year}-{vol}.md"
        modcnt = collections.Counter(r["module"] for r in recs)
        withans = sum(1 for r in recs if r.get("ans"))
        body = [f"# {year} 年{prov}行测（{vol}）", ""]
        body.append(f"- 题量：{len(recs)}（含答案 {withans}）")
        body.append("- 模块分布：" + " / ".join(f"{m}{modcnt[m]}" for m in MODULE_ORDER if modcnt[m]))
        body.append(f"- 试卷编号：`{key[0]}-{year}-{vol}`")
        body.append("")
        body.append("## 题目与答案")
        body.append("")
        for r in recs:
            body.append(f"**【{r['module']}·{r['type']}｜{r['id']}】**")
            if r.get("ctx"):
                body.append(f"> 材料：{r['ctx'][:400]}")
            body.append("")
            body.append(f"{r['num']}. {r['stem']}")
            body.append("")
            body.append(md_opts(r.get("opts") or {}))
            body.append(f"**答案：{r.get('ans') or '暂缺'}**　**考点：{r['type']}**")
            body.append("")
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        rows.append((prov, year, vol, len(recs), withans, fname))
    return rows


def gen_shenlun(s):
    d = os.path.join(REF, "shenlun")
    os.makedirs(d, exist_ok=True)
    groups = collections.defaultdict(list)
    for r in s:
        groups[(r["prov"], r["year"], r["vol"], r["paper"])].append(r)
    rows = []
    for key in sorted(groups, key=lambda k: (PROV_ORDER.get(k[0], 9), k[1], k[2])):
        recs = sorted(groups[key], key=lambda r: r["id"])
        prov, year, vol, paper = key
        fname = f"{prov}-{year}-{vol}.md"
        body = [f"# {year} 年{prov}申论（{vol}）", ""]
        body.append(f"- 题量：{len(recs)}　｜　试卷编号：`{paper}`")
        body.append("- 题型：" + " / ".join(f"{r['type']}" for r in recs))
        body.append("")
        body.append("## 一、给定材料")
        body.append("")
        body.append(recs[0].get("material") or "（材料见原卷）")
        body.append("")
        body.append("## 二、题目")
        body.append("")
        for r in recs:
            body.append(f"**{r['no']}｜{r['type']}｜`{r['id']}`**")
            body.append("")
            body.append(r["stem"])
            body.append("")
        body.append("## 三、参考答案")
        body.append("")
        for r in recs:
            body.append(f"### {r['no']}（{r['type']}）")
            body.append("")
            body.append(r.get("ans") or "（本卷参考答案未能从原始 PDF 中提取，请对照原卷）")
            body.append("")
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        rows.append((prov, year, vol, len(recs), fname))
    return rows


def gen_overview(x, s, kd_rows, juan_rows, sn_rows):
    stats = json.load(open(os.path.join(REPO, "data", "stats.json"), encoding="utf-8"))
    # year x module for 国考/广东/湖北
    def matrix(prov):
        cnt = collections.defaultdict(collections.Counter)
        for r in x:
            if r["prov"] == prov:
                cnt[r["year"]][r["module"]] += 1
        return cnt

    lines = ["# 命题规律总览", ""]
    lines.append(f"> 数据源：{stats['generated_from']}；行测 {stats['xingce']['total']} 题，"
                 f"申论 {stats['shenlun']['total']} 题。")
    lines.append("")
    lines.append("## 一、总体结构")
    lines.append("")
    lines.append("| 模块 | 行测题量 | 占比 |")
    lines.append("|---|---:|---:|")
    tot = stats["xingce"]["total"]
    for m in MODULE_ORDER[:-1]:
        c = stats["xingce"]["by_module"].get(m, 0)
        lines.append(f"| {m} | {c} | {c / tot * 100:.1f}% |")
    lines.append("")
    lines.append("## 二、分省模块题量")
    lines.append("")
    for prov in ("国考", "广东", "湖北"):
        mtx = matrix(prov)
        years = sorted(mtx)
        if not years:
            continue
        lines.append(f"### {prov}（{years[0]}–{years[-1]}，{len(years)} 个年度；同一年度多卷合计）")
        lines.append("")
        lines.append("| 年份 | " + " | ".join(m for m in MODULE_ORDER[:-1]) + " | 合计 |")
        lines.append("|---|" + "---:|" * len(MODULE_ORDER[:-1]) + "---:|")
        for y in years:
            row = [mtx[y].get(m, 0) for m in MODULE_ORDER[:-1]]
            lines.append(f"| {y} | " + " | ".join(str(v) for v in row) + f" | {sum(row)} |")
        lines.append("")
    # 高频考点
    top = sorted(kd_rows, key=lambda r: -r[3])
    lines.append("## 三、高频考点 TOP 20")
    lines.append("")
    lines.append("| 排名 | 考点 | 编码 | 题量 | 年份跨度 | 地区分布 |")
    lines.append("|---:|---|---|---:|---|---|")
    for i, (mod, typ, code, n, span, prov, fname) in enumerate(top[:20], 1):
        lines.append(f"| {i} | {mod}·{typ} | `{code}` | {n} | {span} | {prov} |")
    lines.append("")
    # 变迁
    lines.append("## 四、题型变迁观察")
    lines.append("")
    def span_of(code):
        ys = sorted({r["year"] for r in x if r["code"] == code})
        return (ys[0], ys[-1], len(ys)) if ys else None
    for code in ("SL-SZ", "CS-ZZ", "YY-YJPX", "PD-KX", "ZL-YEAR"):
        sp = span_of(code)
        if sp:
            lines.append(f"- `{code}` {TAXONOMY[code][1]}：{sp[0]}–{sp[1]}，出现于 {sp[2]} 个年度")
    new_pol = sorted({r["year"] for r in x if r["module"] == "常识判断" and r["type"] == "政治常识"})
    if new_pol:
        lines.append(f"- 政治理论/政治常识在 {new_pol[-1]} 年国考中被单列为独立板块（2025 年起）")
    lines.append("")
    lines.append("## 五、申论题型分布")
    lines.append("")
    sc = collections.Counter(r["type"] for r in s)
    for t, c in sc.most_common():
        lines.append(f"- {t}：{c} 题")
    lines.append("")
    with open(os.path.join(REF, "01-命题规律总览.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def gen_index(kd_rows, juan_rows, sn_rows):
    lines = ["# 真题库索引", ""]
    lines.append("## 一、按考点检索（`references/kaodian/`）")
    lines.append("")
    cur = None
    for mod, typ, code, n, span, prov, fname in kd_rows:
        if mod != cur:
            lines.append("")
            lines.append(f"### {mod}")
            lines.append("")
            lines.append("| 考点 | 编码 | 题量 | 年份跨度 | 文件 |")
            lines.append("|---|---|---:|---|---|")
            cur = mod
        lines.append(f"| {typ} | `{code}` | {n} | {span} | [{fname}](kaodian/{fname}) |")
    lines.append("")
    lines.append("## 二、按试卷检索（`references/juan/` 行测、`references/shenlun/` 申论）")
    lines.append("")
    lines.append("| 地区 | 年份 | 卷别 | 题量 | 有答案 | 文件 |")
    lines.append("|---|---|---|---:|---:|---|")
    for prov, year, vol, n, wa, fname in juan_rows:
        lines.append(f"| {prov} | {year} | {vol} | {n} | {wa} | [{fname}](juan/{fname}) |")
    lines.append("")
    lines.append("| 地区 | 年份 | 卷别 | 题量 | 文件 |")
    lines.append("|---|---|---|---:|---|")
    for prov, year, vol, n, fname in sn_rows:
        lines.append(f"| {prov} | {year} | {vol} | {n} | [{fname}](shenlun/{fname}) |")
    lines.append("")
    with open(os.path.join(REF, "00-index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    x = load("xingce.jsonl")
    s = load("shenlun.jsonl")
    kd = gen_kaodian(x, s)
    juan = gen_juan(x)
    sn = gen_shenlun(s)
    gen_index(kd, juan, sn)
    gen_overview(x, s, kd, juan, sn)
    print("kaodian files", len(kd), "juan", len(juan), "shenlun", len(sn))


if __name__ == "__main__":
    main()
