#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""考点标注质量评测 + 检索可用性评测。

评测集 `tests/gold.jsonl` 是「结构化弱标注」评测集，**不是人工逐题标注**：
它的标签来自抽取阶段的原始记录 `pipeline/out/xingce_raw.jsonl` 里原卷自带的小节标题
（`sub`，如「图形推理」）与章节标题（`sec`，如「资料分析」），只覆盖「原卷把话说清楚了」
的那部分题。因此它衡量的是「题库标注与原卷结构证据的一致率」，不是绝对正确率；
`gold_code` 为 null 的样本（资料分析 / 常识判断 / 数学运算）只参与 module 准确率，
不参与 code 准确率。

指标
----
1. module 准确率：全部 gold 样本上，`data/xingce.jsonl` 的 `module` 与 gold 是否一致。
2. code 准确率：仅在 `gold_code` 非 null 的子集上，`code` 是否一致。
3. 混淆矩阵：模块 / 考点各取前 10 个「金标 -> 预测」错配对。
4. 按 gold_module 分组的准确率。
5. 检索可用性：
   - 随机 50 条 gold，`scripts/search.py --id <id>` 能否取到（期望 100%）；
   - 随机 20 条 gold，用题干前 12 个字（去空白）做 `--kw` 检索，目标是否落在前 10 条。

阈值
----
默认 module < 0.85 或 code < 0.70 时退出码 1，并列出失败样本 id（最多 10 个）。
用 `--min-module` / `--min-code` 覆盖；`--verbose` 打印全部错例。

其他
----
- 纯标准库，不联网，不改 `data/`。
- `--rebuild-gold` 用固定随机种子重建 `tests/gold.jsonl`（需要仓库上级的
  `pipeline/out/xingce_raw.jsonl`；CI 里不需要，因为 gold 已入库）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import unicodedata

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
GOLD_PATH = os.path.join(BASE, "tests", "gold.jsonl")
SEARCH = os.path.join(BASE, "scripts", "search.py")
DEFAULT_RAW = os.path.join(BASE, os.pardir, "pipeline", "out", "xingce_raw.jsonl")

SEED = 20240101          # 固定随机种子：gold 抽样与检索抽查都可复现
PER_CELL = 5             # 每个 (prov, decade, 模块) 分层格取 5 条
CELL_CAP = 8             # 每个分层格上限 8 条（硬约束）
MIN_MODULE = 0.85
MIN_CODE = 0.70
N_ID_CHECK = 50
N_KW_CHECK = 20
KW_TOPN = 10
KW_LEN = 12
ID_RE = re.compile(r"\[([A-Z]{2}-\d{4}-[^\]]+)\]")
PLACEHOLDER_STEM = "（本题题干为图形/公式"

# 原卷小节标题 -> (模块, 考点编码)。编码唯一时才作为 gold；None 表示只做模块级标注。
SUB_TO_GOLD = {
    "图形推理": ("判断推理", "PD-TX"),
    "定义判断": ("判断推理", "PD-DY"),
    "类比推理": ("判断推理", "PD-LB"),
    "逻辑判断": ("判断推理", "PD-LJ"),
    "演绎推理": ("判断推理", "PD-LJ"),
    "科学推理": ("判断推理", "PD-KX"),
    "逻辑填空": ("言语理解", "YY-LJTK"),
    "选词填空": ("言语理解", "YY-LJTK"),
    "片段阅读": ("言语理解", "YY-ZXJL"),
    "阅读理解": ("言语理解", "YY-ZXJL"),
    "语句表达": ("言语理解", "YY-YJPX"),
    "篇章阅读": ("言语理解", "YY-PZYD"),
    "数字推理": ("数量关系", "SL-SZ"),
    "数学运算": ("数量关系", None),   # 具体考点不唯一，只做模块级 gold
}

# 原卷章节标题 -> 模块。该章节内包含多个考点，只做模块级 gold。
SEC_TO_MODULE = [("资料分析", "资料分析"), ("常识判断", "常识判断")]

EMOJI = True


def _init_console():
    """GBK 控制台画不出 ✅/❌ 时自动降级为 [OK]/[FAIL]，其余中文照常输出。"""
    global EMOJI
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✅".encode(enc)
    except (UnicodeEncodeError, LookupError):
        EMOJI = False


def mark(ok):
    if not EMOJI:
        return "[OK]" if ok else "[FAIL]"
    return "✅" if ok else "❌"


