#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公考行测组卷 CLI（纯标准库，无第三方依赖）。

用法示例
--------
    # 资料分析 20 题（国考近八年），写入 Markdown 试卷
    python scripts/paper.py --module 资料分析 --count 20 --prov 国考 --years 2019-2026 --out out/paper-资料分析.md

    # 指定考点 10 题，固定随机种子（同一 seed + 同一题库可复现）
    python scripts/paper.py --code ZL-BILI --count 10 --seed 7 --with-answers

    # 图形推理 10 题，排除科学推理，输出 JSON 给程序消费
    python scripts/paper.py --module 判断推理 --exclude-type 科学推理 --count 10 --format json

    # 多模块配额：资料分析 10 题 + 判断推理 10 题（--count 仅作上限）
    python scripts/paper.py --quota 资料分析=10 --quota 判断推理=10 --seed 1 --out out/paper-组合.md

    # 只打印选题清单（id/年份/模块/题型），不写文件
    python scripts/paper.py --module 资料分析 --count 20 --min-year 2022 --dry-run

组卷规则
--------
1. 过滤：--module / --type / --code / --prov / --years / --min-year / --exclude-type；
   默认 --exclude-dup 只取 canonical == id 的主记录（同题变体折叠，--no-exclude-dup 可展开）。
2. 质量过滤（默认开启，--allow-dirty 关闭）：排除
   - 题干含「本试卷由 / 粉笔 / 上岸 / 微信公众号 / 扫码 / 关注我们 / QQ群」等水印广告的题；
   - 题干混入选项碎片（如「） A.」「上 B.」）的题；
   - 题干清洗后不足 8 字的题；
   - ans 为空的题（开关 --allow-no-answer，只放开这一项）；
   - 数据层标记 stem_flag 的题（short/contaminated/watermark/missing_opts，
     开关 --allow-flagged，只放开这一项）。
   成卷说明里会列出被排除的 id 数。
3. 年份配额：单一年份不超过请求题量的 --max-per-year-ratio（默认 0.4）。
   抽样先按考点轮转（考点尽量分散），考点内取「当前已选最少」的年份、同条件取近年，
   年份自然摊平后再用配额做硬约束；配额卡住、凑不满时才从其他年份补，并在试卷里如实提示。
   想集中练近年真题时，用 --min-year / --years 收窄范围即可。
4. 模块配额：--quota 模块=数量（可多次），给定时以配额为准、--count 仅作上限；
   未显式给 --count 时目标题量默认取配额之和（如 5+10+10=25，不会被压成 4+8+8）；
   配额之和超过显式 --count 时才按比例压缩并打印 ⚠ 提示；配额凑不满时打印
   ⚠ 配额不足：<模块> 缺 N 题（已缩减），不静默压缩。
5. 随机种子：未给 --seed 时固定用 20260101，保证 --dry-run 与成卷、两次运行结果一致。
6. 配图：图形题（fig / 图形推理）与资料分析题若存在 references/images/<id>.jpg，则标注该相对路径。
7. 输出：Markdown（标题 + 试题 + 答案与考点页）或 JSON 数组（题库完整字段 + image）；
   --dry-run 只打印选题清单，不写文件。

退出码：0 成功（含可用题量不足）；2 无结果或参数错误。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import unicodedata
from collections import Counter, deque
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
IMAGES = os.path.join(BASE, "references", "images")

# 模块别名 -> 题库里的标准模块名
MODULE_ALIAS = {
    "资料分析": "资料分析", "资料": "资料分析", "zl": "资料分析",
    "判断推理": "判断推理", "判断": "判断推理", "pd": "判断推理",
    "言语理解": "言语理解", "言语": "言语理解", "yy": "言语理解",
    "数量关系": "数量关系", "数量": "数量关系", "sl": "数量关系",
    "常识判断": "常识判断", "常识": "常识判断", "cs": "常识判断",
    "申论": "申论", "sn": "申论",
}

# 模块展示顺序
MODULE_ORDER = {"资料分析": 0, "判断推理": 1, "言语理解": 2, "数量关系": 3, "常识判断": 4, "申论": 5}

# 建议用时基准：(基准题量, 基准分钟, 备注)；与花生十三的套题时间分配一致
MODULE_TIME = {
    "资料分析": (20, 25, ""),
    "判断推理": (40, 35, ""),
    "数量关系": (15, 12, "选做"),
    "言语理解": (40, 35, ""),
    "常识判断": (20, 8, ""),
}

PROV_ALIAS = {
    "国考": "国考", "国家": "国考", "国": "国考", "guokao": "国考", "gk": "国考",
    "广东": "广东", "广东省考": "广东", "gd": "广东",
    "湖北": "湖北", "湖北省考": "湖北", "hb": "湖北",
}

