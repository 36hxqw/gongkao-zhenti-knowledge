# -*- coding: utf-8 -*-
"""为图形题、资料分析（材料为表格图片）生成题目区域截图。

为什么不 OCR：图形/表格本身没有文字，只能靠位图。这里按「题号锚点 + 选项块」
估算每题在页面上的纵向区间，直接裁切，不依赖任何外部服务。

产物：references/images/<id>.jpg（JPEG q=72，最长边 1100px）
"""
import json
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manifest import build as build_manifest  # noqa: E402
from finalize import VOL_CODE, PROV_CODE  # noqa: E402

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPO = os.environ.get("ZHENTI_REPO") or os.path.join(ROOT, "gongkao-zhenti-knowledge")
OUT = os.path.join(REPO, "references", "images")

NUM = re.compile(r"^(\d{1,3})\s*[.、．]")
OPT = re.compile(r"^[A-D]\s*[.、．]|^[A-D]$")

DPI = 150
MAXW = 820
QUALITY = 62


def page_lines(page):
    """[(y0, y1, x0, x1, text)] 按 y 排序，供纵向区间估算。"""
    out = []
    d = page.get_text("dict")
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            txt = "".join(s.get("text", "") for s in ln.get("spans", []))
            if not txt.strip():
                continue
            x0, y0, x1, y1 = ln["bbox"]
            out.append((y0, y1, x0, x1, txt.strip()))
    out.sort(key=lambda t: (t[0], t[2]))
    return out


def crop_question_regions(pdf_path):
    """返回 {num: (page_index, y_start, y_end)}，y 为页面坐标。"""
    doc = pymupdf.open(pdf_path)
    pages = []
    for pi, page in enumerate(doc):
        pages.append(page_lines(page))
    # 题号锚点：按页顺序、纵向顺序，序号单调递增
    marks = []
    expected = 1
    for pi, lines in enumerate(pages):
        for (y0, y1, x0, x1, txt) in lines:
            m = NUM.match(txt)
            if not m:
                continue
            num = int(m.group(1))
            if num == expected or (expected < num <= expected + 60 and len(txt) > 12):
                marks.append({"num": num, "page": pi, "y": y0, "y1": y1})
                expected = num + 1
    # 每题结束位置：该题号到下一题号之间最后一个选项行的下沿
    for i, mk in enumerate(marks):
        nxt = marks[i + 1] if i + 1 < len(marks) else None
        end = None
        for (y0, y1, x0, x1, txt) in pages[mk["page"]]:
            if y0 < mk["y"] - 1:
                continue
            if nxt and nxt["page"] == mk["page"] and y0 >= nxt["y"] - 1:
                break
            if OPT.match(txt):
                end = y1
        if end is None:
            end = mk["y1"] + 4
        mk["end"] = end
    # 区间起点：上一题的结束位置（同一页）；否则本题号上方 12pt
    for i, mk in enumerate(marks):
        prev = marks[i - 1] if i > 0 else None
        if prev and prev["page"] == mk["page"]:
            mk["start"] = min(prev["end"] + 2, mk["y"] - 2) if prev["end"] < mk["y"] else mk["y"] - 2
        else:
            mk["start"] = max(0, mk["y"] - 12)
    doc.close()
    return marks, None


def render_crop(pdf_path, page_index, y0, y1, dest):
    doc = pymupdf.open(pdf_path)
    page = doc[page_index]
    rect = page.rect
    clip = pymupdf.Rect(rect.x0 + 20, max(rect.y0, y0 - 4), rect.x1 - 20, min(rect.y1, y1 + 16))
    if clip.height < 20:
        doc.close()
        return False
    pix = page.get_pixmap(dpi=DPI, clip=clip)
    if pix.width > MAXW:
        pix = page.get_pixmap(dpi=int(DPI * MAXW / pix.width), clip=clip)
    pix.save(dest, output="jpg", jpg_quality=QUALITY)
    doc.close()
    return True


def main(only_recent=True, limit_papers=None):
    os.makedirs(OUT, exist_ok=True)
    recs = [json.loads(l) for l in open(os.path.join(REPO, "data", "xingce.jsonl"), encoding="utf-8")]
    by_paper = {}
    for r in recs:
        by_paper.setdefault((r["prov"], r["year"], r["vol"]), []).append(r)
    papers = {p["prov"] + "|" + str(p["year"]) + "|" + p["volume"]: p for p in build_manifest()}
    todo = []
    for key, rs in by_paper.items():
        k = "|".join([key[0], str(key[1]), key[2]])
        p = papers.get(k)
        if not p or p.get("skip"):
            continue
        targets = [r for r in rs if r["fig"] or r["type"] == "图形推理" or (r["module"] == "资料分析" and not r["ctx"])]
        if only_recent:
            targets = [r for r in targets if (r["year"] or 0) >= 2019]
        if targets:
            todo.append((key, p["qpath"], targets))
    if limit_papers:
        todo = todo[:limit_papers]
    made = failed = 0
    for key, qpath, targets in todo:
        try:
            marks, _ = crop_question_regions(qpath)
        except Exception as e:
            print("PARSE FAIL", key, e)
            continue
        by_num = {m["num"]: m for m in marks}
        for r in targets:
            m = by_num.get(r.get("num"))
            dest = os.path.join(OUT, r["id"] + ".jpg")
            if not m or os.path.exists(dest):
                continue
            ok = render_crop(qpath, m["page"], m["start"], m["end"], dest)
            made += 1 if ok else 0
            failed += 0 if ok else 1
        print(f"{key} targets={len(targets)} marks={len(marks)}")
    print(f"images={made} failed={failed} total_files={len(os.listdir(OUT))}")


if __name__ == "__main__":
    main(only_recent="--all" not in sys.argv,
         limit_papers=int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None)
