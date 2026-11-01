# -*- coding: utf-8 -*-
"""Extract + parse every 行测 paper; emit raw jsonl + QC table."""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textlib import doc_text  # noqa: E402
from parse_lib import parse_paper_text, parse_answers  # noqa: E402
import manifest  # noqa: E402

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "pipeline", "cache")
OUT = os.path.join(ROOT, "pipeline", "out")


def cached_text(path, tag):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1((tag + path).encode("utf-8")).hexdigest()[:16]
    cf = os.path.join(CACHE, key + ".txt")
    if os.path.exists(cf):
        with open(cf, encoding="utf-8") as f:
            return f.read()
    txt = doc_text(path)
    with open(cf, "w", encoding="utf-8") as f:
        f.write(txt)
    return txt


def run():
    os.makedirs(OUT, exist_ok=True)
    papers = manifest.build()
    recs = []
    qc = []
    for p in papers:
        if p["skip"]:
            qc.append({**{k: p[k] for k in ("prov", "year", "volume", "file")},
                       "status": "skip_no_textlayer", "n": 0})
            continue
        qtext = cached_text(p["qpath"], "q")
        qs, _ = parse_paper_text(qtext)
        answers = {}
        if p["apath"] and not p["ans_bad"]:
            atext = cached_text(p["apath"], "a")
            answers = parse_answers(atext)
        got = 0
        for q in qs:
            a = answers.get(q["num"], {})
            ans = a.get("ans")
            if ans:
                got += 1
            rec = {
                "prov": p["prov"], "year": p["year"], "vol": p["volume"],
                "num": q["num"], "sec": q["section"], "sub": q["subtype"],
                "ctx": q["context"], "stem": q["stem"],
                "opts": q["options"], "ans": ans,
                "expl": (a.get("expl") or "")[:4000],
                "qfile": p["file"], "afile": os.path.basename(p["apath"]) if p["apath"] else None,
                "num_found": q["num_found"],
            }
            recs.append(rec)
        n = len(qs)
        nums = [q["num"] for q in qs]
        gaps = 0
        if nums:
            gaps = (max(nums) - min(nums) + 1) - len(set(nums))
        four = sum(1 for q in qs if len(q["options"]) == 4)
        qc.append({
            "prov": p["prov"], "year": p["year"], "volume": p["volume"], "file": p["file"][:44],
            "status": "ok", "n": n, "maxnum": max(nums) if nums else 0,
            "four": round(four / n, 3) if n else 0,
            "ans": got, "ans_rate": round(got / n, 3) if n else 0,
            "gaps": gaps,
            "has_answer_file": bool(p["apath"]) and not p["ans_bad"],
        })
    with open(os.path.join(OUT, "xingce_raw.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    qc.sort(key=lambda r: (r["prov"], r["year"] or 0))
    with open(os.path.join(OUT, "qc_xingce.csv"), "w", encoding="utf-8-sig") as f:
        cols = ["prov", "year", "volume", "status", "n", "maxnum", "four", "ans", "ans_rate", "gaps", "has_answer_file", "file"]
        f.write(",".join(cols) + "\n")
        for r in qc:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print(f"records={len(recs)}")
    for r in qc:
        print(f"{r['prov']} {r['year']} {r.get('volume',''):<8} n={r.get('n',0):<4} four={r.get('four',0):<5} ans={r.get('ans',0):<4} {r['status']} {r['file']}")
    return recs, qc


if __name__ == "__main__":
    run()
