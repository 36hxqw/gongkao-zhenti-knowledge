#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据自检：字段完整性、ID 唯一性、考点编码合法性、索引一致性、module↔code 一致性。

退出码：0 全部通过；1 存在问题（会打印明细）。
用法：python scripts/selfcheck.py [-h]
"""
import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

VALID_CODES = {
    "ZL-BASE", "ZL-GROW", "ZL-RATE", "ZL-BILI", "ZL-AVG", "ZL-BEI", "ZL-YEAR", "ZL-PULL", "ZL-COMP",
    "SL-GC", "SL-XC", "SL-LR", "SL-PL", "SL-GL", "SL-RC", "SL-ZZ", "SL-NL", "SL-JH", "SL-RY",
    "SL-NCC", "SL-JT", "SL-SZ", "SL-OT",
    "YY-LJTK", "YY-ZXJL", "YY-XJPD", "YY-BTTR", "YY-YJTR", "YY-XWTD", "YY-YJXH", "YY-YJPX", "YY-PZYD",
    "PD-TX", "PD-DY", "PD-LB", "PD-LJ", "PD-KX", "PD-SJ",
    "CS-ZZ", "CS-JJ", "CS-FL", "CS-LS", "CS-DL", "CS-KJ", "CS-SZ", "CS-SH",
    "SN-DY", "SN-ZH", "SN-DC", "SN-GW", "SN-DZW",
}
# code 前缀 → 模块（v1.8 P0-1：module 与 code 必须自洽，否则 --module 检索会漏题）
CODE_MODULE = {
    "ZL": "资料分析", "SL": "数量关系", "YY": "言语理解",
    "PD": "判断推理", "CS": "常识判断", "SN": "申论",
}
REQUIRED_X = ["id", "prov", "year", "vol", "num", "module", "type", "code", "stem", "opts", "ans", "kw"]
REQUIRED_S = ["id", "prov", "year", "vol", "paper", "module", "type", "code", "stem", "ans", "material", "kw"]

# ---- 解析结论抽取（v1.10）----------------------------------------------------
# 与 pipeline/parse_lib.py 的 `_conclusions()` 同一口径：只认结论句，不认「数字+字母」
# 的段首弱匹配（「4、A 项正确…」不是答案）。段末取最后一条，先截掉「注：/解析二」尾注。
RE_EXPL_CONCL = re.compile(
    r"(?:正确)?答案(?:应)?(?:为|是|选)\s*[:：]?\s*【?\s*([A-D]{1,4})(?![0-9A-Za-z])")
RE_EXPL_SELECT = re.compile(
    r"(?:故|所以|因此|由此(?:可见|可知)?|综上(?:所述)?)[，,]?\s*(?:选择|应选|选)\s*"
    r"([A-D]{1,4})(?![0-9A-Za-z])")
RE_EXPL_TAIL_NOTE = re.compile(
    r"(?:注\s*[：:]|【\s*注\s*】|解析二|解析\s*2\b|支持\s*[A-D]\s*答案理由)")
MISMATCH_LIMIT = 0.01        # 解析结论字母 ≠ ans 的占比上限（回归断言，v1.10）

# ---- sub 与解析自述 一致性抽检（v1.11）---------------------------------------
# 从 expl 抽取「本题考查/考查」后的考点短语（如「数量规律」「两期比重」），
# 按模块映射到 sub 家族；家族不同的条数占比 > 25% 说明题目 sub 标注可能跑偏。
# 只做抽检告警：sub 为「（待细分）/（综合）」或解析无自述的记录不参与判定。
RE_EXPL_KAOCHA = re.compile(
    r"(?:本题考查|考查)(?:的是|了)?[，,]?\s*([^，。；;：:\n]{2,24})")
SUB_EXPL_LIMIT = 0.25
SUB_FAMILY_RULES = {
    "ZL": (
        ("年均增长率", ["年均"]),
        ("平均数", ["平均数", "平均值", "人均"]),
        ("比重", ["比重"]),
        ("倍数", ["倍数", "几倍"]),
        ("增长量", ["增长量", "增量"]),
        ("增长率", ["增长率", "增速", "增幅", "减少率", "降幅", "增长速度"]),
        ("基期量", ["基期"]),
        ("现期量", ["现期量"]),
        ("拉动与贡献", ["拉动", "贡献率", "贡献"]),
    ),
    "SL": (
        ("工程", ["工程", "效率", "工期", "给定时间", "给定人数"]),
        ("行程", ["行程", "路程", "速度", "相遇", "追及", "流水行船", "平均速度",
                 "环形", "往返"]),
        ("利润", ["利润", "折扣", "成本", "售价"]),
        ("概率", ["概率", "摸球", "抽取", "赛制", "比赛"]),
        ("排列组合", ["排列组合", "捆绑", "插空"]),
        ("容斥", ["容斥", "集合"]),
        ("最值", ["最值", "最不利", "构造"]),
        ("年龄", ["年龄"]),
        ("几何", ["几何", "平面", "立体", "相似", "比例"]),
        ("溶液", ["溶液", "浓度", "十字交叉", "倒出", "稀释"]),
        ("牛吃草", ["牛吃草"]),
        ("鸡兔同笼", ["鸡兔同笼"]),
        ("数字推理", ["数字推理", "数列", "多级", "递推", "幂次"]),
        ("和差倍比", ["和差倍比"]),
        ("基础计算", ["基础计算", "方程", "不定方程", "日期", "钟表",
                     "基础应用题", "简单计算"]),
        ("其他", ["其他"]),
    ),
    "YY": (
        ("逻辑填空", ["逻辑填空", "选词填空", "实词", "成语", "虚词", "语境", "词语",
                     "搭配", "近义", "辨析"]),
        ("中心理解", ["中心理解", "中心句", "主旨", "主题词", "意图", "转折", "因果",
                     "对策", "观点", "态度", "指代"]),
        ("细节判断", ["细节"]),
        ("标题填入", ["标题"]),
        ("语句填入", ["语句填入", "语句填空", "句子填空"]),
        ("下文推断", ["下文推断", "接语"]),
        ("语句衔接", ["衔接"]),
        ("语句排序", ["排序", "语序"]),
        ("篇章阅读", ["篇章"]),
    ),
    "PD": (
        ("位置规律", ["位置", "平移", "旋转", "翻转"]),
        ("属性规律", ["属性", "对称", "曲直", "封闭", "开放"]),
        ("样式规律", ["样式", "遍历", "叠加", "加减同异", "运算"]),
        ("数量规律", ["数量类", "点数量", "线数量", "元素", "数数", "笔画", "数量"]),
        ("立体图形", ["立体", "折纸盒", "三视图", "截面", "剖面", "拼合", "空间重构",
                     "六面体", "四面体", "视图"]),
        ("分组分类", ["分组分类"]),
        ("定义判断", ["定义"]),
        ("类比推理", ["类比", "语义", "语法", "对应", "词性", "程度", "比喻", "象征"]),
        ("翻译推理", ["翻译", "充分条件", "必要条件", "逆否", "假言"]),
        ("真假推理", ["真假", "矛盾关系"]),
        ("加强论证", ["加强", "支持"]),
        ("削弱论证", ["削弱", "质疑", "反驳"]),
        ("前提假设", ["前提", "假设"]),
        ("结论推出", ["结论", "推出"]),
        ("解释评价", ["解释", "评价"]),
        ("朴素逻辑", ["朴素", "排列匹配"]),
        ("科学推理", ["物理", "化学", "生物", "科学"]),
        ("事件先后顺序", ["事件", "先后", "顺序"]),
        ("逻辑判断", ["逻辑"]),
    ),
    "CS": (
        ("历史人文", ["历史", "人文", "文学", "文化", "中国史", "世界史",
                     "古代史", "近代史", "现代史"]),
        ("政治", ["政治", "新时代", "理论", "马克思主义", "党史", "毛中特", "哲学",
                 "中国特色社会主义", "时政", "时事", "政策", "会议"]),
        ("法律", ["法律", "宪法", "民法", "刑法", "行政法", "法条", "法理"]),
        ("经济", ["经济", "宏观", "微观", "CPI", "通货膨胀", "市场", "经济学"]),
        ("地理", ["地理", "时区", "国情", "地形", "气候"]),
        ("科技", ["科技", "科学", "生物", "物理", "化学", "医学", "航天", "航空", "技术"]),
        ("管理", ["管理"]),
        ("生活", ["生活", "常识"]),
    ),
    "SN": (
        ("概括", ["概括", "归纳", "总结", "提炼"]),
        ("对策", ["对策", "建议", "措施", "办法"]),
        ("综合分析", ["综合分析", "分析"]),
        ("公文", ["公文", "文书", "应用文"]),
        ("大作文", ["大作文", "议论文", "文章写作"]),
    ),
}


def family_of(text, prefix):
    """文本 → 家族名；同一模块内按规则表顺序取第一个命中。"""
    for fam, kws in SUB_FAMILY_RULES.get(prefix, ()):
        if any(k in text for k in kws):
            return fam
    return None


def sub_family(rec):
    """sub 去掉「（待细分）/（综合）」后缀后映射家族。"""
    core = re.sub(r"[（(].*?[）)]", "", rec.get("sub") or "")
    return family_of(core, (rec.get("code") or "").split("-")[0])


def expl_kaocha(rec):
    """expl 里「本题考查/考查」后的考点短语；没有自述返回 None。"""
    mo = RE_EXPL_KAOCHA.search(rec.get("expl") or "")
    return mo.group(1).strip() if mo else None


def sub_expl_audit(records):
    """返回 (不一致列表, 有自述条数, 可判定条数, 不一致占比)。

    分母只算「解析自述能映射到家族 且 sub 能映射到家族」的题；sub 为
    「（待细分）/（综合）」或解析没有自述的记录不参与判定。
    """
    mism, phrased, judged = [], 0, 0
    for rec in records:
        phrase = expl_kaocha(rec)
        sub = rec.get("sub") or ""
        if not phrase or "待细分" in sub or "综合" in sub:
            continue
        phrased += 1
        sf = sub_family(rec)
        ef = family_of(phrase, (rec.get("code") or "").split("-")[0])
        if sf is None or ef is None:
            continue
        judged += 1
        if sf != ef:
            mism.append((rec["id"], sub, sf, ef))
    ratio = len(mism) / judged if judged else 0.0
    return mism, phrased, judged, ratio


def norm_ans(letters):
    """多选答案归一：去重保序（ACD / A、C、D → ACD）。"""
    out = ""
    for ch in letters or "":
        if ch in "ABCD" and ch not in out:
            out += ch
    return out


def expl_answer(rec):
    """从 expl 取段末结论字母；取不到返回 None。"""
    body = (rec.get("expl") or "").strip()
    if not body:
        return None
    m = RE_EXPL_TAIL_NOTE.search(body)
    if m and m.start() >= 20:
        body = body[:m.start()]
    hits = [(x.start(), norm_ans(x.group(1))) for x in RE_EXPL_CONCL.finditer(body)]
    hits += [(x.start(), norm_ans(x.group(1))) for x in RE_EXPL_SELECT.finditer(body)]
    hits = sorted(h for h in hits if h[1])
    return hits[-1][1] if hits else None


def valid_ans(ans):
    """答案合法：null 或 1~4 个互不重复的 A-D 字母（多选题允许 ABC/ACD/ABCD）。"""
    if ans is None:
        return True
    if not isinstance(ans, str) or not re.fullmatch(r"[A-D]{1,4}", ans):
        return False
    return len(set(ans)) == len(ans)


def load(name):
    path = os.path.join(DATA, name)
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="selfcheck.py",
        description="数据自检：字段完整性、ID 唯一性、考点编码合法性、module↔code 一致性、索引与统计一致性。",
        epilog="退出码：0 全部通过；1 存在问题（会打印明细）。",
    )
    ap.parse_args(argv)          # --help 只打印用法并退出 0，不跑检查

    problems = []
    x = load("xingce.jsonl")
    s = load("shenlun.jsonl")

    ids = set()
    for r in x:
        for k in REQUIRED_X:
            if k not in r:
                problems.append(f"行测缺字段 {k}: {r.get('id')}")
        if r["id"] in ids:
            problems.append(f"重复 ID: {r['id']}")
        ids.add(r["id"])
        if r["code"] not in VALID_CODES:
            problems.append(f"非法考点编码 {r['code']}: {r['id']}")
        if not isinstance(r["opts"], dict):
            problems.append(f"opts 不是对象: {r['id']}")
        if not valid_ans(r["ans"]):
            problems.append(f"答案非法 {r['ans']}: {r['id']}")
        if not r["stem"] and not r.get("fig"):
            problems.append(f"题干为空: {r['id']}")
        if r["year"] and not (2000 <= r["year"] <= 2026):
            problems.append(f"年份异常 {r['year']}: {r['id']}")
        if not isinstance(r.get("diff"), int) or not (1 <= r["diff"] <= 5):
            problems.append(f"难度缺失或越界 {r.get('diff')}: {r['id']}")
        if not r.get("sub"):
            problems.append(f"子考点为空: {r['id']}")

    for r in s:
        for k in REQUIRED_S:
            if k not in r:
                problems.append(f"申论缺字段 {k}: {r.get('id')}")
        if r["id"] in ids:
            problems.append(f"重复 ID: {r['id']}")
        ids.add(r["id"])
        if r["code"] not in VALID_CODES:
            problems.append(f"非法考点编码 {r['code']}: {r['id']}")
        if not r.get("theme"):
            problems.append(f"申论主题为空: {r['id']}")

    # module ↔ code 前缀必须一致（v1.8 P0-1）：否则 --module 检索会漏题、
    # --list-kaodian 会把同一个 code 拆成多行。不一致的 id 全部列出。
    bad_pairs = []
    for r in x + s:
        want = CODE_MODULE.get(r["code"].split("-")[0])
        if want and r["module"] != want:
            bad_pairs.append((r["id"], r["module"], r["code"], want))
    if bad_pairs:
        for rid, mod, code, want in bad_pairs:
            problems.append(f"module 与 code 前缀不一致: {rid}  module={mod}  code={code}（应为 {want}）")

    # 索引一致性
    idx_ids = set()
    with open(os.path.join(DATA, "search-index.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                problems.append(f"索引列数不足: {line[:40]}")
                continue
            idx_ids.add(parts[0])
    missing = ids - idx_ids
    if missing:
        problems.append(f"索引缺少 {len(missing)} 个 ID，例如 {sorted(missing)[:5]}")

    # 统计一致性
    with open(os.path.join(DATA, "stats.json"), encoding="utf-8") as f:
        stats = json.load(f)
    if stats["xingce"]["total"] != len(x):
        problems.append(f"stats 行测题量不一致: {stats['xingce']['total']} vs {len(x)}")
    if stats["shenlun"]["total"] != len(s):
        problems.append(f"stats 申论题量不一致: {stats['shenlun']['total']} vs {len(s)}")

    # 考点文件是否齐备
    kdir = os.path.join(BASE, "references", "kaodian")
    files = os.listdir(kdir) if os.path.isdir(kdir) else []
    codes = {r["code"] for r in x + s}
    for c in sorted(codes):
        if not any(f.startswith(c + "-") for f in files):
            problems.append(f"缺少考点文件: {c}")

    # ---- v1.10 回归断言：解析结论字母 ≠ ans ----
    # v1.9 时全库 387 条（3.4%）的 ans 与解析结论不符：根因是 parse_lib 用
    # RE_NUM_LETTER 抓解析首句「4、A 项正确…」的 A，以及无答案表的卷把「故正确答案
    # 为X」按序号串行赋值。定案（380 条 set_ans）后应只剩个位数；占比 > 1% 说明
    # `ans` 又被弱匹配/串行赋值带偏，直接失败并列出前 20 个 id。
    mism, mism_first = [], []
    for r in x:
        want = expl_answer(r)
        if want and r.get("ans"):
            if want != norm_ans(r["ans"]):
                mism.append((r["id"], r["ans"], want))
                if want[0] != norm_ans(r["ans"])[0]:
                    mism_first.append((r["id"], r["ans"], want))
    mism_ratio = len(mism) / len(x) if x else 0
    print(f"解析结论≠ans {len(mism)} 条（{mism_ratio * 100:.2f}%，上限 {MISMATCH_LIMIT * 100:.0f}%）"
          f"｜其中首字母也不同 {len(mism_first)} 条（多出来的多为多选题 ans 被截成单字母）")
    if mism:
        print("  " + "、".join(f"{i}(ans={a},解析={e})" for i, a, e in mism[:20]))
    if mism_ratio > MISMATCH_LIMIT:
        problems.append(
            "解析结论与 ans 不一致 %d 条（%.2f%% > %.0f%%），前 20 个 id：%s"
            % (len(mism), mism_ratio * 100, MISMATCH_LIMIT * 100,
               "、".join(i for i, _, _ in mism[:20])))

    # ---- v1.11 抽检：解析自述家族 ≠ sub 家族 ----
    sub_mism, sub_phrased, sub_judged, sub_ratio = sub_expl_audit(x)
    print(f"sub_expl_mismatch {len(sub_mism)} 条（{sub_ratio * 100:.2f}%，"
          f"判定 {sub_judged} / 有自述 {sub_phrased}，上限 {SUB_EXPL_LIMIT * 100:.0f}%）")
    if sub_ratio > SUB_EXPL_LIMIT:
        print("  前 20 个 id：" + "、".join(m[0] for m in sub_mism[:20]))
        problems.append(
            "解析自述家族与 sub 家族不一致 %d 条（%.2f%% > %.0f%%），前 20 个 id：%s"
            % (len(sub_mism), sub_ratio * 100, SUB_EXPL_LIMIT * 100,
               "、".join(m[0] for m in sub_mism[:20])))

    # 答案覆盖率（仅供参考，不算失败）
    no_ans = sum(1 for r in x if not r["ans"])
    print(f"行测 {len(x)} 题 / 申论 {len(s)} 题 / 考点文件 {len(files)} 个")
    print(f"答案缺失 {no_ans} 题（{no_ans / len(x) * 100:.1f}%，原因见各题 ans_note 与 docs/coverage.md）")
    print(f"module↔code 不一致 {len(bad_pairs)} 条")

    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("\n✅ 自检通过：字段、ID、考点编码、module↔code、索引、统计、考点文件全部一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
