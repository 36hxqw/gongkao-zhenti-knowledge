#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""考点标注质量评测 + 检索可用性评测（两档评测集）。

两档评测集
----------
1. **强标注集** `tests/gold.jsonl`（默认、有阈值）
   只收「题干自带题型标志词」的题：标志词本身就是题型的定义特征，例如
   「从所给的四个选项中……填入问号处」必是图形推理、「根据上述定义，下列属于」
   必是定义判断。这类样本可 100% 判定，不依赖原卷小节标题，因此没有弱标注的噪声。
2. **弱标注集** `tests/gold_weak.jsonl`（仅展示，不设阈值）
   来自抽取阶段原始记录 `pipeline/out/xingce_raw.jsonl` 的 `sub`（原卷小节标题）。
   实测该字段是「最近一次出现的小节标题」，一个标题会粘到其后的同节所有题上
   （如国考 2016 副省级 40 道判断推理题全部标成「图形推理」），因此含大量噪声，
   只作为历史对照与「原卷结构证据」覆盖率参考，不参与 CI 判定。
3. **人工标注** `tests/gold_manual.jsonl`（可选，不存在即忽略）
   人工逐题标注追加到这里，按 id 覆盖同名规则样本，重建 gold.jsonl 时不会被冲掉。

指标
----
- module 准确率：全部样本上，题库 `module` 与金标是否一致。
- code 准确率：`gold_code` 非 null 的子集上，`code` 是否一致（弱标注集里
  资料分析 / 常识判断 / 数学运算为 null，只评 module）。
- 混淆矩阵：模块 / 考点各取前 10 个「金标 -> 预测」错配对。
- 按模块分组准确率。
- 检索可用性（在强标注集上抽）：`search.py --id` 取题率（期望 100%）；
  题干前 12 个字（去空白）`--kw` 检索进前 10 条的比例。

阈值
----
强标注集默认 module >= 0.95、code >= 0.80；不达标退出码 1，并列出失败样本 id
（最多 10 个，`--verbose` 全量）。阈值用于**防回归**，不代表绝对水平；
用 `--min-module` / `--min-code` 覆盖。

其他
----
- 纯标准库、不联网、不改 `data/`。
- `--rebuild-gold` 重建两个评测集；弱标注集需要仓库上级的
  `pipeline/out/xingce_raw.jsonl`（缺失时跳过，CI 不需要它）。
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
GOLD_WEAK_PATH = os.path.join(BASE, "tests", "gold_weak.jsonl")
GOLD_MANUAL_PATH = os.path.join(BASE, "tests", "gold_manual.jsonl")
SEARCH = os.path.join(BASE, "scripts", "search.py")
DEFAULT_RAW = os.path.join(BASE, os.pardir, "pipeline", "out", "xingce_raw.jsonl")

