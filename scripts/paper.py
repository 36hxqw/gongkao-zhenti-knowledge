#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公考行测组卷 CLI（纯标准库，无第三方依赖）。

用法示例
--------
    # 资料分析 20 题（国考近八年），写入 Markdown 试卷
    python scripts/paper.py --module 资料分析 --count 20 --prov 国考 --years 2019-2026 --out out/paper-资料分析.md

    # 指定考点 10 题，固定随机种子（同一 seed + 同一题库可复现）
    python scripts/paper.py --code ZL-BILI --count 10 --seed 7 --with-answers

    # 图形推理 10 题，输出 JSON 给程序消费
    python scripts/paper.py --module 判断推理 --type 图形推理 --count 10 --format json

    # 组合模块（多次 --module 或逗号分隔），按模块分别给建议用时
    python scripts/paper.py --module 资料分析,判断推理 --count 30 --seed 1 --out out/paper-组合.md

组卷规则
--------
1. 过滤：--module / --type / --code / --prov / --years / --min-year；
   默认 --exclude-dup 只取 canonical == id 的主记录（同题变体折叠，--no-exclude-dup 可展开）。
2. 分组轮转：按考点 code 分组 → 组内 random.Random(seed) 打乱 →
   按「答案非空优先、年份倒序」排序 → 各考点轮流各取 1 题，直到凑满 --count。
   因此同一套卷里考点尽量分散、近年优先；题量不足时如实提示「可用 N 题（少于请求的 M 题）」，绝不重复凑数。
3. 配图：图形题（fig / 图形推理）与资料分析题若存在 references/images/<id>.jpg，则标注该相对路径。
4. 输出：Markdown（标题 + 试题 + 答案与考点页）或 JSON 数组（题库完整字段 + image）。

退出码：0 成功（含可用题量不足）；2 无结果或参数错误。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
IMAGES = os.path.join(BASE, "references", "images")

# 模块别名 -> 题库里的标准模块名
MODULE_ALIAS = {
    "资料分析": "资料分析", "资料": "资料分析", "zl": "资料分析",
    "判断推理": "判断推理", "判断": "判断推理", "pd": "判断推理",
    "言语理解": "言语理解", "言语": "言语理解", "yy": "言语理解",
    "数量关系": "数量关系", "数量": "数量关系", "sl": "数量关系",
    "常识判断": "常识判断", "常识": "常识判断", "cs": "常识判断",
    "申论": "申论", "sn": "申论",
}

# 模块展示顺序
MODULE_ORDER = {"资料分析": 0, "判断推理": 1, "言语理解": 2, "数量关系": 3, "常识判断": 4, "申论": 5}

# 建议用时基准：(基准题量, 基准分钟, 备注)；与花生十三的套题时间分配一致
MODULE_TIME = {
    "资料分析": (20, 25, ""),
    "判断推理": (40, 35, ""),
    "数量关系": (15, 12, "选做"),
    "言语理解": (40, 35, ""),
    "常识判断": (20, 8, ""),
}

PROV_ALIAS = {
    "国考": "国考", "国家": "国考", "国": "国考", "guokao": "国考", "gk": "国考",
    "广东": "广东", "广东省考": "广东", "gd": "广东",
    "湖北": "湖北", "湖北省考": "湖北", "hb": "湖北",
}

YEAR_SPLIT = re.compile(r"[,，、;；/\s]+")
YEAR_RANGE = re.compile(r"^(\d{4})\s*[-~—–至]\s*(\d{4})$")


def read_jsonl(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"缺少数据文件：{path}\n"
                 f"请先确认题库已生成（可运行 python scripts/selfcheck.py 自检）。")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_years(text):
    """把 '2024' / '2019-2026' / '2019,2021,2024' 解析成年份集合。"""
    years = set()
    # 允许「2019 - 2026」这种带空格的区间写法
    text = re.sub(r"\s*([-~—–至])\s*", r"\1", text.strip())
    for part in YEAR_SPLIT.split(text):
        if not part:
            continue
        m = YEAR_RANGE.match(part)
        if m:
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            years.update(range(lo, hi + 1))
            continue
        if re.fullmatch(r"\d{4}", part):
            years.add(int(part))
            continue
        raise ValueError(part)
    if not years:
        raise ValueError(text)
    return years


