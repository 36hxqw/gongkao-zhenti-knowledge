#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公考真题知识库检索 CLI。

用法示例
--------
    # 单考点 + 省份
    python scripts/search.py --kaodian ZL-BASE --prov 国考

    # 多关键词 AND（零散知识点组合定位；0 命中会自动降级为 2 个词并提示）
    python scripts/search.py --kw 黑土地 --kw 保护
    python scripts/search.py --kw 基期 --kw 比重 --kw 百分点

    # 任一词命中（OR）
    python scripts/search.py --any 新质生产力 低空经济 未来产业 --limit 8

    # 年份 + 模块 + 只要题干摘要
    python scripts/search.py --year 2024 --module 判断推理

    # 多值筛选（年份/模块/省份都支持空格分隔或逗号分隔）
    python scripts/search.py --year 2024 2025 --module 资料分析 --limit 3
    python scripts/search.py --year 2024,2025 --prov 国考 广东

    # 分组展示（组内按考点排序）
    python scripts/search.py --module 资料分析 --group-by 年份 --limit 10

    # 按 ID 取完整题目（含解析；同题变体的 id 也可直接查）
    python scripts/search.py --id GD-2023-xj-X056 --full

    # 输出 JSON（供程序消费）
    python scripts/search.py --kw 黑土地 --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from itertools import combinations

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

# 口语 -> 考点编码 的同义词扩展（与花生十三体系一致）
SYNONYMS = {
    "基期": ["ZL-BASE", "基期量"],
    "现期": ["ZL-BASE"],
    "增长量": ["ZL-GROW"],
    "增量": ["ZL-GROW"],
    "增长率": ["ZL-RATE"],
    "增速": ["ZL-RATE"],
    "增幅": ["ZL-RATE"],
    "比重": ["ZL-BILI"],
    "占比": ["ZL-BILI"],
    "平均数": ["ZL-AVG"],
    "人均": ["ZL-AVG"],
    "倍数": ["ZL-BEI"],
    "年均": ["ZL-YEAR"],
    "拉动": ["ZL-PULL"],
    "贡献率": ["ZL-PULL"],
    "综合分析": ["ZL-COMP"],
    "工程": ["SL-GC"],
    "行程": ["SL-XC"],
    "利润": ["SL-LR"],
    "排列组合": ["SL-PL"],
    "概率": ["SL-GL"],
    "容斥": ["SL-RC"],
    "最值": ["SL-ZZ"],
    "年龄": ["SL-NL"],
    "几何": ["SL-JH"],
    "溶液": ["SL-SR", "SL-RY"],
    "牛吃草": ["SL-NCC"],
    "鸡兔同笼": ["SL-JT"],
    "数字推理": ["SL-SZ"],
    "逻辑填空": ["YY-LJTK"],
    "选词填空": ["YY-LJTK"],
    "中心理解": ["YY-ZXJL"],
    "主旨": ["YY-ZXJL"],
    "意图": ["YY-ZXJL"],
    "细节判断": ["YY-XJPD"],
    "标题": ["YY-BTTR"],
    "语句填入": ["YY-YJTR"],
    "下文推断": ["YY-XWTD"],
    "语句衔接": ["YY-YJXH"],
    "语句排序": ["YY-YJPX"],
    "篇章阅读": ["YY-PZYD"],
    "图形推理": ["PD-TX"],
    "定义判断": ["PD-DY"],
    "类比推理": ["PD-LB"],
    "逻辑判断": ["PD-LJ"],
    "翻译推理": ["PD-LJ"],
    "真假推理": ["PD-LJ"],
    "加强削弱": ["PD-LJ"],
    "科学推理": ["PD-KX"],
    "政治": ["CS-ZZ"],
    "法律": ["CS-FL"],
    "经济": ["CS-JJ"],
    "历史": ["CS-LS"],
    "人文": ["CS-LS"],
    "地理": ["CS-DL"],
    "科技": ["CS-KJ"],
    "时政": ["CS-SZ"],
    "生活": ["CS-SH"],
    "申论": ["SN-DY", "SN-ZH", "SN-DC", "SN-GW", "SN-DZW"],
    "概括": ["SN-DY"],
    "对策": ["SN-DC"],
    "公文": ["SN-GW"],
    "大作文": ["SN-DZW"],
}

