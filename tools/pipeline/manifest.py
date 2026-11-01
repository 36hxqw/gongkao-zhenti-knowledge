# -*- coding: utf-8 -*-
"""Paper manifest v2: difflib pairing + skip flags from the text-layer survey."""
import os
import re
import json
import difflib

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GD_BASE = os.path.join(ROOT, r"广东公务员考试真题pdf版")
HB_BASE = os.path.join(ROOT, r"湖北公务员考试真题pdf版")

RE_YEAR = re.compile(r"(20\d{2}|19\d{2})")

VOLUME_KEYS = [
    (r"行政执法|执法类|执法卷", "行政执法"),
    (r"副省级|副省", "副省级"),
    (r"省级|省部级", "省级"),
    (r"省市", "省市"),
    (r"地市级|地市|市地", "地市级"),
    (r"县镇", "县镇"),
    (r"县乡", "县乡"),
    (r"乡镇级|乡镇", "乡镇"),
    (r"县级", "县级"),
    (r"通用", "通用"),
    (r"公安", "公安"),
    (r"A卷", "A卷"),
    (r"B卷", "B卷"),
    (r"一卷", "一卷"),
    (r"二卷", "二卷"),
    (r"三卷", "三卷"),
    (r"思维能力", "思维能力测验"),
    (r"综合行政", "综合行政能力测验"),
    (r"选调", "选调"),
]


def year_of(name):
    m = RE_YEAR.search(name)
    return int(m.group(1)) if m else None


def volume_of(name):
    if "统一卷" in name:
        return "统一卷"
    for pat, val in VOLUME_KEYS:
        if re.search(pat, name):
            return val
    return "统一卷"


def series_of(name):
    """Normalized comparable title: drop doc-type words and punctuation."""
    n = name
    n = re.sub(r"\.pdf$", "", n, flags=re.I)
    n = re.sub(r"\(1\)|（1）", "", n)
    for w in ("参考答案及解析", "答案及解析", "答案与解析", "答案+解析", "答案解析",
              "参考答案", "答案及", "解析", "答案", "真题", "试题", "题卷", "题",
              "《行测》", "行测", "公务员录用考试", "公务员考试", "录用考试", "考试"):
        n = n.replace(w, "")
    n = re.sub(r"[《》（）()\s\-—–_\.、,，]", "", n)
    return n


def load_bad():
    with open(os.path.join(ROOT, "pipeline", "survey.json"), encoding="utf-8") as f:
        rows = json.load(f)
    return {r["rel"] for r in rows if r.get("sample_cn", 0) < 30}


def build():
    bad = load_bad()
    groups = {
        "国考": (os.path.join(ROOT, r"国考2000-2026真题pdf\2000-2026国考行测PDF\行测-真题"),
                os.path.join(ROOT, r"国考2000-2026真题pdf\2000-2026国考行测PDF\行测-答案及解析")),
        "广东": (os.path.join(GD_BASE, r"广东公务员考试真题——行测04-26pdf版\题目"),
                os.path.join(GD_BASE, r"广东公务员考试真题——行测04-26pdf版\答案及解析")),
        "湖北": (os.path.join(HB_BASE, r"湖北公务员考试真题——行测08-26PDF版\题目"),
                os.path.join(HB_BASE, r"湖北公务员考试真题——行测08-26PDF版\答案及解析")),
    }
    papers = []
    for prov, (qdir, adir) in groups.items():
        ans_files = [f for f in os.listdir(adir) if f.lower().endswith(".pdf")
                     and re.search(r"答案|解析", f)]
        ans_keys = {f: (year_of(f), series_of(f)) for f in ans_files}
        for f in sorted(os.listdir(qdir)):
            if not f.lower().endswith(".pdf"):
                continue
            if re.search(r"答题卡|申论", f):
                continue
            qp = os.path.join(qdir, f)
            rel = os.path.relpath(qp, ROOT)
            y, vol = year_of(f), volume_of(f)
            if vol == "统一卷" and "统一卷" in f:
                vol = "统一卷"
            skip = rel in bad
            cands = []
            for af, (ay, akey) in ans_keys.items():
                if ay != y:
                    continue
                score = difflib.SequenceMatcher(None, series_of(f), akey).ratio()
                cands.append((score, af))
            cands.sort(reverse=True)
            apath, ascore = (None, 0.0)
            if cands and cands[0][0] >= 0.55:
                apath, ascore = os.path.join(adir, cands[0][1]), cands[0][0]
            ans_bad = apath is not None and os.path.relpath(apath, ROOT) in bad
            papers.append({
                "prov": prov, "year": y, "volume": vol,
                "file": f, "qpath": qp, "apath": apath,
                "skip": skip, "ans_bad": ans_bad, "pair_score": round(ascore, 3),
            })
    papers.sort(key=lambda p: (p["prov"], p["year"] or 0, p["volume"], p["file"]))
    return papers


if __name__ == "__main__":
    ps = build()
    ok = [p for p in ps if not p["skip"]]
    print(f"papers={len(ps)} usable={len(ok)} with_good_answer="
          f"{sum(1 for p in ok if p['apath'] and not p['ans_bad'])}")
    for p in ps:
        flag = "SKIP" if p["skip"] else ("NOANS" if not p["apath"] or p["ans_bad"] else "ok   ")
        print(f"{flag} s={p['pair_score']:.2f} {p['prov']} {p['year']} {p['volume']:<10} {p['file'][:40]:<42} -> {os.path.basename(p['apath'])[:38] if p['apath'] else '-'}")
    with open(os.path.join(ROOT, "pipeline", "manifest_xingce.json"), "w", encoding="utf-8") as f:
        json.dump(ps, f, ensure_ascii=False, indent=1)
