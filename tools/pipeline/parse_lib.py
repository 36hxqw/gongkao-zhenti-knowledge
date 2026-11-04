# -*- coding: utf-8 -*-
"""Parse 行测 question PDFs / answer PDFs into structured records (v3).

Design
------
Question numbers restart at 1 for every paper and increase monotonically, so we
anchor on them: a marker is accepted only when it continues the running sequence.
Everything between two markers is one question's "zone".  A zone holds
  (material) + stem + options,  in one of two layouts seen in this corpus:

  type B (国考 2003/2010, 湖北, most 广东):   [N.] stem  A. ... D.
  type A (国考 2025, 广东 2024):              stem  [N.] A. ... D.

The layout is decided per question: if text follows the marker before the option
block, that text is the stem (type B) and preceding text is material; otherwise
the stem is the text accumulated since the previous option block (type A).

Options are parsed with a tolerant scanner that accepts both "A." and "A " marker
styles and both one-per-line and several-per-line layouts.
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textlib import detect_section  # noqa: E402

NUM_START = re.compile(r"^(\d{1,3})\s*[.、．]\s*(.*)$")
DECIMAL_UNIT = re.compile(
    r"^\d{1,3}(?:\.\d+)?\s*(?:万|亿|%|％|倍|元|吨|人|个|平方|立方|千米|公里|米|克|千克|余|多家|余个|分|秒|小时|天|年)"
)
MARKER_DOT = re.compile(r"(?:^|[\s\u3000])([A-D])[.、．]\s*")
MARKER_SPACE = re.compile(r"(?:^|[\s\u3000]{2,})([A-D])[.、．]?\s+(?=\S)")
OPT_HEAD = re.compile(r"^([A-D])\s*(?:[.、．]\s*|\s+)(.*)$")
STEM_OPENERS = re.compile(
    r"^(?:20\d{2}\s*年|19\d{2}\s*年|下列|以下|关于|根据|能够|不能|由此|这段|文中|填入|依次|"
    r"材料|表中|图中|如图|表\d|图\d|据|按|若|已知|某|甲|乙|丙|阅读|资料|注：|（判断题）)"
)
HEADER_NOISE = re.compile(r"(第\s*\d+\s*页|共\s*\d+\s*页|^\s*\d+\s*/\s*\d+\s*$)")


def find_markers(line: str):
    """All option markers in a line: [(letter, start, end)] sorted by position."""
    out = {}
    for m in MARKER_DOT.finditer(line):
        out.setdefault(m.start(1), (m.group(1), m.start(1), m.end()))
    for m in MARKER_SPACE.finditer(line):
        key = m.start(1)
        if all(abs(key - k) > 1 for k in out):
            out.setdefault(key, (m.group(1), m.start(1), m.end()))
    return [out[k] for k in sorted(out)]


def looks_like_stem(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.endswith(("？", "?")):
        return True
    if s.endswith(("的是：", "是：", "的是", "是:")):
        return True
    if STEM_OPENERS.match(s):
        return True
    if NUM_START.match(s):
        return True
    return False


def parse_option_block(lines, start):
    """Parse an option block starting at lines[start].

    Letters are accepted in any order (many papers print options in two
    columns, which puts C before B in the text stream) but each letter is taken
    at most once, and parsing stops as soon as A-D are all present.
    Returns (opts, consumed_lines).
    """
    opts = {}
    cur = None
    order = "ABCD"
    n = len(lines)
    i = start
    while i < n and i < start + 40:
        line = lines[i]
        marks = [m for m in find_markers(line) if m[0] in order]
        if marks:
            for k, (letter, s, e) in enumerate(marks):
                if letter in opts:
                    continue
                if cur and not opts.get(cur) and s > 0:
                    opts[cur] = (opts.get(cur, "") + line[:s]).strip()
                end = marks[k + 1][1] if k + 1 < len(marks) else len(line)
                opts[letter] = line[e:end].strip()
                cur = letter
            if len(opts) >= 4:
                return opts, i - start + 1
            i += 1
            continue
        # continuation of the current option?
        if cur and len(opts.get(cur, "")) < 90 and not looks_like_stem(line) \
                and not re.search(r"[。？！；：]\s*$", opts.get(cur, "")):
            opts[cur] = opts[cur] + line
            i += 1
            continue
        break
    return opts, i - start


def _section_map(lines):
    n = len(lines)
    example = [False] * n
    i = 0
    while i < n:
        if "例题" in lines[i] or "【例" in lines[i]:
            close = None
            for j in range(i + 1, min(n, i + 45)):
                if re.search(r"请开始答题|开始答题", lines[j]):
                    close = j
                    break
            if close is not None:
                for k in range(i, close + 1):
                    example[k] = True
                i = close + 1
                continue
        i += 1
    out = []
    sec, sub = None, None
    for idx, ln in enumerate(lines):
        if example[idx]:
            out.append((sec, sub, True))
            continue
        s, t = detect_section(ln)
        if not s and re.match(r"^第[一二三四五六七八九]部分\s*[：:、]?\s*$", ln) and idx + 1 < n:
            s, t = detect_section(ln + lines[idx + 1])
        if s:
            sec, sub = s, t
            out.append((s, t, True))
        else:
            out.append((sec, sub, False))
    return out


def _questionish(tail: str) -> bool:
    t = (tail or "").strip()
    if len(t) >= 12:
        return True
    if re.search(r"[？?]\s*$|（\s*）\s*$|\(\s*\)\s*$|的是[：:]?$|是[：:]$", t):
        return True
    return False


def _find_markers(lines, smap):
    """Question numbers, accepting large forward jumps only for question-like
    lines (papers routinely lose a run of figure-based questions whose numbers
    never made it into the text layer)."""
    markers = []
    expected = 1
    for idx, line in enumerate(lines):
        if smap[idx][2]:
            continue
        m = NUM_START.match(line)
        if not m:
            continue
        num = int(m.group(1))
        tail = (m.group(2) or "")[:14]
        if DECIMAL_UNIT.match(tail):
            continue
        ok = False
        if num == expected:
            ok = True
        elif expected < num <= expected + 3:
            ok = True
        elif expected < num <= expected + 60 and _questionish(m.group(2)):
            ok = True
        if ok:
            markers.append({"line": idx, "num": num, "inline": bool(m.group(2))})
            expected = num + 1
    return markers


def split_context_stem(text, strong=False):
    """Split long material+stem regions into (context, stem)."""
    t = text.strip()
    limit = 240 if strong else 300
    if len(t) <= limit:
        return "", t
    parts = re.split(r"(?<=[。？！])", t)
    parts = [p for p in parts if p]
    tail, total = [], 0
    for s in reversed(parts):
        tail.append(s)
        total += len(s)
        if total >= 40 and re.search(r"[？?]\s*$", s):
            break
        if total >= 40 and re.search(r"(下列|以下|能够|不能|正确|错误|多少|几倍|比重|增长|平均|说法|是：|的是)", s):
            break
        if total > 200:
            break
    stem = "".join(reversed(tail)).strip()
    ctx = t[: len(t) - len(stem)].strip()
    return ctx, (stem or t)


def parse_paper_text(text):
    raw_lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in raw_lines if ln and not HEADER_NOISE.search(ln)]
    smap = _section_map(lines)
    markers = _find_markers(lines, smap)
    questions = []
    cursor = 0            # first line not yet consumed
    for k, mk in enumerate(markers):
        idx = mk["line"]
        next_idx = markers[k + 1]["line"] if k + 1 < len(markers) else len(lines)
        pre = [lines[j] for j in range(cursor, idx) if not smap[j][2]]
        zone = [lines[j] for j in range(idx + 1, next_idx) if not smap[j][2]]
        inline_txt = ""
        if mk["inline"]:
            m = NUM_START.match(lines[idx])
            inline_txt = m.group(2).strip()
        if inline_txt:
            zone = [inline_txt] + zone
        # locate option block inside zone
        opt_start = None
        for j in range(len(zone)):
            head = find_markers(zone[j])
            if head and head[0][0] == "A":
                ok = len(head) > 1 and head[1][0] == "B"
                if not ok:
                    for nxt in zone[j + 1: j + 6]:
                        if any(l == "B" for l, _, _ in find_markers(nxt)):
                            ok = True
                            break
                if ok:
                    opt_start = j
                    break
        if opt_start is None:
            # no options (图形推理 / 判断题): whole zone is stem
            stem_lines = zone
            opts = {}
            consumed_zone = len(zone)
        else:
            opts, consumed = parse_option_block(zone, opt_start)
            if len(opts) < 2:
                stem_lines = zone
                opts = {}
                consumed_zone = len(zone)
            elif opt_start == 0 and not inline_txt:
                stem_lines = []          # type A: stem sits before the marker
                consumed_zone = opt_start + consumed
            else:
                stem_lines = zone[:opt_start]
                consumed_zone = opt_start + consumed
        sec = smap[idx][0]
        sub = smap[idx][1]
        if stem_lines:
            stem_txt = " ".join(stem_lines).strip()
            ctx = " ".join(pre).strip() if pre else ""
            if sec == "资料分析":
                c2, s2 = split_context_stem((ctx + " " + stem_txt).strip(), strong=True) if ctx else split_context_stem(stem_txt, strong=True)
                ctx, stem_txt = c2, s2
            elif len(stem_txt) > 400:
                c2, s2 = split_context_stem(stem_txt)
                ctx, stem_txt = (ctx + " " + c2).strip(), s2
        else:
            stem_txt = " ".join(pre).strip()
            ctx = ""
            if sec == "资料分析" and len(stem_txt) > 240:
                ctx, stem_txt = split_context_stem(stem_txt, strong=True)
        stem_txt = re.sub(r"\s+", " ", stem_txt).strip()
        ctx = re.sub(r"\s+", " ", ctx).strip()
        judge = bool(re.match(r"^[（(]判断题[）)]", stem_txt))
        if judge:
            opts = {"A": "正确", "B": "错误"}
        questions.append({
            "num": mk["num"], "section": sec, "subtype": sub,
            "context": ctx, "stem": stem_txt, "options": opts,
            "need_figure": not opts, "judge": judge,
            "num_found": True,
        })
        cursor = idx + 1 + consumed_zone
    return questions, smap


# ---------------------------------------------------------------- answers ----
# 答案只认三类**结论性**证据，优先级从高到低：
#   1. 答案表     「1-5 DABBC」「1—5：DABBC」
#   2. 页内标记   「【解析6—正确答案 D】」（无答案表的回忆版卷只有这种逐题标记）
#   3. 段末结论   「故/所以/因此/综上…（正确）答案为X」「正确答案为X」「故选X」
#
# v1.10 修错（387 条「ans 与解析结论不符」的根因，见 sim/ans_conflict/report.md）：
#   * **删除** RE_NUM_LETTER（`^(\d+)\s*[.、．]\s*([A-D])`）这类「数字 + 字母」的弱匹配：
#     它把解析首句「4、A 项正确……」的 A 当成答案（225 条解析题里 216 条的 ans 恰好
#     等于解析首字母，212 条是「A 项」），而真正的结论写在段末。
#   * 同一解析段内取**最后一条**结论（段末结论），并在「注：」「解析二」「支持X答案理由」
#     处截断，避免把补全解析时串进来的下一题结论／争议注当成答案。
#   * **删除**「整卷结论按序号串行赋值」的兜底：广东 2024/2025、湖北 2025 没有答案表，
#     旧逻辑把全卷第 k 条「故正确答案为X」赋给第 k 题，全卷一致率只有 29%/19%/33%。
#     无答案表的卷改用页内标记 → 段末结论。
#   * 全卷体检：解析答案与答案表一致率 < 90% 时打印告警，并把该卷 ans_source 标为
#     inferred（答案表本身不可信时以解析结论为准）。
RE_RANGED = re.compile(r"【?\s*(\d{1,3})\s*[-—–~]\s*(\d{1,3})\s*】?\s*[：:]?\s*([A-D]{2,12})")
RE_ANS_MARK = re.compile(
    r"【?\s*解析\s*(\d{1,3})\s*[—–\-－~]\s*正确答案\s*(?:为|是)?\s*[:：]?\s*【?\s*([A-D]{1,4})")
RE_CONCL = re.compile(
    r"(?:正确)?答案(?:应)?(?:为|是|选)\s*[:：]?\s*【?\s*([A-D]{1,4})(?![0-9A-Za-z])")
RE_SELECT = re.compile(
    r"(?:故|所以|因此|由此(?:可见|可知)?|综上(?:所述)?)[，,]?\s*(?:选择|应选|选)\s*"
    r"([A-D]{1,4})(?![0-9A-Za-z])")
RE_TAIL_NOTE = re.compile(r"(?:注\s*[：:]|【\s*注\s*】|解析二|解析\s*2\b|支持\s*[A-D]\s*答案理由)")
MIN_TABLE_AGREE = 0.90


def _norm_ans(letters):
    """多选答案归一：去重保序（“ACD”/“A、C、D”→ ACD），非法值返回 None。"""
    if not letters:
        return None
    out = ""
    for ch in letters:
        if ch in "ABCD" and ch not in out:
            out += ch
    return out or None


def _trim_tail_note(body):
    """截掉段末的“注：…/解析二…/支持X答案理由…”尾注（段首即出现时不动）。"""
    m = RE_TAIL_NOTE.search(body or "")
    if m and m.start() >= 20:
        return body[:m.start()]
    return body


def _conclusions(body):
    """段内所有强结论 [(pos, letters)]，按出现位置排序。"""
    hits = [(m.start(), _norm_ans(m.group(1))) for m in RE_CONCL.finditer(body or "")]
    hits += [(m.start(), _norm_ans(m.group(1))) for m in RE_SELECT.finditer(body or "")]
    return sorted(h for h in hits if h[1])


def _answer_in_block(body):
    """解析段的段末结论（先截掉尾注）。"""
    hits = _conclusions(_trim_tail_note(body))
    return hits[-1][1] if hits else None


def _answer_table(text):
    """答案表：「1-5 DABBC」这类区间速查表。"""
    table = {}
    for m in RE_RANGED.finditer(text):
        a, b, letters = int(m.group(1)), int(m.group(2)), m.group(3)
        if 0 < b - a + 1 == len(letters):
            for k, ch in enumerate(letters):
                table.setdefault(a + k, ch)
    return table


def _page_marks(text):
    """页内逐题标记：「【解析6—正确答案 D】」。"""
    marks = {}
    for m in RE_ANS_MARK.finditer(text):
        marks.setdefault(int(m.group(1)), _norm_ans(m.group(2)))
    return marks


def _parse_segments(lines):
    """按题号锚点把答案卷切成 {num: 解析段文本}（单调递增，容忍跳号）。"""
    anchors = []      # (line_index, num)
    expected = 1
    MARK_PATTERNS = (
        re.compile(r"^题目\s*(\d{1,3})\s*(?:解析|[.、．])?"),   # 题目1 解析（回忆版）
        re.compile(r"^(\d{1,3})\s*[.、．]\s*正确答案"),            # 1.正确答案为D
        re.compile(r"^(\d{1,3})\s+正确答案(?:是|为)"),            # 2 正确答案是:B
        re.compile(r"^(\d{1,3})\s*[.、．]"),
        re.compile(r"^(\d{1,3})\s*【\s*答案\s*】"),
        re.compile(r"^第?\s*【\s*(\d{1,3})\s*】\s*题?"),   # 【1】解析 / 第【1】题
        re.compile(r"^第\s*(\d{1,3})\s*题"),                # 第1 题
    )
    for i, ln in enumerate(lines):
        m = None
        for pat in MARK_PATTERNS:
            m = pat.match(ln)
            if m:
                break
        if not m:
            continue
        num = int(m.group(1))
        ok = num == expected or (expected < num <= expected + 3)
        if not ok and expected < num <= expected + 60:
            ok = True
        if ok:
            anchors.append((i, num))
            expected = num + 1
    seg = {}
    if len(anchors) >= 5:
        for i, (li, num) in enumerate(anchors):
            end = anchors[i + 1][0] if i + 1 < len(anchors) else len(lines)
            seg[num] = "\n".join(lines[li:end])
    return seg


def parse_answers(text, paper="", min_agree=MIN_TABLE_AGREE):
    """切出每题答案与解析段：``{num: {"ans", "expl", "ans_source"}}``。

    ``ans_source``：``table``（答案表，且全卷一致率达标）/ ``inferred``（页内标记、
    段末结论，或答案表一致率低于阈值时的解析结论）。
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    seg = _parse_segments(lines)
    table = _answer_table(text)
    page = _page_marks(text)
    concl = {num: a for num, body in seg.items() if (a := _answer_in_block(body))}

    # 解析侧证据（页内标记 > 段末结论），用于和答案表对照
    derived = dict(concl)
    derived.update(page)

    # 全卷体检：解析答案 vs 答案表
    agree = None
    if table and derived:
        common = [n for n in table if n in derived]
        if common:
            agree = sum(1 for n in common if table[n] == derived[n]) / len(common)
    low = agree is not None and agree < min_agree
    if low:
        print("⚠ 答案抽取一致率低（%.0f%%，%s）" % (agree * 100, paper or "未命名卷"))

    out = {}
    for num in sorted(set(seg) | set(table) | set(page)):
        if low:
            ans, src = derived.get(num) or table.get(num), "inferred"
        elif num in table:
            ans, src = table[num], "table"
        elif num in page:
            ans, src = page[num], "inferred"
        else:
            ans, src = concl.get(num), "inferred"
        out[num] = {"ans": ans, "expl": seg.get(num, ""),
                    "ans_source": src if ans else None}
    if not table and not page and not concl:
        print("⚠ 未解析出任何答案（%s）：无答案表、无页内标记、无结论句" % (paper or "未命名卷"))
    return out