PROV_ALIAS = {
    "国考": "国考", "国家": "国考", "国": "国考", "guokao": "国考",
    "广东": "广东", "广东省考": "广东", "gd": "广东",
    "湖北": "湖北", "湖北省考": "湖北", "hb": "湖北",
}

# 题号形如 GD-2023-xj-X056 / GK-2025-fs-X010（年份+省份+卷别+题号，便于失配时给最近 id）
ID_RE = re.compile(r"^([A-Za-z]{2,4})-(\d{4})-([A-Za-z0-9]+)-([A-Za-z]+)(\d+)$")
PROV_CODE = {"GK": "国考", "GD": "广东", "HB": "湖北"}
PROV_ORDER = {"国考": 0, "广东": 1, "湖北": 2}

# stem_flag 原值 -> 展示给用户的「原因」
STEM_FLAG_REASON = {
    "short": "题干过短",
    "contaminated": "含邻题残句",
    "watermark": "含广告水印",
    "missing_opts": "选项残缺",
}

# 完全无答案且无 ans_note 时的统一文案（不再写「扫描版」）
NO_ANSWER_TEXT = "该题答案缺失，见原卷"

GROUP_BY_CHOICES = ("年份", "考点", "省份", "年份+考点")


class _Parser(argparse.ArgumentParser):
    """argparse 默认报错只有 usage + 一行英文；这里补一句中文用法示例，避免裸 traceback。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"参数有误：{message}\n"
              f"示例：python scripts/search.py --year 2024 2025 --module 资料分析 --limit 3\n"
              f"      python scripts/search.py --kw 比重 --kw 同比 --group-by 年份",
              file=sys.stderr)
        raise SystemExit(2)


def _soft_stdio():
    """非 UTF-8 控制台（如 GBK）无法编码 ⚠ 等符号时用 ? 兜底，避免直接崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if "utf" not in (stream.encoding or "").lower():
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def split_terms(values):
    """展平可多值的参数：支持空格（nargs）+ 逗号/顿号/加号分隔。"""
    out = []
    for raw in values or []:
        for tok in re.split(r"[,，、+/]+", str(raw)):
            tok = tok.strip()
            if tok and tok not in out:
                out.append(tok)
    return out


def parse_year_values(values):
    """--year 的取值解析：支持 2024 / 2024,2025 / 2024 2025 / 2023-2025。"""
    years = []
    for raw in values or []:
        for tok in re.split(r"[,，、/\s]+", str(raw).strip()):
            if not tok:
                continue
            m = re.fullmatch(r"(\d{4})\s*[-~—–至]\s*(\d{4})", tok)
            if m:
                lo, hi = sorted((int(m.group(1)), int(m.group(2))))
                years.extend(range(lo, hi + 1))
            elif re.fullmatch(r"\d{4}", tok):
                years.append(int(tok))
            else:
                raise ValueError(tok)
    return sorted(set(years))


def answer_text(rec):
    """答案展示口径：有 ans 用 ans；ans 空但有 ans_note 用说明；两者都没有用统一缺失文案。"""
    ans = (rec.get("ans") or "").strip()
    if ans:
        return ans
    note = (rec.get("ans_note") or "").strip()
    if note:
        return note
    return NO_ANSWER_TEXT


def _read_jsonl(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"缺少数据文件：{path}")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def norm(s):
    return (s or "").strip().lower()



# 同义词组：fuzzy 模式下任一说法命中即算命中（解决“换个说法就搜不到”）
SYNONYM_GROUPS = [
    ["比重", "占比", "所占比例", "比例"],
    ["增长率", "增速", "增幅", "增长速度", "涨幅"],
    ["增长量", "增量", "增加量", "净增"],
    ["平均数", "人均", "平均值"],
    ["倍数", "几倍"],
    ["工程", "工程量", "工期"],
    ["行程", "路程", "速度"],
    ["削弱", "质疑", "反驳", "动摇"],
    ["加强", "支持", "强化"],
    ["对策", "建议", "措施", "办法"],
    ["概括", "归纳", "总结", "提炼"],
    ["标题", "题目", "命名"],
    ["排序", "语序", "排列顺序"],
    ["公文", "文书", "应用文"],
    ["大作文", "议论文", "文章写作"],
    ["时政", "时事", "热点"],
    ["科技", "技术", "前沿"],
    ["地理", "地形", "气候"],
    ["法律", "法条", "法规"],
    ["经济", "财经"],
    ["图形", "图案", "图推"],
    ["定义", "概念"],
    ["类比", "比喻"],
    ["逻辑", "推理"],
]
_EXPAND = {}
for _g in SYNONYM_GROUPS:
    for _w in _g:
        _EXPAND.setdefault(_w, set()).update(_g)