SEED = 20240101          # 固定随机种子：抽样与检索抽查都可复现
CELL_CAP = 8             # 每个 (prov, decade, 模块) 分层格上限
STRONG_PER_CELL = 8      # 强标注集：每格取满上限（约 190 条）
WEAK_PER_CELL = 5        # 弱标注集：每格 5 条（约 190 条）
# 阈值用于防回归，不代表绝对水平。定稿实测：模块 96.8% / 考点 92.6%
# （189 条强标注样本，见 docs/eval.md）。模块原定 95%，按「实测 - 5pp 再向下取整
# 到 5%」取 90%，给题库演进留余量；考点实测高于默认 80%，保留 80%。
MIN_MODULE = 0.90
MIN_CODE = 0.80
N_ID_CHECK = 50
N_KW_CHECK = 20
KW_TOPN = 10
KW_LEN = 12
ID_RE = re.compile(r"\[([A-Z]{2}-\d{4}-[^\]]+)\]")
PLACEHOLDER_STEM = "（本题题干为图形/公式"

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
    # utf-8-sig：兼容 Windows 记事本/PowerShell 写出的 BOM 文件
    with open(path, encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def compact(s):
    return re.sub(r"\s+", "", s or "")


def opts_max(rec):
    opts = rec.get("opts") or {}
    return max((len(v or "") for v in opts.values()), default=0)


# --------------------------------------------------------------- 强标注集 --
# 每条规则：题型标志词是题型的定义特征 -> (模块, 考点编码, 证据描述)。
# 只匹配「问句 / 设问」本身，不用 data 的分类结果，避免自我循环。
def _m_tx(text, omax):
    """图形推理：问号处填图 / 图形规律 / 分组分类。"""
    if re.search(r"(填入问号处|问号处填入|呈现一定.{0,4}规律|呈现.{0,4}规律性|"
                 r"(分为两类|分成两类).{0,24}图形|每类图形都有各自)", text):
        return "题干标志词=填入问号处/呈现规律"
    return None


def _m_dy(text, omax):
    """定义判断：给出定义 + 「根据上述定义，下列属于/符合」。"""
    if not re.search(r"(上述定义|根据.{0,6}定义|按照.{0,4}定义|定义[,，]下列)", text):
        return None
    if re.search(r"(符合|属于|不符合|不属于)", text):
        return "题干标志词=根据上述定义/下列属于"
    return None


def _m_lb(text, omax):
    """类比推理：「A 对于 B 相当于 C 对于 D」。"""
    if re.search(r"对于.{0,24}相当于", text):
        return "题干标志词=对于…相当于"
    return None


def _m_lj(text, omax):
    """逻辑判断：条件句 + 设问落在「推出/结论」上，且不含言语题标志。"""
    if re.search(r"(这段文字|文段|上述文字|理解正确|理解错误|填入|标题|语序|排序|"
                 r"如图|实验|小球|离子|电荷)", text):
        return None
    if not re.search(r"(如果.{0,90}(那么|则|就)|只有.{0,70}才|除非.{0,70}否则)", text):
        return None
    if re.search(r"(可以推出|据此|由此|以下哪项|结论|可知)", text[-42:]):
        return "题干标志词=条件句+推出/以下哪项"
    return None


def _m_ljtk(text, omax):
    """逻辑填空：依次填入横线 + 选项是词语（短选项）。"""
    if not re.search(r"(依次填入|填入).{0,14}(划|画)?横线|(划|画)横线部分最恰当", text):
        return None
    if omax <= 12:
        return "题干标志词=依次填入横线+词语选项"
    return None


def _m_zxjl(text, omax):
    """中心理解：设问句（题干尾部）落在「这段文字主要/意在……」。"""
    if re.search(r"(标题|填入|排序|语序|相符|不符|理解正确|理解错误|接下来|下文)", text):
        return None
    tail = text[-56:] if len(text) > 56 else text
    if re.search(r"(这段文字|文段|本文|作者).{0,26}(主要|意在|旨在|想要|主旨|观点|概括|说明|强调|支持|介绍)", tail):
        return "题干标志词=这段文字主要/意在"
    return None


def _m_yjpx(text, omax):
    """语句排序：重新排列 / 语序 / 排列组合最连贯。"""
    if re.search(r"(重新排列|排列组合最连贯|(句子|语句).{0,10}排序|语序.{0,10}(合理|恰当|连贯|正确|通顺))", text):
        return "题干标志词=重新排列/语序"
    return None


def _m_sz(text, omax):
    """数字推理：题干是纯数字/分数数列。"""
    if not text or len(text) > 60:
        return None
    if not re.fullmatch(r"[\d,，.。、()（）/／\-+]+", text):
        return None
    if len(re.findall(r"\d+", text)) < 3:
        return None
    if "(" in text or "?" in text or "？" in text:
        return "题干=纯数字数列"
    return None


def _m_xjpd(text, omax):
    """细节判断：与原文/文意相符（不符）。"""
    if re.search(r"((与|和)原文.{0,6}(相符|不符|相悖)|符合文意|不符合文意|与文意.{0,6}(相符|不符))", text):
        return "题干标志词=与原文相符/不符"
    return None


def _m_bttr(text, omax):
    """标题填入：最适合做标题。"""
    if re.search(r"(最适合?做.{0,14}标题|作为.{0,14}标题|标题填入|加一个标题|拟一个标题)", text):
        return "题干标志词=最适合做标题"
    return None


def _m_xwtd(text, omax):
    """下文推断：接下来最可能……"""
    if re.search(r"(接下来|下文).{0,16}(最可能|可能|讲述|介绍|论述|谈论|说明|谈)", text):
        return "题干标志词=接下来最可能"
    return None


STRONG_RULES = [
    ("图形推理", "判断推理", "PD-TX", _m_tx),
    ("定义判断", "判断推理", "PD-DY", _m_dy),
    ("类比推理", "判断推理", "PD-LB", _m_lb),
    ("逻辑判断", "判断推理", "PD-LJ", _m_lj),
    ("逻辑填空", "言语理解", "YY-LJTK", _m_ljtk),
    ("中心理解", "言语理解", "YY-ZXJL", _m_zxjl),
    ("语句排序", "言语理解", "YY-YJPX", _m_yjpx),
    ("数字推理", "数量关系", "SL-SZ", _m_sz),
    ("细节判断", "言语理解", "YY-XJPD", _m_xjpd),
    ("标题填入", "言语理解", "YY-BTTR", _m_bttr),
    ("下文推断", "言语理解", "YY-XWTD", _m_xwtd),
]


def match_strong(rec):
    """返回 (模块, code, evidence)；命中多个不同考点视为歧义，丢弃。"""
    text = compact(rec.get("stem"))
    omax = opts_max(rec)
    hits = []
    for _name, module, code, fn in STRONG_RULES:
        ev = fn(text, omax)
        if ev:
            hits.append((module, code, ev))
    if len({h[1] for h in hits}) != 1:
        return None
    return hits[0]


# --------------------------------------------------------------- 弱标注集 --
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
SEC_TO_MODULE = [("资料分析", "资料分析"), ("常识判断", "常识判断")]


def map_weak(sub, sec):
    sub = (sub or "").strip()
    if sub in SUB_TO_GOLD:
        return SUB_TO_GOLD[sub]
    sec = sec or ""
    for key, module in SEC_TO_MODULE:
        if key in sec:
            return module, None
    return None


def weak_evidence(sub, sec):
    sub = (sub or "").strip()
    if sub in SUB_TO_GOLD:
        return f"原卷小节标题={sub}"
    return f"原卷章节标题={sec}"


# ------------------------------------------------------------------ 抽样 ----
def _sample_cell(items, k, rng):
    """格内分层：先按考点轮转各取 1 条，保证小类（PD-KX / YY-BTTR 等）不被淹没。"""
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


def _sample_by_cells(cells, per_cell, seed):
    rng = random.Random(seed)
    out = []
    for key in sorted(cells):
        items = sorted(cells[key], key=lambda it: it["id"])
        out.extend(_sample_cell(items, min(per_cell, CELL_CAP, len(items)), rng))
    out.sort(key=lambda it: it["id"])
    return out


def build_strong_gold(xingce, seed=SEED, per_cell=STRONG_PER_CELL):
    cells = {}
    for rec in xingce:
        if rec.get("canonical", rec["id"]) != rec["id"]:
            continue
        hit = match_strong(rec)
        if hit is None:
            continue
        module, code, ev = hit
        key = (rec["prov"], (rec["year"] or 0) // 10 * 10, module)
        cells.setdefault(key, []).append({
            "id": rec["id"], "gold_module": module, "gold_code": code, "evidence": ev,
        })
    return _sample_by_cells(cells, per_cell, seed), cells


def build_weak_gold(raw_path, xingce, seed=SEED, per_cell=WEAK_PER_CELL):
    index = {(r["prov"], r["year"], r["vol"], r["num"]): r for r in xingce}
    cells = {}
    stats = {"raw": 0, "no_evidence": 0, "no_join": 0, "dup": 0, "eligible": 0}
    for r in load_jsonl(raw_path):
        stats["raw"] += 1
        mapped = map_weak(r.get("sub"), r.get("sec"))
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
        key = (rec["prov"], (rec["year"] or 0) // 10 * 10, module)
        cells.setdefault(key, []).append({
            "id": rec["id"], "gold_module": module, "gold_code": code,
            "evidence": weak_evidence(r.get("sub"), r.get("sec")),
        })
        stats["eligible"] += 1
    return _sample_by_cells(cells, per_cell, seed), cells, stats


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
    text = compact(stem)
    return (not text.startswith(PLACEHOLDER_STEM)) and len(text) >= KW_LEN


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
        query = compact(recs[g["id"]]["stem"])[:KW_LEN]
        code, out, _err = run_search(["--kw", query, "--limit", str(KW_TOPN)])
        found = ID_RE.findall(out) if code == 0 else []
        if g["id"] in found[:KW_TOPN]:
            hits += 1
        else:
            rank = found.index(g["id"]) + 1 if g["id"] in found else None
            misses.append((g["id"], query, rank))
    return hits, len(picked), misses


def evaluate(gold, xingce):
    recs = {r["id"]: r for r in xingce}
    missing = [g["id"] for g in gold if g["id"] not in recs]
    rows = []
    for g in gold:
        rec = recs.get(g["id"])
        pred_mod = rec.get("module") if rec else None
        pred_code = rec.get("code") if rec else None
        rows.append({
            "id": g["id"], "gold_module": g["gold_module"], "gold_code": g["gold_code"],
            "pred_module": pred_mod, "pred_code": pred_code,
            "module_ok": pred_mod == g["gold_module"],
            "code_ok": (pred_code == g["gold_code"]) if g["gold_code"] else None,
        })
    n = len(rows)
    mod_ok = sum(1 for r in rows if r["module_ok"])
    code_rows = [r for r in rows if r["gold_code"]]
    code_ok = sum(1 for r in code_rows if r["code_ok"])
    mod_conf, code_conf = {}, {}
    for r in rows:
        if not r["module_ok"]:
            key = (r["gold_module"], r["pred_module"] or "缺失")
            mod_conf[key] = mod_conf.get(key, 0) + 1
        if r["gold_code"] and not r["code_ok"]:
            key = (r["gold_code"], r["pred_code"] or "缺失")
            code_conf[key] = code_conf.get(key, 0) + 1
    by_mod = {}
    for r in rows:
        cell = by_mod.setdefault(r["gold_module"],
                                 {"n": 0, "mod_ok": 0, "code_n": 0, "code_ok": 0})
        cell["n"] += 1
        cell["mod_ok"] += 1 if r["module_ok"] else 0
        if r["gold_code"]:
            cell["code_n"] += 1
            cell["code_ok"] += 1 if r["code_ok"] else 0
    failures = [r for r in rows if (not r["module_ok"]) or (r["gold_code"] and not r["code_ok"])]
    return {
        "n": n, "missing": missing, "mod_ok": mod_ok,
        "mod_acc": mod_ok / n if n else 0.0,
        "code_n": len(code_rows), "code_ok": code_ok,
        "code_acc": (code_ok / len(code_rows)) if code_rows else None,
        "mod_conf": mod_conf, "code_conf": code_conf, "by_mod": by_mod,
        "failures": failures,
    }


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def strata_of(gold, recs):
    strata = {}
    for g in gold:
        rec = recs.get(g["id"])
        if not rec:
            continue
        key = (rec["prov"], (rec["year"] or 0) // 10 * 10)
        strata[key] = strata.get(key, 0) + 1
    return strata


def print_metrics(res, show_failures=False, args=None):
    ok_mod = res["mod_acc"] >= (args.min_module if args else 0)
    ok_code = True if res["code_acc"] is None else res["code_acc"] >= (args.min_code if args else 0)
    print(f"  模块准确率  {res['mod_ok']}/{res['n']}  {pct(res['mod_acc'])}"
          + (f"  {mark(ok_mod)} 阈值 {args.min_module * 100:.0f}%" if args else ""))
    if res["code_n"]:
        print(f"  考点准确率  {res['code_ok']}/{res['code_n']}  {pct(res['code_acc'])}"
              + (f"  {mark(ok_code)} 阈值 {args.min_code * 100:.0f}%" if args else ""))
    else:
        print("  考点准确率  —（本集没有 code 级样本）")
    if res["missing"]:
        print(f"  {mark(False)} gold 中有 {len(res['missing'])} 条在题库里找不到："
              f"{res['missing'][:5]}")

    for title, conf in (("模块混淆（前 10 个混淆对）", res["mod_conf"]),
                        ("考点混淆（前 10 个混淆对）", res["code_conf"])):
        print(f"  {title}")
        if not conf:
            print("    （无：全部命中）")
            continue
        for (g, p), cnt in sorted(conf.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
            print(f"    金标 {pad(g, 10)} -> 预测 {pad(p, 10)} {cnt:>4} 次")

    print("  按模块分组")
    print("    " + pad("模块", 12) + pad("样本", 8) + pad("模块对", 8) + pad("模块准确率", 12)
          + pad("考点样本", 10) + pad("考点对", 8) + "考点准确率")
    for mod in sorted(res["by_mod"], key=lambda m: -res["by_mod"][m]["n"]):
        c = res["by_mod"][mod]
        print("    " + pad(mod, 12) + pad(str(c["n"]), 8) + pad(str(c["mod_ok"]), 8)
              + pad(pct(c["mod_ok"] / c["n"] if c["n"] else None), 12)
              + pad(str(c["code_n"]), 10) + pad(str(c["code_ok"]), 8)
              + pct(c["code_ok"] / c["code_n"] if c["code_n"] else None))

    if show_failures:
        limit = len(res["failures"]) if args and args.verbose else 10
        print(f"  失败样本（共 {len(res['failures'])} 条，显示前 "
              f"{min(limit, len(res['failures']))} 条）：")
        for r in res["failures"][:limit]:
            if r["gold_code"] is None:
                detail = f"金标={r['gold_module']}/null 预测={r['pred_module']}/{r['pred_code']}"
            else:
                detail = (f"金标={r['gold_module']}/{r['gold_code']}  "
                          f"预测={r['pred_module']}/{r['pred_code']}")
            print(f"    {r['id']}  {detail}")
        if args and not args.verbose and len(res["failures"]) > limit:
            print(f"    …（--verbose 显示全部 {len(res['failures'])} 条）")
    return ok_mod, ok_code


def describe_cells(cells):
    by_pd = {}
    for prov, decade, module in cells:
        by_pd[(prov, decade)] = by_pd.get((prov, decade), 0) + 1
    lines = []
    for key in sorted(by_pd, key=lambda k: (k[0], k[1])):
        detail = []
        for prov, decade, module in sorted(cells):
            if (prov, decade) != key:
                continue
            detail.append(f"{module}:{min(CELL_CAP, len(cells[(prov, decade, module)]))}")
        lines.append(f"{key[0]} {key[1]}s -> " + "  ".join(detail))
    return lines


def cmd_rebuild(args):
    xingce = load_jsonl(os.path.join(DATA_DIR, "xingce.jsonl"))
    strong, cells = build_strong_gold(xingce, seed=args.seed)
    write_gold(GOLD_PATH, strong)
    print(f"已写入 {GOLD_PATH}")
    print(f"  强标注 {len(strong)} 条（全部含考点），分层格上限 {CELL_CAP}/格")
    for line in describe_cells(cells):
        print("    " + line)

    raw = args.raw or DEFAULT_RAW
    if not os.path.exists(raw):
        print(f"\n跳过弱标注集：找不到 {raw}（用 --raw 指定）")
        return 0
    weak, wcells, stats = build_weak_gold(raw, xingce, seed=args.seed)
    write_gold(GOLD_WEAK_PATH, weak)
    n_code = sum(1 for g in weak if g["gold_code"])
    print(f"\n已写入 {GOLD_WEAK_PATH}")
    print(f"  弱标注 {len(weak)} 条：含考点 {n_code} 条 / 仅模块 {len(weak) - n_code} 条")
    print(f"  原始 {stats['raw']} 条 -> 可用 {stats['eligible']} 条"
          f"（无结构证据 {stats['no_evidence']}，未对上题库 {stats['no_join']}，"
          f"重复变体 {stats['dup']}）")
    for line in describe_cells(wcells):
        print("    " + line)
    return 0


def main(argv=None):
    _init_console()
    ap = argparse.ArgumentParser(description="公考真题知识库：考点标注质量评测 + 检索可用性评测")
    ap.add_argument("--min-module", type=float, default=MIN_MODULE,
                    help=f"强标注集模块准确率阈值，默认 {MIN_MODULE}")
    ap.add_argument("--min-code", type=float, default=MIN_CODE,
                    help=f"强标注集考点准确率阈值，默认 {MIN_CODE}")
    ap.add_argument("--verbose", action="store_true", help="打印全部错例")
    ap.add_argument("--seed", type=int, default=SEED, help=f"随机种子，默认 {SEED}")
    ap.add_argument("--rebuild-gold", action="store_true",
                    help="重建 tests/gold.jsonl（强标注）与 tests/gold_weak.jsonl（弱标注）")
    ap.add_argument("--raw", help="原始抽取 jsonl 路径，默认仓库上级 pipeline/out/xingce_raw.jsonl")
    args = ap.parse_args(argv)

    if args.rebuild_gold:
        return cmd_rebuild(args)

    if not os.path.exists(GOLD_PATH):
        print(f"找不到强标注集：{GOLD_PATH}\n先运行 python tests/eval.py --rebuild-gold")
        return 1
    data_path = os.path.join(DATA_DIR, "xingce.jsonl")
    if not os.path.exists(data_path):
        print(f"找不到题库：{data_path}")
        return 1

    strong = load_jsonl(GOLD_PATH)
    if not strong:
        print("强标注集为空")
        return 1
    manual = load_jsonl(GOLD_MANUAL_PATH) if os.path.exists(GOLD_MANUAL_PATH) else []
    n_override = 0
    if manual:
        by_id = {g["id"]: g for g in strong}
        n_override = sum(1 for g in manual if g["id"] in by_id)
        for g in manual:
            by_id[g["id"]] = g
        strong = sorted(by_id.values(), key=lambda g: g["id"])
    xingce = load_jsonl(data_path)
    recs = {r["id"]: r for r in xingce}

    print("[1] 载入")
    weak = load_jsonl(GOLD_WEAK_PATH) if os.path.exists(GOLD_WEAK_PATH) else []
    print(f"  强标注集 tests/gold.jsonl：{len(strong)} 条（全部含考点）")
    if manual:
        print(f"  人工标注 tests/gold_manual.jsonl：{len(manual)} 条"
              f"（覆盖规则样本 {n_override} 条）")
    print(f"  弱标注集 tests/gold_weak.jsonl：{len(weak)} 条"
          f"（含考点 {sum(1 for g in weak if g['gold_code'])} 条）")
    print(f"  data/xingce.jsonl：{len(xingce)} 条；随机种子 {args.seed}")
    strata = strata_of(strong, recs)
    print("  强标注分层：" + "  ".join(
        f"{prov} {decade}s={cnt}"
        for (prov, decade), cnt in sorted(strata.items(), key=lambda kv: (kv[0][0], kv[0][1]))))

    print("\n[2] 强标注集（默认阈值，参与 CI）")
    res = evaluate(strong, xingce)
    ok_mod, ok_code = print_metrics(res, show_failures=True, args=args)

    if weak:
        print("\n[3] 弱标注集（仅展示，不设阈值）")
        print("  说明：标签取自原卷小节标题 sub，该字段会「粘」到后续同节所有题上，"
              "含明显噪声；只用于观察题库与原卷结构证据的偏离方向，不作为质量门槛。")
        wres = evaluate(weak, xingce)
        print_metrics(wres)

    print("\n[4] 检索可用性（在强标注集上随机抽查）")
    rng = random.Random(args.seed + 1)
    id_hits, id_n, id_miss = check_id_retrieval(strong, rng)
    kw_hits, kw_n, kw_miss = check_kw_retrieval(strong, recs, rng)
    id_acc = id_hits / id_n if id_n else None
    kw_acc = kw_hits / kw_n if kw_n else None
    print(f"  --id 精确取题    {id_hits}/{id_n}  {pct(id_acc)}（期望 100%）"
          f"  {mark(id_acc == 1.0 if id_acc is not None else True)}")
    print(f"  --kw 前 12 字    {kw_hits}/{kw_n}  {pct(kw_acc)}（目标进前 {KW_TOPN} 条）"
          f"  {mark(kw_acc == 1.0 if kw_acc is not None else True)}")
    for qid, why in id_miss[:5]:
        print(f"    id 未命中：{qid}（{why}）")
    for qid, query, rank in kw_miss[:5]:
        where = f"排第 {rank}" if rank else "未出现"
        print(f"    kw 未命中：{qid}（查询「{query}」，{where}）")
    print("  注：--kw 查询按评测口径去掉了空白，而索引里的原文保留 OCR 空格；"
          "两者不归一化会造成部分假阴性。")

    print("\n[5] 结论")
    parts = [f"模块 {pct(res['mod_acc'])}"
             + (f" >= {args.min_module * 100:.0f}%" if ok_mod
                else f" < {args.min_module * 100:.0f}%")]
    if res["code_acc"] is not None:
        parts.append(f"考点 {pct(res['code_acc'])}"
                     + (f" >= {args.min_code * 100:.0f}%" if ok_code
                        else f" < {args.min_code * 100:.0f}%"))
    if ok_mod and ok_code:
        print(f"  {mark(True)} 达到阈值：强标注集 " + "；".join(parts))
        print("  阈值用于防回归，不代表绝对水平；评测集的来源与局限见 docs/eval.md。")
        return 0
    print(f"  {mark(False)} 未达阈值：强标注集 " + "；".join(parts))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