def disp_width(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s, width):
    return s + " " * max(0, width - disp_width(s))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --------------------------------------------------------------- gold 生成 --
def map_evidence(sub, sec):
    """把原卷结构证据映射成 (模块, 考点编码|None)；无法唯一映射时返回 None。

    小节标题（sub）优先，其次才是章节标题（sec）——后者粒度更粗，只给模块。
    """
    sub = (sub or "").strip()
    if sub in SUB_TO_GOLD:
        return SUB_TO_GOLD[sub]
    sec = sec or ""
    for key, module in SEC_TO_MODULE:
        if key in sec:
            return module, None
    return None


def evidence_of(sub, sec):
    sub = (sub or "").strip()
    if sub in SUB_TO_GOLD:
        return f"原卷小节标题={sub}"
    return f"原卷章节标题={sec}"


def _sample_cell(items, k, rng):
    """格内分层抽样：先按考点轮转各取 1 条，保证 PD-KX / YY-YJPX 等小类不被淹没。"""
    groups = {}
    for it in items:
        groups.setdefault(it["gold_code"] or "MODULE", []).append(it)
    keys = sorted(groups)
    for key in keys:
        groups[key].sort(key=lambda it: it["id"])
        rng.shuffle(groups[key])
    picked, pos = [], {key: 0 for key in keys}
    while len(picked) < k:
        progressed = False
        for key in keys:
            if len(picked) >= k:
                break
            i = pos[key]
            if i < len(groups[key]):
                picked.append(groups[key][i])
                pos[key] = i + 1
                progressed = True
        if not progressed:
            break
    return picked


def build_gold(raw_path, xingce, seed=SEED, per_cell=PER_CELL, cell_cap=CELL_CAP):
    """从原始抽取记录挑出有结构证据的题，按 (prov, decade, 模块) 分层抽样。

    返回 (gold 列表, 统计 dict, 分层格 dict)。重复题（canonical != id）只保留主记录，
    既避免重复计分，也保证 `--id` 一定能取到。
    """
    index = {(r["prov"], r["year"], r["vol"], r["num"]): r for r in xingce}
    cells = {}
    stats = {"raw": 0, "no_evidence": 0, "no_join": 0, "dup": 0, "eligible": 0}
    for r in load_jsonl(raw_path):
        stats["raw"] += 1
        mapped = map_evidence(r.get("sub"), r.get("sec"))
        if mapped is None:
            stats["no_evidence"] += 1
            continue
        rec = index.get((r.get("prov"), r.get("year"), r.get("vol"), r.get("num")))
        if rec is None:
            stats["no_join"] += 1
            continue
        if rec.get("canonical", rec["id"]) != rec["id"]:
            stats["dup"] += 1
            continue
        module, code = mapped
        decade = (rec["year"] or 0) // 10 * 10
        cells.setdefault((rec["prov"], decade, module), []).append({
            "id": rec["id"],
            "gold_module": module,
            "gold_code": code,
            "evidence": evidence_of(r.get("sub"), r.get("sec")),
        })
        stats["eligible"] += 1

    rng = random.Random(seed)
    gold = []
    for key in sorted(cells):
        items = sorted(cells[key], key=lambda it: it["id"])
        gold.extend(_sample_cell(items, min(per_cell, cell_cap, len(items)), rng))
    gold.sort(key=lambda it: it["id"])
    return gold, stats, cells