def _bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)}


def fuzzy_hit(kw, hay):
    """同义词任一命中，或 2-gram 覆盖率 >= 0.6（容忍语序/个别字差异/空格）。"""
    hay_ns = _nospace(hay)
    for v in _EXPAND.get(kw, {kw}):
        if v in hay or _nospace(v) in hay_ns:
            return True
    q = _nospace(kw)
    a = _bigrams(q)
    if not a:
        return q in hay_ns
    hit = sum(1 for g in a if g in hay_ns)
    return hit / len(a) >= 0.6


def match_keywords_fuzzy(rec, kws):
    hay = " ".join([
        rec.get("stem", ""), rec.get("ctx", ""), rec.get("material", ""),
        " ".join((rec.get("opts") or {}).values()),
        rec.get("expl", ""), rec.get("type", ""), rec.get("sub", ""),
    ])
    return all(fuzzy_hit(k, hay) for k in kws)


RE_WS = re.compile(r"\s+")


def _nospace(s):
    return RE_WS.sub("", s or "")

def _hay(rec):
    """一条记录的可检索全文（--kw AND 检索口径）。"""
    return " ".join([
        rec.get("stem", ""), rec.get("ctx", ""), rec.get("material", ""),
        " ".join((rec.get("opts") or {}).values()),
        rec.get("expl", ""), rec.get("ans", "") or "",
        " ".join(rec.get("kw") or []),
        rec.get("type", ""), rec.get("module", ""), rec.get("code", ""), rec.get("sub", ""),
        " ".join(rec.get("theme") or []),
    ])


def match_keywords(rec, kws):
    hay = _hay(rec)
    hay_ns = _nospace(hay)
    return all(k.lower() in hay or _nospace(k).lower() in hay_ns for k in kws)


def match_any(rec, kws):
    hay = " ".join([
        rec.get("stem", ""), rec.get("ctx", ""), rec.get("material", ""),
        " ".join((rec.get("opts") or {}).values()),
        rec.get("expl", ""), " ".join(rec.get("kw") or []),
    ])
    hay_ns = _nospace(hay)
    return any(k.lower() in hay or _nospace(k).lower() in hay_ns for k in kws)


def expand_codes(words):
    codes = set()
    for w in words:
        for key, vals in SYNONYMS.items():
            if w == key or w in key:
                codes.update(v for v in vals if v.startswith(("ZL", "SL", "YY", "PD", "CS", "SN")))
    return codes


