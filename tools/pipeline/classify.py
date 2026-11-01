# -*- coding: utf-8 -*-
"""考点分类器：严格对齐 gongkao-huasheng13 的模块 / 题型命名。

体系来源：
  资料分析  references/ziliao-fenxi.md  题型 1-9
  数量关系  references/shuliang-guanxi.md 题型 1-12
  言语理解  references/yanyu-lianjie.md   逻辑填空 / 片段阅读 / 语句表达 / 篇章阅读
  判断推理  references/panduan-tuili.md   图形/定义/类比/逻辑判断
  常识判断  references/changshi-panduan.md 八大模块
  申论      references/shenlun.md          单一题/综合分析/对策/公文/大作文
"""
import re

# code -> (模块, 题型, 花生十三对应文件/章节)
TAXONOMY = {
    # ---------------- 资料分析 ----------------
    "ZL-BASE": ("资料分析", "基期量计算", "ziliao-fenxi.md#题型1"),
    "ZL-GROW": ("资料分析", "增长量计算", "ziliao-fenxi.md#题型2"),
    "ZL-RATE": ("资料分析", "增长率计算与比较", "ziliao-fenxi.md#题型3"),
    "ZL-BILI": ("资料分析", "比重计算与比较", "ziliao-fenxi.md#题型4"),
    "ZL-AVG": ("资料分析", "平均数计算", "ziliao-fenxi.md#题型5"),
    "ZL-BEI": ("资料分析", "倍数计算", "ziliao-fenxi.md#题型6"),
    "ZL-YEAR": ("资料分析", "年均增长率", "ziliao-fenxi.md#题型7"),
    "ZL-PULL": ("资料分析", "拉动增长率与贡献率", "ziliao-fenxi.md#题型8"),
    "ZL-COMP": ("资料分析", "综合分析", "ziliao-fenxi.md#题型9"),
    # ---------------- 数量关系 ----------------
    "SL-GC": ("数量关系", "工程问题", "shuliang-guanxi.md#题型1"),
    "SL-XC": ("数量关系", "行程问题", "shuliang-guanxi.md#题型2"),
    "SL-LR": ("数量关系", "利润问题", "shuliang-guanxi.md#题型3"),
    "SL-PL": ("数量关系", "排列组合", "shuliang-guanxi.md#题型4"),
    "SL-GL": ("数量关系", "概率问题", "shuliang-guanxi.md#题型5"),
    "SL-RC": ("数量关系", "容斥问题", "shuliang-guanxi.md#题型6"),
    "SL-ZZ": ("数量关系", "最值问题", "shuliang-guanxi.md#题型7"),
    "SL-NL": ("数量关系", "年龄问题", "shuliang-guanxi.md#题型8"),
    "SL-JH": ("数量关系", "几何问题", "shuliang-guanxi.md#题型9"),
    "SL-RY": ("数量关系", "溶液问题", "shuliang-guanxi.md#题型10"),
    "SL-NCC": ("数量关系", "牛吃草问题", "shuliang-guanxi.md#题型11"),
    "SL-JT": ("数量关系", "鸡兔同笼", "shuliang-guanxi.md#题型12"),
    "SL-SZ": ("数量关系", "数字推理", "体系外补充（旧题型，归入数量关系）"),
    # ---------------- 言语理解 ----------------
    "YY-LJTK": ("言语理解", "逻辑填空", "yanyu-lianjie.md#二"),
    "YY-ZXJL": ("言语理解", "中心理解", "yanyu-lianjie.md#3.1"),
    "YY-XJPD": ("言语理解", "细节判断", "yanyu-lianjie.md#3.2"),
    "YY-BTTR": ("言语理解", "标题填入", "yanyu-lianjie.md#3.3"),
    "YY-YJTR": ("言语理解", "语句填入", "yanyu-lianjie.md#3.4"),
    "YY-XWTD": ("言语理解", "下文推断", "yanyu-lianjie.md#3.5"),
    "YY-YJXH": ("言语理解", "语句衔接", "yanyu-lianjie.md#4.2"),
    "YY-YJPX": ("言语理解", "语句排序", "yanyu-lianjie.md#4.1"),
    "YY-PZYD": ("言语理解", "篇章阅读", "yanyu-lianjie.md#五"),
    # ---------------- 判断推理 ----------------
    "PD-TX": ("判断推理", "图形推理", "panduan-tuili.md#一"),
    "PD-DY": ("判断推理", "定义判断", "panduan-tuili.md#二"),
    "PD-LB": ("判断推理", "类比推理", "panduan-tuili.md#三"),
    "PD-LJ": ("判断推理", "逻辑判断", "panduan-tuili.md#四"),
    "PD-KX": ("判断推理", "科学推理", "体系外补充（广东特色，归入判断推理）"),
    # ---------------- 常识判断 ----------------
    "CS-ZZ": ("常识判断", "政治常识", "changshi-panduan.md#2.1"),
    "CS-JJ": ("常识判断", "经济常识", "changshi-panduan.md#2.2"),
    "CS-FL": ("常识判断", "法律常识", "changshi-panduan.md#2.3"),
    "CS-LS": ("常识判断", "历史人文", "changshi-panduan.md#2.4"),
    "CS-DL": ("常识判断", "地理常识", "changshi-panduan.md#2.5"),
    "CS-KJ": ("常识判断", "科技常识", "changshi-panduan.md#2.6"),
    "CS-SZ": ("常识判断", "时事政治", "changshi-panduan.md#2.7"),
    "CS-SH": ("常识判断", "生活常识", "changshi-panduan.md#2.8"),
    # ---------------- 申论 ----------------
    "SN-DY": ("申论", "单一题（归纳概括）", "shenlun.md#二"),
    "SN-ZH": ("申论", "综合分析题", "shenlun.md#三"),
    "SN-DC": ("申论", "提出对策题", "shenlun.md#四"),
    "SN-GW": ("申论", "公文写作题", "shenlun.md#五"),
    "SN-DZW": ("申论", "大作文", "shenlun.md#六"),
}