YEAR_SPLIT = re.compile(r"[,，、;；/\s]+")
YEAR_RANGE = re.compile(r"^(\d{4})\s*[-~—–至]\s*(\d{4})$")

# ---- 质量过滤口径（默认开启，--allow-dirty 关闭）---------------------------- #
# 水印/广告词：题干出现即视为脏题（真题库里「本试卷由粉笔用户…生成」这类）
DIRTY_STEM_RE = re.compile(r"本试卷由|粉笔|上岸|微信公众号|扫码|关注我们|QQ群")
# 选项碎片混入题干：如「） A.下降了20%以」「上 B.下降了不到20%」
STEM_FRAGMENT_RE = re.compile(r"[）)]\s*A[.、．]|\.\s*上\s*[A-D][.、．]")
MIN_STEM_LEN = 8

# 默认随机种子：未显式给 --seed 时固定，保证 --dry-run 与成卷、两次运行结果一致
DEFAULT_SEED = 20260101


def _soft_stdio():
    """非 UTF-8 控制台（如 GBK）无法编码 ⚠ 等符号时用 ? 兜底，避免直接崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if "utf" not in (stream.encoding or "").lower():
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def read_jsonl(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"缺少数据文件：{path}\n"
                 f"请先确认题库已生成（可运行 python scripts/selfcheck.py 自检）。")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_years(text):
    """把 '2024' / '2019-2026' / '2019,2021,2024' 解析成年份集合。"""
    years = set()
    # 允许「2019 - 2026」这种带空格的区间写法
    text = re.sub(r"\s*([-~—–至])\s*", r"\1", text.strip())
    for part in YEAR_SPLIT.split(text):
        if not part:
            continue
        m = YEAR_RANGE.match(part)
        if m:
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            years.update(range(lo, hi + 1))
            continue
        if re.fullmatch(r"\d{4}", part):
            years.add(int(part))
            continue
        raise ValueError(part)
    if not years:
        raise ValueError(text)
    return years


def describe_years(years):
    """把年份集合压回可读区间：'2019-2026' 或 '2019,2021,2024'。"""
    ys = sorted(years)
    if len(ys) > 1 and ys == list(range(ys[0], ys[-1] + 1)):
        return f"{ys[0]}-{ys[-1]}"
    return ",".join(str(y) for y in ys)


def split_modules(values):
    """展平 --module，支持多次传参、逗号/顿号/加号分隔。"""
    mods = []
    for raw in values:
        for tok in re.split(r"[,，、+/]+", raw):
            tok = tok.strip()
            if not tok:
                continue
            mod = MODULE_ALIAS.get(tok, MODULE_ALIAS.get(tok.lower(), tok))
            if mod not in mods:
                mods.append(mod)
    return mods


def split_words(values):
    """展平可多次传参、可逗号/顿号分隔的子串参数（如 --exclude-type）。"""
    words = []
    for raw in values:
        for tok in re.split(r"[,，、;；]+", raw):
            tok = tok.strip()
            if tok and tok not in words:
                words.append(tok)
    return words


def parse_quotas(values):
    """解析 --quota 模块=数量（可多次、可逗号分隔），返回 [(标准模块名, 题量)]。"""
    merged = {}
    order = []
    for raw in values:
        for tok in re.split(r"[,，;；]+", raw):
            tok = tok.strip()
            if not tok:
                continue
            m = re.match(r"^(.+?)\s*[=:：]\s*(\d+)$", tok)
            if not m:
                raise ValueError(tok)
            name = m.group(1).strip()
            mod = MODULE_ALIAS.get(name) or MODULE_ALIAS.get(name.lower()) or name
            n = int(m.group(2))
            if n <= 0:
                raise ValueError(tok)
            if mod not in merged:
                order.append(mod)
                merged[mod] = 0
            merged[mod] += n
    return [(m, merged[m]) for m in order]


def fit_quotas(quotas, cap):
    """--count 仅作上限：配额之和超过上限时按比例压缩（最大余额法）。"""
    total = sum(n for _, n in quotas)
    if not cap or total <= cap:
        return dict(quotas)
    fitted = {m: n * cap // total for m, n in quotas}
    rest = cap - sum(fitted.values())
    if rest > 0:
        ranked = sorted(quotas, key=lambda kv: (-(kv[1] * cap % total), -kv[1], kv[0]))
        for mod, want in ranked:
            if rest <= 0:
                break
            if fitted[mod] < want:
                fitted[mod] += 1
                rest -= 1
    return fitted


def match_code(rec, wants):
    """--code 支持考点编码（精确/前缀）与中文题型名（子串）。"""
    code = (rec.get("code") or "").upper()
    for w in wants:
        wu = w.strip().upper()
        if not wu:
            continue
        if code == wu:
            return True
        if re.fullmatch(r"[A-Z]{2}", wu) and code.startswith(wu + "-"):
            return True
        if w in (rec.get("type") or ""):
            return True
    return False


def image_path(rec):
    """图形题与资料分析题若已生成配图，返回仓库相对路径（POSIX 分隔符）。"""
    looks_figure = bool(rec.get("fig")) or "图形" in (rec.get("type") or "")
    if rec.get("module") != "资料分析" and not looks_figure:
        return None
    name = rec["id"] + ".jpg"
    if not os.path.exists(os.path.join(IMAGES, name)):
        return None
    return "references/images/" + name


def _group_pools(recs, seed):
    """按考点分组；组内打乱后按「答案非空优先、同条件下近年优先」排序。"""
    groups = {}
    for r in recs:
        groups.setdefault(r["code"], []).append(r)

    rnd = random.Random(seed)
    for pool in groups.values():
        rnd.shuffle(pool)
        # 稳定排序：答案非空优先（False < True），同条件下年份倒序，同年内保持打乱顺序
        pool.sort(key=lambda r: (not bool(r.get("ans")), -(r.get("year") or 0)))
    codes = sorted(groups)
    rnd.shuffle(codes)
    return codes, groups


def pick_questions(recs, target, seed, max_per_year=None, module_quota=None):
    """先按考点轮转、再受年份配额约束抽题；配额卡住时从其他年份补。

    轮转：每轮每个考点最多出 1 题，考点尽量分散；
    同考点内挑「当前已选年份题数最少」的年份（同条件下取近年），因此年份自然摊平；
    max_per_year 是硬约束（单年上限），第一轮严格遵守，凑不满时第二轮才放宽补题。

    返回 (picked, notes)：
    - notes["relaxed"]：因年份配额卡住而额外补入的题数（0 表示配额完全满足）；
    - notes["relaxed_years"]：补题涉及的年份及题数；
    - notes["quota_short"]：[(模块, 实得, 配额)]，只列未凑满的模块。
    """
    codes, groups = _group_pools(recs, seed)
    buckets = {}
    for code in codes:
        per_year = {}
        for rec in groups[code]:
            per_year.setdefault(rec.get("year") or 0, deque()).append(rec)
        buckets[code] = per_year
    code_module = {c: groups[c][0].get("module") or "" for c in codes}

    quota = dict(module_quota or {})
    year_count = Counter()
    module_count = Counter()
    picked = []
    relaxed_years = Counter()
    state = {"relaxed": 0}

    def take(code, ignore_cap=False):
        """从该考点取 1 题：最少已选年份优先，同年取较新的题。"""
        best_year, best_key = None, None
        for year, items in buckets[code].items():
            if not items:
                continue
            if not ignore_cap and max_per_year and year_count[year] >= max_per_year:
                continue
            key = (year_count[year], -year)
            if best_key is None or key < best_key:
                best_year, best_key = year, key
        if best_year is None:
            return None
        return buckets[code][best_year].popleft()

    def allowed(code):
        """模块配额未满才允许继续出题。"""
        if not quota:
            return True
        mod = code_module[code]
        return module_count[mod] < quota.get(mod, 0)

    def record(rec, extra=False):
        picked.append(rec)
        year = rec.get("year") or 0
        year_count[year] += 1
        module_count[code_module[rec["code"]]] += 1
        if extra:
            state["relaxed"] += 1
            relaxed_years[year] += 1

    # 第一轮：考点轮转 + 年份配额硬约束
    while len(picked) < target:
        moved = False
        for code in codes:
            if len(picked) >= target:
                break
            if not allowed(code):
                continue
            rec = take(code)
            if rec is None:
                continue
            record(rec)
            moved = True
        if not moved:
            break

    # 第二轮：年份配额卡住、题量凑不满时，从其他年份补（仍优先年份少的，避免更偏）
    while len(picked) < target:
        moved = False
        for code in codes:
            if len(picked) >= target:
                break
            if not allowed(code):
                continue
            rec = take(code, ignore_cap=True)
            if rec is None:
                continue
            record(rec, extra=True)
            moved = True
        if not moved:
            break

    quota_short = [(mod, module_count[mod], want) for mod, want in quota.items()
                   if module_count[mod] < want]
    return picked, {"relaxed": state["relaxed"], "relaxed_years": relaxed_years,
                    "quota_short": quota_short}


def time_plan(picked):
    """按模块统计建议用时，返回 (总分钟, [(模块, 题数, 分钟, 备注)])。"""
    cnt = Counter(r["module"] for r in picked)
    mods = sorted(cnt, key=lambda m: MODULE_ORDER.get(m, 99))
    total = 0
    rows = []
    for mod in mods:
        n = cnt[mod]
        spec = MODULE_TIME.get(mod)
        if not spec:
            rows.append((mod, n, None, ""))
            continue
        base_n, base_min, tag = spec
        minutes = max(1, round(n * base_min / base_n))
        total += minutes
        rows.append((mod, n, minutes, tag))
    return total, rows


def time_text(picked):
    total, rows = time_plan(picked)
    known = [r for r in rows if r[2] is not None]
    if not known:
        return f"按行测整体节奏控制在 {max(1, round(len(picked) * 0.9))} 分钟内（该模块无基准用时）"
    if len(known) == 1:
        mod, n, minutes, tag = known[0]
        base_n, base_min, _ = MODULE_TIME[mod]
        tail = "，选做" if tag else ""
        return f"{minutes} 分钟（{mod} {n} 题；基准 {base_n} 题 ≈ {base_min} 分钟{tail}）"
    parts = []
    for mod, n, minutes, tag in known:
        parts.append(f"{mod} {n} 题 {minutes} 分钟" + ("（选做）" if tag else ""))
    return f"合计 {total} 分钟（按模块分别计算：{'；'.join(parts)}）"


def one_line(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def cell(text):
    return one_line(text).replace("|", "／")


def quality_issues(rec, allow_dirty=False, allow_no_answer=False, allow_flagged=False):
    """返回该题命中的「质量原因」列表；空列表表示可入卷。

    默认排除：题干广告/水印词、选项碎片混入题干、题干过短（< 8 字）、无答案、
    以及数据层标记了 stem_flag 的题（题干可能不完整）。
    --allow-dirty 关闭质量过滤（同时放开无答案与题干异常）；
    --allow-no-answer 只放开无答案，--allow-flagged 只放开题干异常。
    """
    issues = []
    if not allow_dirty:
        stem = one_line(rec.get("stem"))
        if DIRTY_STEM_RE.search(stem):
            issues.append("广告水印")
        if STEM_FRAGMENT_RE.search(stem):
            issues.append("选项碎片")
        if len(stem) < MIN_STEM_LEN:
            issues.append("题干过短")
        flag = (rec.get("stem_flag") or "").strip()
        if flag and not allow_flagged:
            issues.append("题干异常")
    if not (allow_dirty or allow_no_answer) and not (rec.get("ans") or "").strip():
        issues.append("无答案")
    return issues


def describe_drop(drop):
    """把过滤统计整理成一行人话。"""
    if not drop or not drop.get("total"):
        return "未排除（候选题均通过质量检查）"
    issues = drop.get("issues") or {}
    parts = [f"{k} {v}" for k, v in sorted(issues.items(), key=lambda kv: (-kv[1], kv[0]))]
    text = f"排除 {drop['total']} 个 id" + (f"（{'、'.join(parts)}）" if parts else "")
    if sum(issues.values()) > drop["total"]:
        text += "，单题可命中多项"
    return text


def quota_short_text(mod, got, want):
    """配额不足的告警文案（--quota 凑不满时不再静默压缩）。"""
    return f"⚠ 配额不足：{mod} 缺 {max(0, want - got)} 题（已缩减）"


def _width(text):
    """终端显示宽度：CJK 全角按 2 列算，用于对齐选题清单。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text, width):
    text = str(text)
    return text + " " * max(0, width - _width(text))


