# 考点体系（完全对齐 gongkao-huasheng13）

本表是本库唯一的考点字典：题目标注、检索键、`references/kaodian/` 文件名均由此表派生。

**对齐原则**

1. 模块名、题型名、子题型名一律沿用 `gongkao-huasheng13` 的表述，不改写、不合并、不新增二级体系。
2. 体系未单列的旧题型（数字推理、科学推理）只做「模块级对齐 + 显式标注」，在表中标记为「体系外补充」。
3. 一个考点 = 一个 `code`；`code` 只用于检索与文件命名，展示时始终用中文题型名。

**编码规则**：`模块前缀-题型缩写`。ZL=资料分析，SL=数量关系，YY=言语理解，PD=判断推理，CS=常识判断，SN=申论。

**总题量**：11812 题（行测 11393 + 申论 419）；**三级子考点**：193 个标签（其中 46 个是题型兜底项，其余为可精确检索的细粒度子考点）

## 资料分析

花生十三对应文件：`references/ziliao-fenxi.md`、`ziliao-susuan.md`、`ziliao-zonghe.md`

| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |
|---|---|---:|---|---|
| `ZL-BASE` | 基期量计算 | 490 | 2000–2026 | ziliao-fenxi.md#题型1 |
| `ZL-GROW` | 增长量计算 | 86 | 2000–2026 | ziliao-fenxi.md#题型2 |
| `ZL-RATE` | 增长率计算与比较 | 230 | 2000–2026 | ziliao-fenxi.md#题型3 |
| `ZL-BILI` | 比重计算与比较 | 268 | 2000–2026 | ziliao-fenxi.md#题型4 |
| `ZL-AVG` | 平均数计算 | 181 | 2001–2026 | ziliao-fenxi.md#题型5 |
| `ZL-BEI` | 倍数计算 | 70 | 2000–2026 | ziliao-fenxi.md#题型6 |
| `ZL-YEAR` | 年均增长率 | 42 | 2001–2026 | ziliao-fenxi.md#题型7 |
| `ZL-PULL` | 拉动增长率与贡献率 | 0 | — | ziliao-fenxi.md#题型8 |
| `ZL-COMP` | 综合分析 | 319 | 2003–2026 | ziliao-fenxi.md#题型9 |

