# -*- coding: utf-8 -*-
"""Survey all PDFs: page count, extractable chars, chinese ratio."""
import json
import os
import re
import sys

import pymupdf

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(ROOT, "pipeline", "survey.json")


def is_chinese(ch):
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF


def survey():
    rows = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if "pipeline" in dirpath or "gongkao-zhenti-knowledge" in dirpath:
            continue
        for fn in filenames:
            if not fn.lower().endswith(".pdf"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT)
            try:
                doc = pymupdf.open(p)
                npages = len(doc)
                probe = [0, npages // 2, max(0, npages - 1)]
                sample = []
                for i in sorted(set(probe)):
                    try:
                        sample.append(doc[i].get_text("text"))
                    except Exception:
                        sample.append("")
                text = "\n".join(sample)
                total_chars = 0
                for i in range(npages):
                    try:
                        total_chars += len(doc[i].get_text("text"))
                    except Exception:
                        pass
                    if total_chars > 20000:
                        break
                cn = sum(1 for c in text if is_chinese(c))
                rows.append(
                    {
                        "rel": rel,
                        "pages": npages,
                        "sample_cn": cn,
                        "approx_chars": total_chars,
                        "size": os.path.getsize(p),
                    }
                )
                doc.close()
            except Exception as e:  # noqa
                rows.append({"rel": rel, "error": str(e), "size": os.path.getsize(p)})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    total = len(rows)
    bad = [r for r in rows if r.get("sample_cn", 0) < 30]
    print(f"total={total} bad_textlayer={len(bad)}")
    for r in bad:
        print("BAD", r.get("pages"), r["rel"])


if __name__ == "__main__":
    survey()