def render_question(idx, rec):
    out = []
    num = rec.get("num") or rec.get("no") or "?"
    out.append(f"### {idx}. {rec['type']}｜{rec['prov']} {rec['year']} {rec['vol']} 第 {num} 题")
    out.append("")

    ctx = one_line(rec.get("ctx"))
    if ctx:
        out.append(f"> **材料**：{ctx}")
        out.append("")

    stem = one_line(rec.get("stem"))
    img = image_path(rec)
    if stem:
        out.append(f"**题干**：{stem}")
    else:
        out.append("**题干**：（原卷题干为图形/公式，见下方配图）")
    out.append("")

    opts = {k: one_line(v) for k, v in (rec.get("opts") or {}).items()}
    if opts and any(opts.values()):
        for key in sorted(opts):
            value = opts[key] or ("（见配图）" if img else "（原卷缺此选项）")
            out.append(f"- **{key}.** {value}")
    elif img:
        out.append("- （原卷选项为图形/表格，见下方配图）")
    else:
        out.append("- （原卷无选项文本）")
    out.append("")

    if img:
        out.append(f"![{rec['id']} 原题配图]({img})")
        out.append("")
    return out


def render_answers(picked):
    out = ["## 二、答案与考点", ""]
    out.append("| 题号 | 答案 | 模块·题型 | 考点 | id | 解析节选 |")
    out.append("|---:|---|---|---|---|---|")
    for i, rec in enumerate(picked, 1):
        ans = rec.get("ans") or "—"
        expl = cell(rec.get("expl"))
        if len(expl) > 200:
            expl = expl[:199].rstrip() + "…"
        if not expl:
            expl = "（原卷无解析）"
        out.append(f"| {i} | {ans} | {cell(rec['module'] + '·' + rec['type'])} | "
                   f"{rec['code']} | `{rec['id']}` | {expl} |")
    out.append("")
    return out


