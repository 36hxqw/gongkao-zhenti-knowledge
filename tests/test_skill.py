#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试：不依赖 pytest，直接 `python tests/test_skill.py` 即可运行。

覆盖：数据自检、四种检索路径（考点/年份省份/多关键词/ID）、索引与数据一致性、
考点文件与 taxonomy 的对应关系。
"""
import json
import os
import re
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

    print("[12] 难度 / 主题 / 分片 / 发行包")
    check(all(isinstance(r.get("diff"), int) and 1 <= r["diff"] <= 5 for r in x), "每题都有 1–5 难度")
    shen = load_jsonl("shenlun.jsonl")
    check(all(r.get("theme") for r in shen), "申论每题都有主题标签")
    split_dir = os.path.join(BASE, "references", "kaodian", "split")
    n_split = len(os.listdir(split_dir)) if os.path.isdir(split_dir) else 0
    check(n_split > 50, f"考点文件已分片（{n_split} 片）")
    big = max(os.path.getsize(os.path.join(BASE, "references", "kaodian", f))
              for f in os.listdir(os.path.join(BASE, "references", "kaodian"))
              if f.endswith(".md"))
    check(big < 40000, f"考点主文件均 < 40KB（最大 {big // 1024}KB）")
    out = run("--module", "资料分析", "--diff", "5", "--limit", "1").stdout
    check("难度" in out, "--diff 难度过滤可用")
    out = run("--theme", "基层治理", "--limit", "1").stdout
    check("主题" in out, "--theme 主题过滤可用")
    import tempfile, zipfile
    tmpd = tempfile.mkdtemp(prefix="rel-")
    try:
        rc = subprocess.run([PY, os.path.join(BASE, "scripts", "make_release.py"),
                             "--lite", "--version", "0.0.1", "--out", tmpd],
                            capture_output=True, text=True, encoding="utf-8")
        zips = [f for f in os.listdir(tmpd) if f.endswith(".zip")]
        check(rc.returncode == 0 and zips, "lite 发行包可构建")
        if zips:
            with zipfile.ZipFile(os.path.join(tmpd, zips[0])) as z:
                names = z.namelist()
            check(any(n.endswith("SKILL.md") for n in names), "lite 含 SKILL.md")
            check(not any(n.endswith("xingce.jsonl") for n in names), "lite 不含 JSONL 题库")
            check(not any("/images/" in n for n in names), "lite 不含配图")
    finally:
        import shutil as _sh
        _sh.rmtree(tmpd, ignore_errors=True)

    print("[13] SKILL.md frontmatter")
    with open(os.path.join(BASE, "SKILL.md"), encoding="utf-8") as f:
        head = f.read(2000)
    check(head.startswith("---") and "name: gongkao-zhenti-knowledge" in head, "frontmatter 含 name")
    check("description:" in head, "frontmatter 含 description")

    print("[14] --id 命中同题变体（P0-2）")
    variant_ids = ["GD-2023-xj-X056", "GD-2023-xj-X057", "GD-2023-xj-X062",
                   "GD-2023-xj-X068", "GD-2023-xj-X072"]
    all_ok = True
    for vid in variant_ids:
        p = run("--id", vid)
        all_ok = all_ok and p.returncode == 0 and vid in p.stdout
    check(all_ok, "5 个已知同题变体 id 全部可查")
    p = run("--id", "GD-2023-xj-X056")
    check("同题变体" in p.stdout, "变体命中输出「同题变体」提示")
    check("主记录 GD-2023-xz-X061" in p.stdout, "变体提示主记录 id")
    check("2 个变体" in p.stdout, "变体提示 dup_n")

    print("[15] 多词 AND 0 命中自动降级（P1-1）")
    p = run("--kw", "黑土地", "--kw", "保护", "--kw", "粮食安全", "--limit", "2")
    check(p.returncode == 0 and "命中" in p.stdout, "三词 AND 0 命中降级后有结果")
    check("已自动降级" in p.stdout, "输出「已自动降级」")
    check("去掉了「粮食安全」" in p.stdout, "去掉最泛的词，保留 黑土地+保护")
    check("原 3 词 AND 无命中" in p.stdout, "标注原词数与 AND 语义")
    p = run("--kw", "量子纠缠", "--kw", "不存在词", "--limit", "1", expect_ok=False)
    check(p.returncode == 2 and ("1." in p.stderr and "--fuzzy" in p.stderr), "仍 0 命中时给出下一步建议")

    print("[16] 清单查询提示同题变体（P0-2）")
    out = run("--module", "资料分析", "--limit", "1").stdout
    m = re.search(r"另有 (\d+) 条同题变体", out)
    check(m is not None and int(m.group(1)) > 0, "清单查询末尾输出「另有 N 条同题变体」")
    check("加 --all-variants 查看" in out, "提示加 --all-variants 查看")
    out = run("--module", "资料分析", "--limit", "1", "--all-variants").stdout
    check("另有" not in out, "--all-variants 时不再提示折叠")

    print("[17] 不存在的 id 给出最近 3 个 id（P0-2）")
    p = run("--id", "GD-2023-xj-X999", expect_ok=False)
    msg = p.stdout + p.stderr
    check("最近 3 个 id" in msg, "提示按年份+省份+题号给出的最近 3 个 id")
    near = [i for i in re.findall(r"[A-Z]{2}-\d{4}-[A-Za-z0-9]+-[A-Za-z]+\d+", msg)
            if i != "GD-2023-xj-X999"]
    check(len(near) == 3, f"恰好给出 3 个候选 id（{near}）")
    p = run("--id", "GD-2023-X999", expect_ok=False)
    check("GD-2023-xj-X056" in (p.stdout + p.stderr), "非法格式 id 提示正确格式")

    print("[18] 申论命中占比提示（P2-3）")
    out = run("--kw", "新质生产力", "--limit", "1").stdout
    check("申论命中" in out and "--xingce" in out, "默认检索申论占比高时提示 --xingce")
    out = run("--kw", "新质生产力", "--xingce", "--limit", "1").stdout
    check("申论命中" not in out, "--xingce 时不再提示申论占比")

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