def describe_years(years):
    """把年份集合压回可读区间：'2019-2026' 或 '2019,2021,2024'。"""
    ys = sorted(years)
    if len(ys) > 1 and ys == list(range(ys[0], ys[-1] + 1)):
        return f"{ys[0]}-{ys[-1]}"
    return ",".join(str(y) for y in ys)


def split_modules(values):
    """展平 --module，支持多次传参、逗号/顿号/加号分隔。"""
    mods = []
    for raw in values:
        for tok in re.split(r"[,，、+/]+", raw):
            tok = tok.strip()
            if not tok:
                continue
            mod = MODULE_ALIAS.get(tok, MODULE_ALIAS.get(tok.lower(), tok))
            if mod not in mods:
                mods.append(mod)
    return mods


def match_code(rec, wants):
    """--code 支持考点编码（精确/前缀）与中文题型名（子串）。"""
    code = (rec.get("code") or "").upper()
    for w in wants:
        wu = w.strip().upper()
        if not wu:
            continue
        if code == wu:
            return True
        if re.fullmatch(r"[A-Z]{2}", wu) and code.startswith(wu + "-"):
            return True
        if w in (rec.get("type") or ""):
            return True
    return False


def image_path(rec):
    """图形题与资料分析题若已生成配图，返回仓库相对路径（POSIX 分隔符）。"""
    looks_figure = bool(rec.get("fig")) or "图形" in (rec.get("type") or "")
    if rec.get("module") != "资料分析" and not looks_figure:
        return None
    name = rec["id"] + ".jpg"
    if not os.path.exists(os.path.join(IMAGES, name)):
        return None
    return "references/images/" + name


def pick_questions(recs, count, seed):
    """按考点分组轮转抽题：考点尽量分散、组内答案非空优先、近年优先。"""
    groups = {}
    for r in recs:
        groups.setdefault(r["code"], []).append(r)

    rnd = random.Random(seed)
    codes = sorted(groups)
    for code in codes:
        pool = groups[code]
        rnd.shuffle(pool)
        # 稳定排序：答案非空优先（False < True），同条件下年份倒序，同年内保持打乱顺序
        pool.sort(key=lambda r: (not bool(r.get("ans")), -(r.get("year") or 0)))
    rnd.shuffle(codes)

    picked = []
    level = 0
    while len(picked) < count:
        moved = False
        for code in codes:
            pool = groups[code]
            if level < len(pool):
                picked.append(pool[level])
                moved = True
                if len(picked) == count:
                    break
        if not moved:
            break
        level += 1
    return picked


def time_plan(picked):
    """按模块统计建议用时，返回 (总分钟, [(模块, 题数, 分钟, 备注)])。"""
    cnt = Counter(r["module"] for r in picked)
    mods = sorted(cnt, key=lambda m: MODULE_ORDER.get(m, 99))
    total = 0
    rows = []
    for mod in mods:
        n = cnt[mod]
        spec = MODULE_TIME.get(mod)
        if not spec:
            rows.append((mod, n, None, ""))
            continue
        base_n, base_min, tag = spec
        minutes = max(1, round(n * base_min / base_n))
        total += minutes
        rows.append((mod, n, minutes, tag))
    return total, rows


def time_text(picked):
    total, rows = time_plan(picked)
    known = [r for r in rows if r[2] is not None]
    if not known:
        return f"按行测整体节奏控制在 {max(1, round(len(picked) * 0.9))} 分钟内（该模块无基准用时）"
    if len(known) == 1:
        mod, n, minutes, tag = known[0]
        base_n, base_min, _ = MODULE_TIME[mod]
        tail = "，选做" if tag else ""
        return f"{minutes} 分钟（{mod} {n} 题；基准 {base_n} 题 ≈ {base_min} 分钟{tail}）"
    parts = []
    for mod, n, minutes, tag in known:
        parts.append(f"{mod} {n} 题 {minutes} 分钟" + ("（选做）" if tag else ""))
    return f"合计 {total} 分钟（按模块分别计算：{'；'.join(parts)}）"


