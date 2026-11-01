# -*- coding: utf-8 -*-
"""Extract 申论 papers: material + questions + reference answers."""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textlib import doc_text  # noqa: E402
from classify import classify_shenlun  # noqa: E402
import manifest as mx  # noqa: E402

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "pipeline", "cache")
OUT = os.path.join(ROOT, "pipeline", "out")

SN_DIRS = {
    "国考": os.path.join(ROOT, r"国考2000-2026真题pdf\2000-2026国考申论PDF"),
    "广东": os.path.join(ROOT, r"广东公务员考试真题pdf版\广东公务员考试真题——申论03-26pdf版"),
    "湖北": os.path.join(ROOT, r"湖北公务员考试真题pdf版\湖北公务员考试真题——申论07-25PDF版"),
}

ANSWER_MARK = re.compile(r"(参考答案|参考要点|答案解析|答案及解析|【答案】|答案：|参考答案及解析)")
Q_MARK = re.compile(
    r"^\s*(?:"
    r"【\s*问题\s*([一二三四五六七八九十\d]{1,3})\s*】"
    r"|【\s*题目\s*([一二三四五六七八九十\d]{1,3})\s*】"
    r"|问题\s*([一二三四五六七八九十\d]{1,3})\s*[：:．.、]"
    r"|第\s*([一二三四五六七八九十\d]{1,3})\s*题"
    r"|([一二三四五六七八九十]{1,2})\s*[、．.]"
    r"|(\d{1,2})\s*[.、．]"
    r")\s*"
)
Q_HINT = re.compile(r"(概括|归纳|分析|提出|对策|建议|谈谈|理解|看法|启示|拟定|撰写|写一篇|起草|拟写|"
                    r"简报|报告|讲话稿|倡议书|短评|公开信|工作方案|宣传稿|编者按|要求|分\)|字数|作答)")
SCORE_HINT = re.compile(r"(\d{1,2}\s*分\s*[）)]|要求\s*[:：]|字数|不超过\s*\d+\s*字|条理|紧扣材料)")


def ctext(path, tag):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1((tag + path).encode("utf-8")).hexdigest()[:16]
    cf = os.path.join(CACHE, key + ".txt")
    if os.path.exists(cf):
        return open(cf, encoding="utf-8").read()
    t = doc_text(path)
    open(cf, "w", encoding="utf-8").write(t)
    return t


def shenlun_files():
    from manifest import load_bad
    bad = load_bad()
    items = []
    for prov, d in SN_DIRS.items():
        for dirpath, _, files in os.walk(d):
            for f in files:
                if not f.lower().endswith(".pdf"):
                    continue
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, ROOT)
                items.append({"prov": prov, "file": f, "path": p,
                              "year": mx.year_of(f), "volume": mx.volume_of(f),
                              "bad": rel in bad,
                              "is_answer": bool(re.search(r"答案|解析", f)),
                              "size": os.path.getsize(p)})
    return items


def pair_papers(items):
    """Pair 试题 file with 答案 file when they are split."""
    qs = [i for i in items if not i["is_answer"] and not i["bad"]]
    ans = [i for i in items if i["is_answer"] and not i["bad"]]
    used = set()
    papers = []
    for q in qs:
        best, score = None, 0.0
        for a in ans:
            if a["path"] in used or a["year"] != q["year"]:
                continue
            import difflib
            sc = difflib.SequenceMatcher(None, mx.series_of(q["file"]), mx.series_of(a["file"])).ratio()
            if sc > score:
                best, score = a, sc
        has_inline = bool(re.search(r"答案|解析|参考", q["file"]))
        apath = None
        if not has_inline and best and score >= 0.45:
            apath = best["path"]
            used.add(best["path"])
        papers.append({**q, "apath": apath})
    # answer-only files that pair with nothing: keep as standalone Q+A docs
    for a in ans:
        if a["path"] not in used:
            papers.append({**a, "apath": None, "answer_only": True})
    papers.sort(key=lambda p: (p["prov"], p["year"] or 0, p["volume"]))
    return papers


