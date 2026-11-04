#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错题本 CLI（错因口径对齐花生十三四类错因：知识盲区 / 技巧不熟 / 粗心大意 / 时间不够）。

用法示例
--------
    # 记录单题：错因 + 一句话错因备注
    python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟 --note "比重差算成增长率"

    # 一次记录多题（同一错因）
    python scripts/wrongbook.py add --ids GK-2024-fs-X112 GD-2023-xj-X045 --reason 粗心失误

    # 按错因筛选，关联题库渲染题干/选项/答案/考点/配图
    python scripts/wrongbook.py list --reason 技巧不熟 --limit 20

    # 生成 Markdown 复盘报告（含「错因 → 花生十三技巧章节」与针对性复习建议）
    python scripts/wrongbook.py report --out out/wrongbook.md

    # 终端三维统计：模块 / 考点 / 错因 的计数与占比
    python scripts/wrongbook.py stats

存储
----
默认 user/wrongbook.jsonl（目录自动创建），每行一个 JSON：
    {"id": "...", "added_at": "2026-11-01T22:10:00", "reason": "技巧不熟", "note": "...", "tags": []}
同一 id 重复 add 只更新时间、错因与备注，不产生重复行。
可用环境变量 GONGKAO_WRONGBOOK 覆盖存储路径（测试或多套错题本隔离用）。

错因别名：「粗心失误 / 粗心 / 马虎」统一记为「粗心大意」，「没时间 / 时间不足」记为「时间不够」。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
USER_DIR = os.path.join(BASE, "user")
DEFAULT_BOOK = os.path.join(USER_DIR, "wrongbook.jsonl")
BOOK = os.environ.get("GONGKAO_WRONGBOOK") or DEFAULT_BOOK
TAXONOMY = os.path.join(BASE, "docs", "kaodian-taxonomy.md")
KAODIAN_DIR = os.path.join(BASE, "references", "kaodian")
IMAGES_DIR = os.path.join(BASE, "references", "images")

REASONS = ["知识盲区", "技巧不熟", "粗心大意", "时间不够"]
REASON_ALIAS = {
    "知识盲区": "知识盲区", "盲区": "知识盲区", "不会": "知识盲区", "知识": "知识盲区",
    "技巧不熟": "技巧不熟", "技巧": "技巧不熟", "不熟": "技巧不熟", "方法不熟": "技巧不熟",
    "粗心大意": "粗心大意", "粗心失误": "粗心大意", "粗心": "粗心大意", "马虎": "粗心大意",
    "时间不够": "时间不够", "没时间": "时间不够", "时间不足": "时间不够", "时间": "时间不够",
}
REASON_ACTION = {
    "知识盲区": "重学理论 + 默写公式 + 做基础题巩固（cuoti-muban 4.1.1）",
    "技巧不熟": "专项限时训练 + 反复练速算（cuoti-muban 4.1.2）",
    "粗心大意": "审题圈关键词 + 算完核对 + 涂卡检查（cuoti-muban 4.1.3）",
    "时间不够": "调做题顺序 + 学会放弃 + 限时提速（cuoti-muban 4.1.4）",
}
REASON_TIP = {
    "知识盲区": "先回看对应理论章节、把公式默写一遍，再做 20 道同类基础题验证；不要用刷题代替补基础",
    "技巧不熟": "做限时专项：截位直除 / 415 份数 / 假设分配 / 代入排除各练 10 题，练到 30 秒内出结果",
    "粗心大意": "审题时圈出时间、单位、问法，算完回代核对选项，涂卡后二次检查题号",
    "时间不够": "固定做题顺序（先资料分析，再判断与言语，数量最后），单题 90 秒熔断，超时先标记跳过",
}
MODULE_REF_FILE = {
    "ZL": "ziliao-fenxi.md", "SL": "shuliang-guanxi.md", "YY": "yanyu-lianjie.md",
    "PD": "panduan-tuili.md", "CS": "changshi-panduan.md", "SN": "shenlun.md",
}
MODULE_ORDER = {"资料分析": 0, "判断推理": 1, "言语理解": 2, "数量关系": 3, "常识判断": 4, "申论": 5}
PROV_ALIAS = {
    "国考": "国考", "国家": "国考", "国": "国考", "guokao": "国考", "gk": "国考",
    "广东": "广东", "广东省考": "广东", "gd": "广东",
    "湖北": "湖北", "湖北省考": "湖北", "hb": "湖北",
}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def one_line(text):
    return " ".join((text or "").split())


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text, width, right=False):
    space = " " * max(0, width - display_width(text))
    return space + text if right else text + space