def one_line(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def cell(text):
    return one_line(text).replace("|", "／")


def render_question(idx, rec):
    out = []
    num = rec.get("num") or rec.get("no") or "?"
    out.append(f"### {idx}. {rec['type']}｜{rec['prov']} {rec['year']} {rec['vol']} 第 {num} 题")
    out.append("")

    ctx = one_line(rec.get("ctx"))
    if ctx:
        out.append(f"> **材料**：{ctx}")
        out.append("")

    stem = one_line(rec.get("stem"))
    img = image_path(rec)
    if stem:
        out.append(f"**题干**：{stem}")
    else:
        out.append("**题干**：（原卷题干为图形/公式，见下方配图）")
    out.append("")

    opts = {k: one_line(v) for k, v in (rec.get("opts") or {}).items()}
    if opts and any(opts.values()):
        for key in sorted(opts):
            value = opts[key] or ("（见配图）" if img else "（原卷缺此选项）")
            out.append(f"- **{key}.** {value}")
    elif img:
        out.append("- （原卷选项为图形/表格，见下方配图）")
    else:
        out.append("- （原卷无选项文本）")
    out.append("")

    if img:
        out.append(f"![{rec['id']} 原题配图]({img})")
        out.append("")
    return out


def render_answers(picked):
    out = ["## 二、答案与考点", ""]
    out.append("| 题号 | 答案 | 模块·题型 | 考点 | id | 解析节选 |")
    out.append("|---:|---|---|---|---|---|")
    for i, rec in enumerate(picked, 1):
        ans = rec.get("ans") or "—"
        expl = cell(rec.get("expl"))
        if len(expl) > 200:
            expl = expl[:200] + "…"
        if not expl:
            expl = "（原卷无解析）"
        out.append(f"| {i} | {ans} | {cell(rec['module'] + '·' + rec['type'])} | "
                   f"{rec['code']} | `{rec['id']}` | {expl} |")
    out.append("")
    return out


def render_md(picked, total_avail, filters_desc, seed, count_requested):
    mods = []
    for r in picked:
        if r["module"] not in mods:
            mods.append(r["module"])
    mods.sort(key=lambda m: MODULE_ORDER.get(m, 99))
    title = "、".join(mods) if mods else "全部模块"

    lines = [f"# 行测组卷 · {title}（{len(picked)} 题）", ""]
    lines.append(f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **筛选条件**：{filters_desc}")
    lines.append(f"- **题量**：{len(picked)} 题（候选 {total_avail} 题，按考点轮转抽取）")
    lines.append(f"- **建议用时**：{time_text(picked)}")
    if seed is None:
        lines.append("- **随机种子**：未指定（本次随机，--seed N 可复现）")
    else:
        lines.append(f"- **随机种子**：{seed}（同一 seed + 同一题库可复现）")
    dist = Counter(r["code"] for r in picked)
    if dist:
        parts = [f"{code} {n}" for code, n in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))]
        lines.append(f"- **考点分布**：{'、'.join(parts)}（共 {len(dist)} 个考点）")
    if len(picked) < count_requested:
        lines.append(f"- **提示**：可用 {len(picked)} 题（少于请求的 {count_requested} 题），"
                     f"已按实际题量出卷，未重复凑数；可放宽 --years/--prov 或去掉 --type 再组。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、试题")
    lines.append("")
    for i, rec in enumerate(picked, 1):
        lines.extend(render_question(i, rec))
    if picked:
        lines.extend(render_answers(picked))
    return "\n".join(lines).rstrip() + "\n"