def fmt(rec, full=False, show_expl=True):
    head = f"[{rec['id']}] {rec['year']} {rec['prov']}·{rec['vol']}"
    num = rec.get("num") or rec.get("no")
    head += f" 第 {num} 题　| {rec['module']}·{rec['type']}（{rec['code']}）"
    if rec.get("sub"):
        head += f"　子考点：{rec['sub']}"
    if rec.get("diff"):
        head += f"　难度：{'★' * rec['diff']}{'☆' * (5 - rec['diff'])}"
    if rec.get("theme"):
        head += f"　主题：{'/'.join(rec['theme'])}"
    out = [head]
    if rec.get("ctx"):
        ctx = rec["ctx"] if full else rec["ctx"][:160] + ("…" if len(rec["ctx"]) > 160 else "")
        out.append(f"  材料：{ctx}")
    out.append(f"  题干：{rec['stem']}")
    flag = (rec.get("stem_flag") or "").strip()
    if flag:
        out.append(f"  ⚠ 题干可能不完整（{STEM_FLAG_REASON.get(flag, flag)}）")
    opts = rec.get("opts") or {}
    if opts:
        line = "  " + "　".join(f"{k}. {v}" for k, v in opts.items())
        out.append(line)
    img_dir = os.path.join(BASE, "references", "images")
    mat = rec.get("mat_img")
    if mat and os.path.exists(os.path.join(img_dir, mat)):
        out.append(f"  材料图：references/images/{mat}")
    img = os.path.join(img_dir, rec["id"] + ".jpg")
    if os.path.exists(img):
        out.append(f"  配图：references/images/{rec['id']}.jpg")
    if rec.get("dup_n", 1) > 1:
        out.append(f"  （同题另有 {rec['dup_n'] - 1} 个变体，--all-variants 展开）")
    out.append(f"  【答案】{answer_text(rec)}")
    if show_expl and rec.get("expl"):
        expl = rec["expl"] if full else rec["expl"][:220] + ("…" if len(rec["expl"]) > 220 else "")
        out.append(f"  【解析】{expl}")
    if rec.get("code", "").startswith("SN") and rec.get("ans"):
        out.append(f"  【参考答案】{rec['ans'] if full else rec['ans'][:220] + '…'}")
    return "\n".join(out)


def _canonical_of(rec):
    """主记录 id；无 canonical 字段（如申论）时视为自身。"""
    return rec.get("canonical") or rec["id"]


def query_by_id(args, recs):
    """--id 精确查询：命中即返回，不经同题折叠。"""
    qid = (args.qid or "").strip()
    hit = next((r for r in recs if r["id"].upper() == qid.upper()), None)
    if hit is None:
        _print_id_miss(qid, recs)
        return 2
    if args.json:
        print(json.dumps([hit], ensure_ascii=False, indent=1))
        return 0
    main_id = _canonical_of(hit)
    if main_id != hit["id"]:
        dup = hit.get("dup_n")
        if not dup:
            dup = sum(1 for r in recs if _canonical_of(r) == main_id)
        print(f"该 id 为同题变体（主记录 {main_id}，该题共 {dup} 个变体）")
    print(fmt(hit, full=args.full))
    return 0


def _rec_num(rec):
    """题号（统一转 int，个别记录可能是字符串）。"""
    n = rec.get("num") or rec.get("no") or 0
    try:
        return int(n)
    except (TypeError, ValueError):
        return 0


def _group_sort_key(rec):
    """组内排序：考点 → 省份 → 年份新 → 题号。"""
    return (rec.get("code") or "", PROV_ORDER.get(rec.get("prov"), 9),
            -(rec.get("year") or 0), _rec_num(rec), rec["id"])


def group_hits(sel, mode):
    """按 --group-by 维度分组，返回 [(组标题, 组内记录)]；组按维度排序，组内按考点排序。"""
    if not mode:
        return []

    def group_of(rec):
        year = rec.get("year") or 0
        prov = rec.get("prov") or "未知省份"
        code = rec.get("code") or "未知考点"
        if mode == "年份":
            return ((-year,), f"{year or '未知'} 年")
        if mode == "省份":
            return ((PROV_ORDER.get(prov, 9), prov), prov)
        if mode == "考点":
            title = code + (f" {rec['type']}" if rec.get("type") else "")
            return ((code,), title)
        # 年份+考点
        return ((-year, code), f"{year or '未知'} 年 · {code}")

    buckets = {}
    for rec in sel:
        key, title = group_of(rec)
        bucket = buckets.setdefault(key, {"title": title, "items": []})
        bucket["items"].append(rec)
    out = []
    for key in sorted(buckets):
        bucket = buckets[key]
        out.append((bucket["title"], sorted(bucket["items"], key=_group_sort_key)))
    return out


