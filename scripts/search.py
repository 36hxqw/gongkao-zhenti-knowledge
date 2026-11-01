#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公考真题知识库检索 CLI。

用法示例
--------
    # 单考点 + 省份
    python scripts/search.py --kaodian ZL-BASE --prov 国考

    # 多关键词 AND（零散知识点组合定位）
    python scripts/search.py --kw 基期 --kw 比重 --kw 百分点

    # 任一词命中（OR）
    python scripts/search.py --any 新质生产力 低空经济 未来产业 --limit 8

    # 年份 + 模块 + 只要题干摘要
    python scripts/search.py --year 2024 --module 判断推理

    # 按 ID 取完整题目（含解析）
    python scripts/search.py --id GK-2025-fs-X010 --full

    # 输出 JSON（供程序消费）
    python scripts/search.py --kw 黑土地 --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

# 口语 -> 考点编码 的同义词扩展（与花生十三体系一致）
SYNONYMS = {
    "基期": ["ZL-BASE", "基期量"],
    "现期": ["ZL-BASE"],
    "增长量": ["ZL-GROW"],
    "增量": ["ZL-GROW"],
    "增长率": ["ZL-RATE"],
    "增速": ["ZL-RATE"],
    "增幅": ["ZL-RATE"],
    "比重": ["ZL-BILI"],
    "占比": ["ZL-BILI"],
    "平均数": ["ZL-AVG"],
    "人均": ["ZL-AVG"],
    "倍数": ["ZL-BEI"],
    "年均": ["ZL-YEAR"],
    "拉动": ["ZL-PULL"],
    "贡献率": ["ZL-PULL"],
    "综合分析": ["ZL-COMP"],
    "工程": ["SL-GC"],
    "行程": ["SL-XC"],
    "利润": ["SL-LR"],
    "排列组合": ["SL-PL"],
    "概率": ["SL-GL"],
    "容斥": ["SL-RC"],
    "最值": ["SL-ZZ"],
    "年龄": ["SL-NL"],
    "几何": ["SL-JH"],
    "溶液": ["SL-SR", "SL-RY"],
    "牛吃草": ["SL-NCC"],
    "鸡兔同笼": ["SL-JT"],
    "数字推理": ["SL-SZ"],
    "逻辑填空": ["YY-LJTK"],
    "选词填空": ["YY-LJTK"],
    "中心理解": ["YY-ZXJL"],
    "主旨": ["YY-ZXJL"],
    "意图": ["YY-ZXJL"],
    "细节判断": ["YY-XJPD"],
    "标题": ["YY-BTTR"],
    "语句填入": ["YY-YJTR"],
    "下文推断": ["YY-XWTD"],
    "语句衔接": ["YY-YJXH"],
    "语句排序": ["YY-YJPX"],
    "篇章阅读": ["YY-PZYD"],
    "图形推理": ["PD-TX"],
    "定义判断": ["PD-DY"],
    "类比推理": ["PD-LB"],
    "逻辑判断": ["PD-LJ"],
    "翻译推理": ["PD-LJ"],
    "真假推理": ["PD-LJ"],
    "加强削弱": ["PD-LJ"],
    "科学推理": ["PD-KX"],
    "政治": ["CS-ZZ"],
    "法律": ["CS-FL"],
    "经济": ["CS-JJ"],
    "历史": ["CS-LS"],
    "人文": ["CS-LS"],
    "地理": ["CS-DL"],
    "科技": ["CS-KJ"],
    "时政": ["CS-SZ"],
    "生活": ["CS-SH"],
    "申论": ["SN-DY", "SN-ZH", "SN-DC", "SN-GW", "SN-DZW"],
    "概括": ["SN-DY"],
    "对策": ["SN-DC"],
    "公文": ["SN-GW"],
    "大作文": ["SN-DZW"],
}

PROV_ALIAS = {
    "国考": "国考", "国家": "国考", "国": "国考", "guokao": "国考",
    "广东": "广东", "广东省考": "广东", "gd": "广东",
    "湖北": "湖北", "湖北省考": "湖北", "hb": "湖北",
}


def _read_jsonl(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"缺少数据文件：{path}")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def norm(s):
    return (s or "").strip().lower()


def match_keywords(rec, kws):
    hay = " ".join([
        rec.get("stem", ""), rec.get("ctx", ""), rec.get("material", ""),
        " ".join((rec.get("opts") or {}).values()),
        rec.get("expl", ""), rec.get("ans", "") or "",
        " ".join(rec.get("kw") or []),
        rec.get("type", ""), rec.get("module", ""), rec.get("code", ""),
    ])
    return all(k.lower() in hay for k in kws)


def match_any(rec, kws):
    hay = " ".join([
        rec.get("stem", ""), rec.get("ctx", ""), rec.get("material", ""),
        " ".join((rec.get("opts") or {}).values()),
        rec.get("expl", ""), " ".join(rec.get("kw") or []),
    ])
    return any(k.lower() in hay for k in kws)


def expand_codes(words):
    codes = set()
    for w in words:
        for key, vals in SYNONYMS.items():
            if w == key or w in key:
                codes.update(v for v in vals if v.startswith(("ZL", "SL", "YY", "PD", "CS", "SN")))
    return codes