SECTION_TO_MODULE = {
    "资料分析": "资料分析",
    "数量关系": "数量关系",
    "言语理解与表达": "言语理解",
    "判断推理": "判断推理",
    "常识判断": "常识判断",
    "政治理论": "常识判断",
    "知觉速度与准确性": "常识判断",
}

# ------------------------------------------------------------------ helpers --
def _any(pat, text):
    return re.search(pat, text or "") is not None


def _opts_len(opts):
    if not opts:
        return 0
    return sum(len(v) for v in opts.values()) / len(opts)


# ------------------------------------------------------------------ 资料分析 --
def classify_ziliao(q):
    stem = q.get("stem") or ""
    opts = q.get("options") or q.get("opts") or {}
    s = stem
    opt_txt = " ".join(opts.values())
    pct_opts = sum(1 for v in opts.values() if "%" in v or "％" in v)
    if _any(r"(说法(正确|错误)|能够(从.*)?推出|不能推出|可以推出|正确的(是|有|个数)|错误的(是|有|个数)|"
            r"符合(资料|材料)|饼图|如下(图|表)|排序(正确|错误)|由高到低|从高到低|排列(正确|错误)|"
            r"说法与资料相符)", s):
        return "ZL-COMP"
    if _any(r"(年均|平均每年|年平均)", s):
        return "ZL-YEAR"
    if _any(r"(拉动|贡献率)", s):
        return "ZL-PULL"
    if _any(r"(占|比重|占比)", s):
        return "ZL-BILI"
    if _any(r"(平均|人均|每亩|亩产|单位面积|每(万|吨|人|户|家|个|台))", s):
        return "ZL-AVG"
    if _any(r"倍", s) or _any(r"倍", opt_txt):
        return "ZL-BEI"
    rate = _any(r"(增长率|增速|增幅|增长速度|涨幅|降幅|上升了|下降了)", s)
    amount = _any(r"(增长量|增加量|净增|增量|增加了|增长了|减少了|下降了|比上年同期多|同比多)", s)
    if rate and not amount:
        return "ZL-RATE"
    if amount and not rate:
        return "ZL-GROW"
    if _any(r"(增长率|增速|增幅)", s):
        return "ZL-RATE"
    if _any(r"(增长量|增加值|增量)", s):
        return "ZL-GROW"
    # 选项全是百分数 / 问上升下降幅度 → 增长率
    if pct_opts >= 3 or _any(r"(比上年同期|同比).{0,12}[：:]?\s*$", s):
        return "ZL-RATE"
    # 问差额（多/少多少 + 单位）→ 增长量比较
    if _any(r"(多|少|高|低)\s*[\d.]+?\s*(亿元|万元|万吨|亿吨|吨|万人|人|个|百分点)", s):
        return "ZL-GROW"
    if _any(r"(上年|去年|前年|基期|同期)", s):
        return "ZL-BASE"
    return "ZL-BASE"