def _marker_label(m):
    for g in m.groups():
        if g:
            return g
    return ""


def split_material_questions(text):
    """Return (material_text, [(num_label, stem)]) from a 申论 paper."""
    m = ANSWER_MARK.search(text)
    body = text[: m.start()] if m else text
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    marks = []
    for i, ln in enumerate(lines):
        mm = Q_MARK.match(ln)
        if not mm:
            continue
        label = _marker_label(mm)
        lookahead = "\n".join(lines[i: i + 9])
        if not SCORE_HINT.search(lookahead) and not Q_HINT.search(lookahead):
            continue
        marks.append((i, label, mm.end()))
    if not marks:
        return body, []
    material = "\n".join(lines[: marks[0][0]])
    questions = []
    for k, (start, label, endpos) in enumerate(marks):
        stop = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        first = lines[start][endpos:].strip() or ""
        block = ([first] if first else []) + lines[start + 1: stop]
        stem = "\n".join(block).strip()
        if 12 <= len(stem) <= 1200:
            questions.append((label, stem))
    return material, questions


def _strip_front_matter(text):
    """Drop 注意事项 / 考试说明 before the real material."""
    i = text.find("给定资料")
    j = text.find("给定材料")
    k = text.find("材料一")
    k2 = text.find("【材料一】")
    cands = [x for x in (i, j, k, k2) if x > 0]
    if cands and min(cands) < 900:
        return text[min(cands):]
    return text


def extract_questions(text):
    """分值-anchored question extraction.

    Every 申论 question carries （20分）/（15分）, which is far more reliable than
    the numbering style (【问题一】/一、/1./问题1 all appear in this corpus).
    """
    m = ANSWER_MARK.search(text)
    body = text[: m.start()] if m else text
    body = _strip_front_matter(body)
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    joined = "\n".join(lines)
    score_pos = list(re.finditer(
        r"[（(]\s*(?:本题|满分|共|分值)?\s*(\d{1,5})\s*分\s*[)）]|满分\s*(\d{1,5})\s*分|本题\s*(\d{1,5})\s*分",
        joined))
    if len(score_pos) < 2:
        return split_material_questions(text)
    marks = []
    prev_end = 0
    for idx, sm in enumerate(score_pos):
        if sm.start() <= prev_end:
            continue
        back = joined[: sm.start()]
        cands = []
        for pat in (r"(?:^|\n)\s*【\s*问题\s*[一二三四五六七八九十\d]+\s*】",
                    r"(?:^|\n)\s*问题\s*[一二三四五六七八九十\d]+\s*[：:．.]?",
                    r"(?:^|\n)\s*第\s*[一二三四五六七八九十\d]+\s*题",
                    r"(?:^|\n)\s*[（(]\s*[一二三四五六七八九十\d]+\s*[）)]",
                    r"(?:^|\n)\s*[一二三四五六七八九十]\s*[、．.]",
                    r"(?:^|\n)\s*\d{1,2}\s*[.、．]"):
            for f in re.finditer(pat, back):
                if f.start() >= prev_end and len(back) - f.start() <= 420:
                    cands.append(f.start())
        if cands:
            start = max(cands)
        else:
            k = max(back.rfind("。", prev_end), back.rfind("\n", prev_end))
            start = k + 1 if k >= prev_end else prev_end
        stem = joined[start: sm.end()].strip()
        # requirement block right after the score marker
        tail = joined[sm.end(): sm.end() + 260]
        tlines = []
        for ln in tail.split("\n"):
            if re.match(r"^\s*(要求|（\d+）|\(\d+\)|不超过|字数)", ln) and len(tlines) < 6:
                tlines.append(ln.strip())
            elif tlines:
                break
            elif ln.strip():
                break
        req = "\n".join(tlines)
        stem_full = stem + ("\n" + req if req else "")
        label = ""
        mm = Q_MARK.match(stem.strip())
        if mm:
            label = _marker_label(mm)
        prev_end = sm.end() + (len(req) if req else 0)
        if len(stem_full) >= 15 and len(stem) >= 8 and len(stem) <= 1200:
            marks.append((label or str(idx + 1), stem_full))
    # material = everything before the first question
    first_start = joined.find(marks[0][1][:20]) if marks else -1
    material = joined[: first_start].strip() if first_start > 0 else ""
    return material, marks


