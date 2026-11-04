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

# 测试输出统一 UTF-8，避免 GBK 控制台无法编码 ✅/❌ 时半途崩掉
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def run(*args, expect_ok=True):
    cmd = [PY, os.path.join(BASE, "scripts", "search.py"), *args]
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       env=child_env)
    if expect_ok and p.returncode != 0:
        FAILED.append(f"命令失败: {' '.join(args)}\n{p.stderr[:300]}")
    return p


def mark(ok):
    """✅/❌ 在 GBK 终端不可编码时退化为 ASCII，保证测试在任何控制台都能跑完。"""
    symbol = "✅" if ok else "❌"
    try:
        symbol.encode(sys.stdout.encoding or "utf-8")
        return symbol
    except (UnicodeEncodeError, LookupError):
        return "[PASS]" if ok else "[FAIL]"


def check(cond, msg):
    if not cond:
        FAILED.append(msg)
    print(f"  {mark(bool(cond))} {msg}")


def load_jsonl(name):
    with open(os.path.join(BASE, "data", name), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    print("[1] 数据自检")
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([PY, os.path.join(BASE, "scripts", "selfcheck.py")],
                       capture_output=True, text=True, encoding="utf-8", env=child_env)
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

    print("[19] --year 多值（P1-5）")
    x = load_jsonl("xingce.jsonl")
    expected_hits = sum(1 for r in x
                        if r["year"] in (2024, 2025) and "资料分析" in r["module"]
                        and r["prov"] == "国考"
                        and r.get("canonical", r["id"]) == r["id"])
    p = run("--year", "2024", "2025", "--prov", "国考", "--module", "资料分析", "--limit", "6")
    check(p.returncode == 0, "--year 2024 2025 正常退出（不再 argparse 报错）")
    check(f"命中 {expected_hits} 题" in p.stdout, f"多值年份按 OR 命中 {expected_hits} 题")
    check("Traceback" not in (p.stdout + p.stderr), "多值年份无裸 traceback")
    p = run("--year", "2024", "--limit", "1")
    check(p.returncode == 0 and "2024" in p.stdout, "--year 单值仍可用")
    p = run("--year", "2024,2025", "--limit", "1")
    check(p.returncode == 0 and "命中" in p.stdout, "--year 逗号写法可用")
    p = run("--year", "20x4", expect_ok=False)
    check(p.returncode == 2 and "Traceback" not in p.stderr and "--year" in p.stderr,
          "非法年份给友好提示（退出码 2）")
    p = run("--diff", "4-x", expect_ok=False)
    check(p.returncode == 2 and "Traceback" not in p.stderr, "非法 --diff 给友好提示")

    print("[20] 答案展示改用 ans_note（P1-1）")
    x = load_jsonl("xingce.jsonl")
    noted = next(r for r in x if not (r.get("ans") or "").strip() and r.get("ans_note"))
    p = run("--id", noted["id"])
    check(f"【答案】{noted['ans_note']}" in p.stdout,
          f"空答案 + ans_note 显示说明文案（{noted['id']}）")
    check("暂缺（原卷为扫描版）" not in p.stdout, "不再显示「暂缺（原卷为扫描版）」")
    missing = next(r for r in x if not (r.get("ans") or "").strip() and not r.get("ans_note"))
    p = run("--id", missing["id"])
    check("【答案】该题答案缺失，见原卷" in p.stdout,
          "空答案且无 ans_note 显示「该题答案缺失，见原卷」")
    answered = next(r for r in x if (r.get("ans") or "").strip() and not r.get("ans_note"))
    p = run("--id", answered["id"])
    check(f"【答案】{answered['ans']}" in p.stdout, "有答案且无 ans_note 正常显示答案")
    shen = load_jsonl("shenlun.jsonl")
    snoted = next(r for r in shen if not (r.get("ans") or "").strip() and r.get("ans_note"))
    p = run("--id", snoted["id"])
    check(f"【答案】{snoted['ans_note']}" in p.stdout,
          f"申论空答案显示 ans_note（{snoted['id']}）")

    print("[21] --group-by 分组与截断提示（P2-1）")
    pool = [r for r in x if "资料分析" in r["module"] and r["prov"] == "湖北"
            and r.get("canonical", r["id"]) == r["id"]]
    per_year = {}
    for rec in pool:
        per_year[rec["year"]] = per_year.get(rec["year"], 0) + 1
    newest = max(per_year)
    p = run("--module", "资料分析", "--prov", "湖北", "--limit", str(per_year[newest] + 1),
            "--group-by", "年份")
    check(p.returncode == 0, "--group-by 年份 正常退出")
    # 组头可能是「（N 题）」或「（显示 N / 共 M 题）」，这里同时兼容两种
    heads = re.findall(r"── (\d{4}) 年（(?:显示 \d+ / 共 )?\d+ 题）──", p.stdout)
    check(len(heads) >= 2, f"年份分组标题出现（{heads}）")
    check(heads == sorted(heads, reverse=True), "年份分组按年份倒序")
    p = run("--module", "资料分析", "--limit", "10", "--group-by", "考点")
    codes = re.findall(r"── ([A-Z]{2}-[A-Z]+) [^（]*（(?:显示 \d+ / 共 )?\d+ 题）──", p.stdout)
    check(len(codes) >= 2 and codes == sorted(codes), f"考点分组标题出现且按考点排序（{codes}）")
    p = run("--module", "资料分析", "--limit", "10", "--group-by", "省份")
    check("── 国考（" in p.stdout or "── 广东（" in p.stdout, "省份分组标题出现")
    p = run("--module", "资料分析", "--limit", "10", "--group-by", "年份+考点")
    check(re.search(r"── \d{4} 年 · [A-Z]{2}-[A-Z]+（(?:显示 \d+ / 共 )?\d+ 题）──", p.stdout)
          is not None, "年份+考点分组标题出现")
    p = run("--module", "资料分析", "--limit", "3")
    check("（已截断：命中" in p.stdout and "显示前 3 条；用 --limit 调整）" in p.stdout,
          "文本模式截断提示出现")
    p = run("--module", "资料分析", "--limit", "3", "--json")
    check("已截断" in p.stderr, "JSON 模式截断提示写 stderr")
    try:
        parsed = json.loads(p.stdout)
        ok_json = isinstance(parsed, list) and len(parsed) == 3
    except json.JSONDecodeError:
        ok_json = False
    check(ok_json, "JSON 截断后 stdout 仍为 3 元素数组")

    print("[22] stem_flag 警示（P1-3）")
    sys.path.insert(0, os.path.join(BASE, "scripts"))
    import search as search_mod
    base_rec = {"id": "GK-2024-ty-X001", "year": 2024, "prov": "国考", "vol": "统一卷",
                "num": 1, "module": "资料分析", "type": "基期量计算", "code": "ZL-BASE",
                "stem": "某年某指标为多少", "ans": "A", "opts": {"A": "1", "B": "2"}}
    reasons = {"short": "题干过短", "contaminated": "含邻题残句",
               "watermark": "含广告水印", "missing_opts": "选项残缺"}
    all_ok = True
    for flag, reason in reasons.items():
        line = search_mod.fmt(dict(base_rec, stem_flag=flag))
        all_ok = all_ok and f"⚠ 题干可能不完整（{reason}）" in line
    check(all_ok, "四种 stem_flag 都映射成中文原因并显示警示行")
    check("⚠" not in search_mod.fmt(dict(base_rec, stem_flag=None)),
          "stem_flag 为空时不显示警示")
    check(search_mod.answer_text(dict(base_rec, ans="", ans_note=None)) == "该题答案缺失，见原卷",
          "无答案且无 ans_note 的统一文案")
    check(search_mod.answer_text(dict(base_rec, ans="", ans_note="见原卷")) == "见原卷",
          "ans_note 原样输出")

    print("[23] --kw 与 --any 单关键词字段集合对齐（P1-1）")
    def hit_total(text):
        m = re.search(r"命中 (\d+) 题", text)
        return int(m.group(1)) if m else -1

    kw_n = hit_total(run("--kw", "新质生产力", "--limit", "1").stdout)
    any_n = hit_total(run("--any", "新质生产力", "--limit", "1").stdout)
    check(kw_n > 0 and kw_n == any_n, f"--kw 与 --any 单关键词命中数相同（{kw_n} vs {any_n}）")
    check(search_mod.match_any({"stem": "正文", "module": "资料分析"}, ["资料分析"]),
          "--any 覆盖 module 字段（与 --kw 同字段集合）")
    check(search_mod.match_any({"stem": "正文", "code": "ZL-BASE"}, ["ZL-BASE"]),
          "--any 覆盖 code 字段")
    check(search_mod.match_any({"stem": "正文", "theme": ["基层治理"]}, ["基层治理"]),
          "--any 覆盖 theme 字段")
    check(search_mod.match_any({"stem": "正文", "ans": "A"}, ["A"]),
          "--any 覆盖 ans 字段")

    print("[24] --fuzzy 阈值、合并与 ≈模糊 标记（P1-2）")
    def ids_of(text):
        return set(re.findall(r"^\[([A-Z]{2}-\d{4}-[^]]+)\]", text, re.M))

    exact_out = run("--kw", "占比", "--xingce", "--limit", "2000").stdout
    fuzzy_out = run("--kw", "占比", "--fuzzy", "--xingce", "--limit", "2000").stdout
    exact_ids, fuzzy_ids = ids_of(exact_out), ids_of(fuzzy_out)
    check(bool(exact_ids) and exact_ids <= fuzzy_ids,
          f"fuzzy 结果包含全部精确命中（{len(exact_ids)} ⊆ {len(fuzzy_ids)}）")
    check(len(fuzzy_ids) > len(exact_ids),
          f"fuzzy 额外补入 {len(fuzzy_ids) - len(exact_ids)} 条模糊命中")
    marked = re.search(r"^\[([A-Z]{2}-\d{4}-[^]]+)\][^\n]*\n  ≈模糊", fuzzy_out, re.M)
    check(marked is not None, "fuzzy-only 命中带「≈模糊」标记")
    check(marked is not None and marked.group(1) not in exact_ids,
          "「≈模糊」只标在 fuzzy-only 命中上")
    check("≈模糊" not in exact_out, "未加 --fuzzy 时不出现模糊标记")
    try:
        jdata = json.loads(run("--kw", "占比", "--fuzzy", "--xingce",
                               "--limit", "700", "--json").stdout)
    except json.JSONDecodeError:
        jdata = []
    marked_json = {r.get("id") for r in jdata if r.get("fuzzy") is True}
    check(bool(marked_json), "JSON 模糊命中带 \"fuzzy\": true")
    check(marked_json <= fuzzy_ids - exact_ids, "JSON fuzzy 只标在 fuzzy-only 命中上")
    exact_new = hit_total(run("--kw", "新质生产力", "--limit", "1").stdout)
    fuzzy_new = hit_total(run("--kw", "新质生产力", "--fuzzy", "--limit", "1").stdout)
    check(fuzzy_new == exact_new,
          f"0.75 阈值后「新质生产力」无多出的假阳性（{exact_new} vs {fuzzy_new}）")

    print("[25] --group-by 组头显示 / 共（P1-3）")
    p = run("--module", "资料分析", "--limit", "3", "--group-by", "年份")
    head = re.search(r"── (\d{4}) 年（显示 (\d+) / 共 (\d+) 题）──", p.stdout)
    check(head is not None, "截断时组头含「显示 N / 共 M 题」")
    if head:
        zl_per_year = {}
        for rec in x:
            if "资料分析" in rec["module"] and rec.get("canonical", rec["id"]) == rec["id"]:
                zl_per_year[rec["year"]] = zl_per_year.get(rec["year"], 0) + 1
        check(int(head.group(3)) > int(head.group(2)),
              f"组头「共」为全年题量而非显示条数（{head.group(2)} / {head.group(3)}）")
        check(head.group(3) == str(zl_per_year.get(int(head.group(1)), -1)),
              "组头「共」与该年份实际题量一致")
    p = run("--module", "资料分析", "--prov", "湖北", "--limit", "100000",
            "--group-by", "年份")
    check(re.search(r"── \d{4} 年（\d+ 题）──", p.stdout) is not None, "未截断时组头写（N 题）")
    check("（显示" not in p.stdout, "未截断时不出现「显示」字样")

    print("[26] --list-kaodian 按 code 聚合与 --json（P1-4）")
    all_recs = load_jsonl("xingce.jsonl") + load_jsonl("shenlun.jsonl")
    code_set = {r["code"] for r in all_recs}
    p = run("--list-kaodian")
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    check(p.returncode == 0 and len(lines) == len(code_set),
          f"行数 = 不同 code 数（{len(lines)} vs {len(code_set)}）")
    check(all(re.fullmatch(r"[A-Z]{2}-[A-Z]+\s+\S+·\S+\s+\d+ 题", ln) for ln in lines),
          "每行 = code + module·type + 题量")
    total = sum(int(m.group(1)) for m in
                (re.search(r"(\d+) 题$", ln) for ln in lines) if m)
    check(total == len(all_recs), f"各 code 题量合计 = 全量题数（{total}）")
    try:
        kdata = json.loads(run("--list-kaodian", "--json").stdout)
    except json.JSONDecodeError:
        kdata = []
    check(isinstance(kdata, list) and len(kdata) == len(code_set),
          "--list-kaodian --json 可被 json.loads 且项数 = 不同 code 数")
    check({d.get("code") for d in kdata} == code_set
          and all({"code", "module", "type", "n"} <= set(d) for d in kdata),
          "JSON 每项含 code/module/type/n")
    check(sum(d.get("n", 0) for d in kdata) == len(all_recs), "JSON 题量合计 = 全量题数")

    print("[27] --fields 只输出指定字段（P2）")
    answered = next(r for r in x if (r.get("ans") or "").strip() and not r.get("ans_note"))
    p = run("--id", answered["id"], "--fields", "id,ans")
    check(p.stdout.strip() == f"{answered['id']}\t{answered['ans']}",
          f"--id + --fields id,ans 只输出两列（{p.stdout.strip()!r}）")
    check("【答案】" not in p.stdout, "--fields 不输出模板文案")
    p = run("--module", "资料分析", "--limit", "2", "--fields", "id,ans")
    rows = [ln for ln in p.stdout.splitlines() if ln.strip()]
    check(len(rows) == 2 and all(len(ln.split("\t")) == 2 for ln in rows),
          "--fields 列表中每条一行、恰好两列")
    check("命中" not in p.stdout, "--fields 不输出命中摘要（便于脚本）")
    p = run("--fields", "id,nope", expect_ok=False)
    check(p.returncode == 2 and "未知字段" in p.stderr, "--fields 未知字段给友好提示（退出码 2）")

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