def _nearest_ids(qid, recs, n=3):
    """按「年份+省份+题号」给最接近的 n 个 id（用于 --id 未命中时兜底）。"""
    m = ID_RE.match(qid)
    if not m:
        return []
    prov_code, year_s, vol_code, _letter, num_s = m.groups()
    try:
        year, num = int(year_s), int(num_s)
    except ValueError:
        return []
    prov = PROV_CODE.get(prov_code.upper())

    def key(r):
        parts = r["id"].split("-")
        rid_vol = parts[2].lower() if len(parts) >= 3 else ""
        return (abs(_rec_num(r) - num),
                0 if rid_vol == vol_code.lower() else 1,
                _rec_num(r), r["id"])

    pools = []
    if prov:
        pools.append([r for r in recs if r["year"] == year and r["prov"] == prov])
    pools.append([r for r in recs if r["year"] == year])
    if prov:
        pools.append([r for r in recs if r["prov"] == prov])
    pools.append(recs)
    picked = []
    for pool in pools:
        for r in sorted(pool, key=key):
            if r["id"] not in picked:
                picked.append(r["id"])
            if len(picked) >= n:
                return picked[:n]
    return picked[:n]


def _print_id_miss(qid, recs):
    print(f"未找到 id「{qid}」。", file=sys.stderr)
    if not ID_RE.match(qid):
        print("id 形如 GD-2023-xj-X056（省份-年份-卷别-题号）；也可改用 --year/--prov/--kw 检索。",
              file=sys.stderr)
        return
    print("该 id 形如合法题号：可加 --all-variants 展开同题变体，或核对该题号是否输入有误。",
          file=sys.stderr)
    near = _nearest_ids(qid, recs)
    if near:
        print("按「年份+省份+题号」相近的最近 3 个 id：" + "、".join(near), file=sys.stderr)
    else:
        print("按「年份+省份+题号」未找到相近 id，可改用 --year/--prov/--kw 检索。", file=sys.stderr)


def _term_df(kws, hays):
    """每个词在全库中的文档出现次数（越泛次数越多）。"""
    norms = [_nospace(h) for h in hays]
    counts = {}
    for word in kws:
        w, wns = word.lower(), _nospace(word).lower()
        counts[word] = sum(1 for h, hn in zip(hays, norms) if w in h or wns in hn)
    return counts


def keyword_search(sel, kws, corpus, fuzzy=False):
    """关键词 AND 检索；0 命中且词数 > 2 时自动降级为 2 个词。

    降级策略：按词在全库的出现次数「从多到少」依次去掉词（优先去掉最泛的词，
    尽量保住题干里更有区分度的词），保留 2 个词重试，首个有命中的组合生效。
    返回 (命中记录, 被去掉的词列表)。
    """
    matcher = match_keywords_fuzzy if fuzzy else match_keywords
    hits = [r for r in sel if matcher(r, kws)]
    if hits or len(kws) <= 2:
        return hits, []

    freq = _term_df(kws, [_hay(r) for r in corpus])
    drop_n = len(kws) - 2
    cands = sorted(combinations(range(len(kws)), drop_n),
                   key=lambda idxs: (-sum(freq[kws[i]] for i in idxs), idxs))
    for idxs in cands[:30]:
        keep = [k for i, k in enumerate(kws) if i not in idxs]
        hits = [r for r in sel if matcher(r, keep)]
        if hits:
            dropped = sorted((kws[i] for i in idxs), key=lambda w: -freq[w])
            return hits, dropped
    return [], []


def _downgrade_msg(dropped, n_words):
    gone = "、".join(f"「{w}」" for w in dropped)
    return f"已自动降级：去掉了{gone}（原 {n_words} 词 AND 无命中）"


def _print_no_hit(args):
    """0 命中时给出可执行的下一步建议。"""
    print("未命中任何题目。", file=sys.stderr)
    tips = []
    if args.kw:
        tips.append("换同义词或更宽的说法（如 黑土地保护 → 黑土地/耕地保护，比重 ↔ 占比）")
        tips.append("加 --fuzzy 容忍换说法、错字与语序差异")
        if args.year or args.prov or args.module or args.type_ or args.sub or args.vol:
            tips.append("去掉 --year/--prov/--module 等限制，或减少到 2 个关键词")
        else:
            tips.append("只保留 2 个关键词，或改用 --any 任一词命中")
    else:
        tips.append("换用 --kw 关键词检索，或减少 --year/--prov/--module 等限制")
        tips.append("用 --any 改为任一词命中")
        tips.append("用 --all-variants 展开同题变体后重试")
    for i, t in enumerate(tips[:3], 1):
        print(f"  {i}. {t}", file=sys.stderr)