def fmt(rec, full=False, show_expl=True):
    head = f"[{rec['id']}] {rec['year']} {rec['prov']}·{rec['vol']}"
    num = rec.get("num") or rec.get("no")
    head += f" 第 {num} 题　| {rec['module']}·{rec['type']}（{rec['code']}）"
    out = [head]
    if rec.get("ctx"):
        ctx = rec["ctx"] if full else rec["ctx"][:160] + ("…" if len(rec["ctx"]) > 160 else "")
        out.append(f"  材料：{ctx}")
    out.append(f"  题干：{rec['stem']}")
    opts = rec.get("opts") or {}
    if opts:
        line = "  " + "　".join(f"{k}. {v}" for k, v in opts.items())
        out.append(line)
    img = os.path.join(BASE, "references", "images", rec["id"] + ".jpg")
    if os.path.exists(img):
        out.append(f"  配图：references/images/{rec['id']}.jpg")
    if rec.get("dup_n", 1) > 1:
        out.append(f"  （同题另有 {rec['dup_n'] - 1} 个变体，--all-variants 展开）")
    out.append(f"  【答案】{rec.get('ans') or '暂缺（原卷为扫描版）'}")
    if show_expl and rec.get("expl"):
        expl = rec["expl"] if full else rec["expl"][:220] + ("…" if len(rec["expl"]) > 220 else "")
        out.append(f"  【解析】{expl}")
    if rec.get("code", "").startswith("SN") and rec.get("ans"):
        out.append(f"  【参考答案】{rec['ans'] if full else rec['ans'][:220] + '…'}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="公考真题知识库检索")
    ap.add_argument("--kw", action="append", default=[], help="关键词，可多次；多个为 AND")
    ap.add_argument("--any", nargs="*", default=[], help="任一词命中（OR）")
    ap.add_argument("--kaodian", "--code", dest="kaodian", action="append", default=[],
                    help="考点编码或考点名（如 ZL-BASE / 基期量计算）")
    ap.add_argument("--module", help="模块：资料分析/数量关系/言语理解/判断推理/常识判断/申论")
    ap.add_argument("--type", dest="type_", help="题型名，如 图形推理")
    ap.add_argument("--year", type=int, action="append", default=[], help="年份，可多次（OR）")
    ap.add_argument("--from-year", type=int, help="起始年份")
    ap.add_argument("--to-year", type=int, help="结束年份")
    ap.add_argument("--prov", help="国考/广东/湖北")
    ap.add_argument("--vol", help="卷别：副省级/地市级/行政执法/县级/乡镇/统一卷…")
    ap.add_argument("--id", dest="qid", help="按 ID 精确取题")
    ap.add_argument("--limit", type=int, default=5, help="返回条数，默认 5")
    ap.add_argument("--full", action="store_true", help="输出完整题干与解析")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--shenlun", action="store_true", help="只检索申论")
    ap.add_argument("--xingce", action="store_true", help="只检索行测")
    ap.add_argument("--list-kaodian", action="store_true", help="列出全部考点及题量")
    ap.add_argument("--all-variants", action="store_true", help="展开同题变体（默认折叠，只出主记录）")
    args = ap.parse_args(argv)

    xingce = [] if args.shenlun else _read_jsonl("xingce.jsonl")
    shenlun = [] if args.xingce else _read_jsonl("shenlun.jsonl")
    recs = xingce + shenlun

    if args.list_kaodian:
        from collections import Counter
        cnt = Counter((r["module"], r["type"], r["code"]) for r in recs)
        for (mod, typ, code), n in sorted(cnt.items(), key=lambda kv: (kv[0][0], -kv[1])):
            print(f"{code:8s} {mod}·{typ}  {n} 题")
        return 0

    sel = recs
    if args.qid:
        sel = [r for r in sel if r["id"].upper() == args.qid.upper()]
    if args.prov:
        p = PROV_ALIAS.get(args.prov, args.prov)
        sel = [r for r in sel if r["prov"] == p]
    if args.vol:
        sel = [r for r in sel if args.vol in r["vol"]]
    if args.year:
        sel = [r for r in sel if r["year"] in args.year]
    if args.from_year:
        sel = [r for r in sel if r["year"] and r["year"] >= args.from_year]
    if args.to_year:
        sel = [r for r in sel if r["year"] and r["year"] <= args.to_year]
    if args.module:
        sel = [r for r in sel if args.module in r["module"]]
    if args.type_:
        sel = [r for r in sel if args.type_ in r["type"]]
    if args.kaodian:
        want = set()
        for k in args.kaodian:
            if re.fullmatch(r"[A-Z]{2}-[A-Z]+", k.upper()):
                want.add(k.upper())
            else:
                want |= {r["code"] for r in sel if k in r["type"] or k in r["code"]}
                want |= expand_codes([k])
        sel = [r for r in sel if r["code"] in want]
    if args.kw:
        sel = [r for r in sel if match_keywords(r, args.kw)]
    if args.any:
        sel = [r for r in sel if match_any(r, args.any)]

    if not args.all_variants:
        sel = [r for r in sel if r.get("canonical", r["id"]) == r["id"]]

    # 排序：年份新 → 省份（国考/广东/湖北）→ 题号
    order = {"国考": 0, "广东": 1, "湖北": 2}
    sel.sort(key=lambda r: (-(r["year"] or 0), order.get(r["prov"], 9),
                            r.get("num") or 0, r["id"]))

    if args.json:
        print(json.dumps(sel[: args.limit], ensure_ascii=False, indent=1))
        return 0

    if not sel:
        print("未命中任何题目。建议：①减少关键词（只留 2 个）②换同义词（比重/占比、增速/增长率）"
              "③去掉省份或年份限制 ④用 --any 改为任一词命中。", file=sys.stderr)
        return 2
    folded = sum(1 for r in recs if r.get("canonical", r["id"]) != r["id"])
    tip = f"（已折叠 {folded} 条同题变体，--all-variants 可展开）" if not args.all_variants and folded else ""
    print(f"命中 {len(sel)} 题{tip}，显示前 {min(args.limit, len(sel))} 题：\n")
    for r in sel[: args.limit]:
        print(fmt(r, full=args.full))
        print("-" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