def render_md(picked, total_avail, filters_desc, seed, plan, seed_given=True):
    """渲染 Markdown 试卷；plan 提供目标题量、年份配额、过滤与配额统计。"""
    mods = []
    for r in picked:
        if r["module"] not in mods:
            mods.append(r["module"])
    mods.sort(key=lambda m: MODULE_ORDER.get(m, 99))
    title = "、".join(mods) if mods else "全部模块"
    target = plan.get("target") or len(picked)

    lines = [f"# 行测组卷 · {title}（{len(picked)} 题）", ""]
    lines.append(f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **筛选条件**：{filters_desc}")
    lines.append(f"- **题量**：{len(picked)} 题（候选 {total_avail} 题，按考点轮转抽取）")
    year_cap = plan.get("year_cap")
    ratio = plan.get("ratio") or 0.4
    if year_cap:
        lines.append(f"- **年份配额**：单一年份最多 {year_cap} 题"
                     f"（{ratio:.0%} 上限，--max-per-year-ratio {ratio}）")
    years = Counter(r.get("year") or 0 for r in picked)
    if years:
        dist = "、".join(f"{y} 年 {years[y]} 题" for y in sorted(years, reverse=True))
        share = max(years.values()) / target
        tail = f"，上限 {ratio:.0%}" if year_cap else ""
        lines.append(f"- **年份分布**：{dist}（按请求 {target} 题计，最多一年占 {share:.0%}{tail}）")
    if plan.get("quota"):
        quota_txt = "、".join(f"{m} {n} 题" for m, n in plan["quota"].items())
        lines.append(f"- **模块配额**：{quota_txt}（--count 仅作上限）")
        if plan.get("quota_compressed"):
            lines.append(f"- **⚠ 配额压缩**：--count {plan['quota_cap']} 小于配额之和 "
                         f"{plan['quota_sum']}，已按比例压缩")
    lines.append(f"- **质量过滤**：{plan.get('filter_desc') or '开启'}")
    lines.append(f"- **建议用时**：{time_text(picked)}")
    if seed_given:
        lines.append(f"- **随机种子**：{seed}（同一 seed + 同一题库可复现）")
    else:
        lines.append(f"- **随机种子**：{seed}（默认固定；同一参数两次结果一致，--seed N 可改）")
    dist = Counter(r["code"] for r in picked)
    if dist:
        parts = [f"{code} {n}" for code, n in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))]
        lines.append(f"- **考点分布**：{'、'.join(parts)}（共 {len(dist)} 个考点）")
    if len(picked) < target:
        lines.append(f"- **提示**：可用 {len(picked)} 题（少于请求的 {target} 题），"
                     f"已按实际题量出卷，未重复凑数；可放宽 --years/--prov 或去掉 --type 再组。")
    if plan.get("relaxed"):
        ry = plan.get("relaxed_years") or {}
        years_txt = "、".join(f"{y} 年 {n} 题" for y, n in sorted(ry.items(), reverse=True))
        lines.append(f"- **提示**：年份配额不足以凑满，已从其他年份补 {plan['relaxed']} 题"
                     f"（{years_txt}）；如需严格限年可减少 --count 或放宽 --years。")
    for mod, got, want in plan.get("quota_short") or []:
        lines.append(f"- **提示**：{quota_short_text(mod, got, want)}；"
                     f"可用 {got} 题 / 配额 {want} 题，"
                     f"可放宽 --years/--prov 或去掉 --type。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、试题")
    lines.append("")
    for i, rec in enumerate(picked, 1):
        lines.extend(render_question(i, rec))
    if picked:
        lines.extend(render_answers(picked))
    return "\n".join(lines).rstrip() + "\n"


