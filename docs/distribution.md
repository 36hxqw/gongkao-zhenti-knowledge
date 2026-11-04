# 发行与部署

本库提供**两种发行包**，按使用场景选一个即可。

| | lite | full |
|---|---|---|
| 体积（zip / 解压） | **6.6 MB / 约 18 MB** | 41.0 MB / 106.8 MB |
| 内容 | 全部 Markdown 题库（考点 48 + 原卷 98 + 申论 106 + 分片 128）、`data/search-index.tsv`、`stats.json`、`scripts/search.py` `selfcheck.py` | lite 全部内容 + `data/*.jsonl` 题库 + `references/images/` 3 536 张配图 + 组卷/错题本/评测/CI/流水线 |
| 检索方式 | 打开 Markdown 直接读；或按 `search-index.tsv` 文本匹配拿 `id` 再回原卷 | `scripts/search.py` 全功能（考点/子考点/形态 `--form`/关键词/模糊/难度/主题/折叠） |
| 图形题与图表材料 | **无配图**（Markdown 中的配图引用已在打包时移除） | 完整配图 |
| 适用 | 豆包等宿主上传（体积友好）、只需"查真题 + 看答案" | 本地刷题、组卷、错题本、评测、二次开发 |

> 体积口径：`dist/` 目前只有 **v1.4.0** 的打包产物（full zip **41.0 MB**、lite zip **6.6 MB**，解压 76.1 / 18.3 MB），见 `dist/MANIFEST-v1.4.0.txt`；**v1.11.0 尚未重新打包**，full 解压后体积以当前工作树实测 **106.8 MB** 为准（数据与配图在 v1.4.0 之后有增补）。数字随数据修订变化，以 `docs/stats-snapshot.md` 为准。

## 一、自己打包

```bash
python scripts/make_release.py                  # 两个都打，版本读 skill.json
python scripts/make_release.py --lite           # 只打 lite
python scripts/make_release.py --full --version 1.2.0
```

产物在 `dist/`（已加入 `.gitignore`）：

```
dist/gongkao-zhenti-knowledge-lite-v1.2.0.zip
dist/gongkao-zhenti-knowledge-full-v1.2.0.zip
dist/MANIFEST-v1.2.0.txt
```

lite 打包时会自动**移除 Markdown 里的配图引用**（否则全是死链），并在清单里注明“无配图、无 JSONL”。

## 二、发布到 GitHub Release

```bash
git tag -a v1.2.0 -m "公考真题知识库 v1.2.0"
git push origin main --tags
# 在 GitHub 页面 New release → 选择 tag → 上传 dist/ 下两个 zip 与 MANIFEST
```

建议 Release 说明直接引用 `CHANGELOG.md` 对应段落，并注明“lite 无配图”。

## 三、装到豆包工作模式

- **优先 lite**：解压得到 `gongkao-zhenti-knowledge/`，确认顶层有 `SKILL.md`，整体上传即可（6.6MB）。
- 需要看图形题/图表材料时再换 full。
- 同时安装 `gongkao-huasheng13` 才能“真题 + 技巧”联动。

## 四、体积构成（full）

| 部分 | 约 |
|---|---|
| `references/images/`（3 536 张 JPEG） | 55.4 MB |
| `references/juan/`（98 套行测原卷） | 6.8 MB |
| `references/shenlun/`（106 套申论原卷） | 3.6 MB |
| `references/kaodian/` + 分片 | 6.0 MB |
| `data/xingce.jsonl` | 18.7 MB |
| `data/shenlun.jsonl` | 9.3 MB |
| `data/search-index.tsv` | 2.7 MB |

要更小可以：删 `references/images/`（-55.4MB）、或把 `data/*.jsonl` 换成按省分片（`xingce-gk/gd/hb.jsonl`）。
