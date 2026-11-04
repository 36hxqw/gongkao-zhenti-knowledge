#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档数字校验：`docs/stats-snapshot.md` 单一事实源 + 关键数字交叉核对。

为什么需要它
------------
题量、答案覆盖、配图、子考点、评测准确率这些数字原先散落在 `SKILL.md` / `README.md` /
`docs/*.md` 里手写，每次数据修订都要人工同步，v1.7 就漂移过 40 处。本脚本做两件事：

1. **快照比对**：从 `data/xingce.jsonl` / `data/shenlun.jsonl` / `references/images/`
   独立复算全部指标（不复用 `gen_docs.py` 的代码，避免生成器与校验器同错同对），
   与 `docs/stats-snapshot.md` 的表逐行比对。
2. **文档扫描**：把 `SKILL.md`、`README.md`、`docs/coverage.md`、`docs/distribution.md`、
   `docs/install.md`、`docs/eval.md`、`docs/data-spec.md`、`skill.json` 里出现的
   关键数字与实测比对，不一致时按 `文件:行 → 文档值 vs 实测值` 列出并退出码 1。

用法
----
    python scripts/doc_check.py             # 人类可读报告；不一致退出 1
    python scripts/doc_check.py --json      # 结构化输出（CI / 脚本消费）
    python scripts/doc_check.py --fix       # 把文档里的旧值替换为实测值（幂等，可重复跑）
    python scripts/doc_check.py --fix --json

说明：纯标准库、只读 `data/`、不联网；`--fix` 只改 Markdown / JSON 里的数字，
`docs/stats-snapshot.md` 请用 `python pipeline/gen_docs.py` 重新生成。
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
REF = os.path.join(BASE, "references")
DIST = os.path.join(BASE, "dist")
SNAPSHOT = os.path.join(BASE, "docs", "stats-snapshot.md")

WS = "\u00a0\u2009\u3000"


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #
def load_jsonl(name):
    with open(os.path.join(DATA, name), encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def has_ans(rec):
    return bool((rec.get("ans") or "").strip())


# --------------------------------------------------------------------------- #
# 指标复算：key -> 数值（int / float / str）；None 表示当前环境不可判定
# --------------------------------------------------------------------------- #
def _tree_mb(root, skip=("dist", ".git", "__pycache__")):
    total = 0
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(cur, f))
            except OSError:
                pass
    return total / 1048576


