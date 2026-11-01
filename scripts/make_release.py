#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包发行版：lite（纯 Markdown，体积小）与 full（含题库 JSONL 与配图）。

用法
----
    python scripts/make_release.py --version 1.2.0            # 两个都打
    python scripts/make_release.py --lite --out dist          # 只打 lite
    python scripts/make_release.py --full --version 1.2.0

产物
----
    dist/gongkao-zhenti-knowledge-lite-v<ver>.zip
    dist/gongkao-zhenti-knowledge-full-v<ver>.zip
    dist/MANIFEST-v<ver>.txt

lite 适用：豆包/其他宿主上传（体积友好），检索靠 Markdown（references/）与
           data/search-index.tsv 的纯文本匹配。
full 适用：本地 CLI 全功能（JSONL 题库、配图、组卷、错题本、评测）。
"""
import argparse
import json
import os
import re
import shutil
import sys
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COMMON = ["SKILL.md", "README.md", "LICENSE", "CHANGELOG.md", "skill.json"]
LITE_DIRS = ["docs"]
LITE_REF = ["00-index.md", "01-命题规律总览.md"]
LITE_DATA = ["search-index.tsv", "stats.json"]
LITE_SCRIPTS = ["search.py", "selfcheck.py"]
FULL_ONLY = ["references/images", "data/xingce.jsonl", "data/shenlun.jsonl", "tests", "tools",
             ".github", "scripts/paper.py", "scripts/wrongbook.py"]


def _ignore_factory(forbidden):
    def _ignore(dirpath, names):
        out = set()
        for n in names:
            full = os.path.join(dirpath, n).replace("\\", "/")
            rel = os.path.relpath(full, BASE).replace("\\", "/")
            if n in ("__pycache__", ".git", "dist", "out", "user"):
                out.add(n)
            elif rel in forbidden:
                out.add(n)
        return out
    return _ignore


def copy_tree(dest, forbidden):
    ignore = _ignore_factory(forbidden)
    for item in COMMON:
        src = os.path.join(BASE, item)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, item))
    for d in LITE_DIRS:
        src = os.path.join(BASE, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, d), ignore=ignore, dirs_exist_ok=True)
    # references：主文件 + kaodian/juan/shenlun（lite 也要，因为原题与答案都在这里）
    os.makedirs(os.path.join(dest, "references"), exist_ok=True)
    for f in os.listdir(os.path.join(BASE, "references")):
        src = os.path.join(BASE, "references", f)
        if os.path.isfile(src) and (f in LITE_REF or f.endswith(".md")):
            shutil.copy2(src, os.path.join(dest, "references", f))
    for sub in ("kaodian", "juan", "shenlun"):
        src = os.path.join(BASE, "references", sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, "references", sub), ignore=ignore, dirs_exist_ok=True)
    # data：lite 只放索引与统计
    os.makedirs(os.path.join(dest, "data"), exist_ok=True)
    for f in LITE_DATA:
        src = os.path.join(BASE, "data", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, "data", f))
    # scripts
    os.makedirs(os.path.join(dest, "scripts"), exist_ok=True)
    for f in LITE_SCRIPTS:
        src = os.path.join(BASE, "scripts", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, "scripts", f))


def copy_full_extras(dest):
    shutil.copytree(os.path.join(BASE, "references", "images"),
                    os.path.join(dest, "references", "images"), dirs_exist_ok=True)
    for f in ("xingce.jsonl", "shenlun.jsonl"):
        shutil.copy2(os.path.join(BASE, "data", f), os.path.join(dest, "data", f))
    for d in ("tests", "tools", ".github"):
        src = os.path.join(BASE, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, d),
                            ignore=_ignore_factory(set()), dirs_exist_ok=True)
    for f in ("paper.py", "wrongbook.py"):
        src = os.path.join(BASE, "scripts", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, "scripts", f))


def strip_image_links(root):
    """lite 包里没有图片，去掉 Markdown 里的配图引用，避免死链。"""
    pat = re.compile(r"^!\[[^\]]*\]\([^)]*images/[^)]*\)\s*$")
    removed = 0
    for r, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".md"):
                continue
            p = os.path.join(r, f)
            with open(p, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
            kept = [ln for ln in lines if not pat.match(ln.strip())]
            if len(kept) != len(lines):
                removed += len(lines) - len(kept)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(kept))
    return removed


def zip_dir(src, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _, files in os.walk(src):
            for f in files:
                p = os.path.join(root, f)
                arc = os.path.join(os.path.basename(src), os.path.relpath(p, src))
                z.write(p, arc.replace("\\", "/"))


def dir_size(p):
    total, count = 0, 0
    for root, _, files in os.walk(p):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
            count += 1
    return total, count


def main(argv=None):
    ap = argparse.ArgumentParser(description="打包 lite / full 发行版")
    ap.add_argument("--version", default="", help="版本号，默认读 skill.json")
    ap.add_argument("--out", default=os.path.join(BASE, "dist"), help="输出目录，默认 dist/")
    ap.add_argument("--lite", action="store_true", help="只打 lite")
    ap.add_argument("--full", action="store_true", help="只打 full")
    args = ap.parse_args(argv)
    ver = args.version
    if not ver:
        with open(os.path.join(BASE, "skill.json"), encoding="utf-8") as f:
            ver = json.load(f).get("version", "0")
    do_lite = args.lite or not (args.lite or args.full)
    do_full = args.full or not (args.lite or args.full)
    os.makedirs(args.out, exist_ok=True)
    manifest = [f"# 发行清单 v{ver}", ""]
    for flavor, want in (("lite", do_lite), ("full", do_full)):
        if not want:
            continue
        stage = os.path.join(args.out, f"_stage_{flavor}", "gongkao-zhenti-knowledge")
        if os.path.exists(os.path.dirname(stage)):
            shutil.rmtree(os.path.dirname(stage))
        os.makedirs(stage)
        copy_tree(stage, set())
        if flavor == "full":
            copy_full_extras(stage)
        else:
            n = strip_image_links(stage)
            print(f"[lite] 移除配图引用 {n} 处（lite 不含图片）")
        size, count = dir_size(stage)
        zp = os.path.join(args.out, f"gongkao-zhenti-knowledge-{flavor}-v{ver}.zip")
        zip_dir(stage, zp)
        zsize = os.path.getsize(zp)
        print(f"[{flavor}] {count} 个文件，解压后 {size / 1048576:.1f} MB，zip {zsize / 1048576:.1f} MB -> {os.path.basename(zp)}")
        note = "含 JSONL 题库、配图、组卷/错题本/评测" if flavor == "full" else "纯 Markdown 题库（无配图、无 JSONL），检索用 data/search-index.tsv 文本匹配"
        manifest += [f"## {flavor}", f"- 说明：{note}", f"- 文件数：{count}", f"- 解压后：{size / 1048576:.1f} MB",
                     f"- zip：{zsize / 1048576:.1f} MB", f"- 包：{os.path.basename(zp)}", ""]
        shutil.rmtree(os.path.dirname(stage))
    with open(os.path.join(args.out, f"MANIFEST-v{ver}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(manifest))
    print(f"清单：{os.path.join(args.out, f'MANIFEST-v{ver}.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
