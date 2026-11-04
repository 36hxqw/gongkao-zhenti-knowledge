# -*- coding: utf-8 -*-
"""Finalize the knowledge base: ids, classification, keywords, stats, markdown."""
import collections
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import classify, TAXONOMY  # noqa: E402

ROOT = os.environ.get("ZHENTI_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(ROOT, "pipeline", "out")
REPO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROV_CODE = {"国考": "GK", "广东": "GD", "湖北": "HB"}
VOL_CODE = {
    "副省级": "fs", "地市级": "ds", "行政执法": "zf", "省级": "sj", "统一卷": "ty",
    "县级": "xj", "乡镇": "xz", "县镇": "xz", "县乡": "xx", "省市": "ss", "通用": "ty2",
    "A卷": "a", "B卷": "b", "一卷": "1", "二卷": "2", "三卷": "3",
    "选调": "xd", "思维能力测验": "sw", "综合行政能力测验": "zh", "公安": "ga",
}
MODULE_ORDER = ["资料分析", "数量关系", "言语理解", "判断推理", "常识判断", "申论"]

# A compact domain lexicon used to describe each question with searchable tags.
DOMAIN_LEXICON = """
基期 现期 增长量 增长率 增速 增幅 比重 占比 平均数 人均 倍数 年均 拉动 贡献率 综合分析
同比 环比 百分点 翻番 顺差 逆差 中位数 众数 指数
工程 行程 利润 排列组合 概率 容斥 最值 年龄 几何 溶液 牛吃草 鸡兔同笼 数字推理
等差数列 等比数列 递推 幂次数列 多级数列 分数数列 图形数阵
逻辑填空 实词 成语 语境 搭配 感情色彩 中心理解 主旨 细节判断 标题填入 语句排序
语句衔接 下文推断 篇章阅读 转折 因果 递进 并列 对策 观点
图形推理 位置规律 样式规律 数量规律 属性规律 对称性 一笔画 封闭面 曲直 分组分类
立体图形 折纸盒 截面图 三视图 定义判断 单定义 多定义 类比推理 语义关系 逻辑关系
对应关系 语法关系 翻译推理 真假推理 加强削弱 前提假设 解释评价 归纳推导 充分条件
必要条件 逆否 矛盾关系 反对关系 论证结构
政治常识 马克思主义 唯物辩证法 认识论 党史 党的二十大 二十届三中全会 政府工作报告
新质生产力 中国式现代化 全过程人民民主 共同富裕 高质量发展 乡村振兴 生态文明 双碳
碳中和 一带一路 人类命运共同体 放管服 营商环境 基层治理 社会治理 公共服务 数字政府
法治政府 民法典 宪法 刑法 行政法 行政处罚 行政复议 行政诉讼 刑事诉讼 民事诉讼法
正当防卫 紧急避险 善意取得 物权 合同 侵权 继承 婚姻 劳动法 行政处罚法 国家赔偿
经济常识 财政政策 货币政策 通货膨胀 通货紧缩 GDP CPI PPI 恩格尔系数 基尼系数
供求关系 机会成本 边际效用 规模经济 市场经济 宏观调控 供给侧 需求侧 转移支付
历史人文 朝代 先秦 秦汉 唐宋 元明清 诗经 楚辞 唐诗 宋词 四大名著 史记 资治通鉴
诸子百家 儒家 道家 法家 科举 二十四节气 传统节日 甲骨文 书法 京剧 中医
地理常识 气候 季风 地形 高原 盆地 平原 丘陵 山脉 河流 湖泊 长江 黄河 珠三角
粤港澳大湾区 长三角 京津冀 世界地理 大洲 洋流 板块
科技常识 航天 载人航天 嫦娥 天问 北斗 量子 芯片 半导体 5G 人工智能 大数据 云计算
区块链 新能源 光伏 核电 特高压 基因 疫苗 细胞 病毒 物理 化学 生物 材料 超导
时政 中央经济工作会议 两会 十四五 十五五 规划 改革 开放 自贸区 自贸港 城市更新
粮食安全 就业 教育 医疗 养老 住房 生育 人口老龄化 消费 投资 出口 产业链 供应链
科技自立自强 人才强国 文化自信 中华优秀传统文化 非遗 文旅融合 网络治理 数据安全
""".split()


def load_raw(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def clean(s, limit=None):
    s = re.sub(r"[ \t]+", " ", (s or "")).strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    if limit:
        s = s[:limit]
    return s


def make_id(prov, year, vol, num, kind="X"):
    return f"{PROV_CODE.get(prov, 'XX')}-{year}-{VOL_CODE.get(vol, 'ty')}-{kind}{num:03d}"


def kw_of(text, vocab):
    text = text or ""
    hits = [w for w in vocab if w in text]
    # dedupe, keep shorter-first for precision
    seen, out = set(), []
    for w in hits:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:12]


def build_vocab(recs):
    """Domain lexicon + frequent bigrams (data-driven补词)."""
    vocab = list(dict.fromkeys(DOMAIN_LEXICON))
    cnt = collections.Counter()
    for r in recs:
        t = (r.get("stem") or "") + (r.get("ctx") or "") + " ".join((r.get("opts") or {}).values())
        for i in range(len(t) - 1):
            a, b = t[i], t[i + 1]
            if "\u4e00" <= a <= "\u9fff" and "\u4e00" <= b <= "\u9fff":
                cnt[a + b] += 1
    STOP = set("的是在了和与及或等我们你们他们这个那个可以以下下列关于根据进行通过以及不是没有为一二三四五")
    extra = [w for w, c in cnt.most_common(4000)
             if c >= 40 and w not in vocab and not any(ch in STOP for ch in w)]
    vocab = vocab + extra[:1200]
    return vocab


def stat_block(recs):
    years = sorted({r["year"] for r in recs if r["year"]})
    by_year = collections.Counter(r["year"] for r in recs)
    by_prov = collections.Counter(r["prov"] for r in recs)
    by_mod = collections.Counter(r["module"] for r in recs)
    by_code = collections.Counter(r["code"] for r in recs)
    return {
        "total": len(recs),
        "years": [min(years), max(years)] if years else [],
        "papers": len({(r["prov"], r["year"], r["vol"]) for r in recs}),
        "by_year": dict(sorted(by_year.items())),
        "by_prov": dict(by_prov),
        "by_module": dict(by_mod),
        "by_code": dict(by_code.most_common()),
    }


def main():
    raw_x = load_raw("xingce_raw.jsonl")
    raw_s = load_raw("shenlun_raw.jsonl")
    vocab = build_vocab(raw_x)

    # ---------------- 行测 ----------------
    seen = set()
    x = []
    for r in raw_x:
        cls = classify(r)
        rec_id = make_id(r["prov"], r["year"], r["vol"], r["num"])
        if rec_id in seen:
            continue
        seen.add(rec_id)
        stem = clean(r["stem"])
        fig = bool(r.get("need_figure"))
        if not stem:
            stem = "（本题题干为图形/公式，文字层无题干，图见原卷）"
            fig = True
        opts = {k: clean(v) for k, v in (r["opts"] or {}).items()}
        expl = clean(r["expl"])
        ctx = clean(r["ctx"])
        rec = {
            "id": rec_id, "prov": r["prov"], "year": r["year"], "vol": r["vol"],
            "num": r["num"], "module": cls["module"], "type": cls["type"],
            "code": cls["code"], "stem": stem, "opts": opts,
            "ans": r["ans"], "expl": expl, "ctx": ctx,
            # v1.10：答案来源（table=答案表 / inferred=页内标记或解析结论）
            "ans_source": r.get("ans_source") or "inferred",
            "kw": kw_of(stem + " ".join(opts.values()) + ctx[:400], vocab),
            "fig": fig,
            "src": f"{r['qfile']}|{r['afile'] or ''}",
        }
        x.append(rec)
    x.sort(key=lambda r: (r["prov"], r["year"], r["vol"], r["num"]))

    # ---------------- 申论 ----------------
    s = []
    for p in raw_s:
        for i, q in enumerate(p["questions"], 1):
            qid = f"{PROV_CODE.get(p['prov'],'XX')}-{p['year']}-{VOL_CODE.get(p['vol'],'ty')}-S{i:02d}"
            code = q.get("code") or classify({"stem": q["stem"], "sec": "申论"})["code"]
            mod, typ, _ = TAXONOMY[code]
            ans = ""
            for b in p["answer_blocks"]:
                if str(b["no"]) == str(q["no"]) or b["no"] in (q["no"], str(i)):
                    ans = b["text"]
                    break
            if not ans and len(p["answer_blocks"]) == len(p["questions"]):
                ans = p["answer_blocks"][i - 1]["text"]
            s.append({
                "id": qid, "prov": p["prov"], "year": p["year"], "vol": p["vol"],
                "paper": p["paper_id"], "no": q["no"], "module": mod, "type": typ, "code": code,
                "stem": clean(q["stem"]), "ans": clean(ans, 6000),
                "material": clean(p["material"], 14000),
                "kw": kw_of(q["stem"] + p["material"][:600], vocab),
                "src": p["file"],
            })
    s.sort(key=lambda r: (r["prov"], r["year"], r["vol"], r["id"]))

    os.makedirs(os.path.join(REPO, "data"), exist_ok=True)
    with open(os.path.join(REPO, "data", "xingce.jsonl"), "w", encoding="utf-8") as f:
        for r in x:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(REPO, "data", "shenlun.jsonl"), "w", encoding="utf-8") as f:
        for r in s:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = {
        "xingce": stat_block(x),
        "shenlun": stat_block(s),
        "papers": len({(r["prov"], r["year"], r["vol"]) for r in x}),
        "shenlun_papers": len({r["paper"] for r in s}),
        "generated_from": "%d 套行测卷 / %d 套申论卷" % (
            len({(r["prov"], r["year"], r["vol"]) for r in x}), len({r["paper"] for r in s})),
    }
    with open(os.path.join(REPO, "data", "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    # ---------------- compact search index ----------------
    with open(os.path.join(REPO, "data", "search-index.tsv"), "w", encoding="utf-8") as f:
        f.write("#id\tyear\tprov\tvol\tmodule\ttype\tkw\tstem60\n")
        for r in x:
            f.write("\t".join([
                r["id"], str(r["year"]), r["prov"], r["vol"], r["module"], r["type"],
                " ".join(r["kw"][:8]), r["stem"][:60].replace("\t", " ").replace("\n", " "),
            ]) + "\n")
        for r in s:
            f.write("\t".join([
                r["id"], str(r["year"]), r["prov"], r["vol"], r["module"], r["type"],
                " ".join(r["kw"][:8]), r["stem"][:60].replace("\t", " ").replace("\n", " "),
            ]) + "\n")
    print("xingce", len(x), "shenlun", len(s))
    print(json.dumps(stats["xingce"]["by_module"], ensure_ascii=False))
    print(json.dumps(stats["shenlun"]["by_module"], ensure_ascii=False))
    return x, s, stats


if __name__ == "__main__":
    main()