def _load_eval_module():
    path = os.path.join(BASE, "tests", "eval.py")
    if not os.path.exists(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("_doccheck_eval", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:                                    # noqa: BLE001
        return None


def _eval_metrics(x):
    ev = _load_eval_module()
    if ev is None:
        return None
    try:
        strong = ev.load_jsonl(ev.GOLD_PATH)
        manual = (ev.load_jsonl(ev.GOLD_MANUAL_PATH)
                  if os.path.exists(ev.GOLD_MANUAL_PATH) else [])
        by_id = {g["id"]: g for g in strong}
        for g in manual:
            by_id[g["id"]] = g
        merged = sorted(by_id.values(), key=lambda g: g["id"])
        res = ev.evaluate(merged, x)
        rule = ev.evaluate(strong, x)
        out = {
            "eval_n": res["n"], "eval_mod_ok": res["mod_ok"],
            "eval_mod_pct": round(res["mod_acc"] * 100, 1),
            "eval_code_ok": res["code_ok"], "eval_code_n": res["code_n"],
            "eval_code_pct": round(res["code_acc"] * 100, 1),
            "eval_rule": len(strong), "eval_manual": len(manual),
            "eval_rule_ok": rule["mod_ok"],
            "eval_rule_pct": round(rule["mod_acc"] * 100, 1),
            "eval_rule_code_ok": rule["code_ok"],
            "eval_rule_code_pct": round(rule["code_acc"] * 100, 1),
        }
        if os.path.exists(ev.GOLD_WEAK_PATH):
            weak = ev.load_jsonl(ev.GOLD_WEAK_PATH)
            wres = ev.evaluate(weak, x)
            out.update({
                "weak_n": wres["n"], "weak_mod_ok": wres["mod_ok"],
                "weak_mod_pct": round(wres["mod_acc"] * 100, 1),
                "weak_code_n": wres["code_n"], "weak_code_ok": wres["code_ok"],
                "weak_code_pct": round(wres["code_acc"] * 100, 1),
            })
        return out
    except Exception:                                    # noqa: BLE001
        return None


def compute():
    x = load_jsonl("xingce.jsonl")
    s = load_jsonl("shenlun.jsonl")
    m = {}

    x_ans = [r for r in x if has_ans(r)]
    s_ans = [r for r in s if has_ans(r)]
    x_main = [r for r in x if r.get("canonical", r["id"]) == r["id"]]

    groups = collections.defaultdict(list)
    for r in x:
        groups[r.get("canonical") or r["id"]].append(r)
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    conflicts = [k for k, v in groups.items()
                 if len({r["ans"] for r in v if has_ans(r)}) > 1]
    cross_mod = [k for k, v in groups.items() if len({r.get("module") for r in v}) > 1]

    m["xingce_total"] = len(x)
    m["shenlun_total"] = len(s)
    m["total"] = len(x) + len(s)
    m["x_papers"] = len({(r["prov"], r["year"], r["vol"]) for r in x})
    m["s_papers"] = len({r["paper"] for r in s})
    m["x_main"] = len(x_main)
    m["variants"] = len(x) - len(x_main)
    m["variant_pct"] = round((len(x) - len(x_main)) / len(x) * 100, 1)
    m["folded_total"] = len(x_main) + len(s)
    m["groups"] = len(groups)
    m["multi_groups"] = len(multi)
    m["ans_conflicts"] = len(conflicts)
    m["cross_module_groups"] = len(cross_mod)
    m["x_ans"] = len(x_ans)
    m["x_missing"] = len(x) - len(x_ans)
    m["x_ans_pct"] = round(len(x_ans) / len(x) * 100, 1)
    m["x_missing_pct"] = round((len(x) - len(x_ans)) / len(x) * 100, 1)
    # ans_note 有两类（v1.10）：
    #   ① 置空说明（ans 为空）：答案越界/同题变体冲突，输出时代替答案；
    #   ② 订正说明（ans 非空）：`答案按原卷解析订正（原 ans=X 与解析结论不一致）`，
    #      答案本身可用，说明只作附注。
    # 文档里的「答案置空 N 条」「其中 N 条是判断题」只统计 ①，所以 x_ans_note 保持
    # 只数「ans 为空」的说明；「带 ans_note 合计」用 x_ans_note_all。
    x_ans_note_recs = [r for r in x
                       if (r.get("ans_note") or "").strip() and not has_ans(r)]
    m["x_ans_note"] = len(x_ans_note_recs)
    m["ans_note_judge"] = sum(
        1 for r in x_ans_note_recs
        if set((r.get("opts") or {}).values()) == {"正确", "错误"})
    m["x_ans_note_all"] = sum(1 for r in x if (r.get("ans_note") or "").strip())
    m["x_ans_fixed"] = m["x_ans_note_all"] - m["x_ans_note"]
    m["ans_note_variant"] = sum(
        1 for r in x
        if (r.get("ans_note") or "").strip().startswith("同题变体答案不一致"))
    m["s_ans"] = len(s_ans)
    m["s_missing"] = len(s) - len(s_ans)
    snotes = collections.Counter((r.get("ans_note") or "").strip()
                                 for r in s if (r.get("ans_note") or "").strip())
    m["s_ans_note"] = sum(snotes.values())
    m["s_note_align"] = snotes.get("答案无法可靠对齐，见本卷「参考答案原文」", 0)
    m["s_note_absent"] = snotes.get("原卷未提供可提取的参考答案", 0)
    m["ans_note_total"] = m["x_ans_note_all"] + m["s_ans_note"]

    flags = collections.Counter(r.get("stem_flag") for r in x)
    for f in ("short", "watermark", "contaminated", "missing_opts"):
        m["flag_" + f] = flags.get(f, 0)
    m["flag_total"] = sum(1 for r in x if r.get("stem_flag"))

    idir = os.path.join(REF, "images")
    imgs = os.listdir(idir) if os.path.isdir(idir) else []
    m["img_total"] = len(imgs)
    m["img_m"] = sum(1 for n in imgs if n.endswith("-m.jpg"))
    m["img_p2"] = sum(1 for n in imgs if "-p2" in n)
    m["img_q"] = len(imgs) - m["img_m"] - m["img_p2"]
    m["mat_recs"] = sum(1 for r in x if r.get("mat_img"))
    if imgs:
        m["img_mb"] = round(sum(os.path.getsize(os.path.join(idir, n)) for n in imgs) / 1048576, 1)

    code_cnt = collections.Counter(r["code"] for r in x + s)
    m["codes"] = len(code_cnt)
    # 考点体系全集：以 docs/kaodian-taxonomy.md 的编码表为准（无流水线时唯一可得的字典）
    tax = os.path.join(BASE, "docs", "kaodian-taxonomy.md")
    if os.path.exists(tax):
        with open(tax, encoding="utf-8") as f:
            body = f.read()
        m["codes_total"] = len(set(re.findall(r"^\|\s*`([A-Z]{2}-[A-Z]+)`\s*\|", body, re.M)))
        m["zero_codes"] = max(0, m["codes_total"] - m["codes"])
        m["sub_tags"] = _sub_tags(body)
    kd = os.path.join(REF, "kaodian")
    if os.path.isdir(kd):
        m["kd_files"] = len([n for n in os.listdir(kd) if n.endswith(".md")])
        m["kd_entries"] = len(os.listdir(kd))
    sp = os.path.join(kd, "split")
    if os.path.isdir(sp):
        m["split_files"] = len([n for n in os.listdir(sp) if n.endswith(".md")])

    mods = collections.Counter(r["module"] for r in x)
    for k, name in (("zl", "资料分析"), ("sl", "数量关系"), ("yy", "言语理解"),
                    ("pd", "判断推理"), ("cs", "常识判断")):
        m["mod_" + k] = mods.get(name, 0)
        m["mod_" + k + "_pct"] = round(mods.get(name, 0) / len(x) * 100, 1)

    pt = [r for r in x if r["code"] == "PD-TX"]
    m["pdtx"] = len(pt)
    m["pdtx_folded"] = sum(1 for r in pt if r.get("canonical", r["id"]) == r["id"])
    for key, name in (("origami", "折纸盒"), ("views", "三视图"),
                      ("section", "截面"), ("assemble", "立体拼合")):
        rs = [r for r in pt if (r.get("sub") or "") == name]
        m[key] = len(rs)
        m[key + "_f"] = sum(1 for r in rs if r.get("canonical", r["id"]) == r["id"])

    def sub_count_of(code, name):
        rs = [r for r in x if r["code"] == code and (r.get("sub") or "") == name]
        return len(rs), sum(1 for r in rs if r.get("canonical", r["id"]) == r["id"])

    m["bili_full"], m["bili_folded"] = sub_count_of("ZL-BILI", "两期比重差")
    m["buli_full"], m["buli_folded"] = sub_count_of("SL-ZZ", "最不利构造")
    for i, name in enumerate(("一空", "两空", "三空及以上"), 1):
        full, folded = sub_count_of("YY-LJTK", name)
        m["ljt%d_full" % i], m["ljt%d_folded" % i] = full, folded
    zl = [r for r in x if r["code"] == "ZL-BASE"]
    m["zlbase_full"] = len(zl)
    m["zlbase_folded"] = sum(1 for r in zl if r.get("canonical", r["id"]) == r["id"])

    papers = collections.defaultdict(list)
    for r in x:
        papers[(r["prov"], r["year"], r["vol"])].append(r)
    m["papers"] = {k: (len(v), sum(1 for r in v if has_ans(r))) for k, v in papers.items()}
    complete = zero = partial = 0
    for n, a in m["papers"].values():
        complete += 1 if a == n else 0
        zero += 1 if a == 0 else 0
        partial += 1 if 0 < a < n else 0
    m["complete_papers"], m["zero_papers"], m["partial_papers"] = complete, zero, partial

    m["fig"] = sum(1 for r in x if r.get("fig"))
    m["fig_noopts"] = sum(1 for r in x if r.get("fig") and not r.get("opts"))

    sp_papers = collections.defaultdict(list)
    for r in s:
        sp_papers[r["paper"]].append(r)
    m["s_with_sub"] = sum(1 for v in sp_papers.values() if any(has_ans(r) for r in v))
    m["s_only_paper"] = sum(1 for v in sp_papers.values()
                            if not any(has_ans(r) for r in v)
                            and any(r.get("paper_answer") for r in v))
    m["s_none"] = sum(1 for v in sp_papers.values()
                      if not any(has_ans(r) for r in v)
                      and not any(r.get("paper_answer") for r in v))

    ev = _eval_metrics(x)
    if ev:
        m.update(ev)
    else:
        for k in ("eval_n", "eval_mod_ok", "eval_mod_pct", "eval_code_ok",
                  "eval_code_n", "eval_code_pct", "eval_rule", "eval_manual",
                  "weak_n", "weak_mod_ok", "weak_mod_pct", "weak_code_n", "weak_code_ok", "weak_code_pct"):
            m[k] = None

    m["full_tree_mb"] = round(_tree_mb(BASE), 1)
    zips = os.listdir(DIST) if os.path.isdir(DIST) else []
    for tag in ("lite", "full"):
        name = next((n for n in zips if tag in n and n.endswith(".zip")), None)
        m[tag + "_zip_mb"] = (round(os.path.getsize(os.path.join(DIST, name)) / 1048576, 1)
                              if name else None)
        m[tag + "_zip_name"] = name

    for name, key in (("xingce.jsonl", "size_x"), ("shenlun.jsonl", "size_s"),
                      ("search-index.tsv", "size_idx")):
        p = os.path.join(DATA, name)
        if os.path.exists(p):
            m[key + "_mb"] = round(os.path.getsize(p) / 1048576, 1)
    for sub, key in (("images", "size_img"), ("juan", "size_juan"),
                     ("shenlun", "size_sn"), ("kaodian", "size_kd")):
        d = os.path.join(REF, sub)
        if os.path.isdir(d):
            m[key + "_mb"] = round(_tree_mb(d, skip=()), 1)

    m["version"] = None
    sp = os.path.join(BASE, "skill.json")
    if os.path.exists(sp):
        try:
            with open(sp, encoding="utf-8-sig") as f:
                m["version"] = json.load(f).get("version")
        except (OSError, ValueError):
            pass
    return m


def _sub_tags(tax_body):
    """三级子考点标签总数：优先读流水线定义（本地），CI 无流水线时取 taxonomy 表头。"""
    pipe = os.path.join(os.path.dirname(BASE), "pipeline", "subtaxonomy.py")
    if os.path.exists(pipe):
        try:
            spec = importlib.util.spec_from_file_location("_doccheck_sub", pipe)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.sub_count()
        except Exception:                                # noqa: BLE001
            pass
    hit = re.search(r"三级子考点\*\*：(\d+) 个标签", tax_body)
    return int(hit.group(1)) if hit else None


# --------------------------------------------------------------------------- #
# 版本号一致性（v1.11）：skill.json / SKILL.md frontmatter / CHANGELOG 首条
# --------------------------------------------------------------------------- #
VERSION_RULES = (
    ("skill.json", re.compile(r'"version"\s*:\s*"([^"]+)"')),
    ("SKILL.md", re.compile(r"(?m)^version:\s*([^\s#]+)\s*$")),
    ("CHANGELOG.md", re.compile(r"(?m)^##\s*v(\d+\.\d+\.\d+)")),
)


def read_versions(texts=None):
    """返回 [(文件, 版本, 行号, 起列, 止列)]；texts 可覆盖磁盘读取（测试用）。"""
    out = []
    for fname, rx in VERSION_RULES:
        if texts is not None:
            text = texts.get(fname)
        else:
            path = os.path.join(BASE, fname)
            text = _read_text(path) if os.path.exists(path) else None
        if text is None:
            continue
        mo = rx.search(text)
        if not mo:
            continue
        out.append((fname, mo.group(1), text[:mo.start()].count("\n") + 1,
                    mo.start(1), mo.end(1)))
    return out


def check_version(texts=None):
    """三项版本号必须相同；缺失或漂移时返回一条「版本号不一致」mismatch。"""
    found = read_versions(texts)
    if len(found) != len(VERSION_RULES):
        seen = {f for f, *_ in found}
        missing = [f for f, _ in VERSION_RULES if f not in seen]
        return [{"file": " / ".join(missing), "line": 0, "col": None, "end": None,
                 "name": "版本号不一致", "key": "version",
                 "doc": "未读到版本号",
                 "actual": "skill.json / SKILL.md / CHANGELOG.md 都要能解析出版本号",
                 "fixable": False}]
    values = [v for _, v, *_ in found]
    if len(set(values)) == 1:
        return []
    summary = "当前 " + " / ".join(f"{f}={v}" for f, v, *_ in found)
    return [{"file": " / ".join(f for f, *_ in found), "line": 0, "col": None, "end": None,
             "name": "版本号不一致", "key": "version",
             "doc": summary, "actual": "三者必须相同", "fixable": False}]


def _read_text(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


# --------------------------------------------------------------------------- #
# 指标元信息：格式 + 人类可读名
# --------------------------------------------------------------------------- #
KIND = {}
for _k in ("xingce_total shenlun_total total x_papers s_papers x_main variants groups "
           "multi_groups folded_total ans_conflicts cross_module_groups x_ans x_missing x_ans_note "
           "ans_note_judge s_ans s_missing s_ans_note s_note_align s_note_absent "
           "flag_short flag_watermark flag_contaminated flag_missing_opts flag_total "
           "img_total img_q img_m img_p2 mat_recs codes codes_total zero_codes sub_tags "
           "kd_files kd_entries split_files mod_zl mod_sl mod_yy mod_pd mod_cs pdtx "
           "pdtx_folded origami origami_f views views_f section section_f assemble "
           "assemble_f bili_full bili_folded buli_full buli_folded ljt1_full ljt1_folded "
           "ljt2_full ljt2_folded ljt3_full ljt3_folded zlbase_full zlbase_folded "
           "complete_papers zero_papers partial_papers fig fig_noopts s_with_sub "
           "s_only_paper s_none eval_n eval_mod_ok eval_code_ok eval_code_n eval_rule "
           "eval_manual weak_n weak_mod_ok weak_code_n weak_code_ok ans_note_total ans_note_variant "
           "eval_rule_ok eval_rule_code_ok").split():
    KIND[_k] = "int"
for _k in ("variant_pct x_ans_pct x_missing_pct mod_zl_pct mod_sl_pct mod_yy_pct "
           "mod_pd_pct mod_cs_pct eval_mod_pct eval_code_pct weak_mod_pct "
           "weak_code_pct eval_rule_pct eval_rule_code_pct").split():
    KIND[_k] = "pct"
for _k in ("img_mb full_tree_mb lite_zip_mb full_zip_mb size_x_mb size_s_mb "
           "size_idx_mb size_img_mb size_juan_mb size_sn_mb size_kd_mb").split():
    KIND[_k] = "mb"
KIND["version"] = "str"

NAME = {
    "xingce_total": "行测题量", "shenlun_total": "申论题量", "total": "合计题量",
    "x_main": "折叠后主记录", "variants": "同题变体", "variant_pct": "变体占比",
    "folded_total": "折叠后合计", "groups": "折叠组", "multi_groups": "含变体的组",
    "ans_conflicts": "同组答案冲突",
    "cross_module_groups": "跨模块变体组", "x_ans": "行测有答案", "x_missing": "行测缺答案",
    "x_ans_pct": "行测有答案占比", "x_missing_pct": "缺失比例", "x_ans_note": "行测 ans_note",
    "ans_note_judge": "判断题置空条数", "s_ans": "申论有答案", "s_missing": "申论缺答案",
    "s_ans_note": "申论 ans_note", "s_note_align": "申论对齐失败", "s_note_absent": "申论原卷未提供",
    "flag_short": "stem_flag short", "flag_watermark": "stem_flag watermark",
    "flag_contaminated": "stem_flag contaminated", "flag_missing_opts": "stem_flag missing_opts",
    "flag_total": "stem_flag 合计", "img_total": "配图总数", "img_q": "题目图",
    "img_m": "材料图", "img_p2": "跨页续图", "mat_recs": "材料图记录数",
    "img_mb": "配图体积", "codes": "考点 code 数", "codes_total": "考点编码全集",
    "zero_codes": "零题编码", "sub_tags": "三级子考点标签", "kd_files": "考点文件",
    "kd_entries": "考点目录条目", "split_files": "年代分片", "pdtx": "PD-TX 全量",
    "pdtx_folded": "PD-TX 折叠后", "origami": "折纸盒全量", "origami_f": "折纸盒折叠后",
    "views": "三视图全量", "views_f": "三视图折叠后", "section": "截面全量",
    "section_f": "截面折叠后", "assemble": "立体拼合全量", "assemble_f": "立体拼合折叠后",
    "complete_papers": "答案完整卷", "zero_papers": "零答案卷", "partial_papers": "部分缺失卷",
    "fig": "fig=true", "fig_noopts": "fig 且 opts 为空", "eval_n": "eval 样本数",
    "eval_mod_ok": "eval 模块命中", "eval_mod_pct": "eval 模块准确率",
    "eval_code_ok": "eval 考点命中", "eval_code_n": "eval 考点样本",
    "eval_code_pct": "eval 考点准确率", "eval_rule": "规则集样本", "eval_manual": "人工集样本",
    "eval_rule_ok": "规则集模块命中", "eval_rule_pct": "规则集模块准确率",
    "eval_rule_code_ok": "规则集考点命中", "eval_rule_code_pct": "规则集考点准确率",
    "ans_note_total": "ans_note 总数", "ans_note_variant": "变体冲突置空条数",
    "x_ans_note_all": "行测 ans_note 总数", "x_ans_fixed": "行测答案订正说明",
    "weak_n": "弱标注样本", "weak_mod_pct": "弱标注模块准确率",
    "weak_code_n": "弱标注考点样本", "weak_code_ok": "弱标注考点命中", "weak_code_pct": "弱标注考点准确率",
    "full_tree_mb": "full 解压体积", "lite_zip_mb": "lite zip 体积",
    "full_zip_mb": "full zip 体积", "mod_zl": "资料分析题量", "mod_sl": "数量关系题量",
    "mod_yy": "言语理解题量", "mod_pd": "判断推理题量", "mod_cs": "常识判断题量",
    "bili_full": "两期比重差全量", "bili_folded": "两期比重差折叠后",
    "buli_full": "最不利构造全量", "buli_folded": "最不利构造折叠后",
    "ljt1_full": "逻辑填空一空全量", "ljt1_folded": "逻辑填空一空折叠后",
    "ljt2_full": "逻辑填空两空全量", "ljt2_folded": "逻辑填空两空折叠后",
    "ljt3_full": "逻辑填空三空全量", "ljt3_folded": "逻辑填空三空折叠后",
    "zlbase_full": "ZL-BASE 全量", "zlbase_folded": "ZL-BASE 折叠后",
    "s_with_sub": "申论含小题答案卷", "s_only_paper": "申论仅原文卷", "s_none": "申论两者皆无",
    "version": "版本号",
}


def fmt(key, value):
    kind = KIND.get(key, "int")
    if value is None:
        return ""
    if kind == "int":
        return f"{int(round(value)):,}".replace(",", " ")
    if kind == "pct":
        return f"{float(value):.1f}"
    if kind == "mb":
        return f"{float(value):.1f}"
    return str(value)


def parse_num(text):
    t = text.strip()
    for ch in " \t" + WS + "%":
        t = t.replace(ch, "")
    t = t.replace(",", "").replace("，", "")
    try:
        return float(t)
    except ValueError:
        return None


def same(key, doc_num, expected):
    if doc_num is None or expected is None:
        return True
    kind = KIND.get(key)
    if kind == "int":
        return int(round(doc_num)) == int(round(expected))
    if kind == "mb":
        # 体积随文件增删有 ~1MB 抖动（工作树 vs CI 检出），按 1MB 容差比对
        return abs(doc_num - float(expected)) < 1.0
    return abs(doc_num - float(expected)) < 0.05


# --------------------------------------------------------------------------- #
# 1) 快照表比对
# --------------------------------------------------------------------------- #
SNAPSHOT_KEYS = [
    ("行测题量", ["xingce_total"]),
    ("申论题量", ["shenlun_total"]),
    ("合计题量", ["total"]),
    ("行测试卷", ["x_papers"]),
    ("申论试卷", ["s_papers"]),
    ("折叠后主记录（行测）", ["x_main"]),
    ("同题变体（行测）", ["variants"]),
    ("折叠组", ["groups"]),
    ("行测有答案", ["x_ans", "x_ans_pct"]),
    ("行测缺答案", ["x_missing", "x_missing_pct"]),
    ("行测 ans_note", ["x_ans_note"]),
    ("行测答案订正说明", ["x_ans_fixed"]),
    ("同组答案冲突", ["ans_conflicts"]),
    ("申论有答案", ["s_ans"]),
    ("申论缺答案", ["s_missing"]),
    ("申论 ans_note", ["s_ans_note"]),
    ("stem_flag short", ["flag_short"]),
    ("stem_flag watermark", ["flag_watermark"]),
    ("stem_flag contaminated", ["flag_contaminated"]),
    ("stem_flag missing_opts", ["flag_missing_opts"]),
    ("stem_flag 合计", ["flag_total"]),
    ("配图总数", ["img_total"]),
    ("题目图", ["img_q"]),
    ("材料图", ["img_m"]),
    ("跨页续图", ["img_p2"]),
    ("考点 code 数（有题）", ["codes"]),
    ("零题编码", ["zero_codes"]),
    ("考点文件", ["kd_files"]),
    ("三级子考点标签", ["sub_tags"]),
    ("模块题量 资料分析", ["mod_zl"]),
    ("模块题量 数量关系", ["mod_sl"]),
    ("模块题量 言语理解", ["mod_yy"]),
    ("模块题量 判断推理", ["mod_pd"]),
    ("模块题量 常识判断", ["mod_cs"]),
    ("PD-TX 全量", ["pdtx"]),
    ("PD-TX 折叠后", ["pdtx_folded"]),
    ("折纸盒", ["origami", "origami_f"]),
    ("三视图", ["views", "views_f"]),
    ("截面", ["section", "section_f"]),
    ("立体拼合", ["assemble", "assemble_f"]),
    ("行测答案完整卷", ["complete_papers"]),
    ("行测零答案卷", ["zero_papers"]),
    ("行测部分缺失卷", ["partial_papers"]),
    ("fig=true", ["fig"]),
    ("eval 模块准确率", ["eval_mod_pct", "eval_mod_ok", "eval_n"]),
    ("eval 考点准确率", ["eval_code_pct", "eval_code_ok", "eval_code_n"]),
    ("eval 样本", ["eval_n"]),
    ("eval 弱标注 module", ["weak_mod_pct", "weak_mod_ok", "weak_n"]),
    ("eval 弱标注 code", ["weak_code_pct", "weak_code_ok", "weak_code_n"]),
    ("发行包 full（解压）", ["full_tree_mb"]),
    ("发行包 lite（zip）", ["lite_zip_mb"]),
]
SNAPSHOT_LABELS = {label: keys for label, keys in SNAPSHOT_KEYS}


def check_snapshot(m):
    """返回 (mismatches, notes)。mismatches 里的项不带 span（快照请重跑 gen_docs）。"""
    out, notes = [], []
    if not os.path.exists(SNAPSHOT):
        out.append({"file": "docs/stats-snapshot.md", "line": 0, "name": "文件缺失",
                    "doc": "", "actual": "不存在，先跑 python pipeline/gen_docs.py",
                    "fixable": False})
        return out, notes
    with open(SNAPSHOT, encoding="utf-8") as f:
        lines = f.read().splitlines()

    seen = {}
    for i, line in enumerate(lines, 1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("指标", "---"):
            continue
        label = cells[0]
        if label not in SNAPSHOT_LABELS:
            out.append({"file": "docs/stats-snapshot.md", "line": i, "name": "未知指标",
                        "doc": label, "actual": "doc_check 未登记该指标", "fixable": False})
            continue
        seen[label] = i
        keys = SNAPSHOT_LABELS[label]
        doc_nums = [parse_num(t) for t in re.findall(r"\d[\d  \u00a0\u2009]*\.?\d*", cells[1])]
        doc_nums = [n for n in doc_nums if n is not None]
        expected = [m.get(k) for k in keys]
        if all(v is None for v in expected):
            notes.append("%s: 当前环境无法复算，已跳过" % label)
            continue
        if len(doc_nums) != len(expected):
            out.append({"file": "docs/stats-snapshot.md", "line": i, "name": label,
                        "doc": cells[1],
                        "actual": " / ".join(fmt(k, m.get(k)) for k in keys if m.get(k) is not None),
                        "fixable": False})
            continue
        bad = [(k, d, m.get(k)) for k, d in zip(keys, doc_nums) if not same(k, d, m.get(k))]
        if bad:
            out.append({"file": "docs/stats-snapshot.md", "line": i, "name": label,
                        "doc": cells[1],
                        "actual": " / ".join(fmt(k, m.get(k)) for k in keys if m.get(k) is not None),
                        "fixable": False})

    for label in SNAPSHOT_LABELS:
        if label not in seen:
            out.append({"file": "docs/stats-snapshot.md", "line": 0, "name": "缺少指标：" + label,
                        "doc": "—", "actual": "快照表缺该行（重跑 gen_docs）", "fixable": False})
    return out, notes


# --------------------------------------------------------------------------- #
# 2) 文档关键数字扫描
# --------------------------------------------------------------------------- #
# 每条规则：(文件, 正则, [(组号, 指标key), ...])
# 正则里必须用命名组 g0/g1/... 标记要核对的数字，其余部分只做上下文定位。
RULES = [
    # ---------------- SKILL.md ----------------
    ("SKILL.md", r"^version: (?P<g0>[\d.]+)$", [(0, "version")]),
    ("SKILL.md", r"make_release\.py --version (?P<g0>[\d.]+)", [(0, "version")]),
    ("SKILL.md", r"行测 (?P<g0>[\d ]+) 题 \+ 申论 (?P<g1>\d+) 题", [(0, "xingce_total"), (1, "shenlun_total")]),
    ("SKILL.md", r"1 行 1 题，(?P<g0>[\d ]+) 题", [(0, "xingce_total")]),
    ("SKILL.md", r"1 行 1 小题，(?P<g0>\d+) 题（(?P<g1>\d+) 题有参考答案，(?P<g2>\d+) 题见原卷）",
     [(0, "shenlun_total"), (1, "s_ans"), (2, "s_missing")]),
    ("SKILL.md", r"(?P<g0>\d+) 个考点文件", [(0, "kd_files")]),
    ("SKILL.md", r"(?P<g0>\d+) 个年代分片", [(0, "split_files")]),
    ("SKILL.md", r"(?P<g0>[\d ]+) 张原题配图", [(0, "img_total")]),
    ("SKILL.md", r"\*\*全量\*\*（含同题变体） \| 行测 (?P<g0>[\d ]+) \+ 申论 (?P<g1>\d+) = \*\*(?P<g2>[\d ]+)\*\*",
     [(0, "xingce_total"), (1, "shenlun_total"), (2, "total")]),
    ("SKILL.md", r"\*\*同题折叠后\*\*（主记录） \| 行测 (?P<g0>[\d ]+) \+ 申论 (?P<g1>\d+) = \*\*(?P<g2>[\d ]+)\*\*",
     [(0, "x_main"), (1, "shenlun_total"), (2, "folded_total")]),
    ("SKILL.md", r"两者相差约 \*\*(?P<g0>[\d.]+)%\*\*（行测 [\d ]+ 条里有 \*\*(?P<g1>[\d ]+) 条是同题变体）",
     [(0, "variant_pct"), (1, "variants")]),
    ("SKILL.md", r"\*\*(?P<g0>[\d ]+) / [\d ]+ 题有答案\*\*；(?P<g1>[\d ]+) 题缺失（\*\*(?P<g2>[\d.]+)%\*\*）",
     [(0, "x_ans"), (1, "x_missing"), (2, "x_missing_pct")]),
    ("SKILL.md", r"集中在 (?P<g0>\d+) 套原始答案 PDF 无文字层的卷", [(0, "zero_papers")]),
    ("SKILL.md", r"\*\*行测答案置空 (?P<g0>\d+) 条\*\*", [(0, "x_ans_note")]),
    ("SKILL.md", r"当前 (?P<g0>\d+) 条，其中 (?P<g1>\d+) 条是判断题", [(0, "x_ans_note"), (1, "ans_note_judge")]),
    ("SKILL.md", r"419 题中 \*\*(?P<g0>\d+) 题有参考答案\*\*，\*\*(?P<g1>\d+) 题见原卷\*\*"
                 r"（(?P<g2>\d+) 条 `ans_note=\"答案无法可靠对齐",
     [(0, "s_ans"), (1, "s_missing"), (2, "s_note_align")]),
    ("SKILL.md", r"当前同组答案冲突 \*\*(?P<g0>\d+) 组\*\*", [(0, "ans_conflicts")]),
    ("SKILL.md", r"(\d+) 套中 \*\*(?P<g0>\d+) 套\*\*有「三、参考答案（按小题）」\+「四、参考答案原文」，"
                 r"\*\*(?P<g1>\d+) 套\*\*只有「四、参考答案原文」（小题级答案无法可靠对齐），"
                 r"\*\*(?P<g2>\d+) 套\*\*两者皆无",
     [(0, "s_with_sub"), (1, "s_only_paper"), (2, "s_none")]),
    ("SKILL.md", r"全库 (?P<g0>[\d ]+) 个含变体的组已逐一校验：同组答案冲突 (?P<g1>\d+) 组、"
                 r"跨模块变体组 (?P<g2>\d+) 组",
     [(0, "multi_groups"), (1, "ans_conflicts"), (2, "cross_module_groups")]),
    ("SKILL.md", r"全库 `fig=true`（选项本身是图片）\*\*(?P<g0>[\d ]+) 条\*\*", [(0, "fig")]),
    ("SKILL.md", r"（全库 \*\*(?P<g0>[\d ]+) 条\*\*，其中 (?P<g1>[\d ]+) 条 `opts` 为空）",
     [(0, "fig"), (1, "fig_noopts")]),
    ("SKILL.md", r"折叠后 (?P<g0>\d+) 道（全量 (?P<g1>\d+) 道", [(0, "zlbase_folded"), (1, "zlbase_full")]),
    ("SKILL.md", r"折叠后 (?P<g0>\d+) 题，全量 (?P<g1>\d+) 题", [(0, "zlbase_folded"), (1, "zlbase_full")]),
    ("SKILL.md", r"`两期比重差` \*\*(?P<g0>\d+) 题\*\*（全量 (?P<g1>\d+)）",
     [(0, "bili_folded"), (1, "bili_full")]),
    ("SKILL.md", r"`最不利构造` \*\*(?P<g0>\d+) 题\*\*（全量 (?P<g1>\d+)）",
     [(0, "buli_folded"), (1, "buli_full")]),
    ("SKILL.md", r"一空 (?P<g0>\d+) / 两空 (?P<g1>\d+) / 三空及以上 (?P<g2>\d+)"
                 r"（全量 (?P<g3>[\d ]+) / (?P<g4>[\d ]+) / (?P<g5>[\d ]+)）",
     [(0, "ljt1_folded"), (1, "ljt2_folded"), (2, "ljt3_folded"),
      (3, "ljt1_full"), (4, "ljt2_full"), (5, "ljt3_full")]),
    ("SKILL.md", r"题量不变（(?P<g0>\d+) 全量，折叠后 (?P<g1>\d+)）",
     [(0, "pdtx"), (1, "pdtx_folded")]),
    ("SKILL.md", r"\| 折纸盒 \| (?P<g0>\d+) \| (?P<g1>\d+) \|", [(0, "origami"), (1, "origami_f")]),
    ("SKILL.md", r"\| 三视图 \| (?P<g0>\d+) \| (?P<g1>\d+) \|", [(0, "views"), (1, "views_f")]),
    ("SKILL.md", r"\| 截面 \| (?P<g0>\d+) \| (?P<g1>\d+) \|", [(0, "section"), (1, "section_f")]),
    ("SKILL.md", r"\| 立体拼合 \| (?P<g0>\d+) \| (?P<g1>\d+) \|", [(0, "assemble"), (1, "assemble_f")]),
    ("SKILL.md", r"命中 (?P<g0>\d+) 题（折叠后）", [(0, "origami_f")]),
    ("SKILL.md", r"命中 (?P<g0>\d+) 题（折叠后；按同题计 (?P<g1>\d+)）",
     [(0, "views_f"), (1, "views")]),
    ("SKILL.md", r"当前标记 \*\*(?P<g0>\d+) 条\*\*（`short` (?P<g1>\d+) / `watermark` (?P<g2>\d+) / "
                 r"`contaminated` (?P<g3>\d+) / `missing_opts` (?P<g4>\d+)）",
     [(0, "flag_total"), (1, "flag_short"), (2, "flag_watermark"),
      (3, "flag_contaminated"), (4, "flag_missing_opts")]),
    ("SKILL.md", r"（`short` (?P<g0>\d+) / `watermark` (?P<g1>\d+) / `contaminated` (?P<g2>\d+) / "
                 r"`missing_opts` (?P<g3>\d+)，共 (?P<g4>\d+) 条）",
     [(0, "flag_short"), (1, "flag_watermark"), (2, "flag_contaminated"),
      (3, "flag_missing_opts"), (4, "flag_total")]),
    # ---------------- README.md ----------------
    ("README.md", r"历年基期量真题 (?P<g0>\d+) 道（同题折叠后；全量 (?P<g1>\d+) 道）",
     [(0, "zlbase_folded"), (1, "zlbase_full")]),
    ("README.md", r"有答案 (?P<g0>[\d ]+) 题\*\*；同题变体 (?P<g1>[\d ]+) 条已折叠，折叠后 (?P<g2>[\d ]+) 题",
     [(0, "x_ans"), (1, "variants"), (2, "x_main")]),
    ("README.md", r"\*\*(?P<g0>\d+)\*\* 题有参考答案，\*\*(?P<g1>\d+)\*\* 题见原卷",
     [(0, "s_ans"), (1, "s_missing")]),
    ("README.md", r"另有 (?P<g0>\d+) 条答案因越界/同题变体冲突被置空", [(0, "x_ans_note")]),
    ("README.md", r"3 536 个文件（约 (?P<g0>\d+)MB）：题目图 (?P<g1>[\d ]+) \+ 材料图 (?P<g2>\d+)"
                 r"（表格/图表独立裁切、同组共享；按记录计 (?P<g3>[\d ]+) 条）\+ 跨页续图 (?P<g4>\d+)",
     [(0, "img_mb"), (1, "img_q"), (2, "img_m"), (3, "mat_recs"), (4, "img_p2")]),
    ("README.md", r"模块分布：判断推理 (?P<g0>[\d.]+)%、言语理解 (?P<g1>[\d.]+)%、"
                 r"常识判断 (?P<g2>[\d.]+)%、资料分析 (?P<g3>[\d.]+)%、数量关系 (?P<g4>[\d.]+)%",
     [(0, "mod_pd_pct"), (1, "mod_yy_pct"), (2, "mod_cs_pct"),
      (3, "mod_zl_pct"), (4, "mod_sl_pct")]),
    ("README.md", r"答案缺失 \*\*(?P<g0>[\d.]+)%（(?P<g1>[\d ]+) 题）\*\*",
     [(0, "x_missing_pct"), (1, "x_missing")]),
    ("README.md", r"(?P<g0>\d+) 个年代分片", [(0, "split_files")]),
    ("README.md", r"# 行测 (?P<g0>[\d ]+) 题 / 申论 (?P<g1>\d+) 题 / 考点文件 (?P<g2>\d+) 个",
     [(0, "xingce_total"), (1, "shenlun_total"), (2, "kd_entries")]),
    ("README.md", r"# 答案缺失 (?P<g0>[\d ]+) 题（(?P<g1>[\d.]+)%）",
     [(0, "x_missing"), (1, "x_missing_pct")]),
    ("README.md", r"(?P<g0>\d+) 个有题考点（`--list-kaodian` 合计 (?P<g1>[\d ]+) 题）",
     [(0, "codes"), (1, "total")]),
    ("README.md", r"三级子考点 (?P<g0>\d+) 个标签", [(0, "sub_tags")]),
    ("README.md", r"make_release\.py --version (?P<g0>[\d.]+)", [(0, "version")]),
    # ---------------- docs/coverage.md ----------------
    ("docs/coverage.md", r"\| 行测有答案 \| \*\*(?P<g0>[\d ]+) 题（(?P<g1>[\d.]+)%）\*\*",
     [(0, "x_ans"), (1, "x_ans_pct")]),
    ("docs/coverage.md", r"\| 行测答案完整卷 \| (?P<g0>\d+) 套 \|", [(0, "complete_papers")]),
    ("docs/coverage.md", r"\| 行测零答案卷 \| (?P<g0>\d+) 套", [(0, "zero_papers")]),
    ("docs/coverage.md", r"\| 行测部分缺失卷 \| (?P<g0>\d+) 套", [(0, "partial_papers")]),
    ("docs/coverage.md", r"\| 申论小题 \| 419 题（\*\*(?P<g0>\d+)\*\* 题有参考答案，\*\*(?P<g1>\d+)\*\* 题见原卷）",
     [(0, "s_ans"), (1, "s_missing")]),
    ("docs/coverage.md", r"3 536 个文件（题目图 (?P<g0>[\d ]+) \+ 材料图 (?P<g1>\d+) \+ 跨页续图 (?P<g2>\d+)，"
                          r"约 (?P<g3>\d+)MB；材料图按记录计 (?P<g4>[\d ]+) 条）",
     [(0, "img_q"), (1, "img_m"), (2, "img_p2"), (3, "img_mb"), (4, "mat_recs")]),
    ("docs/coverage.md", r"同题变体 \| (?P<g0>[\d ]+) 条（已折叠，--all-variants 展开）；含变体的组 (?P<g1>[\d ]+) 组",
     [(0, "variants"), (1, "multi_groups")]),
    ("docs/coverage.md", r"折纸盒 (?P<g0>\d+) / 三视图 (?P<g1>\d+) / 截面 (?P<g2>\d+) / 立体拼合 (?P<g3>\d+)"
                          r"（`PD-TX` 二级子考点，全量口径；折叠后 (?P<g4>\d+) / (?P<g5>\d+) / (?P<g6>\d+) / (?P<g7>\d+)）",
     [(0, "origami"), (1, "views"), (2, "section"), (3, "assemble"),
      (4, "origami_f"), (5, "views_f"), (6, "section_f"), (7, "assemble_f")]),
    ("docs/coverage.md", r"\*\*答案置空 (?P<g0>\d+) 条\*\*", [(0, "x_ans_note")]),
    ("docs/coverage.md", r"图选项题（`fig=true`，(?P<g0>\d+) 条）", [(0, "fig")]),
    ("docs/coverage.md", r"`fig=true`（全库 (?P<g0>\d+) 条", [(0, "fig")]),
    ("docs/coverage.md", r"全库 \*\*(?P<g0>\d+) 条\*\*——`short` (?P<g1>\d+)、`watermark` (?P<g2>\d+)、"
                          r"`contaminated` (?P<g3>\d+)、`missing_opts` (?P<g4>\d+)",
     [(0, "flag_total"), (1, "flag_short"), (2, "flag_watermark"),
      (3, "flag_contaminated"), (4, "flag_missing_opts")]),
    ("docs/coverage.md", r"419 题中 \*\*(?P<g0>\d+) 题有参考答案\*\*，\*\*(?P<g1>\d+) 题见原卷\*\*："
                          r"其中 (?P<g2>\d+) 条 `ans_note=\"答案无法可靠对齐",
     [(0, "s_ans"), (1, "s_missing"), (2, "s_note_align")]),
    ("docs/coverage.md", r"卷文件层面：\*\*(?P<g0>\d+) 套\*\*有「三、参考答案（按小题）」\+「四、参考答案原文」；"
                          r"\*\*(?P<g1>\d+) 套\*\*只有「四、参考答案原文」（小题级答案无法可靠对齐）；"
                          r"\*\*(?P<g2>\d+) 套\*\*两者皆无",
     [(0, "s_with_sub"), (1, "s_only_paper"), (2, "s_none")]),
    # ---------------- docs/distribution.md ----------------
    ("docs/distribution.md", r"体积（zip / 解压） \| (?P<g0>[\d.]+) MB / 约 [\d.]+ MB \| "
                             r"(?P<g1>[\d.]+) MB / (?P<g2>[\d.]+) MB",
     [(0, "lite_zip_mb"), (1, "full_zip_mb"), (2, "full_tree_mb")]),
    ("docs/distribution.md", r"3 536 张 JPEG） \| (?P<g0>[\d.]+) MB", [(0, "size_img_mb")]),
    ("docs/distribution.md", r"（(?P<g0>\d+) 套行测原卷） \| (?P<g1>[\d.]+) MB", [(0, "x_papers"), (1, "size_juan_mb")]),
    ("docs/distribution.md", r"（(?P<g0>\d+) 套申论原卷） \| (?P<g1>[\d.]+) MB", [(0, "s_papers"), (1, "size_sn_mb")]),
    ("docs/distribution.md", r"\+ 分片 \| (?P<g0>[\d.]+) MB", [(0, "size_kd_mb")]),
    ("docs/distribution.md", r"`data/xingce\.jsonl` \| (?P<g0>[\d.]+) MB", [(0, "size_x_mb")]),
    ("docs/distribution.md", r"`data/shenlun\.jsonl` \| (?P<g0>[\d.]+) MB", [(0, "size_s_mb")]),
    ("docs/distribution.md", r"`data/search-index\.tsv` \| (?P<g0>[\d.]+) MB", [(0, "size_idx_mb")]),
    ("docs/distribution.md", r"申论 106 \+ 分片 (?P<g0>\d+)）", [(0, "split_files")]),
    # ---------------- docs/install.md ----------------
    ("docs/install.md", r"\| \*\*lite\*\* \| (?P<g0>[\d.]+) MB", [(0, "lite_zip_mb")]),
    ("docs/install.md", r"\| \*\*full\*\* \| (?P<g0>[\d.]+) MB", [(0, "full_zip_mb")]),
    ("docs/install.md", r"\+ (?P<g0>[\d ]+) 张配图", [(0, "img_total")]),
    ("docs/install.md", r"适用版本：v(?P<g0>[\d.]+)", [(0, "version")]),
    # ---------------- docs/eval.md ----------------
    ("docs/eval.md", r"\| 规则集 (?P<g0>\d+) 条 \| \*\*规则 \+ 人工 (?P<g1>\d+) 条\*\*",
     [(0, "eval_rule"), (1, "eval_n")]),
    ("docs/eval.md", r"\| module \| (?P<g0>[\d.]+)%（(?P<g1>\d+)/(?P<g2>\d+)） \| "
                     r"\*\*(?P<g3>[\d.]+)%（(?P<g4>\d+)/(?P<g5>\d+)）\*\*",
     [(0, "eval_rule_pct"), (1, "eval_rule_ok"), (2, "eval_rule"),
      (3, "eval_mod_pct"), (4, "eval_mod_ok"), (5, "eval_n")]),
    ("docs/eval.md", r"\| code \| (?P<g0>[\d.]+)%（(?P<g1>\d+)/(?P<g2>\d+)） \| "
                     r"\*\*(?P<g3>[\d.]+)%（(?P<g4>\d+)/(?P<g5>\d+)）\*\*",
     [(0, "eval_rule_code_pct"), (1, "eval_rule_code_ok"), (2, "eval_rule"),
      (3, "eval_code_pct"), (4, "eval_code_ok"), (5, "eval_code_n")]),
    ("docs/eval.md", r"当前规模 \*\*(?P<g0>\d+) 条\*\*", [(0, "eval_rule")]),
    ("docs/eval.md", r"当前 \*\*(?P<g0>\d+) 条\*\*（含考点 (?P<g1>\d+) 条", [(0, "weak_n"), (1, "weak_code_n")]),
    ("docs/eval.md", r"考点准确率（当前 \*\*(?P<g0>[\d.]+)%\*\*）", [(0, "weak_code_pct")]),
    ("docs/eval.md", r"模块准确率（当前 \*\*(?P<g0>[\d.]+)%\*\*）", [(0, "weak_mod_pct")]),
    ("docs/eval.md", r"人工标注集 `tests/gold_manual.jsonl`（(?P<g0>\d+) 条）", [(0, "eval_manual")]),
    # ---------------- docs/data-spec.md ----------------
    ("docs/data-spec.md", r"`ans_note` \| string\\\|null \| .*?当前 (?P<g0>\d+) 条："
                           r"(?P<g1>\d+) 条 `\"原卷答案与选项不匹配\"`",
     [(0, "x_ans_note_all"), (1, "x_ans_note")]),
    ("docs/data-spec.md", r"全库 \*\*(?P<g0>\d+)\*\* 条，其中 (?P<g1>\d+) 条 `opts` 为空",
     [(0, "fig"), (1, "fig_noopts")]),
    ("docs/data-spec.md", r"当前 (?P<g0>\d+) 条：`short` (?P<g1>\d+) / `watermark` (?P<g2>\d+) / "
                           r"`contaminated` (?P<g3>\d+) / `missing_opts` (?P<g4>\d+)",
     [(0, "flag_total"), (1, "flag_short"), (2, "flag_watermark"),
      (3, "flag_contaminated"), (4, "flag_missing_opts")]),
    ("docs/data-spec.md", r"`null` 表示答案不可用（当前 (?P<g0>\d+) 条）", [(0, "s_missing")]),
    ("docs/data-spec.md", r"共 \*\*3 536 个文件、约 (?P<g0>\d+)MB\*\*：题目图 (?P<g1>[\d ]+) \+ "
                           r"材料图 (?P<g2>\d+)（.*?故 `mat_img` 字段有 \*\*(?P<g3>[\d ]+) 条\*\*记录引用）"
                           r"\+ 跨页续图 (?P<g4>\d+)",
     [(0, "img_mb"), (1, "img_q"), (2, "img_m"), (3, "mat_recs"), (4, "img_p2")]),
    ("docs/data-spec.md", r"合计 (?P<g0>\d+) 条带 `ans_note`（行测 (?P<g1>\d+) \+ 申论 (?P<g2>\d+)）",
     [(0, "ans_note_total"), (1, "x_ans_note_all"), (2, "s_ans_note")]),
    ("docs/data-spec.md", r"全库 (?P<g0>[\d ]+) 条为同题变体（行测 [\d ]+ → 折叠后 (?P<g1>[\d ]+)）",
     [(0, "variants"), (1, "x_main")]),
    ("docs/data-spec.md", r"含变体的组共 \*\*(?P<g0>[\d ]+)\*\* 组", [(0, "multi_groups")]),
    ("docs/data-spec.md", r"结果：\*\*(?P<g0>\d+) 组答案冲突、\*\*(?P<g1>\d+) 条成员答案置空\*\*",
     [(0, "ans_conflicts"), (1, "ans_note_variant")]),
    ("docs/data-spec.md", r"共 \*\*(?P<g0>[\d ]+) 题（(?P<g1>[\d.]+)%）\*\*", [(0, "x_missing"), (1, "x_missing_pct")]),
    # ---------------- skill.json ----------------
    ("skill.json", r"\"version\": \"(?P<g0>[\d.]+)\"", [(0, "version")]),
]


def _line_rules():
    """按文件聚合规则，便于逐行扫描。"""
    by_file = collections.defaultdict(list)
    for fname, pattern, groups in RULES:
        by_file[fname].append((re.compile(pattern), groups))
    return by_file


def check_docs(m, texts=None):
    """扫描文档关键数字。texts={"文件名": 文本} 可覆盖磁盘读取（供回归/审计用）。"""
    out = []
    by_file = _line_rules()
    for fname, rules in by_file.items():
        path = os.path.join(BASE, fname)
        if texts is not None:
            if fname not in texts:
                continue
            lines = texts[fname].splitlines()
        else:
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
        for i, line in enumerate(lines):
            for rx, groups in rules:
                for mo in rx.finditer(line):
                    for gi, key in groups:
                        text = mo.group("g%d" % gi)
                        if text is None:
                            continue
                        expected = m.get(key)
                        if expected is None:
                            continue
                        if KIND.get(key) == "str":
                            if text != str(expected):
                                out.append(_mk(fname, i + 1, mo.span("g%d" % gi), key, text, expected))
                            continue
                        doc_num = parse_num(text)
                        if doc_num is not None and not same(key, doc_num, expected):
                            out.append(_mk(fname, i + 1, mo.span("g%d" % gi), key, text, expected))
    return out


def _mk(fname, lineno, span, key, doc, expected):
    return {"file": fname, "line": lineno, "col": span[0], "end": span[1],
            "name": NAME.get(key, key), "key": key,
            "doc": doc, "actual": fmt(key, expected), "fixable": True}


# ---- 特殊：coverage 逐卷表（98 行，按 (prov, year, vol) 动态比对） ----
PAPER_ROW = re.compile(r"^\| (国考|广东|湖北) \| (\d{4}) \| ([^|]+?) \| (\d+) \| (\d+) \| ([^|]+?) \|$")
STATUS = {"✅": "ok", "⚠️": "part", "❌": "zero", "⚠": "part"}


def check_paper_table(m):
    path = os.path.join(BASE, "docs", "coverage.md")
    if not os.path.exists(path) or not m.get("papers"):
        return []
    out = []
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    seen = set()
    for i, line in enumerate(lines):
        mo = PAPER_ROW.match(line)
        if not mo:
            continue
        prov, year, vol, n, a, status = mo.groups()
        key = (prov, int(year), vol.strip())
        want = m["papers"].get(key)
        if not want:
            continue
        seen.add(key)
        want_n, want_a = want
        if int(n) != want_n:
            out.append(_mk("docs/coverage.md", i + 1, mo.span(4), "papers", n, want_n))
        if int(a) != want_a:
            out.append(_mk("docs/coverage.md", i + 1, mo.span(5), "papers", a, want_a))
        want_status = "ok" if want_a == want_n else ("zero" if want_a == 0 else "part")
        if STATUS.get(status.strip()) != want_status:
            emoji = {"ok": "✅", "part": "⚠️", "zero": "❌"}[want_status]
            out.append({"file": "docs/coverage.md", "line": i + 1,
                        "col": mo.start(6), "end": mo.end(6), "name": "试卷答案状态",
                        "key": "paper_status", "doc": status.strip(),
                        "actual": emoji, "fixable": True})
    return out


# --------------------------------------------------------------------------- #
# --fix
# --------------------------------------------------------------------------- #
def apply_fix(mismatches):
    """按 (文件, 行, 列) 逆序替换；返回实际改动条数。"""
    fixed = 0
    by_file = collections.defaultdict(list)
    for it in mismatches:
        if it.get("fixable") and it.get("col") is not None:
            by_file[it["file"]].append(it)
    for fname, items in by_file.items():
        path = os.path.join(BASE, fname)
        with open(path, encoding="utf-8-sig", newline="") as f:
            text = f.read()
        lines = text.splitlines(keepends=True)
        # 同一行多次替换：按列号逆序
        for it in sorted(items, key=lambda d: (d["line"], d["col"]), reverse=True):
            idx = it["line"] - 1
            if not (0 <= idx < len(lines)):
                continue
            line = lines[idx]
            s, e = it["col"], it["end"]
            if line[s:e] != it["doc"]:
                continue
            lines[idx] = line[:s] + it["actual"] + line[e:]
            fixed += 1
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lines))
    return fixed


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="文档数字校验（docs/stats-snapshot.md 单一事实源）")
    ap.add_argument("--json", action="store_true", help="结构化 JSON 输出")
    ap.add_argument("--fix", action="store_true", help="把文档里的旧值替换为实测值")
    args = ap.parse_args(argv)

    m = compute()
    mismatches, notes = check_snapshot(m)
    mismatches += check_version()
    mismatches += check_docs(m)
    mismatches += check_paper_table(m)

    fixed = apply_fix(mismatches) if args.fix and mismatches else 0
    remaining = [it for it in mismatches if not it.get("fixable")]

    if args.json:
        payload = {
            "ok": not mismatches and not remaining,
            "fixed": fixed,
            "count": len(mismatches),
            "mismatches": [
                {k: it.get(k) for k in ("file", "line", "name", "doc", "actual", "fixable")}
                for it in mismatches
            ],
            "skipped": notes,
            "snapshot_rows": len(SNAPSHOT_KEYS),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0 if payload["ok"] else 1

    print("== 文档数字校验 ==")
    print(f"快照指标 {len(SNAPSHOT_KEYS)} 项；扫描文件 {len({r[0] for r in RULES})} 个")
    if notes:
        for n in notes:
            print("  跳过：" + n)
    if not mismatches:
        print("\n✅ 全部一致：docs/stats-snapshot.md 与 6+ 份文档的关键数字均与实测相符")
        return 0

    print(f"\n发现 {len(mismatches)} 处漂移：")
    for it in mismatches:
        where = f"{it['file']}:{it['line']}" if it["line"] else it["file"]
        print(f"  - {where} → {it['name']}：文档值 {it['doc']!r} vs 实测 {it['actual']!r}")
    if args.fix:
        print(f"\n--fix 已改写 {fixed} 处（剩余 {len(remaining)} 处需手工处理）")
        if remaining:
            return 1
        # 修复后复跑一遍确认
        m2 = compute()
        again, _ = check_snapshot(m2)
        again += check_docs(m2)
        again += check_paper_table(m2)
        if not again:
            print("✅ 复查通过：--fix 后所有数字与实测一致")
            return 0
        print(f"⚠ 复查仍有 {len(again)} 处不一致")
        return 1
    print("\n修复建议：python scripts/doc_check.py --fix（快照表请重跑 python pipeline/gen_docs.py）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
