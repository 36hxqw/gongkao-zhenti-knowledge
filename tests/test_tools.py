#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组卷与错题本两个 CLI 的冒烟测试（纯标准库，不依赖 pytest）。

覆盖
----
1. paper.py 生成 Markdown：题量、题号连续、考点分散、建议用时
2. paper.py 答案页与题库一致、配图路径标注
3. paper.py --format json：可解析、字段完整、考点过滤、默认折叠同题变体
4. paper.py 边界：题量不足如实提示、无结果退出码 2、--shenlun 预留报错
5. wrongbook.py add → list → report → stats 全链路
6. wrongbook.py 重复 add 幂等（不产生重复行，更新错因与备注）
7. wrongbook.py 非法 id 退出码非 0、提示最接近的 3 个 id、不写脏数据
8. 存储目录自动创建、.gitignore 已忽略 user/

运行
----
    python tests/test_tools.py

测试产物写在仓库内的临时目录（tempfile.mkdtemp），结束时删除；
错题本存储用环境变量 GONGKAO_WRONGBOOK 指向临时文件，不碰真实的 user/wrongbook.jsonl。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
FAILED = []

Q_NUM = re.compile(r"^### (\d+)\. ", re.M)
ANS_ROW = re.compile(
    r"^\| (\d+) \| ([A-D—]) \| ([^|]+?) \| ([A-Z]{2}-[A-Z]+) \| `([^`]+)` \|", re.M)
IMG_REF = re.compile(r"!\[[^\]]*\]\((references/images/[^)]+)\)")


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


