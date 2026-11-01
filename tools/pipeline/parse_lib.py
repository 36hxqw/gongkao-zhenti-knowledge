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
RE_RANGED = re.compile(r"【?\s*(\d{1,3})\s*[-—–~]\s*(\d{1,3})\s*】?\s*[：:]?\s*([A-D]{2,12})")
RE_CORRECT = re.compile(r"故(?:正确)?答案(?:应)?(?:为|是)\s*[：:]?\s*【?\s*([A-D])\s*】?")
RE_CHOOSE = re.compile(r"(?:因此|故|所以)[，,]?\s*(?:选择|应选|选)\s*([A-D])\s*(?:选项|项|$|。|，)")
RE_ANS_TAG = re.compile(r"【\s*答案\s*】\s*[:：]?\s*([A-D])")
RE_NUM_LETTER = re.compile(r"^(\d{1,3})\s*[.、．]\s*([A-D])\s*(?:项|$|[：:，,、。［\[（(])")


def _answer_in_block(body):
    m = RE_CORRECT.search(body)
    if m:
        return m.group(1)
    m = RE_CHOOSE.search(body)
    if m:
        return m.group(1)
    m = RE_ANS_TAG.search(body)
    if m:
        return m.group(1)
    m = re.search(r"(?:正确)?答案(?:应)?(?:为|是|选)\s*[:：]?\s*([A-D])\b", body)
    if m:
        return m.group(1)
    return None


def parse_answers(text):
    out = {}

    def put(num, ans, expl=None):
        rec = out.setdefault(num, {"ans": None, "expl": ""})
        if ans and not rec["ans"]:
            rec["ans"] = ans
        if expl and len(expl) > len(rec["expl"]):
            rec["expl"] = expl

    for m in RE_RANGED.finditer(text):
        a, b, letters = int(m.group(1)), int(m.group(2)), m.group(3)
        if 0 < b - a + 1 == len(letters):
            for k, ch in enumerate(letters):
                put(a + k, ch)

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    marks = []      # (line_index, num)
    expected = 1
    for i, ln in enumerate(lines):
        m = NUM_START.match(ln)
        if not m:
            m = re.match(r"^(\d{1,3})\s*【\s*答案\s*】", ln)
        if not m:
            continue
        num = int(m.group(1))
        ok = num == expected or (expected < num <= expected + 3)
        if not ok and expected < num <= expected + 60:
            ok = True
        if ok:
            marks.append((i, num))
            expected = num + 1
    if len(marks) >= 5:
        for i, (li, num) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(lines)
            body = "\n".join(lines[li:end])
            # letter right after the number (F1 style: "1．B")
            m0 = RE_NUM_LETTER.match(lines[li].strip())
            ans = m0.group(2) if m0 else None
            if not ans:
                ans = _answer_in_block(body)
            put(num, ans, body)
    if sum(1 for v in out.values() if v["ans"]) < 5:
        seq = RE_CORRECT.findall(text)
        if len(seq) >= 8:
            for i, ch in enumerate(seq):
                put(i + 1, ch)
    return out