def write_gold(path, gold):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for it in gold:
            row = {
                "id": it["id"],
                "gold_module": it["gold_module"],
                "gold_code": it["gold_code"],
                "evidence": it["evidence"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_rebuild(args):
    raw = args.raw or DEFAULT_RAW
    if not os.path.exists(raw):
        print(f"找不到原始抽取文件：{raw}")
        print("请用 --raw 指定，或设置环境变量 ZHENTI_RAW。"
              "（该文件在仓库上级 pipeline/out/ 中，CI 不重建 gold）")
        return 1
    xingce = load_jsonl(os.path.join(DATA_DIR, "xingce.jsonl"))
    gold, stats, cells = build_gold(raw, xingce, seed=args.seed,
                                    per_cell=args.per_cell, cell_cap=CELL_CAP)
    write_gold(GOLD_PATH, gold)
    n_code = sum(1 for g in gold if g["gold_code"])
    print(f"已写入 {GOLD_PATH}")
    print(f"  gold {len(gold)} 条：含考点 {n_code} 条 / 仅模块 {len(gold) - n_code} 条")
    print(f"  原始 {stats['raw']} 条 -> 可用 {stats['eligible']} 条"
          f"（无结构证据 {stats['no_evidence']}，未对上题库 {stats['no_join']}，"
          f"重复变体 {stats['dup']}）")
    by_pd = {}
    for prov, decade, module in cells:
        by_pd[(prov, decade)] = by_pd.get((prov, decade), 0) + 1
    print("  分层格（prov/decade/模块）：")
    for key in sorted(by_pd, key=lambda k: (k[0], k[1])):
        detail = []
        for prov, decade, module in sorted(cells):
            if (prov, decade) != key:
                continue
            detail.append(f"{module}:{min(PER_CELL, len(cells[(prov, decade, module)]))}")
        print(f"    {key[0]} {key[1]}s -> " + "  ".join(detail))
    return 0


# ------------------------------------------------------------------ 评测 ----
def run_search(argv, timeout=180):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run([sys.executable, SEARCH] + argv, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=timeout)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def usable_stem(stem):
    """能独立做关键词检索的题干：排除「图/公式见原卷」这类占位题干。"""
    compact = re.sub(r"\s+", "", stem or "")
    return (not compact.startswith(PLACEHOLDER_STEM)) and len(compact) >= KW_LEN


def check_id_retrieval(gold, rng, n=N_ID_CHECK):
    ids = [g["id"] for g in gold]
    picked = rng.sample(ids, min(n, len(ids)))
    hits, misses = 0, []
    for qid in sorted(picked):
        code, out, _err = run_search(["--id", qid])
        if code == 0 and f"[{qid}]" in out:
            hits += 1
        else:
            misses.append((qid, f"退出码 {code}"))
    return hits, len(picked), misses


def check_kw_retrieval(gold, recs, rng, n=N_KW_CHECK):
    pool = [g for g in gold if g["id"] in recs and usable_stem(recs[g["id"]].get("stem"))]
    picked = rng.sample(pool, min(n, len(pool))) if pool else []
    hits, misses = 0, []
    for g in sorted(picked, key=lambda it: it["id"]):
        query = re.sub(r"\s+", "", recs[g["id"]]["stem"])[:KW_LEN]
        code, out, _err = run_search(["--kw", query, "--limit", str(KW_TOPN)])
        found = ID_RE.findall(out) if code == 0 else []
        if g["id"] in found[:KW_TOPN]:
            hits += 1
        else:
            rank = found.index(g["id"]) + 1 if g["id"] in found else None
            misses.append((g["id"], query, rank))
    return hits, len(picked), misses


def evaluate(gold, xingce, args):
    recs = {r["id"]: r for r in xingce}
    missing = [g["id"] for g in gold if g["id"] not in recs]
    rows = []
    for g in gold:
        rec = recs.get(g["id"])
        pred_mod = rec.get("module") if rec else None
        pred_code = rec.get("code") if rec else None
        rows.append({
            "id": g["id"],
            "gold_module": g["gold_module"],
            "gold_code": g["gold_code"],
            "pred_module": pred_mod,
            "pred_code": pred_code,
            "module_ok": pred_mod == g["gold_module"],
            "code_ok": (pred_code == g["gold_code"]) if g["gold_code"] else None,
        })

    n = len(rows)
    mod_ok = sum(1 for r in rows if r["module_ok"])
    code_rows = [r for r in rows if r["gold_code"]]
    code_ok = sum(1 for r in code_rows if r["code_ok"])

    mod_conf = {}
    code_conf = {}
    for r in rows:
        if not r["module_ok"]:
            key = (r["gold_module"], r["pred_module"] or "缺失")
            mod_conf[key] = mod_conf.get(key, 0) + 1
        if r["gold_code"] and not r["code_ok"]:
            key = (r["gold_code"], r["pred_code"] or "缺失")
            code_conf[key] = code_conf.get(key, 0) + 1

    mod_acc = mod_ok / n if n else 0.0
    code_acc = code_ok / len(code_rows) if code_rows else None

    # 按 gold_module 分组
    by_mod = {}
    for r in rows:
        cell = by_mod.setdefault(r["gold_module"], {"n": 0, "mod_ok": 0, "code_n": 0, "code_ok": 0})
        cell["n"] += 1
        cell["mod_ok"] += 1 if r["module_ok"] else 0
        if r["gold_code"]:
            cell["code_n"] += 1
            cell["code_ok"] += 1 if r["code_ok"] else 0

    # 分层构成（prov / decade）
    strata = {}
    for g in gold:
        rec = recs.get(g["id"])
        if not rec:
            continue
        key = (rec["prov"], (rec["year"] or 0) // 10 * 10)
        strata[key] = strata.get(key, 0) + 1

    rng = random.Random(args.seed + 1)
    id_hits, id_n, id_miss = check_id_retrieval(gold, rng)
    kw_hits, kw_n, kw_miss = check_kw_retrieval(gold, recs, rng)

    # 失败样本：模块错 或 考点错（gold_code 非空时）
    failures = [r for r in rows if (not r["module_ok"]) or (r["gold_code"] and not r["code_ok"])]
    return {
        "n": n, "missing": missing, "mod_acc": mod_acc, "mod_ok": mod_ok,
        "code_acc": code_acc, "code_ok": code_ok, "code_n": len(code_rows),
        "mod_conf": mod_conf, "code_conf": code_conf, "by_mod": by_mod,
        "strata": strata, "failures": failures,
        "id_hits": id_hits, "id_n": id_n, "id_miss": id_miss,
        "kw_hits": kw_hits, "kw_n": kw_n, "kw_miss": kw_miss,
    }


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def report(res, args):
    print("[1] 载入")
    print(f"  gold：{res['n']} 条（含考点 {res['code_n']} 条 / 仅模块 {res['n'] - res['code_n']} 条）")
    print(f"  data/xingce.jsonl：{res['data_n']} 条")
    print(f"  随机种子：{args.seed}")
    if res["missing"]:
        print(f"  {mark(False)} gold 中有 {len(res['missing'])} 条在题库里找不到：{res['missing'][:5]}")
    else:
        print(f"  {mark(True)} gold 全部能在题库中对上")
    if res["strata"]:
        parts = [f"{prov} {decade}s={cnt}" for (prov, decade), cnt in
                 sorted(res["strata"].items(), key=lambda kv: (kv[0][0], kv[0][1]))]
        print("  分层：" + "  ".join(parts))

    print("\n[2] 标注准确率")
    ok_mod = res["mod_acc"] >= args.min_module
    print(f"  模块准确率  {res['mod_ok']}/{res['n']}  {pct(res['mod_acc'])}  "
          f"{mark(ok_mod)} 阈值 {args.min_module * 100:.0f}%")
    if res["code_n"]:
        ok_code = res["code_acc"] >= args.min_code
        print(f"  考点准确率  {res['code_ok']}/{res['code_n']}  {pct(res['code_acc'])}  "
              f"{mark(ok_code)} 阈值 {args.min_code * 100:.0f}%")
    else:
        ok_code = True
        print("  考点准确率  —（本集没有 code 级样本，跳过）")

    for title, conf in (("[3] 混淆矩阵（模块，前 10 个混淆对）", res["mod_conf"]),
                        ("[4] 混淆矩阵（考点，前 10 个混淆对）", res["code_conf"])):
        print("\n" + title)
        if not conf:
            print("  （无：全部命中）")
            continue
        for (gold, pred), cnt in sorted(conf.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
            print(f"  金标 {pad(gold, 10)} -> 预测 {pad(pred, 10)} {cnt:>4} 次")

    print("\n[5] 按模块分组")
    print("  " + pad("模块", 12) + pad("样本", 8) + pad("模块对", 8) + pad("模块准确率", 12)
          + pad("考点样本", 10) + pad("考点对", 8) + "考点准确率")
    for mod in sorted(res["by_mod"], key=lambda m: -res["by_mod"][m]["n"]):
        c = res["by_mod"][mod]
        mod_acc = c["mod_ok"] / c["n"] if c["n"] else None
        code_acc = c["code_ok"] / c["code_n"] if c["code_n"] else None
        print("  " + pad(mod, 12) + pad(str(c["n"]), 8) + pad(str(c["mod_ok"]), 8)
              + pad(pct(mod_acc), 12) + pad(str(c["code_n"]), 10) + pad(str(c["code_ok"]), 8)
              + pct(code_acc))

    print("\n[6] 检索可用性")
    id_acc = res["id_hits"] / res["id_n"] if res["id_n"] else None
    kw_acc = res["kw_hits"] / res["kw_n"] if res["kw_n"] else None
    print(f"  --id 精确取题    {res['id_hits']}/{res['id_n']}  {pct(id_acc)}（期望 100%）"
          f"  {mark(id_acc == 1.0 if id_acc is not None else True)}")
    print(f"  --kw 前 12 字    {res['kw_hits']}/{res['kw_n']}  {pct(kw_acc)}"
          f"（目标进前 {KW_TOPN} 条）  {mark(kw_acc == 1.0 if kw_acc is not None else True)}")
    for item in res["id_miss"][:5]:
        print(f"    id 未命中：{item[0]}（{item[1]}）")
    for qid, query, rank in res["kw_miss"][:5]:
        where = "50 条以外" if rank and rank > KW_TOPN else "未出现"
        print(f"    kw 未命中：{qid}（查询「{query}」，{where}）")

    print("\n[7] 结论")
    if ok_mod and ok_code:
        print(f"  {mark(True)} 达到阈值：模块 {pct(res['mod_acc'])} / 考点 {pct(res['code_acc'])}")
        print("  注：gold 为结构化弱标注集，阈值达标只说明「与原卷结构证据一致」，不等于人工正确率。")
        return 0
    verdict = []
    if ok_mod:
        verdict.append(f"模块 {pct(res['mod_acc'])} 通过")
    else:
        verdict.append(f"模块 {pct(res['mod_acc'])} < {args.min_module * 100:.0f}%")
    if ok_code:
        verdict.append(f"考点 {pct(res['code_acc'])} 通过")
    else:
        verdict.append(f"考点 {pct(res['code_acc'])} < {args.min_code * 100:.0f}%")
    print(f"  {mark(False)} 未达阈值：" + "；".join(verdict))
    limit = len(res["failures"]) if args.verbose else 10
    print(f"  失败样本（共 {len(res['failures'])} 条，显示前 {min(limit, len(res['failures']))} 条）：")
    for r in res["failures"][:limit]:
        code_part = (f"金标={r['gold_module']}/{r['gold_code']}  "
                     f"预测={r['pred_module']}/{r['pred_code']}")
        if r["gold_code"] is None:
            code_part = f"金标={r['gold_module']}/null 预测={r['pred_module']}/{r['pred_code']}"
        print(f"    {r['id']}  {code_part}")
    if not args.verbose and len(res["failures"]) > limit:
        print(f"    …（--verbose 显示全部 {len(res['failures'])} 条）")
    return 1


def main(argv=None):
    _init_console()
    ap = argparse.ArgumentParser(
        description="公考真题知识库：考点标注质量评测 + 检索可用性评测")
    ap.add_argument("--min-module", type=float, default=MIN_MODULE,
                    help=f"模块准确率阈值，默认 {MIN_MODULE}")
    ap.add_argument("--min-code", type=float, default=MIN_CODE,
                    help=f"考点准确率阈值，默认 {MIN_CODE}")
    ap.add_argument("--verbose", action="store_true", help="打印全部错例详情")
    ap.add_argument("--seed", type=int, default=SEED, help=f"随机种子，默认 {SEED}")
    ap.add_argument("--rebuild-gold", action="store_true",
                    help="用原始抽取记录重建 tests/gold.jsonl（需要 pipeline/out/xingce_raw.jsonl）")
    ap.add_argument("--raw", help="原始抽取 jsonl 路径，默认仓库上级 pipeline/out/xingce_raw.jsonl")
    ap.add_argument("--per-cell", type=int, default=PER_CELL,
                    help=f"每个分层格抽样条数，默认 {PER_CELL}（上限 {CELL_CAP}）")
    args = ap.parse_args(argv)

    if args.rebuild_gold:
        return cmd_rebuild(args)

    if not os.path.exists(GOLD_PATH):
        print(f"找不到评测集：{GOLD_PATH}\n先运行 python tests/eval.py --rebuild-gold")
        return 1
    if not os.path.exists(os.path.join(DATA_DIR, "xingce.jsonl")):
        print(f"找不到题库：{os.path.join(DATA_DIR, 'xingce.jsonl')}")
        return 1

    gold = load_jsonl(GOLD_PATH)
    if not gold:
        print("评测集为空")
        return 1
    xingce = load_jsonl(os.path.join(DATA_DIR, "xingce.jsonl"))
    res = evaluate(gold, xingce, args)
    res["data_n"] = len(xingce)
    return report(res, args)


if __name__ == "__main__":
    raise SystemExit(main())