def run(script, *args, expect_ok=True, env=None):
    cmd = [PY, os.path.join(BASE, "scripts", script), *args]
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env.update(env or {})
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=child_env)
    if expect_ok and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[:400]
        FAILED.append(f"命令失败（退出码 {proc.returncode}）：{script} {' '.join(args)}\n{detail}")
    return proc


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_bank():
    bank = {}
    for name in ("xingce.jsonl", "shenlun.jsonl"):
        path = os.path.join(BASE, "data", name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    bank.setdefault(rec["id"], rec)
    return bank


def first(bank, pred):
    for rec in bank.values():
        if pred(rec):
            return rec
    return None


TAX_ROW = re.compile(
    r"^\|\s*`([A-Z]{2}-[A-Z]+)`\s*\|\s*([^|]+?)\s*\|\s*[^|]*\|\s*[^|]*\|\s*([^|]+?)\s*\|")


def taxonomy_ref(code, path=None):
    """从 docs/kaodian-taxonomy.md 读该考点对应的花生十三章节（与实现同源）。"""
    path = path or os.path.join(BASE, "docs", "kaodian-taxonomy.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            match = TAX_ROW.match(line)
            if match and match.group(1) == code:
                return match.group(3).strip()
    return ""


def main():
    tmp = tempfile.mkdtemp(prefix="_tmp_tools_", dir=BASE)
    book = os.path.join(tmp, "wb", "nested", "wrongbook.jsonl")
    env = {"GONGKAO_WRONGBOOK": book}
    bank = load_bank()
    img_dir = os.path.join(BASE, "references", "images")

    try:
        # ------------------------------------------------------------------ #
        print("[1] paper.py 生成 Markdown 试卷")
        md_path = os.path.join(tmp, "paper-资料分析.md")
        proc = run("paper.py", "--module", "资料分析", "--count", "20", "--prov", "国考",
                   "--years", "2019-2026", "--seed", "7", "--out", md_path)
        check(proc.returncode == 0, "组卷命令成功退出")
        check(os.path.exists(md_path), "已写出 Markdown 文件")
        text = read_text(md_path)
        numbers = [int(n) for n in Q_NUM.findall(text)]
        check(numbers == list(range(1, 21)), "题号 1–20 连续无缺号")
        rows = ANS_ROW.findall(text)
        check(len(rows) == 20, f"答案页 20 行（实际 {len(rows)} 行）")
        check("建议用时" in text and "25 分钟" in text, "资料分析 20 题建议用时 25 分钟")
        check("## 二、答案与考点" in text, "含「答案与考点」页")
        codes = [row[3] for row in rows]
        available = {rec["code"] for rec in bank.values()
                     if rec.get("module") == "资料分析" and rec.get("prov") == "国考"
                     and 2019 <= (rec.get("year") or 0) <= 2026
                     and rec.get("canonical", rec["id"]) == rec["id"]}
        expected_spread = min(8, len(available))
        check(len(set(codes)) >= expected_spread,
              f"考点分散：20 题覆盖 {len(set(codes))} 个考点（≥{expected_spread}）")
        check(len(set(codes[:expected_spread])) == expected_spread,
              f"前 {expected_spread} 题覆盖 {expected_spread} 个不同考点（轮转抽样生效）")
        ids = [row[4] for row in rows]
        check(len(set(ids)) == 20, "同一套卷无重复题")

        # ------------------------------------------------------------------ #
        print("[2] 答案页与题库一致、配图路径")
        wrong = [(row[0], row[1], row[4]) for row in rows
                 if bank[row[4]]["ans"] and bank[row[4]]["ans"] != row[1]]
        check(not wrong, f"答案页每题答案与题库 ans 一致（不一致 {len(wrong)} 题）")
        check(all(bank[i].get("canonical", i) == i for i in ids), "默认只取 main 记录（canonical==id）")
        expected = {f"references/images/{i}.jpg" for i in ids
                    if os.path.exists(os.path.join(img_dir, i + ".jpg"))}
        check(set(IMG_REF.findall(text)) == expected,
              f"配图标注与磁盘一致（{len(expected)} 张）")
        ctx_count = sum(1 for i in ids if (bank[i].get("ctx") or "").strip())
        check(text.count("> **材料**：") == ctx_count,
              f"资料分析题有 ctx 时先输出材料（{ctx_count} 题）")

        # ------------------------------------------------------------------ #
        print("[3] paper.py --format json")
        proc = run("paper.py", "--code", "ZL-BILI", "--count", "10", "--seed", "7", "--format", "json")
        check(proc.returncode == 0, "JSON 组卷命令成功退出")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            data = []
            FAILED.append(f"JSON 无法解析：{exc}")
        check(isinstance(data, list) and len(data) == 10, "stdout 为可解析的 10 元素数组")
        required = ["id", "prov", "year", "vol", "num", "module", "type", "code",
                    "stem", "opts", "ans", "expl", "ctx", "kw", "fig", "canonical", "dup_n", "src"]
        check(all(set(required) <= set(rec) for rec in data), "每题含题库完整字段")
        check(all(rec["code"] == "ZL-BILI" for rec in data), "考点过滤生效（全部 ZL-BILI）")
        check(all(rec.get("ans") for rec in data), "优先选答案非空的题")
        check(len({rec["id"] for rec in data}) == 10, "JSON 无重复题")

        json_path = os.path.join(tmp, "paper.json")
        proc = run("paper.py", "--module", "判断推理", "--type", "图形推理", "--count", "5",
                   "--seed", "3", "--format", "json", "--out", json_path)
        check(os.path.exists(json_path), "--format json --out 写出文件")
        file_data = json.loads(read_text(json_path))
        check(len(file_data) == 5, f"JSON 文件 5 题（实际 {len(file_data)}）")
        check(all((rec.get("image") or "").startswith("references/images/")
                  or rec.get("image") is None for rec in file_data),
              "图形题 JSON 带配图字段")
        check(any(rec.get("image") for rec in file_data), "图形推理题有配图路径")

        # ------------------------------------------------------------------ #
        print("[4] paper.py 边界")
        proc = run("paper.py", "--module", "数量关系", "--type", "牛吃草问题",
                   "--count", "10", "--seed", "1")
        body = proc.stdout
        match = re.search(r"可用 (\d+) 题（少于请求的 (\d+) 题）", body)
        check(proc.returncode == 0, "题量不足时仍正常出卷（退出码 0）")
        check(match is not None and match.group(2) == "10", "如实提示「可用 N 题（少于请求的 10 题）」")
        check(match is not None and int(match.group(1)) == len(Q_NUM.findall(body)),
              "不足时不重复凑数（提示数 = 实际题数）")

        proc = run("paper.py", "--module", "资料分析", "--code", "SL-GC", expect_ok=False)
        check(proc.returncode == 2, "无结果退出码 2")
        check("建议" in proc.stderr and "未命中" in proc.stderr, "无结果时给出可执行建议")

        proc = run("paper.py", "--shenlun", "--module", "资料分析", expect_ok=False)
        check(proc.returncode == 2 and "暂不支持" in proc.stderr, "--shenlun 预留并提示暂不支持")

        # ------------------------------------------------------------------ #
        print("[5] wrongbook.py add 与幂等")
        zl = first(bank, lambda r: r.get("code") == "ZL-BILI" and r.get("ans")
                   and r.get("canonical", r["id"]) == r["id"]
                   and os.path.exists(os.path.join(img_dir, r["id"] + ".jpg")))
        pd = first(bank, lambda r: r.get("code") == "PD-TX" and r.get("ans")
                   and r.get("canonical", r["id"]) == r["id"])
        yy = first(bank, lambda r: r.get("module") == "言语理解" and r.get("ans")
                   and r.get("canonical", r["id"]) == r["id"])
        check(all([zl, pd, yy]), "测试样本题可在题库中定位")

        proc = run("wrongbook.py", "add", "--id", zl["id"], "--reason", "技巧不熟",
                   "--note", "比重差算成增长率", env=env)
        check(proc.returncode == 0, "add 单题成功")
        entries = read_jsonl(book)
        check(len(entries) == 1 and entries[0]["id"] == zl["id"], "wrongbook.jsonl 写入 1 行")
        check(entries and entries[0]["reason"] == "技巧不熟", "记录错因")
        check(entries and entries[0]["note"] == "比重差算成增长率", "记录备注")
        check(entries and "T" in (entries[0].get("added_at") or ""), "added_at 为 ISO 时间")
        check(entries and isinstance(entries[0].get("tags"), list), "tags 为数组")
        check(os.path.isdir(os.path.dirname(book)), "存储目录自动创建（多层）")

        proc = run("wrongbook.py", "add", "--id", zl["id"], "--reason", "知识盲区",
                   "--note", "重新归类", env=env)
        entries = read_jsonl(book)
        check(len(entries) == 1, "重复 add 不产生重复行")
        check(entries and entries[0]["reason"] == "知识盲区", "重复 add 更新错因")
        check(entries and entries[0]["note"] == "重新归类", "重复 add 更新备注")

        proc = run("wrongbook.py", "add", "--ids", pd["id"], yy["id"], "--reason", "粗心失误", env=env)
        entries = read_jsonl(book)
        check(len(entries) == 3, "add --ids 一次记录 2 题（累计 3 行）")
        check(all(e["reason"] == "粗心大意" for e in entries if e["id"] != zl["id"]),
              "「粗心失误」对齐为四类错因「粗心大意」")

        # ------------------------------------------------------------------ #
        print("[6] wrongbook.py list")
        proc = run("wrongbook.py", "list", "--reason", "知识盲区", "--limit", "20", env=env)
        out = proc.stdout
        check(proc.returncode == 0, "list 命令成功")
        check(zl["id"] in out and zl["stem"].strip()[:10] in out, "list 关联渲染题干")
        check(f"【答案】{zl['ans']}" in out, "list 渲染答案")
        check("【考点】" in out and zl["code"] in out, "list 渲染考点")
        check(f"{zl['prov']} {zl['year']}" in out, "list 渲染年份省份")
        check(f"references/images/{zl['id']}.jpg" in out, "list 渲染配图路径")
        opts = sorted(zl.get("opts") or {})
        check(bool(opts) and f"{opts[0]}. " in out, "list 渲染选项")

        proc = run("wrongbook.py", "list", "--reason", "粗心大意", env=env)
        check(pd["id"] in proc.stdout and yy["id"] in proc.stdout, "按错因筛选命中 2 题")

        # ------------------------------------------------------------------ #
        print("[7] wrongbook.py report")
        report_path = os.path.join(tmp, "wrongbook.md")
        proc = run("wrongbook.py", "report", "--out", report_path, env=env)
        check(proc.returncode == 0 and os.path.exists(report_path), "report 写出 Markdown")
        text = read_text(report_path)
        check("错题本复盘报告" in text and "错题总数" in text and "3 题" in text,
              "报告含总览与错题总数")
        check("按模块" in text and "按考点" in text and "按错因" in text, "总览三维分布齐备")
        check("错因：" in text and "→ 花生十三" in text, "每题给出「错因 → 花生十三技巧章节」")
        zl_ref = taxonomy_ref(zl["code"])
        pd_ref = taxonomy_ref(pd["code"])
        check(bool(zl_ref) and zl_ref in text, f"{zl['code']} 对应技巧章节 {zl_ref}")
        check(bool(pd_ref) and pd_ref in text, f"{pd['code']} 对应技巧章节 {pd_ref}")
        advice = text.split("## 三、复习建议")[-1]
        tips = re.findall(r"^(\d+)\. ", advice, re.M)
        check(3 <= len(tips) <= 5, f"复习建议 3–5 条（实际 {len(tips)} 条）")
        check("知识盲区" in advice and "粗心大意" in advice, "复习建议引用四类错因改进动作")

        # ------------------------------------------------------------------ #
        print("[8] wrongbook.py stats")
        proc = run("wrongbook.py", "stats", env=env)
        out = proc.stdout
        check(proc.returncode == 0, "stats 命令成功")
        check("[按模块]" in out and "[按考点]" in out and "[按错因]" in out, "三个维度表格齐备")
        check("题数" in out and "占比" in out and "%" in out, "表格含计数与占比")
        check("66.7%" in out, "占比计算生效（2/3 = 66.7%）")
        check("知识盲区" in out and "粗心大意" in out, "错因维度显示四类错因口径")

        # ------------------------------------------------------------------ #
        print("[9] wrongbook.py 非法 id")
        before = len(read_jsonl(book))
        proc = run("wrongbook.py", "add", "--id", "GK-2024-fs-X9999", "--reason", "技巧不熟",
                   env=env, expect_ok=False)
        check(proc.returncode != 0, "非法 id 退出码非 0")
        near = re.search(r"最接近的 3 个：(.+)", proc.stderr or "")
        check(near is not None, "提示最接近的 3 个 id")
        if near:
            ids = [x for x in near.group(1).strip().split("、") if x]
            check(len(ids) == 3 and all(i in bank for i in ids), f"建议 id 真实存在：{ids}")
        check(len(read_jsonl(book)) == before, "非法 id 不写脏数据")

        proc = run("wrongbook.py", "add", "--ids", zl["id"], "GD-2099-ty-X999", "--reason",
                   "时间不够", env=env, expect_ok=False)
        check(proc.returncode != 0, "批量 add 含非法 id 时整体失败")
        check(len(read_jsonl(book)) == before, "批量失败时不写入任何一行（不会只写一半）")

        # ------------------------------------------------------------------ #
        print("[10] 仓库卫生")
        check("user/" in [line.strip() for line in read_text(os.path.join(BASE, ".gitignore")).splitlines()],
              ".gitignore 已加入 user/")
        check(os.path.abspath(book).startswith(os.path.abspath(tmp) + os.sep),
              "错题本数据写在临时目录，未污染 user/")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print(f"{mark(False)} {len(FAILED)} 项失败：")
        for item in FAILED:
            print("  -", item)
        return 1
    print(f"{mark(True)} 全部测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
