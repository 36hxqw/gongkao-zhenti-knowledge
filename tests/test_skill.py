#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试：不依赖 pytest，直接 `python tests/test_skill.py` 即可运行。

覆盖：数据自检、四种检索路径（考点/年份省份/多关键词/ID）、索引与数据一致性、
考点文件与 taxonomy 的对应关系。
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
FAILED = []


def run(*args, expect_ok=True):
    cmd = [PY, os.path.join(BASE, "scripts", "search.py"), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if expect_ok and p.returncode != 0:
        FAILED.append(f"命令失败: {' '.join(args)}\n{p.stderr[:300]}")
    return p


def check(cond, msg):
    if not cond:
        FAILED.append(msg)
    print(("  ✅ " if cond else "  ❌ ") + msg)


def load_jsonl(name):
    with open(os.path.join(BASE, "data", name), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    print("[1] 数据自检")
    p = subprocess.run([PY, os.path.join(BASE, "scripts", "selfcheck.py")],
                       capture_output=True, text=True, encoding="utf-8")
    check(p.returncode == 0, "selfcheck.py 通过")
    print(p.stdout.strip().splitlines()[-1] if p.stdout else "")

    print("[2] 按考点检索")
    out = run("--kaodian", "ZL-BASE", "--prov", "国考", "--limit", "3").stdout
    check("ZL-BASE" in out, "命中资料分析·基期量计算（国考）")
    check(out.count("[GK-") >= 3, "返回 3 条国考题目")

    print("[3] 按年份 + 省份 + 模块检索")
    out = run("--year", "2024", "--prov", "广东", "--limit", "5").stdout
    check("2024" in out and "广东" in out, "命中 2024 广东卷")
    check("GD-2024" in out, "ID 前缀正确")

    print("[4] 多关键词 AND 全文检索")
    out = run("--kw", "黑土地", "--kw", "保护", "--limit", "3").stdout
    check("黑土地" in out, "「黑土地 + 保护」命中")
    check("【答案】" in out, "输出包含答案")

    print("[5] 关键词命中解析正文（图形推理规律）")
    out = run("--kw", "一笔画", "--module", "判断推理", "--limit", "3").stdout
    check("一笔画" in out or "PD-TX" in out, "「一笔画」命中判断推理解析")

    print("[6] 任一关键词 OR 检索")
    out = run("--any", "新质生产力", "低空经济", "--limit", "3").stdout
    check("命中" in out, "OR 检索有结果")

    print("[7] 按 ID 精确取题")
    x = load_jsonl("xingce.jsonl")
    target = next(r for r in x if r["ans"] and r["opts"])
    out = run("--id", target["id"], "--full").stdout
    check(target["id"] in out and target["stem"][:12] in out, f"ID 精确取题 {target['id']}")

    print("[8] 数据结构一致性")
    idx = 0
    with open(os.path.join(BASE, "data", "search-index.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            idx += 1
    check(idx == len(x) + len(load_jsonl("shenlun.jsonl")), "索引行数 = 行测 + 申论题数")

    print("[9] 考点文件齐备")
    kdir = os.path.join(BASE, "references", "kaodian")
    codes = {r["code"] for r in x}
    missing = [c for c in codes if not any(fn.startswith(c + "-") for fn in os.listdir(kdir))]
    check(not missing, f"每个考点都有对应 md 文件（缺 {missing[:3]}）")

    print("[10] 同题折叠与配图")
    a = run("--module", "资料分析", "--limit", "1").stdout
    b = run("--module", "资料分析", "--limit", "1", "--all-variants").stdout
    na = int(a.split("命中")[1].split("题")[0]) if "命中" in a else 0
    nb = int(b.split("命中")[1].split("题")[0]) if "命中" in b else 0
    check(nb >= na, f"默认折叠生效（默认 {na} ≤ 展开 {nb}）")
    check("已折叠" in a, "输出提示折叠数量")
    img_dir = os.path.join(BASE, "references", "images")
    imgs = os.listdir(img_dir) if os.path.isdir(img_dir) else []
    check(len(imgs) > 1000, f"配图已生成（{len(imgs)} 张）")
    out = run("--type", "图形推理", "--limit", "1").stdout
    check("配图" in out or not out, "图形题检索提示配图路径")

    print("[11] 三级子考点与模糊检索")
    out = run("--sub", "两期比重差", "--limit", "2").stdout
    check("两期比重差" in out, "--sub 子考点检索命中")
    check("子考点" in out, "输出展示子考点")
    out = run("--kw", "占比", "--kw", "提高", "--fuzzy", "--limit", "2").stdout
    check("命中" in out, "--fuzzy 模糊检索可用")
    x = load_jsonl("xingce.jsonl")
    check(all(r.get("sub") for r in x), "每题都有 sub 字段")

    print("[12] SKILL.md frontmatter")
    with open(os.path.join(BASE, "SKILL.md"), encoding="utf-8") as f:
        head = f.read(2000)
    check(head.startswith("---") and "name: gongkao-zhenti-knowledge" in head, "frontmatter 含 name")
    check("description:" in head, "frontmatter 含 description")

    print()
    if FAILED:
        print(f"❌ {len(FAILED)} 项失败：")
        for m in FAILED:
            print("  -", m)
        return 1
    print("✅ 全部测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