def format_table(headers, rows, right_cols=()):
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], display_width(str(value)))
    lines = ["  ".join(pad(h, widths[i], i in right_cols) for i, h in enumerate(headers))]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append("  ".join(pad(str(v), widths[i], i in right_cols) for i, v in enumerate(row)))
    return "\n".join(lines).rstrip()


def normalize_reason(text):
    if not text:
        return None
    key = text.strip()
    return REASON_ALIAS.get(key) or REASON_ALIAS.get(key.replace(" ", ""))


def read_jsonl(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_bank():
    """id -> 题目记录（行测优先，申论其次）。"""
    bank = {}
    for name in ("xingce.jsonl", "shenlun.jsonl"):
        for rec in read_jsonl(name):
            bank.setdefault(rec["id"], rec)
    if not bank:
        sys.exit("题库为空或缺少 data/xingce.jsonl。\n"
                 "请先确认题库已生成（可运行 python scripts/selfcheck.py 自检）。")
    return bank


def load_book():
    entries = []
    if not os.path.exists(BOOK):
        return entries
    with open(BOOK, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print(f"警告：{BOOK} 第 {lineno} 行不是合法 JSON，已跳过。", file=sys.stderr)
                continue
            entry.setdefault("tags", [])
            entries.append(entry)
    return entries


def save_book(entries):
    os.makedirs(os.path.dirname(os.path.abspath(BOOK)) or ".", exist_ok=True)
    tmp = BOOK + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    os.replace(tmp, BOOK)


def append_book(entries):
    os.makedirs(os.path.dirname(os.path.abspath(BOOK)) or ".", exist_ok=True)
    with open(BOOK, "a", encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def rel_book_path():
    try:
        return os.path.relpath(BOOK, BASE)
    except ValueError:
        return BOOK


def default_book_rel():
    """默认错题本路径（POSIX 分隔符，供 --help 展示）。"""
    try:
        return os.path.relpath(DEFAULT_BOOK, BASE).replace(os.sep, "/")
    except ValueError:
        return DEFAULT_BOOK.replace(os.sep, "/")


def edit_distance(a, b):
    """Levenshtein 距离（两行滚动 DP，纯标准库）。"""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggest_ids(bad, bank_ids, n=3):
    """前缀命中 + 编辑距离，给出最接近的 n 个题目 id。"""
    import difflib

    bad_u = bad.strip().upper()
    by_upper = {i.upper(): i for i in bank_ids}
    pool = set()

    base, _, _ = bad_u.rpartition("-")
    if base:
        prefix = base + "-"
        pool.update(i for i in bank_ids if i.upper().startswith(prefix))
    pool.update(by_upper[u] for u in difflib.get_close_matches(bad_u, list(by_upper), n=30, cutoff=0.5))
    if not pool:
        pool = set(bank_ids)

    def score(qid):
        qu = qid.upper()
        distance = edit_distance(bad_u, qu)
        if base and not qu.startswith(base):
            distance += 1  # 前缀不同的 id 排在后面
        return distance, len(qu), qu

    return sorted(pool, key=score)[:n]


def taxonomy_table():
    """解析 docs/kaodian-taxonomy.md：code -> (题型, 花生十三对齐位置)。"""
    table = {}
    if not os.path.exists(TAXONOMY):
        return table
    import re
    row_re = re.compile(r"^\|\s*`([A-Z]{2}-[A-Z]+)`\s*\|\s*([^|]+?)\s*\|\s*[^|]*\|\s*[^|]*\|\s*([^|]+?)\s*\|")
    with open(TAXONOMY, encoding="utf-8") as f:
        for line in f:
            m = row_re.match(line)
            if m:
                table[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    return table


def tech_chapter(code, rec_type, tax):
    """返回「花生十三技巧章节」的可读描述。"""
    if code in tax:
        name, ref = tax[code]
        if ".md" in ref:
            return f"花生十三 `{ref}`"
        return f"{ref}（体系外补充，无对应技巧章节）"
    prefix = (code or "").split("-")[0]
    fallback = MODULE_REF_FILE.get(prefix)
    if fallback:
        return f"花生十三 `{fallback}`（该考点未在 docs/kaodian-taxonomy.md 命中，按模块定位）"
    return "docs/kaodian-taxonomy.md 中无该考点，建议先运行 python scripts/selfcheck.py 检查题库"


def kaodian_card(code):
    if not os.path.isdir(KAODIAN_DIR):
        return None
    for name in sorted(os.listdir(KAODIAN_DIR)):
        if name.startswith(code + "-") and name.endswith(".md"):
            return "references/kaodian/" + name
    return None


def image_of(rec):
    name = rec["id"] + ".jpg"
    if os.path.exists(os.path.join(IMAGES_DIR, name)):
        return "references/images/" + name
    return None


def question_number(rec):
    return rec.get("num") or rec.get("no") or "?"


def source_line(rec):
    return f"{rec.get('prov', '?')} {rec.get('year', '?')} {rec.get('vol', '')} 第 {question_number(rec)} 题"


# --------------------------------------------------------------------------- #
# add
# --------------------------------------------------------------------------- #
def cmd_add(args):
    ids = []
    if args.id:
        ids.append(args.id)
    ids.extend(args.ids or [])
    ids = [i.strip() for i in ids if i and i.strip()]
    seen = set()
    ids = [i for i in ids if not (i.upper() in seen or seen.add(i.upper()))]
    if not ids:
        print("请至少给一个题目 id：--id GK-2024-fs-X112 或 --ids ID1 ID2。", file=sys.stderr)
        return 2

    reason = normalize_reason(args.reason)
    if not reason:
        print(f"错因「{args.reason}」不在四类错因内。\n"
              f"可选：{'、'.join(REASONS)}（粗心失误=粗心大意，没时间=时间不够）。\n"
              f"例如：python scripts/wrongbook.py add --id {ids[0]} --reason 技巧不熟", file=sys.stderr)
        return 2

    tags = []
    for raw in list(args.tag or []) + list(args.tags or []):
        for tok in raw.replace("，", ",").split(","):
            tok = tok.strip()
            if tok and tok not in tags:
                tags.append(tok)

    bank = load_bank()
    by_upper = {i.upper(): i for i in bank}
    missing = [i for i in ids if i.upper() not in by_upper]
    if missing:
        print(f"以下 id 不在题库中（共 {len(missing)} 个）：", file=sys.stderr)
        suggestions = {}
        for bad in missing:
            near = suggest_ids(bad, list(bank), n=3)
            suggestions[bad] = near
            print(f"  - {bad}", file=sys.stderr)
            if near:
                print(f"    最接近的 3 个：{'、'.join(near)}", file=sys.stderr)
        hint = suggestions.get(missing[0]) or []
        print("核对方法：python scripts/search.py --id "
              f"{hint[0] if hint else 'GK-2024-fs-X112'} --full"
              "（或用 python scripts/search.py --kw 关键词 检索真实 id）。", file=sys.stderr)
        return 2

    canonical = [by_upper[i.upper()] for i in ids]
    entries = load_book()
    index = {e.get("id", "").upper(): e for e in entries}
    now = datetime.now().isoformat(timespec="seconds")
    added, updated = [], []
    for qid in canonical:
        old = index.get(qid.upper())
        if old is not None:
            old["reason"] = reason
            old["added_at"] = now
            if args.note:
                old["note"] = args.note
            if tags:
                merged = list(old.get("tags") or [])
                for t in tags:
                    if t not in merged:
                        merged.append(t)
                old["tags"] = merged
            old.setdefault("note", "")
            updated.append(qid)
        else:
            entry = {"id": qid, "added_at": now, "reason": reason,
                     "note": args.note or "", "tags": tags}
            entries.append(entry)
            index[qid.upper()] = entry
            added.append(qid)

    if added and not updated:
        append_book([e for e in entries if e.get("id") in added])
    else:
        save_book(entries)

    if args.reason.strip() != reason:
        print(f"提示：错因「{args.reason}」已对齐为「{reason}」（花生十三四类错因口径）。")
    print(f"已记录 {len(canonical)} 题（错因：{reason}）：")
    for qid in canonical:
        rec = bank[qid]
        mark = "更新" if qid in updated else "新增"
        note = f"｜{args.note}" if args.note and qid in updated else ""
        print(f"  [{mark}] {qid}  {rec.get('module', '')}·{rec.get('type', '')}"
              f"（{rec.get('code', '')}）｜{source_line(rec)}{note}")
    print(f"错题本共 {len(entries)} 题：{rel_book_path()}")
    print("下一步：python scripts/wrongbook.py stats 看错因分布，"
          "或 python scripts/wrongbook.py report --out out/wrongbook.md 生成复盘报告。")
    return 0


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
def cmd_list(args):
    reason = None
    if args.reason:
        reason = normalize_reason(args.reason)
        if not reason:
            print(f"错因「{args.reason}」不在四类错因内。可选：{'、'.join(REASONS)}。", file=sys.stderr)
            return 2

    entries = load_book()
    if not entries:
        print("错题本为空。先记录错题，例如：\n"
              "  python scripts/wrongbook.py add --id <题目ID> --reason 技巧不熟 --note \"错因一句话\"\n"
              "题目 ID 可用 python scripts/search.py --kw 关键词 检索。")
        return 0

    bank = load_bank()
    rows = []
    for entry in entries:
        rec = bank.get(entry.get("id"))
        if reason and normalize_reason(entry.get("reason")) != reason:
            continue
        if args.module and rec and args.module not in (rec.get("module") or ""):
            continue
        if args.code and rec and args.code.upper() not in (rec.get("code") or "").upper():
            continue
        rows.append((entry, rec))

    if not rows:
        print("没有符合条件的错题。建议：去掉 --reason/--module/--code 再试，"
              "或用 python scripts/wrongbook.py stats 看现有分布。")
        return 0

    rows.sort(key=lambda pair: pair[0].get("added_at") or "", reverse=True)
    limit = args.limit if args.limit is not None else 20
    shown = rows if limit <= 0 else rows[:limit]

    print(f"错题本共 {len(entries)} 题，命中 {len(rows)} 题，显示 {len(shown)} 题：\n")
    for i, (entry, rec) in enumerate(shown, 1):
        if not rec:
            print(f"[{i}] {entry.get('id')}　（题库中已找不到该题，可能题库更新过）")
            print(f"    错因：{entry.get('reason') or '未标注'}　记录于 {entry.get('added_at') or '?'}")
            print("-" * 72)
            continue
        head = (f"[{i}] {rec['id']}　{source_line(rec)}"
                f"　| {rec.get('module')}·{rec.get('type')}（{rec.get('code')}）")
        print(head)
        print(f"    错因：{entry.get('reason') or '未标注'}　记录于 {entry.get('added_at') or '?'}"
              f"　标签：{'、'.join(entry.get('tags') or []) or '无'}")
        if entry.get("note"):
            print(f"    备注：{entry['note']}")
        if rec.get("ctx"):
            print(f"    材料：{one_line(rec['ctx'])[:120]}")
        elif rec.get("material"):
            print(f"    材料：{one_line(rec['material'])[:120]}")
        print(f"    题干：{rec.get('stem') or ''}")
        opts = rec.get("opts") or {}
        if opts:
            print("    " + "　".join(f"{k}. {one_line(v)}" for k, v in sorted(opts.items())))
        print(f"    【答案】{rec.get('ans') or '暂缺（原卷为扫描版）'}")
        print(f"    【考点】{rec.get('code')} {rec.get('type')}（{rec.get('module')}）")
        img = image_of(rec)
        if img:
            print(f"    【配图】{img}")
        print("-" * 72)
    return 0


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def cmd_report(args):
    entries = load_book()
    out = args.out or os.path.join("out", "wrongbook.md")
    bank = load_bank()
    tax = taxonomy_table()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = ["# 错题本复盘报告", ""]
    lines.append(f"- **生成时间**：{now}")
    lines.append(f"- **错题总数**：{len(entries)} 题")
    lines.append(f"- **数据来源**：`{rel_book_path()}`")
    lines.append(f"- **错因口径**：花生十三四类错因（{' / '.join(REASONS)}）")
    lines.append("")

    if not entries:
        lines.append("## 一、总览")
        lines.append("")
        lines.append("错题本还是空的。先记录错题再生成报告：")
        lines.append("")
        lines.append("```")
        lines.append("python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟 --note \"比重差算成增长率\"")
        lines.append("```")
        lines.append("")
        write_report(out, lines)
        print(f"已生成错题本报告：{out}（错题本为空，报告内附上手步骤）")
        return 0

    total = len(entries)
    module_cnt, code_cnt, reason_cnt = {}, {}, {}
    for entry in entries:
        rec = bank.get(entry.get("id")) or {}
        module = rec.get("module") or "未知"
        code = rec.get("code") or "未知"
        reason = normalize_reason(entry.get("reason")) or "未标注"
        module_cnt[module] = module_cnt.get(module, 0) + 1
        code_cnt[code] = code_cnt.get(code, 0) + 1
        reason_cnt[reason] = reason_cnt.get(reason, 0) + 1

    lines.append("## 一、总览")
    lines.append("")
    lines.append("### 1.1 按模块")
    lines.append("")
    lines.append("| 模块 | 错题数 | 占比 |")
    lines.append("|---|---:|---:|")
    for module, n in sorted(module_cnt.items(), key=lambda kv: (-kv[1], MODULE_ORDER.get(kv[0], 99))):
        lines.append(f"| {module} | {n} | {n / total * 100:.1f}% |")
    lines.append("")
    lines.append("### 1.2 按考点")
    lines.append("")
    lines.append("| 考点 | 题型 | 错题数 | 占比 |")
    lines.append("|---|---|---:|---:|")
    for code, n in sorted(code_cnt.items(), key=lambda kv: (-kv[1], kv[0])):
        name = tax.get(code, (code, ""))[0] or code
        lines.append(f"| {code} | {name} | {n} | {n / total * 100:.1f}% |")
    lines.append("")
    lines.append("### 1.3 按错因")
    lines.append("")
    lines.append("| 错因 | 错题数 | 占比 | 改进动作（cuoti-muban） |")
    lines.append("|---|---:|---:|---|")
    for reason in REASONS + (["未标注"] if reason_cnt.get("未标注") else []):
        n = reason_cnt.get(reason, 0)
        if not n:
            continue
        action = REASON_ACTION.get(reason, "先补错因标注，再按四类错因复盘")
        lines.append(f"| {reason} | {n} | {n / total * 100:.1f}% | {action} |")
    lines.append("")

    lines.append("## 二、按考点分组的错题清单")
    lines.append("")
    groups = {}
    for entry in entries:
        rec = bank.get(entry.get("id")) or {}
        groups.setdefault(rec.get("code") or "未知", []).append((entry, rec))
    for code, pairs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        name = tax.get(code, (code, ""))[0] if code in tax else (pairs[0][1].get("type") or code)
        card = kaodian_card(code)
        title = f"### {code} · {name}（{len(pairs)} 题）"
        lines.append(title)
        lines.append("")
        if card:
            lines.append(f"> 本库考点卡：`{card}`")
            lines.append("")
        pairs.sort(key=lambda p: p[0].get("added_at") or "", reverse=True)
        for entry, rec in pairs:
            if rec:
                head = f"- `{rec['id']}`｜{source_line(rec)}｜答案 {rec.get('ans') or '—'}"
                stem = one_line(rec.get("stem"))
            else:
                head = f"- `{entry.get('id')}`｜（题库中已找不到该题）"
                stem = ""
            lines.append(head)
            reason = normalize_reason(entry.get("reason")) or "未标注"
            lines.append(f"  - 错因：{reason} → {tech_chapter(code, rec.get('type') if rec else '', tax)}")
            if entry.get("note"):
                lines.append(f"  - 备注：{entry['note']}")
            if stem:
                lines.append(f"  - 题干：{stem[:60]}{'…' if len(stem) > 60 else ''}")
        lines.append("")

    lines.append("## 三、复习建议")
    lines.append("")
    for i, tip in enumerate(review_tips(reason_cnt, code_cnt, total, tax, module_cnt), 1):
        lines.append(f"{i}. {tip}")
    lines.append("")
    lines.append("> 复盘五步：对答案 → 析错因 → 找规律 → 调策略 → 定计划（cuoti-muban 5.1）。")
    lines.append("")

    write_report(out, lines)
    print(f"已生成错题本报告：{out}（{total} 题）")
    print("建议接着看：python scripts/wrongbook.py stats")
    return 0


def review_tips(reason_cnt, code_cnt, total, tax, module_cnt=None):
    tips = []
    module_cnt = module_cnt or {}
    calc_heavy = sum(module_cnt.get(m, 0) for m in ("资料分析", "数量关系"))
    ranked = sorted(((n, r) for r, n in reason_cnt.items() if r in REASON_ACTION), key=lambda kv: -kv[0])
    for n, reason in ranked[:3]:
        tip = REASON_TIP[reason]
        if reason == "技巧不熟" and module_cnt and not calc_heavy:
            tip = ("按题型连做 10 题并计时，先把识别标志与排除顺序固定下来，再追求提速；"
                   "言语/判断优先练「先看问法再读文段」的流程（cuoti-muban 4.1.2）")
        tips.append(f"**{reason}（{n} 题，{n / total * 100:.0f}%）**：{tip}。")
    if code_cnt:
        code, n = sorted(code_cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        name = tax.get(code, (code, ""))[0] if code in tax else code
        tips.append(f"**考点最集中：{code} {name}（{n} 题）**：技巧章节：{tech_chapter(code, '', tax)}；"
                    f"再用 `python scripts/paper.py --code {code} --count 10 --seed 7` 组一套专项卷限时做。")
    tips.append("**复习节奏**：按当天 / 第 2 天 / 第 7 天 / 第 15 天 / 第 30 天重做，遮住答案写完整过程，"
                "仍错的题标出来回到对应章节（cuoti-muban 6.1、6.3）。")
    while len(tips) < 3:
        tips.append("**先补齐样本**：错题少于 3 题时分布不可信，继续用 "
                    "`python scripts/paper.py --count 20` 限时刷套题并当天记录错题。")
    return tips[:5]


def write_report(out, lines):
    path = os.path.abspath(out)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")


# --------------------------------------------------------------------------- #
# stats
# --------------------------------------------------------------------------- #
def cmd_stats(args):
    entries = load_book()
    if not entries:
        print("错题本为空。先记录错题，例如：\n"
              "  python scripts/wrongbook.py add --id <题目ID> --reason 技巧不熟 --note \"错因一句话\"")
        return 0

    bank = load_bank()
    total = len(entries)
    module_cnt, code_cnt, reason_cnt = {}, {}, {}
    code_name = {}
    for entry in entries:
        rec = bank.get(entry.get("id")) or {}
        module = rec.get("module") or "未知"
        code = rec.get("code") or "未知"
        if code != "未知":
            code_name[code] = rec.get("type") or code
        reason = normalize_reason(entry.get("reason")) or "未标注"
        module_cnt[module] = module_cnt.get(module, 0) + 1
        code_cnt[code] = code_cnt.get(code, 0) + 1
        reason_cnt[reason] = reason_cnt.get(reason, 0) + 1

    print(f"错题本统计（共 {total} 题）")
    print(f"来源：{rel_book_path()}")
    print()

    print("[按模块]")
    rows = [(m, str(n), f"{n / total * 100:.1f}%")
            for m, n in sorted(module_cnt.items(), key=lambda kv: (-kv[1], MODULE_ORDER.get(kv[0], 99)))]
    print(format_table(["模块", "题数", "占比"], rows, right_cols=(1, 2)))
    print()

    print("[按考点]")
    rows = [(c, code_name.get(c, c), str(n), f"{n / total * 100:.1f}%")
            for c, n in sorted(code_cnt.items(), key=lambda kv: (-kv[1], kv[0]))]
    print(format_table(["考点", "题型", "题数", "占比"], rows, right_cols=(2, 3)))
    print()

    print("[按错因]")
    rows = [(r, str(n), f"{n / total * 100:.1f}%")
            for r, n in sorted(reason_cnt.items(), key=lambda kv: (-kv[1], kv[0]))]
    print(format_table(["错因", "题数", "占比"], rows, right_cols=(1, 2)))
    print()

    top_reason = sorted(reason_cnt.items(), key=lambda kv: -kv[1])[0][0]
    if top_reason in REASON_ACTION:
        print(f"主要错因：{top_reason} → {REASON_ACTION[top_reason]}")
        print(f"下一步：python scripts/wrongbook.py report --out out/wrongbook.md"
              f"（含「{top_reason}」的针对性复习建议）")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser():
    default_path = default_book_rel()
    ap = argparse.ArgumentParser(
        description=("公考错题本：记录错题、关联题库渲染、按考点生成复盘报告\n"
                     f"默认错题本路径：{default_path}"
                     "（环境变量 GONGKAO_WRONGBOOK 可覆盖，用于隔离多套错题本）"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("示例：python scripts/wrongbook.py add --id GK-2024-fs-X112 --reason 技巧不熟 "
                "--note \"比重差算成增长率\"\n"
                f"错题本存储：{default_path}（非 report 的 --out 报告路径）"))
    sub = ap.add_subparsers(dest="cmd", metavar="add|list|report|stats")

    p_add = sub.add_parser("add", help="记录错题（同一 id 重复记录只更新时间与错因）")
    p_add.add_argument("--id", help="单个题目 ID，如 GK-2024-fs-X112")
    p_add.add_argument("--ids", nargs="+", help="多个题目 ID，空格分隔")
    p_add.add_argument("--reason", required=True,
                       help=f"错因：{'/'.join(REASONS)}（粗心失误=粗心大意，没时间=时间不够）")
    p_add.add_argument("--note", default="", help="一句话错因备注，如「比重差算成增长率」")
    p_add.add_argument("--tag", action="append", default=[], help="标签，可多次，如 --tag 比重 --tag 截位")
    p_add.add_argument("--tags", nargs="*", default=[], help="标签列表，空格或逗号分隔")

    p_list = sub.add_parser("list", help="按错因/模块/考点列出错题，并关联题库渲染题目")
    p_list.add_argument("--reason", help=f"错因：{'/'.join(REASONS)}")
    p_list.add_argument("--module", help="模块，如 资料分析")
    p_list.add_argument("--code", help="考点编码，如 ZL-BILI")
    p_list.add_argument("--limit", type=int, default=20, help="显示条数，默认 20；0 表示全部")

    p_report = sub.add_parser("report", help="生成 Markdown 复盘报告")
    p_report.add_argument("--out", help="输出路径，默认 out/wrongbook.md")

    sub.add_parser("stats", help="终端三维统计：模块 / 考点 / 错因")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2
    return {"add": cmd_add, "list": cmd_list, "report": cmd_report, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