# ------------------------------------------------------------------ 数量关系 --
SL_RULES = [
    ("SL-GC", r"(工程|效率|单独完成|合作|修路|挖渠|注水|完成这项?工作|生产.*天)"),
    ("SL-XC", r"(速度|千米/小时|公里/小时|米/秒|相遇|追上|追及|相向|同向|顺水|逆水|流水|环形|往返|行驶|航行)"),
    ("SL-LR", r"(利润|成本|售价|进价|折扣|打折|定价|毛利|盈利|亏损)"),
    ("SL-PL", r"(排列|组合|多少种|不同的(方法|方式|排法|选法|安排)|站成一排|相邻|不相邻|捆绑|插空)"),
    ("SL-GL", r"(概率|可能性|随机|摸球|抽到|至少.*次)"),
    ("SL-RC", r"(容斥|既.*又|都不|至少有一个|两科|三科|参加.*\d+人)"),
    ("SL-NL", r"(年龄|岁|属相|出生)"),
    ("SL-RY", r"(浓度|溶液|盐水|糖水|酒精|蒸发|稀释|溶质)"),
    ("SL-NCC", r"(牛吃草|草场|牧草|抽水机|漏水|水库.*(放水|抽水))"),
    ("SL-JT", r"(鸡|兔|头.*脚|脚.*头|雉)"),
    ("SL-JH", r"(面积|体积|周长|边长|半径|直径|三角形|正方形|长方形|圆形|圆|正方体|长方体|圆柱|圆锥|角度|平行|垂直|梯形|扇形)"),
    ("SL-ZZ", r"(最多|最少|至少|最大|最小|至多)"),
]


def classify_shuliang(q):
    stem = q.get("stem") or ""
    if q.get("subtype") == "数字推理" or _any(r"(数列|中缺|下一个数|（\s*）\s*$|\(\s*\)\s*$)", stem[:60]):
        if _any(r"(数列|中缺|下一个|（\s*）|\(\s*\))", stem) and not _any(
                r"(工程|行程|利润|浓度|年龄|面积|体积|概率|排列|组合|倍)", stem):
            return "SL-SZ"
    hits = [code for code, pat in SL_RULES if re.search(pat, stem)]
    if not hits:
        return "SL-ZZ"
    # 最值 is a fallback tag: only used when nothing more specific matches
    specific = [h for h in hits if h != "SL-ZZ"]
    return specific[0] if specific else "SL-ZZ"


# ------------------------------------------------------------------ 言语理解 --
def classify_yanyu(q):
    stem = q.get("stem") or ""
    opts = q.get("options") or {}
    long_opt = _opts_len(opts) > 22
    if _any(r"(重新排列|语序|顺序最(合理|恰当)|排列组合最连贯|排序)", stem):
        return "YY-YJPX"
    if _any(r"(接下来|下文|后文|下一段)", stem):
        return "YY-XWTD"
    if _any(r"标题", stem):
        return "YY-BTTR"
    if _any(r"(与原文(相符|不符)|符合文意|不符合文意|可以推出|不能推出|理解(正确|错误)|分析(正确|错误))", stem):
        return "YY-XJPD"
    if _any(r"(填入|划横线|横线部分|画横线)", stem) and not long_opt:
        return "YY-LJTK"
    if long_opt and _any(r"(填入|横线)", stem):
        return "YY-YJTR"
    if _any(r"(这段文字|文段|这段|作者|主要|意在|主旨|中心|强调|概括|复述|观点)", stem):
        return "YY-ZXJL"
    if re.search(r"[_＿]{2,}|（\s*）|\(\s*\)", stem) and not long_opt:
        return "YY-LJTK"
    if long_opt:
        return "YY-ZXJL"
    return "YY-LJTK"


# ------------------------------------------------------------------ 判断推理 --
LB_SHORT = 34


def classify_panduan(q):
    stem = q.get("stem") or ""
    opts = q.get("options") or {}
    if q.get("need_figure") or not opts or _any(
            r"(图形|问号处|所给四个选项|立体|截面|三视图|折纸盒|拼合|展开图|规律性)", stem):
        return "PD-TX"
    if _any(r"(根据上述定义|上述定义|定义，下列|符合.*定义|不属于.*定义)", stem):
        return "PD-DY"
    if _any(r"(削弱|加强|支持|质疑|反驳|前提|假设|解释|论证|结论|推出)", stem):
        return "PD-LJ"
    if len(stem) <= LB_SHORT and _any(r"[：:]", stem) and opts and _opts_len(opts) <= 16:
        return "PD-LB"
    if _any(r"(如果|只有|除非|那么|则|必然|可能|所有|有些)", stem) and opts and _opts_len(opts) <= 20:
        return "PD-LJ"
    if _any(r"(科学|物理|化学|生物|电路|重力|光的|力学|细胞|元素|遗传)", stem) and q.get("section") == "判断推理":
        return "PD-KX"
    if opts and _opts_len(opts) <= 16 and len(stem) <= LB_SHORT:
        return "PD-LB"
    return "PD-LJ"


