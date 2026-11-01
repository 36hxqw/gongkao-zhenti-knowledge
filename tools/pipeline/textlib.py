# -*- coding: utf-8 -*-
"""Shared text extraction + normalization for the gongkao zhenti pipeline."""
import os
import re
import unicodedata

import pymupdf

CJK = r"\u4e00-\u9fff"

# ---- line level noise -------------------------------------------------------
RE_PAGENO = re.compile(r"^\s*[-—–]?\s*\d{1,4}\s*[-—–]?\s*$")
RE_PAGEFOOT = re.compile(r"第\s*\d+\s*页\s*[,，]?\s*共\s*\d+\s*页")
RE_ONLY_SYMBOL = re.compile(r"^[\W_]+$")


def norm_text(s: str) -> str:
    """Normalize unicode + whitespace but keep newlines."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # collapse >2 blank lines
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


def page_lines(page) -> list[str]:
    """Return lines in *content-stream* order.

    Stream order is more reliable than coordinate order for this corpus: many
    PDFs use fonts with broken glyph widths, which distorts bbox x positions and
    scrambles coordinate-sorted option lines (e.g. 'B' landing after '.①③').
    """
    d = page.get_text("dict")
    lines = []
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in line.get("spans", []))
            if not txt.strip():
                continue
            lines.append(txt)
    return lines


RE_SINGLE_LETTER = re.compile(r"^\s*([ABCD])\s*$")
RE_LEADING_DOT = re.compile(r"^\s*[.．、]\s*")


def merge_letter_dots(lines: list[str]) -> list[str]:
    """'B' + '.①③'  ->  'B.①③'  (artifacts of split glyph runs)."""
    out = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        m = RE_SINGLE_LETTER.match(cur)
        if m and i + 1 < len(lines) and RE_LEADING_DOT.match(lines[i + 1]):
            nxt = RE_LEADING_DOT.sub("", lines[i + 1], count=1)
            out.append(dict(letter=m.group(1), rest=nxt))  # type: ignore[arg-type]
            i += 2
            continue
        out.append(cur)
        i += 1
    res = []
    for x in out:
        if isinstance(x, dict):
            res.append(x["letter"] + "." + x["rest"])
        else:
            res.append(x)
    return res


def clean_lines(lines: list[str], drop_patterns: list[re.Pattern] | None = None) -> list[str]:
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if RE_PAGEFOOT.search(s) and len(s) < 40:
            continue
        if RE_PAGENO.match(s):
            continue
        if drop_patterns and any(p.search(s) for p in drop_patterns):
            continue
        out.append(s)
    return out


def pdf_pages_text(path: str, header_patterns: list[re.Pattern] | None = None) -> list[str]:
    """Extract cleaned page text list; each page joined by '\\n'."""
    doc = pymupdf.open(path)
    pages = []
    try:
        for page in doc:
            lines = merge_letter_dots(page_lines(page))
            lines = clean_lines(lines, header_patterns)
            pages.append("\n".join(lines))
    finally:
        doc.close()
    return pages


def doc_text(path: str, header_patterns: list[re.Pattern] | None = None) -> str:
    return "\n".join(pdf_pages_text(path, header_patterns))


# ---- section detection ------------------------------------------------------
SECTION_PATTERNS = [
    # (regex, canonical section label)
    (re.compile(r"(政治理论|政治常识)"), "政治理论"),
    (re.compile(r"常识(判断|应用|知识)"), "常识判断"),
    (re.compile(r"言语理解(与表达)?"), "言语理解与表达"),
    (re.compile(r"(选词填空|逻辑填空|语句表达|阅读理解|片段阅读|篇章阅读)"), "言语理解与表达"),
    (re.compile(r"(数量关系|数学运算|数字推理)"), "数量关系"),
    (re.compile(r"判断推理"), "判断推理"),
    (re.compile(r"(图形推理|定义判断|类比推理|逻辑判断|事件排序|科学推理|机械推理)"), "判断推理"),
    (re.compile(r"资料分析"), "资料分析"),
    (re.compile(r"(知觉速度|知觉与速度)"), "知觉速度与准确性"),
]

SUBTYPE_PATTERNS = [
    (re.compile(r"图形推理"), "图形推理"),
    (re.compile(r"定义判断"), "定义判断"),
    (re.compile(r"类比推理"), "类比推理"),
    (re.compile(r"(逻辑判断|演绎推理|逻辑推理|逻辑推断)"), "逻辑判断"),
    (re.compile(r"事件排序"), "事件排序"),
    (re.compile(r"(科学推理|机械推理)"), "科学推理"),
    (re.compile(r"数字推理"), "数字推理"),
    (re.compile(r"(数学运算|数理计算)"), "数学运算"),
    (re.compile(r"(选词填空|逻辑填空)"), "逻辑填空"),
    (re.compile(r"语句表达"), "语句表达"),
    (re.compile(r"(阅读理解|片段阅读)"), "片段阅读"),
    (re.compile(r"篇章阅读"), "篇章阅读"),
]

RE_PART_HEAD = re.compile(r"^第[一二三四五六七八九十]{1,2}部分")
RE_NUM_HEAD = re.compile(r"^[一二三四五六七八九十]{1,2}\s*[、.．]")
RE_PAREN_HEAD = re.compile(r"^[（(]\s*[一二三四五六七八九十]{1,2}\s*[）)]")


def _is_heading_shaped(s: str) -> bool:
    """Section headings carry an explicit numbering marker or are short.

    Headings in this corpus range from a bare "图形推理" to
    "二、言语理解与表达（共20 题，参考时限20 分钟）", so the gate is shape-based
    rather than length-based. Wrapped continuation fragments such as
    "推理、逻辑判断。" are rejected: no marker, ends with a period.
    """
    if RE_PART_HEAD.match(s) or RE_NUM_HEAD.match(s) or RE_PAREN_HEAD.match(s):
        return True
    if len(s) <= 16 and not s.endswith("。") and not s.startswith(("、", "，", ",")):
        return True
    return False


def detect_section(line: str):
    """Return (section, subtype) if this line is a heading, else (None, None)."""
    s = line.strip()
    if not s or len(s) > 80:
        return None, None
    if re.match(r"^[A-D]\s*[.、．]", s):
        return None, None
    if not _is_heading_shaped(s):
        return None, None
    for pat, label in SECTION_PATTERNS:
        if pat.search(s):
            sub = None
            for sp, slab in SUBTYPE_PATTERNS:
                if sp.search(s):
                    sub = slab
                    break
            return label, sub
    return None, None