def record_for_json(rec):
    out = dict(rec)
    out["image"] = image_path(rec)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="公考行测组卷：按考点轮转抽题，输出 Markdown 试卷或 JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python scripts/paper.py --module 资料分析 --count 20 --prov 国考 "
               "--years 2019-2026 --out out/paper-资料分析.md")
    ap.add_argument("--module", action="append", default=[],
                    help="模块：资料分析/数量关系/言语理解/判断推理/常识判断；可多次或逗号分隔")
    ap.add_argument("--type", dest="type_", help="题型（子串匹配），如 图形推理、综合分析")
    ap.add_argument("--code", action="append", default=[],
                    help="考点编码或中文题型名，可多次，如 ZL-BILI / 比重计算与比较")
    ap.add_argument("--prov", help="省份：国考/广东/湖北")
    ap.add_argument("--years", help="年份或区间：2024 或 2019-2026（也支持 2019,2021,2024）")
    ap.add_argument("--min-year", type=int, help="只取不早于该年的题，如 --min-year 2022")
    ap.add_argument("--count", type=int, default=20, help="题量，默认 20")
    ap.add_argument("--seed", type=int, help="随机种子；同一 seed + 同一题库可复现同一套卷")
    ap.add_argument("--with-answers", dest="with_answers", action="store_true", default=True,
                    help="附带「答案与考点」页（默认开启）")
    ap.add_argument("--no-answers", dest="with_answers", action="store_false",
                    help="不输出答案页，适合先自测再对答案")
    ap.add_argument("--format", dest="fmt", choices=["md", "json"], default="md",
                    help="输出格式：md（默认）或 json")
    ap.add_argument("--out", help="输出文件路径，如 out/paper-资料分析.md；缺省打印到终端")
    ap.add_argument("--exclude-dup", action=argparse.BooleanOptionalAction, default=True,
                    help="只取 canonical==id 的主记录（默认开启；--no-exclude-dup 展开同题变体）")
    ap.add_argument("--shenlun", action="store_true", help="申论组卷（接口预留，本轮暂不支持）")
    args = ap.parse_args(argv)

    if args.shenlun:
        print("暂不支持：paper.py 本轮只组行测卷。\n"
              "申论请用 python scripts/search.py --shenlun --kw 概括 --limit 5 逐题检索，"
              "或先用 python scripts/wrongbook.py add 记录申论错题。", file=sys.stderr)
        return 2
    if args.count <= 0:
        print("--count 必须为正整数，例如 --count 20。", file=sys.stderr)
        return 2

    mods = split_modules(args.module)
    prov = None
    if args.prov:
        key = args.prov.strip()
        prov = PROV_ALIAS.get(key) or PROV_ALIAS.get(key.lower()) or key

    years = None
    if args.years:
        try:
            years = parse_years(args.years)
        except ValueError:
            print(f"--years 格式不对：{args.years}\n"
                  f"正确写法：2024 或 2019-2026 或 2019,2021,2024。", file=sys.stderr)
            return 2

    recs = read_jsonl("xingce.jsonl")
    sel = recs
    if mods:
        sel = [r for r in sel if any(r["module"] == m or m in r["module"] for m in mods)]
    if args.type_:
        sel = [r for r in sel if args.type_ in (r.get("type") or "")]
    if args.code:
        sel = [r for r in sel if match_code(r, args.code)]
    if prov:
        sel = [r for r in sel if r["prov"] == prov]
    if years is not None:
        sel = [r for r in sel if r["year"] in years]
    if args.min_year:
        sel = [r for r in sel if (r.get("year") or 0) >= args.min_year]
    if args.exclude_dup:
        sel = [r for r in sel if r.get("canonical", r["id"]) == r["id"]]

    if not sel:
        print("未命中任何题目，无法组卷。建议：\n"
              "  ① 放宽年份：--years 2015-2026（或去掉 --years）\n"
              "  ② 去掉省份限制：--prov 国考 换成 广东/湖北，或不加 --prov\n"
              "  ③ 换模块/题型：--module 资料分析、--type 图形推理\n"
              "  ④ 换考点编码：--code ZL-BILI（先用 python scripts/search.py --list-kaodian 查编码）\n"
              "  ⑤ 展开同题变体：加 --no-exclude-dup", file=sys.stderr)
        return 2

    picked = pick_questions(sel, args.count, args.seed)

    filters = []
    if mods:
        filters.append("模块=" + "、".join(mods))
    if args.type_:
        filters.append("题型=" + args.type_)
    if args.code:
        filters.append("考点=" + "、".join(args.code))
    if prov:
        filters.append("省份=" + prov)
    if years is not None:
        filters.append("年份=" + describe_years(years))
    if args.min_year:
        filters.append(f"起始年>={args.min_year}")
    if not args.exclude_dup:
        filters.append("含同题变体")
    filters_desc = "；".join(filters) or "全部题库"

    if args.fmt == "json":
        payload = json.dumps([record_for_json(r) for r in picked], ensure_ascii=False, indent=1)
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload + "\n")
            print(f"已生成组卷（JSON）：{args.out}")
        else:
            print(payload)
    else:
        md = render_md(picked, len(sel), filters_desc, args.seed, args.count)
        if not args.with_answers:
            cut = md.find("## 二、答案与考点")
            if cut > 0:
                md = md[:cut].rstrip() + "\n"
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(md)
            print(f"已生成组卷：{args.out}")
            print(f"题量：{len(picked)} 题（候选 {len(sel)} 题）｜建议用时：{time_text(picked)}")
            dist = Counter(r["code"] for r in picked)
            print("考点分布：" + "、".join(f"{c} {n}" for c, n in
                                      sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))))
        else:
            print(md, end="")

    if len(picked) < args.count:
        print(f"注意：可用 {len(picked)} 题（少于请求的 {args.count} 题），已按实际题量出卷，未重复凑数。",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
