# -*- coding: utf-8 -*-
"""把「材料 + 设问」粘连的题干切开：材料进 ctx，设问留 stem。

资料分析、篇章阅读的 PDF 里，材料与设问之间没有结构标记，只能靠设问句特征
反推：设问句通常以「下列/以下/能够/关于/20XX年…」开头，以「？」「：」结尾，
长度一般 ≤ 220 字；它之前的内容就是材料。
"""
import re

QUESTION_CUES = re.compile(
    r"(下列|以下|能够|不能|关于|根据|说法|正确|错误|多少|约|几倍|倍|比重|占|增长|下降|"
    r"平均|人均|年均|同比|环比|排序|由高到低|从低到高|饼图|图中|表中|资料|材料|这[段篇]文字|"
    r"作者|主要|意在|填入|依次)"
)
SENT_END = "。？！"


def split_material(stem: str, min_material: int = 90, max_question: int = 260):
    """Return (material, question). 不改动过短的题干。"""
    s = (stem or "").strip()
    if len(s) < min_material + 20:
        return "", s
    # 只在尾部 400 字内找设问句，避免把材料中间的分句误判
    base = max(0, len(s) - 400)
    window = s[base:]
    ends = [m.end() for m in re.finditer(r"[。？！\n]", window)]
    for cut in reversed(ends):
        cand = window[cut:].strip()
        if not cand or len(cand) > max_question:
            continue
        if len(cand) < 6:
            continue
        head = cand[:40]
        if cand.endswith(("？", "：")) or QUESTION_CUES.search(head) or re.match(r"^\d{1,4}\s*年", cand):
            material = s[: base + cut].strip()
            if len(material) >= min_material:
                return material, cand
    return "", s
