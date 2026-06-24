#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取 Phosphor / Lucide 上游官方分类，转成项目自有的缓存格式。

这两个主题在 Iconify API 返回的 categories 为空，但上游仓库实际维护着结构化的
分类数据。本脚本一次性拉取、解析、转成 Themes/_iconify-categories/<prefix>.json
（与 Iconify 缓存同构），让 _build_index.py 像对待其他官方分类主题一样使用。

拉取后**不保留**原始文件（如 Lucide 的 ~1700 个 per-icon JSON），只保留合并后的
单一缓存文件。

使用：
  python _fetch_extra_categories.py              # 默认拉 ph + lucide
  python _fetch_extra_categories.py ph           # 只拉 Phosphor
  python _fetch_extra_categories.py lucide       # 只拉 Lucide
"""
from __future__ import annotations

import json
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / "Themes" / "_iconify-categories"

# Phosphor IconCategory enum 名 -> 字符串值
# 源：phosphor-icons/core/src/types.ts 的 IconCategory 枚举
PHOSPHOR_ICON_CATEGORY = {
    "ARROWS": "arrows",
    "BRAND": "brands",
    "COMMERCE": "commerce",
    "COMMUNICATION": "communications",
    "DESIGN": "design",
    "DEVELOPMENT": "technology & development",
    "EDITOR": "editor",
    "FINANCE": "finances",
    "GAMES": "games",
    "HEALTH": "health & wellness",
    "MAP": "maps & travel",
    "MEDIA": "media",
    "NATURE": "nature",
    "OBJECTS": "objects",
    "OFFICE": "office",
    "PEOPLE": "people",
    "SYSTEM": "system",
    "WEATHER": "weather",
}


def fetch_text(url: str, timeout: int = 30, retries: int = 3) -> str:
    """带重试的文本拉取。retries=3 时一共最多试 3 次。"""
    last_err = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "ExtraCategoriesFetcher/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except HTTPError as e:
            if e.code == 404:
                raise  # 404 不重试，让上层判定为"不存在"
            last_err = e
        except (URLError, socket.timeout, OSError) as e:
            last_err = e
        if attempt < retries - 1:
            time.sleep(1.5 ** attempt)
    raise last_err if last_err else RuntimeError("unknown fetch error")


def fetch_json(url: str, timeout: int = 15):
    return json.loads(fetch_text(url, timeout=timeout))


def _invert(icon_to_cats: dict) -> tuple[dict, list]:
    """{icon: [cats]} -> ({cat: [icons]}, [icons without cat])。"""
    categories: dict[str, list[str]] = {}
    for icon, cats in icon_to_cats.items():
        for c in cats:
            categories.setdefault(c, []).append(icon)
    for c in categories:
        categories[c].sort()
    uncategorized = sorted(n for n, c in icon_to_cats.items() if not c)
    return categories, uncategorized


def fetch_phosphor() -> dict:
    """解析 phosphor-icons/core/src/icons.ts。

    每个条目形如：
      { name: "acorn", ..., categories: [IconCategory.FINANCE, IconCategory.NATURE], ... }
    部分条目带 alias 子对象（也含 name/pascal_name），用正则一次性匹配
    name + 紧随其后的首个 categories 数组，alias 的 name 不会单独命中
    （它会被外层 match 一并吞掉）。
    """
    print("[ph] 拉 phosphor-icons/core/src/icons.ts ...")
    src = fetch_text(
        "https://raw.githubusercontent.com/phosphor-icons/core/main/src/icons.ts",
        timeout=120,
    )

    pattern = re.compile(
        r'name:\s*"([^"]+)"[^[]*?categories:\s*\[([^\]]*)\]', re.DOTALL
    )
    icon_to_cats: dict[str, list[str]] = {}
    for m in pattern.finditer(src):
        name = m.group(1)
        tokens = re.findall(r"IconCategory\.(\w+)", m.group(2))
        cats = [PHOSPHOR_ICON_CATEGORY[t] for t in tokens if t in PHOSPHOR_ICON_CATEGORY]
        icon_to_cats[name] = cats

    categories, uncategorized = _invert(icon_to_cats)
    print(f"[ph] 解析到 {len(icon_to_cats)} 个图标，"
          f"{len(categories)} 个分类，{len(uncategorized)} 个无分类")
    return {
        "prefix": "ph",
        "total": len(icon_to_cats),
        "categories": categories,
        "uncategorized": uncategorized,
        "aliases": {},
    }


def _lucide_icon_names() -> tuple[list[str], dict[str, str]]:
    """返回 (真图标名清单, {alias: real})。Iconify 接口给的真名直接拉元数据，
    alias 不拉（其元数据复用 real 的）。"""
    data = fetch_json("https://api.iconify.design/collection?prefix=lucide")
    real_icons: set[str] = set()
    for n in data.get("uncategorized", []):
        real_icons.add(n)
    for cat_icons in data.get("categories", {}).values():
        real_icons.update(cat_icons)
    for n in data.get("hidden", []):
        real_icons.add(n)
    aliases: dict[str, str] = dict(data.get("aliases", {}))
    # aliases 值是 real name，从 real_icons 移除可能混入的 alias 名
    real_icons -= set(aliases)
    return sorted(real_icons), aliases


def fetch_lucide() -> dict:
    """并发拉 Lucide 每个 *真* icon 的 icons/<name>.json，提取 categories。
    alias 用 real 的 categories 继承（不单独拉）。

    Lucide 上游用 per-icon JSON 存储元数据（schema 强制要求 categories 字段），
    没有打包好的合并文件，所以必须逐个拉取。约 1500+ 个请求。
    """
    real_icons, aliases = _lucide_icon_names()
    print(f"[lucide] {len(real_icons)} 个真图标 + {len(aliases)} 个别名，"
          f"并发拉 per-icon JSON ...")
    base = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons"

    def fetch_one(name: str):
        url = f"{base}/{name}.json"
        try:
            d = fetch_json(url, timeout=30)
            return name, d.get("categories", []) or []
        except HTTPError as e:
            if e.code == 404:
                return name, None  # 上游无对应元数据
            return name, None
        except (URLError, socket.timeout, OSError):
            return name, None  # 网络故障，记入 missing 但不中断

    real_to_cats: dict[str, list[str]] = {}
    missing: list[str] = []
    done = 0
    last = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(fetch_one, n): n for n in real_icons}
        for fut in as_completed(futs):
            name, cats = fut.result()
            done += 1
            if cats is None:
                missing.append(name)
            else:
                real_to_cats[name] = cats
            now = time.time()
            if done <= 3 or now - last >= 2.0 or done == len(real_icons):
                last = now
                print(f"  [lucide] {done}/{len(real_icons)}  "
                      f"ok={len(real_to_cats)}  miss={len(missing)}",
                      flush=True)

    if missing:
        print(f"[lucide] 缺失 {len(missing)} 个（前 10: {missing[:10]})")

    # 应用别名：alias 继承 real 的分类
    icon_to_cats = dict(real_to_cats)
    for alias, real in aliases.items():
        if real in real_to_cats:
            icon_to_cats[alias] = real_to_cats[real]

    categories, uncategorized = _invert(icon_to_cats)
    print(f"[lucide] 总计 {len(icon_to_cats)} 个图标（含别名），"
          f"{len(categories)} 个分类，{len(uncategorized)} 个无分类")
    return {
        "prefix": "lucide",
        "total": len(icon_to_cats),
        "categories": categories,
        "uncategorized": uncategorized,
        "aliases": aliases,
    }


FETCHERS = {"ph": fetch_phosphor, "lucide": fetch_lucide}


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["ph", "lucide"]
    for t in targets:
        if t not in FETCHERS:
            print(f"未知目标: {t}（可选: {', '.join(FETCHERS)}）")
            continue
        data = FETCHERS[t]()
        out = CACHE_DIR / f"{t}.json"
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        sz = out.stat().st_size / 1024
        print(f"  -> {out.relative_to(ROOT_DIR)} ({sz:.0f} KB)\n")


if __name__ == "__main__":
    main()