def record_for_json(rec):
    out = dict(rec)
    out["image"] = image_path(rec)
    return out


def print_dry_run(picked, plan, filters_desc):
    """打印选题清单（id/年份/模块/题型/考点），不写文件。"""
    target = plan.get("target") or len(picked)
    print(f"[dry-run] 筛选条件：{filters_desc}")
    print(f"[dry-run] 选题 {len(picked)} 题（目标 {target} 题；本次不写文件）")
    print()
    header = ["#", "id", "年份", "模块", "题型", "考点"]
    rows = [header]
    for i, rec in enumerate(picked, 1):
        rows.append([str(i), rec["id"], str(rec.get("year") or "?"),
                     rec.get("module") or "", rec.get("type") or "", rec.get("code") or ""])
    widths = [max(_width(row[i]) for row in rows) for i in range(len(header))]
    for row in rows:
        print("  " + "  ".join(_pad(c, w) for c, w in zip(row, widths)).rstrip())
    print()
    years = Counter(r.get("year") or 0 for r in picked)
    if years:
        print("年份分布：" + "、".join(f"{y} 年 {years[y]} 题" for y in sorted(years, reverse=True)))
    if plan.get("quota"):
        print("模块配额：" + "、".join(f"{m} {plan['quota'][m]} 题" for m in plan["quota"]))
    if plan.get("quota_compressed"):
        print(f"⚠ 配额压缩：--count {plan['quota_cap']} 小于配额之和 "
              f"{plan['quota_sum']}，已按比例压缩")
    print("质量过滤：" + (plan.get("filter_desc") or "开启"))
    print(f"建议用时：{time_text(picked)}")
    if plan.get("relaxed"):
        print(f"注意：年份配额不足以凑满，补入 {plan['relaxed']} 题")
    for mod, got, want in plan.get("quota_short") or []:
        print(quota_short_text(mod, got, want))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="公考行测组卷：按考点轮转抽题、按年份配额摊平，输出 Markdown 试卷或 JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python scripts/paper.py --module 资料分析 --count 20 --prov 国考 "
               "--years 2019-2026 --out out/paper-资料分析.md")
    ap.add_argument("--module", action="append", default=[],
                    help="模块：资料分析/数量关系/言语理解/判断推理/常识判断；可多次或逗号分隔")
    ap.add_argument("--type", dest="type_", help="题型（子串匹配），如 图形推理、综合分析")
    ap.add_argument("--exclude-type", dest="exclude_type", action="append", default=[],
                    metavar="KW", help="排除题型（子串匹配，可多次），如 --exclude-type 科学推理")
    ap.add_argument("--code", action="append", default=[],
                    help="考点编码或中文题型名，可多次，如 ZL-BILI / 比重计算与比较")
    ap.add_argument("--prov", help="省份：国考/广东/湖北")
    ap.add_argument("--years", help="年份或区间：2024 或 2019-2026（也支持 2019,2021,2024）")
    ap.add_argument("--min-year", type=int, help="只取不早于该年的题，如 --min-year 2022")
    ap.add_argument("--count", type=int, default=None,
                    help="题量；缺省时有 --quota 取配额之和（25），否则 20；给定 --quota 时仅作上限")
    ap.add_argument("--quota", action="append", default=[], metavar="模块=数量",
                    help="模块配额，可多次，如 --quota 资料分析=10 --quota 判断推理=10")
    ap.add_argument("--max-per-year-ratio", type=float, default=0.4, dest="max_per_year_ratio",
                    metavar="R",
                    help="单一年份最多占请求题量的比例，默认 0.4；<=0 或 >=1 表示不限制")
    ap.add_argument("--allow-dirty", dest="allow_dirty", action="store_true",
                    help="关闭质量过滤（水印/广告、选项碎片、题干过短、无答案、题干异常）")
    ap.add_argument("--allow-no-answer", dest="allow_no_answer", action="store_true",
                    help="只放开「无答案」这一项质量过滤，其余仍生效")
    ap.add_argument("--allow-flagged", dest="allow_flagged", action="store_true",
                    help="只放开「题干异常」这一项质量过滤（stem_flag 非空），其余仍生效")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="只打印选题清单（id/年份/模块/题型），不写文件")
    ap.add_argument("--seed", type=int,
                    help=f"随机种子，默认 {DEFAULT_SEED}（固定默认保证可复现）")
    ap.add_argument("--with-answers", dest="with_answers", action="store_true", default=True,
                    help="附带「答案与考点」页（默认开启）")
    ap.add_argument("--no-answers", dest="with_answers", action="store_false",
                    help="不输出答案页，适合先自测再对答案")
    ap.add_argument("--format", dest="fmt", choices=["md", "json"], default="md",
                    help="输出格式：md（默认）或 json")
    ap.add_argument("--out", help="输出文件路径，如 out/paper-资料分析.md；缺省打印到终端")
    ap.add_argument("--exclude-dup", action=argparse.BooleanOptionalAction, default=True,
                    help="只取 canonical==id 的主记录（默认开启；--no-exclude-dup 展开同题变体）")
    ap.add_argument("--shenlun", action="store_true", help="申论组卷（接口预留，本轮暂不支持）")
    args = ap.parse_args(argv)
    _soft_stdio()

    if args.shenlun:
        print("暂不支持：paper.py 本轮只组行测卷。\n"
              "申论请用 python scripts/search.py --shenlun --kw 概括 --limit 5 逐题检索，"
              "或先用 python scripts/wrongbook.py add 记录申论错题。", file=sys.stderr)
        return 2
    if args.count is not None and args.count <= 0:
        print("--count 必须为正整数，例如 --count 20。", file=sys.stderr)
        return 2

    seed_given = args.seed is not None
    seed = args.seed if seed_given else DEFAULT_SEED

    mods = split_modules(args.module)
    exclude_types = split_words(args.exclude_type)
    quotas = []
    if args.quota:
        try:
            quotas = parse_quotas(args.quota)
        except ValueError as exc:
            print(f"--quota 格式不对：{exc}\n"
                  f"正确写法：--quota 资料分析=10 --quota 判断推理=10（= 号分隔，数量为正整数）。",
                  file=sys.stderr)
            return 2
    prov = None
    if args.prov:
        key = args.prov.strip()
        prov = PROV_ALIAS.get(key) or PROV_ALIAS.get(key.lower()) or key

    years = None
    if args.years:
        try:
            years = parse_years(args.years)
        except ValueError:
            print(f"--years 格式不对：{args.years}\n"
                  f"正确写法：2024 或 2019-2026 或 2019,2021,2024。", file=sys.stderr)
            return 2

    recs = read_jsonl("xingce.jsonl")
    sel = recs
    if mods:
        sel = [r for r in sel if any(r["module"] == m or m in r["module"] for m in mods)]
    if args.type_:
        sel = [r for r in sel if args.type_ in (r.get("type") or "")]
    if args.code:
        sel = [r for r in sel if match_code(r, args.code)]
    if prov:
        sel = [r for r in sel if r["prov"] == prov]
    if years is not None:
        sel = [r for r in sel if r["year"] in years]
    if args.min_year:
        sel = [r for r in sel if (r.get("year") or 0) >= args.min_year]
    if exclude_types:
        def excluded(rec):
            text = f"{rec.get('type') or ''} {rec.get('code') or ''}"
            return any(kw in text for kw in exclude_types)
        sel = [r for r in sel if not excluded(r)]
    if args.exclude_dup:
        sel = [r for r in sel if r.get("canonical", r["id"]) == r["id"]]

    # 质量过滤（默认开启）：结构过滤之后再按题干/答案做脏题筛查
    dropped = {"total": 0, "issues": Counter()}
    if sel:
        clean = []
        for rec in sel:
            issues = quality_issues(rec, args.allow_dirty, args.allow_no_answer,
                                    args.allow_flagged)
            if issues:
                dropped["total"] += 1
                dropped["issues"].update(issues)
            else:
                clean.append(rec)
        sel = clean

    if not sel:
        if dropped["total"]:
            print(f"命中 {dropped['total']} 题，但全部被质量过滤排除：{describe_drop(dropped)}。\n"
                  f"可加 --allow-dirty 关闭质量过滤，或加 --allow-no-answer 放开无答案题。",
                  file=sys.stderr)
        else:
            print("未命中任何题目，无法组卷。建议：\n"
                  "  ① 放宽年份：--years 2015-2026（或去掉 --years）\n"
                  "  ② 去掉省份限制：--prov 国考 换成 广东/湖北，或不加 --prov\n"
                  "  ③ 换模块/题型：--module 资料分析、--type 图形推理\n"
                  "  ④ 换考点编码：--code ZL-BILI（先用 python scripts/search.py --list-kaodian 查编码）\n"
                  "  ⑤ 展开同题变体：加 --no-exclude-dup", file=sys.stderr)
        return 2

    # 目标题量：有配额时以配额之和为准（--count 仅作上限）；未给 --count 时不再压到默认 20
    module_quota = None
    quota_sum = 0
    quota_cap = None
    quota_compressed = False
    if quotas:
        quota_sum = sum(n for _, n in quotas)
        quota_cap = args.count if args.count is not None else quota_sum
        module_quota = fit_quotas(quotas, quota_cap)
        target = sum(module_quota.values())
        quota_compressed = quota_cap < quota_sum
        if target <= 0:
            print("配额之和为 0，无法组卷；请检查 --quota。", file=sys.stderr)
            return 2
    else:
        target = args.count if args.count is not None else 20

    ratio = args.max_per_year_ratio
    max_per_year = None
    if ratio is not None and 0 < ratio < 1:
        max_per_year = max(1, int(math.floor(ratio * target + 1e-9)))

    picked, notes = pick_questions(sel, target, seed, max_per_year, module_quota)
    if not picked:
        print("按当前条件没有可入卷的题（可能是 --quota 的模块不在筛选结果里）。\n"
              "建议：检查 --quota 模块名是否与 --module/--prov/--years 冲突。", file=sys.stderr)
        return 2

    filters = []
    if mods:
        filters.append("模块=" + "、".join(mods))
    if args.type_:
        filters.append("题型=" + args.type_)
    if exclude_types:
        filters.append("排除题型=" + "、".join(exclude_types))
    if args.code:
        filters.append("考点=" + "、".join(args.code))
    if prov:
        filters.append("省份=" + prov)
    if years is not None:
        filters.append("年份=" + describe_years(years))
    if args.min_year:
        filters.append(f"起始年>={args.min_year}")
    if module_quota:
        filters.append("模块配额=" + "、".join(f"{m}{n}" for m, n in module_quota.items()))
    if not args.exclude_dup:
        filters.append("含同题变体")
    filters_desc = "；".join(filters) or "全部题库"

    if args.allow_dirty:
        filter_desc = "已关闭（--allow-dirty）"
    else:
        filter_desc = describe_drop(dropped)
        if args.allow_no_answer:
            filter_desc += "；无答案题已放开（--allow-no-answer）"
        if args.allow_flagged:
            filter_desc += "；题干异常题已放开（--allow-flagged）"

    plan = {
        "target": target,
        "year_cap": max_per_year,
        "ratio": ratio,
        "quota": module_quota,
        "quota_cap": quota_cap,
        "quota_sum": quota_sum,
        "quota_compressed": quota_compressed,
        "drop": None if args.allow_dirty else dropped,
        "filter_desc": filter_desc,
        "relaxed": notes["relaxed"],
        "relaxed_years": notes["relaxed_years"],
        "quota_short": notes["quota_short"],
    }

    if args.dry_run:
        if args.fmt == "json":
            print(json.dumps([record_for_json(r) for r in picked], ensure_ascii=False, indent=1))
        else:
            print_dry_run(picked, plan, filters_desc)
        if args.out:
            print("dry-run：本次不写文件（已忽略 --out）。", file=sys.stderr)
        return 0

    if args.fmt == "json":
        payload = json.dumps([record_for_json(r) for r in picked], ensure_ascii=False, indent=1)
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload + "\n")
            print(f"已生成组卷（JSON）：{args.out}")
        else:
            print(payload)
    else:
        md = render_md(picked, len(sel), filters_desc, seed, plan, seed_given=seed_given)
        if not args.with_answers:
            cut = md.find("## 二、答案与考点")
            if cut > 0:
                md = md[:cut].rstrip() + "\n"
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(md)
            print(f"已生成组卷：{args.out}")
            print(f"题量：{len(picked)} 题（候选 {len(sel)} 题）｜建议用时：{time_text(picked)}")
            year_dist = Counter(r.get("year") or 0 for r in picked)
            print("年份分布：" + "、".join(f"{y} 年 {n} 题"
                                      for y, n in sorted(year_dist.items(), reverse=True)))
            dist = Counter(r["code"] for r in picked)
            print("考点分布：" + "、".join(f"{c} {n}" for c, n in
                                      sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))))
        else:
            print(md, end="")

    if dropped["total"] and not args.allow_dirty:
        print(f"质量过滤：{describe_drop(dropped)}（--allow-dirty 可关闭）", file=sys.stderr)
    if quota_compressed:
        print(f"⚠ 配额压缩：--count {quota_cap} 小于配额之和 {quota_sum}，已按比例压缩。",
              file=sys.stderr)
    if notes["relaxed"]:
        print(f"注意：年份配额不足以凑满，已从其他年份补 {notes['relaxed']} 题。", file=sys.stderr)
    for mod, got, want in notes["quota_short"]:
        print(quota_short_text(mod, got, want), file=sys.stderr)
    if len(picked) < target:
        print(f"注意：可用 {len(picked)} 题（少于请求的 {target} 题），已按实际题量出卷，未重复凑数。",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