def main(argv=None):
    ap = _Parser(description="公考真题知识库检索")
    ap.add_argument("--kw", action="append", default=[],
                    help="关键词，可多次；多个为 AND（0 命中自动降级为 2 个词）")
    ap.add_argument("--any", nargs="*", default=[], help="任一词命中（OR）")
    ap.add_argument("--fuzzy", action="store_true", help="模糊匹配：同义词 + 2-gram 相似（容忍换说法/错字）")
    ap.add_argument("--kaodian", "--code", dest="kaodian", action="append", default=[],
                    help="考点编码或考点名（如 ZL-BASE / 基期量计算）")
    ap.add_argument("--module", nargs="+", metavar="模块", help="模块：资料分析/数量关系/言语理解/判断推理/常识判断/申论"
                    "（可多个：--module 资料分析 判断推理）")
    ap.add_argument("--type", dest="type_", help="题型名，如 图形推理")
    ap.add_argument("--sub", help="子考点名（三级），如 两期比重差 / 翻译推理 / 最不利构造")
    ap.add_argument("--diff", dest="diff", help="难度：4 或 4-5 或 1,2（1 易 – 5 难）")
    ap.add_argument("--theme", help="申论主题，如 基层治理 / 乡村振兴 / 科技创新")
    ap.add_argument("--year", nargs="+", metavar="年份", default=[],
                    help="年份，可多个（OR）：--year 2024 2025 / --year 2024,2025 / --year 2023-2025")
    ap.add_argument("--from-year", type=int, help="起始年份")
    ap.add_argument("--to-year", type=int, help="结束年份")
    ap.add_argument("--prov", nargs="+", metavar="省份", default=[], help="国考/广东/湖北，可多个（OR）")
    ap.add_argument("--vol", help="卷别：副省级/地市级/行政执法/县级/乡镇/统一卷…")
    ap.add_argument("--id", dest="qid", help="按 ID 精确取题（同题变体 id 也直接命中，不折叠）")
    ap.add_argument("--limit", type=int, default=5, help="返回条数，默认 5")
    ap.add_argument("--group-by", dest="group_by", choices=GROUP_BY_CHOICES, metavar="维度",
                    help="分组展示：年份/考点/省份/年份+考点（组内按考点排序）")
    ap.add_argument("--full", action="store_true", help="输出完整题干与解析")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--shenlun", action="store_true", help="只检索申论")
    ap.add_argument("--xingce", action="store_true", help="只检索行测")
    ap.add_argument("--list-kaodian", action="store_true", help="列出全部考点及题量")
    ap.add_argument("--all-variants", action="store_true", help="展开同题变体（默认折叠，只出主记录）")
    args = ap.parse_args(argv)
    _soft_stdio()

    try:
        years = parse_year_values(args.year)
    except ValueError as exc:
        print(f"--year 格式不对：「{exc}」\n"
              f"正确写法：--year 2024 2025 / --year 2024,2025 / --year 2023-2025。",
              file=sys.stderr)
        return 2

    xingce = [] if args.shenlun else _read_jsonl("xingce.jsonl")
    shenlun = [] if args.xingce else _read_jsonl("shenlun.jsonl")
    recs = xingce + shenlun

    if args.list_kaodian:
        from collections import Counter
        cnt = Counter((r["module"], r["type"], r["code"]) for r in recs)
        for (mod, typ, code), n in sorted(cnt.items(), key=lambda kv: (kv[0][0], -kv[1])):
            print(f"{code:8s} {mod}·{typ}  {n} 题")
        return 0

    # --id 精确查询：命中即返回（同题变体不被折叠），未命中给最近 3 个 id 建议
    if args.qid:
        return query_by_id(args, recs)

    sel = recs
    provs = []
    for p in split_terms(args.prov):
        std = PROV_ALIAS.get(p) or PROV_ALIAS.get(p.lower()) or p
        if std not in provs:
            provs.append(std)
    mods = split_terms(args.module)
    if provs:
        sel = [r for r in sel if r["prov"] in provs]
    if args.vol:
        sel = [r for r in sel if args.vol in r["vol"]]
    if years:
        sel = [r for r in sel if r["year"] in years]
    if args.from_year:
        sel = [r for r in sel if r["year"] and r["year"] >= args.from_year]
    if args.to_year:
        sel = [r for r in sel if r["year"] and r["year"] <= args.to_year]
    if mods:
        sel = [r for r in sel if any(m in (r.get("module") or "") for m in mods)]
    if args.type_:
        sel = [r for r in sel if args.type_ in r["type"]]
    if args.sub:
        sel = [r for r in sel if args.sub in (r.get("sub") or "")]
    if args.diff:
        want = set()
        try:
            for part in str(args.diff).split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    want.update(range(int(a), int(b) + 1))
                elif part:
                    want.add(int(part))
        except ValueError:
            print(f"--diff 格式不对：「{args.diff}」\n"
                  f"正确写法：--diff 4 / --diff 4-5 / --diff 1,2（1 易 – 5 难）。", file=sys.stderr)
            return 2
        sel = [r for r in sel if r.get("diff") in want]
    if args.theme:
        sel = [r for r in sel if any(args.theme in t for t in (r.get("theme") or []))]
    if args.kaodian:
        want = set()
        for k in args.kaodian:
            if re.fullmatch(r"[A-Z]{2}-[A-Z]+", k.upper()):
                want.add(k.upper())
            else:
                want |= {r["code"] for r in sel if k in r["type"] or k in r["code"]}
                want |= expand_codes([k])
        sel = [r for r in sel if r["code"] in want]
    dropped = []
    if args.kw:
        sel, dropped = keyword_search(sel, args.kw, recs, fuzzy=args.fuzzy)
    if args.any:
        sel = [r for r in sel if match_any(r, args.any)]

    # 默认折叠同题变体；记下本次命中集合里被折叠的变体数
    n_variants = 0
    if not args.all_variants:
        n_variants = sum(1 for r in sel if _canonical_of(r) != r["id"])
        sel = [r for r in sel if _canonical_of(r) == r["id"]]

    # 排序：年份新 → 省份（国考/广东/湖北）→ 题号
    order = {"国考": 0, "广东": 1, "湖北": 2}
    sel.sort(key=lambda r: (-(r["year"] or 0), order.get(r["prov"], 9),
                            _rec_num(r), r["id"]))

    if args.json:
        if args.group_by:
            print("（JSON 输出为扁平数组，--group-by 仅作用于文本输出）", file=sys.stderr)
        if len(sel) > args.limit:
            print(f"（已截断：命中 {len(sel)} 条，显示前 {args.limit} 条；用 --limit 调整）",
                  file=sys.stderr)
        print(json.dumps(sel[: args.limit], ensure_ascii=False, indent=1))
        if dropped:
            print(_downgrade_msg(dropped, len(args.kw)), file=sys.stderr)
        return 0

    if not sel:
        if n_variants:
            print(f"（折叠同题变体后无主记录：另有 {n_variants} 条同题变体，加 --all-variants 查看）",
                  file=sys.stderr)
        _print_no_hit(args)
        return 2

    if dropped:
        print(_downgrade_msg(dropped, len(args.kw)))
    shown = sel[: args.limit]
    print(f"命中 {len(sel)} 题，显示前 {len(shown)} 题：\n")
    if len(sel) > len(shown):
        print(f"（已截断：命中 {len(sel)} 条，显示前 {len(shown)} 条；用 --limit 调整）\n")

    # 检索范围提示：默认（行测+申论）下申论占比过高时点明
    if not (args.xingce or args.shenlun):
        n_shen = sum(1 for r in sel if r.get("module") == "申论")
        if n_shen and n_shen / len(sel) > 0.30:
            print(f"申论命中 {n_shen} 条（材料重复度高），可用 --xingce 只看行测\n")

    if args.group_by:
        for title, items in group_hits(shown, args.group_by):
            print(f"── {title}（{len(items)} 题）──")
            for r in items:
                print(fmt(r, full=args.full))
                print("-" * 72)
    else:
        for r in shown:
            print(fmt(r, full=args.full))
            print("-" * 72)
    if n_variants:
        print(f"另有 {n_variants} 条同题变体，加 --all-variants 查看（默认已折叠）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