def split_answers(text):
    m = ANSWER_MARK.search(text)
    if not m:
        return ""
    return text[m.end():].strip()


def answer_blocks(ans_text):
    """Split the reference-answer section into per-question blocks."""
    lines = [ln.strip() for ln in ans_text.split("\n") if ln.strip()]
    marks = []
    for i, ln in enumerate(lines):
        mm = Q_MARK.match(ln)
        if mm:
            marks.append((i, _marker_label(mm), mm.end()))
    if not marks:
        return [("", "\n".join(lines))] if lines else []
    blocks = []
    for k, (start, label, endpos) in enumerate(marks):
        stop = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        first = lines[start][endpos:].strip() or ""
        block = ([first] if first else []) + lines[start + 1: stop]
        body = "\n".join(block).strip()
        if len(body) >= 20:
            blocks.append((label, body))
    return blocks


def run():
    items = [i for i in shenlun_files() if "答题" not in i["file"]]
    papers = pair_papers(items)
    recs = []
    qc = []
    for p in papers:
        try:
            t = ctext(p["path"], "sn")
        except Exception as e:
            qc.append({"file": p["file"], "err": str(e)})
            continue
        material, questions = extract_questions(t)
        ans_text = ""
        if p.get("apath"):
            ans_text = ctext(p["apath"], "sn")
        else:
            ans_text = split_answers(t)
        blocks = answer_blocks(ans_text) if ans_text else []
        paper_id = f"{p['prov']}-{p['year']}-{p['volume']}"
        recs.append({
            "prov": p["prov"], "year": p["year"], "vol": p["volume"],
            "paper_id": paper_id, "file": p["file"],
            "material": material[:14000],
            "questions": [{"no": no, "stem": s, "code": classify_shenlun(s)} for no, s in questions],
            "answer_blocks": [{"no": no, "text": b[:6000]} for no, b in blocks],
            "full_answer": ans_text[:14000],
        })
        qc.append({"file": p["file"], "prov": p["prov"], "year": p["year"], "vol": p["volume"],
                   "nq": len(questions), "nab": len(blocks),
                   "mat": len(material), "ans": len(ans_text),
                   "pair": os.path.basename(p["apath"])[:36] if p.get("apath") else ""})
    # dedupe by (prov, year, vol): keep the record with the most questions
    best = {}
    for r in recs:
        key = (r["prov"], r["year"], r["vol"])
        cur = best.get(key)
        score = (len(r["questions"]), len(r["full_answer"]))
        if cur is None or score > (len(cur["questions"]), len(cur["full_answer"])):
            best[key] = r
    recs = sorted(best.values(), key=lambda r: (r["prov"], r["year"] or 0, r["vol"]))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "shenlun_raw.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    qc.sort(key=lambda r: (r.get("prov", ""), r.get("year") or 0))
    ok = 0
    for r in qc:
        if r.get("nq", 0) >= 2 and r.get("mat", 0) > 500:
            ok += 1
        print(f"{r.get('prov','?')} {r.get('year')} {str(r.get('vol','')):<8} nq={r.get('nq'):<3} nab={r.get('nab'):<3} mat={r.get('mat'):<6} ans={r.get('ans'):<6} {r.get('file','')[:44]}")
    print("papers", len(recs), "usable", ok)
    return recs


if __name__ == "__main__":
    run()