# ------------------------------------------------------------------ 常识判断 --
CS_RULES = [
    ("CS-FL", r"(宪法|民法典|刑法|行政法|诉讼|法律|条例|规定|判|罪|权利|义务|合同|赔偿|起诉|监察|立法)"),
    ("CS-JJ", r"(经济|GDP|通货|货币|财政|税收|市场|价格|供求|利率|汇率|产业|投资|消费)"),
    ("CS-LS", r"(历史|朝代|古代|唐朝|宋朝|明清|诗人|诗句|文学|小说|名著|成语|典籍|书法|绘画|传统|节日|文化)"),
    ("CS-DL", r"(地理|气候|地形|山脉|河流|湖泊|海洋|洲|国家|首都|经纬|盆地|高原|季风)"),
    ("CS-KJ", r"(科技|航天|卫星|量子|芯片|5G|人工智能|核|基因|细胞|物理|化学|生物|能源|材料)"),
    ("CS-SZ", r"(二十大|三中全会|习近平|总书记|政府工作报告|会议|规划|战略|政策|十四五|新质生产力)"),
    ("CS-ZZ", r"(马克思|哲学|唯物|辩证法|矛盾|认识论|党史|党的|社会主义|中国特色|政治)"),
    ("CS-SH", r"(生活|饮食|健康|安全|交通|消防|急救|食品)"),
]


def classify_changshi(q):
    stem = q.get("stem") or ""
    if q.get("section") == "政治理论":
        return "CS-ZZ"
    for code, pat in CS_RULES:
        if re.search(pat, stem):
            return code
    return "CS-ZZ"


# ------------------------------------------------------------------- 申论 ----
def classify_shenlun(stem):
    s = stem or ""
    if _any(r"(大作文|议论文|文章|自拟标题|写一篇|字数.*1000|联系实际)", s):
        return "SN-DZW"
    if _any(r"(公文|通知|倡议书|讲话稿|工作方案|汇报|建议书|公开信|短评|编者按|函|报告|宣传稿)", s):
        return "SN-GW"
    if _any(r"(提出.*对策|对策建议|如何解决|措施|建议)", s):
        return "SN-DC"
    if _any(r"(谈谈.*理解|谈谈.*看法|分析|评析|比较|启示|含义|解释)", s):
        return "SN-ZH"
    return "SN-DY"


# ------------------------------------------------------------------ public ---
def _get(q, *names, default=None):
    for n in names:
        if n in q and q[n] not in (None, ""):
            return q[n]
    return default


def classify(q):
    """Return dict(code, module, type, ref).

    Accepts either the internal record keys (sec/sub/opts) or the public ones
    (section/subtype/options).
    """
    sec = _get(q, "section", "sec")
    stem = _get(q, "stem", default="") or ""
    q = dict(q)
    q["section"] = sec
    q["subtype"] = _get(q, "subtype", "sub")
    q["options"] = _get(q, "options", "opts", default={}) or {}
    q["need_figure"] = _get(q, "need_figure", default=False)
    module = SECTION_TO_MODULE.get(sec)
    if module is None:
        # infer from section name fragments
        if _any(r"资料", sec or ""):
            module = "资料分析"
        elif _any(r"数量|数学", sec or ""):
            module = "数量关系"
        elif _any(r"言语|阅读", sec or ""):
            module = "言语理解"
        elif _any(r"判断|推理", sec or ""):
            module = "判断推理"
        elif _any(r"常识|政治", sec or ""):
            module = "常识判断"
        elif _any(r"申论", sec or ""):
            module = "申论"
    if module is None:
        # content-based fallback
        if _any(r"(图形|问号处)", stem):
            module = "判断推理"
        elif _any(r"(根据上述定义|定义，下列)", stem):
            module = "判断推理"
        elif _any(r"(填入|横线|这段文字|主要|意在|主旨)", stem):
            module = "言语理解"
        elif _any(r"(比重|增长率|同比|年均|占.*%)", stem):
            module = "资料分析"
        elif _any(r"(工程|行程|利润|排列|概率|容斥|浓度)", stem):
            module = "数量关系"
        else:
            module = "常识判断"
    if module == "资料分析":
        code = classify_ziliao(q)
    elif module == "数量关系":
        code = classify_shuliang(q)
    elif module == "言语理解":
        code = classify_yanyu(q)
    elif module == "判断推理":
        code = classify_panduan(q)
    elif module == "常识判断":
        code = classify_changshi(q)
    else:
        code = classify_shenlun(stem)
    mod, typ, ref = TAXONOMY[code]
    return {"code": code, "module": mod, "type": typ, "ref": ref}
