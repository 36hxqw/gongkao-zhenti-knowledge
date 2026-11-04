#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据自检：字段完整性、ID 唯一性、考点编码合法性、索引一致性、module↔code 一致性。

退出码：0 全部通过；1 存在问题（会打印明细）。
用法：python scripts/selfcheck.py [-h]
"""
import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

VALID_CODES = {
    "ZL-BASE", "ZL-GROW", "ZL-RATE", "ZL-BILI", "ZL-AVG", "ZL-BEI", "ZL-YEAR", "ZL-PULL", "ZL-COMP",
    "SL-GC", "SL-XC", "SL-LR", "SL-PL", "SL-GL", "SL-RC", "SL-ZZ", "SL-NL", "SL-JH", "SL-RY",
    "SL-NCC", "SL-JT", "SL-SZ", "SL-OT",
    "YY-LJTK", "YY-ZXJL", "YY-XJPD", "YY-BTTR", "YY-YJTR", "YY-XWTD", "YY-YJXH", "YY-YJPX", "YY-PZYD",
    "PD-TX", "PD-DY", "PD-LB", "PD-LJ", "PD-KX", "PD-SJ",
    "CS-ZZ", "CS-JJ", "CS-FL", "CS-LS", "CS-DL", "CS-KJ", "CS-SZ", "CS-SH",
    "SN-DY", "SN-ZH", "SN-DC", "SN-GW", "SN-DZW",
}
# code 前缀 → 模块（v1.8 P0-1：module 与 code 必须自洽，否则 --module 检索会漏题）
CODE_MODULE = {
    "ZL": "资料分析", "SL": "数量关系", "YY": "言语理解",
    "PD": "判断推理", "CS": "常识判断", "SN": "申论",
}
REQUIRED_X = ["id", "prov", "year", "vol", "num", "module", "type", "code", "stem", "opts", "ans", "kw"]
REQUIRED_S = ["id", "prov", "year", "vol", "paper", "module", "type", "code", "stem", "ans", "material", "kw"]


def load(name):
    path = os.path.join(DATA, name)
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="selfcheck.py",
        description="数据自检：字段完整性、ID 唯一性、考点编码合法性、module↔code 一致性、索引与统计一致性。",
        epilog="退出码：0 全部通过；1 存在问题（会打印明细）。",
    )
    ap.parse_args(argv)          # --help 只打印用法并退出 0，不跑检查

    problems = []
    x = load("xingce.jsonl")
    s = load("shenlun.jsonl")

    ids = set()
    for r in x:
        for k in REQUIRED_X:
            if k not in r:
                problems.append(f"行测缺字段 {k}: {r.get('id')}")
        if r["id"] in ids:
            problems.append(f"重复 ID: {r['id']}")
        ids.add(r["id"])
        if r["code"] not in VALID_CODES:
            problems.append(f"非法考点编码 {r['code']}: {r['id']}")
        if not isinstance(r["opts"], dict):
            problems.append(f"opts 不是对象: {r['id']}")
        if r["ans"] not in (None, "A", "B", "C", "D"):
            problems.append(f"答案非法 {r['ans']}: {r['id']}")
        if not r["stem"] and not r.get("fig"):
            problems.append(f"题干为空: {r['id']}")
        if r["year"] and not (2000 <= r["year"] <= 2026):
            problems.append(f"年份异常 {r['year']}: {r['id']}")
        if not isinstance(r.get("diff"), int) or not (1 <= r["diff"] <= 5):
            problems.append(f"难度缺失或越界 {r.get('diff')}: {r['id']}")
        if not r.get("sub"):
            problems.append(f"子考点为空: {r['id']}")

    for r in s:
        for k in REQUIRED_S:
            if k not in r:
                problems.append(f"申论缺字段 {k}: {r.get('id')}")
        if r["id"] in ids:
            problems.append(f"重复 ID: {r['id']}")
        ids.add(r["id"])
        if r["code"] not in VALID_CODES:
            problems.append(f"非法考点编码 {r['code']}: {r['id']}")
        if not r.get("theme"):
            problems.append(f"申论主题为空: {r['id']}")

    # module ↔ code 前缀必须一致（v1.8 P0-1）：否则 --module 检索会漏题、
    # --list-kaodian 会把同一个 code 拆成多行。不一致的 id 全部列出。
    bad_pairs = []
    for r in x + s:
        want = CODE_MODULE.get(r["code"].split("-")[0])
        if want and r["module"] != want:
            bad_pairs.append((r["id"], r["module"], r["code"], want))
    if bad_pairs:
        for rid, mod, code, want in bad_pairs:
            problems.append(f"module 与 code 前缀不一致: {rid}  module={mod}  code={code}（应为 {want}）")

    # 索引一致性
    idx_ids = set()
    with open(os.path.join(DATA, "search-index.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                problems.append(f"索引列数不足: {line[:40]}")
                continue
            idx_ids.add(parts[0])
    missing = ids - idx_ids
    if missing:
        problems.append(f"索引缺少 {len(missing)} 个 ID，例如 {sorted(missing)[:5]}")

    # 统计一致性
    with open(os.path.join(DATA, "stats.json"), encoding="utf-8") as f:
        stats = json.load(f)
    if stats["xingce"]["total"] != len(x):
        problems.append(f"stats 行测题量不一致: {stats['xingce']['total']} vs {len(x)}")
    if stats["shenlun"]["total"] != len(s):
        problems.append(f"stats 申论题量不一致: {stats['shenlun']['total']} vs {len(s)}")

    # 考点文件是否齐备
    kdir = os.path.join(BASE, "references", "kaodian")
    files = os.listdir(kdir) if os.path.isdir(kdir) else []
    codes = {r["code"] for r in x + s}
    for c in sorted(codes):
        if not any(f.startswith(c + "-") for f in files):
            problems.append(f"缺少考点文件: {c}")

    # 答案覆盖率（仅供参考，不算失败）
    no_ans = sum(1 for r in x if not r["ans"])
    print(f"行测 {len(x)} 题 / 申论 {len(s)} 题 / 考点文件 {len(files)} 个")
    print(f"答案缺失 {no_ans} 题（{no_ans / len(x) * 100:.1f}%，原因见各题 ans_note 与 docs/coverage.md）")
    print(f"module↔code 不一致 {len(bad_pairs)} 条")

    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("\n✅ 自检通过：字段、ID、考点编码、module↔code、索引、统计、考点文件全部一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