#### 三级子考点
)
            lines.append("| 题型 | 子考点 | 题量 |")
            lines.append("|---|---|---:|")
            for c in codes:
                subs = SUB_TAXONOMY.get(c, [])
                if len(subs) <= 1:
                    continue
                for name, _pat in subs:
                    n = subcnt.get((c, name), 0)
                    lines.append(f"| {TAXONOMY[c][1]} | {name} | {n} |")
            lines.append(
> 本库未命中的题型（存量真题中未出现或抽取失败）：`ZL-PULL`

## 数量关系

花生十三对应文件：`references/shuliang-guanxi.md`、`shuliang-gongshi.md`

| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |
|---|---|---:|---|---|
| `SL-GC` | 工程问题 | 58 | 2002–2026 | shuliang-guanxi.md#题型1 |
| `SL-XC` | 行程问题 | 100 | 2000–2026 | shuliang-guanxi.md#题型2 |
| `SL-LR` | 利润问题 | 57 | 2000–2026 | shuliang-guanxi.md#题型3 |
| `SL-PL` | 排列组合 | 64 | 2004–2026 | shuliang-guanxi.md#题型4 |
| `SL-GL` | 概率问题 | 59 | 2009–2026 | shuliang-guanxi.md#题型5 |
| `SL-RC` | 容斥问题 | 31 | 2005–2025 | shuliang-guanxi.md#题型6 |
| `SL-ZZ` | 最值问题 | 116 | 2000–2026 | shuliang-guanxi.md#题型7 |
| `SL-NL` | 年龄问题 | 36 | 2000–2026 | shuliang-guanxi.md#题型8 |
| `SL-JH` | 几何问题 | 106 | 2002–2026 | shuliang-guanxi.md#题型9 |
| `SL-RY` | 溶液问题 | 10 | 2005–2024 | shuliang-guanxi.md#题型10 |
| `SL-NCC` | 牛吃草问题 | 2 | 2006–2009 | shuliang-guanxi.md#题型11 |
| `SL-JT` | 鸡兔同笼 | 3 | 2005–2019 | shuliang-guanxi.md#题型12 |
| `SL-SZ` | 数字推理 | 290 | 2000–2026 | 体系外补充（旧题型，归入数量关系） |
| `SL-OT` | 其他数量关系 | 424 | 2000–2026 | 体系外补充（方程/和差倍比/基础计算，归入数量关系） |

#### 三级子考点
)
            lines.append("| 题型 | 子考点 | 题量 |")
            lines.append("|---|---|---:|")
            for c in codes:
                subs = SUB_TAXONOMY.get(c, [])
                if len(subs) <= 1:
                    continue
                for name, _pat in subs:
                    n = subcnt.get((c, name), 0)
                    lines.append(f"| {TAXONOMY[c][1]} | {name} | {n} |")
            lines.append(
## 言语理解

花生十三对应文件：`references/yanyu-lianjie.md`、`yanyu-ciyu.md`、`yanyu-zhuanxiang.md`

| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |
|---|---|---:|---|---|
| `YY-LJTK` | 逻辑填空 | 1468 | 2001–2026 | yanyu-lianjie.md#二 |
| `YY-ZXJL` | 中心理解 | 1039 | 2000–2026 | yanyu-lianjie.md#3.1 |
| `YY-XJPD` | 细节判断 | 69 | 2000–2026 | yanyu-lianjie.md#3.2 |
| `YY-BTTR` | 标题填入 | 73 | 2003–2026 | yanyu-lianjie.md#3.3 |
| `YY-YJTR` | 语句填入 | 18 | 2003–2026 | yanyu-lianjie.md#3.4 |
| `YY-XWTD` | 下文推断 | 62 | 2007–2026 | yanyu-lianjie.md#3.5 |
| `YY-YJXH` | 语句衔接 | 0 | — | yanyu-lianjie.md#4.2 |
| `YY-YJPX` | 语句排序 | 108 | 2002–2026 | yanyu-lianjie.md#4.1 |
| `YY-PZYD` | 篇章阅读 | 0 | — | yanyu-lianjie.md#五 |

#### 三级子考点
)
            lines.append("| 题型 | 子考点 | 题量 |")
            lines.append("|---|---|---:|")
            for c in codes:
                subs = SUB_TAXONOMY.get(c, [])
                if len(subs) <= 1:
                    continue
                for name, _pat in subs:
                    n = subcnt.get((c, name), 0)
                    lines.append(f"| {TAXONOMY[c][1]} | {name} | {n} |")
            lines.append(
> 本库未命中的题型（存量真题中未出现或抽取失败）：`YY-YJXH`、`YY-PZYD`

## 判断推理

花生十三对应文件：`references/panduan-tuili.md`、`panduan-guilv.md`、`panduan-tuxing.md`

| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |
|---|---|---:|---|---|
| `PD-TX` | 图形推理 | 835 | 2000–2026 | panduan-tuili.md#一 |
| `PD-DY` | 定义判断 | 471 | 2004–2026 | panduan-tuili.md#二 |
| `PD-LB` | 类比推理 | 705 | 2006–2026 | panduan-tuili.md#三 |
| `PD-LJ` | 逻辑判断 | 1253 | 2000–2026 | panduan-tuili.md#四 |
| `PD-KX` | 科学推理 | 29 | 2002–2025 | 体系外补充（广东特色，归入判断推理） |
| `PD-SJ` | 事件排序 | 80 | 2000–2024 | 体系外补充（旧国考题型，归入判断推理） |

#### 三级子考点
)
            lines.append("| 题型 | 子考点 | 题量 |")
            lines.append("|---|---|---:|")
            for c in codes:
                subs = SUB_TAXONOMY.get(c, [])
                if len(subs) <= 1:
                    continue
                for name, _pat in subs:
                    n = subcnt.get((c, name), 0)
                    lines.append(f"| {TAXONOMY[c][1]} | {name} | {n} |")
            lines.append(
## 常识判断

花生十三对应文件：`references/changshi-panduan.md`、`shizheng-redian.md`

| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |
|---|---|---:|---|---|
| `CS-ZZ` | 政治常识 | 1205 | 2000–2026 | changshi-panduan.md#2.1 |
| `CS-JJ` | 经济常识 | 168 | 2000–2026 | changshi-panduan.md#2.2 |
| `CS-FL` | 法律常识 | 233 | 2002–2026 | changshi-panduan.md#2.3 |
| `CS-LS` | 历史人文 | 195 | 2000–2026 | changshi-panduan.md#2.4 |
| `CS-DL` | 地理常识 | 104 | 2002–2026 | changshi-panduan.md#2.5 |
| `CS-KJ` | 科技常识 | 118 | 2001–2026 | changshi-panduan.md#2.6 |
| `CS-SZ` | 时事政治 | 65 | 2003–2026 | changshi-panduan.md#2.7 |
| `CS-SH` | 生活常识 | 53 | 2006–2026 | changshi-panduan.md#2.8 |

#### 三级子考点
)
            lines.append("| 题型 | 子考点 | 题量 |")
            lines.append("|---|---|---:|")
            for c in codes:
                subs = SUB_TAXONOMY.get(c, [])
                if len(subs) <= 1:
                    continue
                for name, _pat in subs:
                    n = subcnt.get((c, name), 0)
                    lines.append(f"| {TAXONOMY[c][1]} | {name} | {n} |")
            lines.append(
## 申论

花生十三对应文件：`references/shenlun.md`、`shenlun-biaoda.md`、`shenlun-sucai.md`

| 编码 | 题型 | 题量 | 出现年份 | 花生十三对齐位置 |
|---|---|---:|---|---|
| `SN-DY` | 单一题（归纳概括） | 151 | 2000–2026 | shenlun.md#二 |
| `SN-ZH` | 综合分析题 | 61 | 2000–2026 | shenlun.md#三 |
| `SN-DC` | 提出对策题 | 69 | 2000–2026 | shenlun.md#四 |
| `SN-GW` | 公文写作题 | 64 | 2003–2026 | shenlun.md#五 |
| `SN-DZW` | 大作文 | 74 | 2001–2026 | shenlun.md#六 |

#### 三级子考点
)
            lines.append("| 题型 | 子考点 | 题量 |")
            lines.append("|---|---|---:|")
            for c in codes:
                subs = SUB_TAXONOMY.get(c, [])
                if len(subs) <= 1:
                    continue
                for name, _pat in subs:
                    n = subcnt.get((c, name), 0)
                    lines.append(f"| {TAXONOMY[c][1]} | {name} | {n} |")
            lines.append(
## 体系外补充说明

| 编码 | 题型 | 处理方式 |
|---|---|---|
| `SL-SZ` | 数字推理 | 花生十三数量关系体系未单列；国考 2000–2012、广东/湖北联考旧卷大量出现，按语义归入数量关系模块，题名沿用真题叫法「数字推理」 |
| `PD-KX` | 科学推理 | 广东特色题型（物理/化学/生物），花生十三判断推理体系未单列；按语义归入判断推理模块 |

## 与技巧层的调用契约

```
用户问题 → 判定考点 code → 本库取原题与答案
                       ↘ 按上表 ref 读取 gongkao-huasheng13 对应章节 → 输出方法/速算/易错点
```

资料分析、数量关系的题必须给出速算过程（截位直除 / 415 份数 / 假设分配 / 代入排除）；
言语、判断必须给「识别标志 + 排除顺序」；申论必须给「采分点结构」。