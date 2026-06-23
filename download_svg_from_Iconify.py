"""
下载 Iconify SVG 图标集

支持下载任意一个或多个图标集，也可一键下载全部 212 个图标集。
图标来自 https://icon-sets.iconify.design/ ，全部开源。

使用方法：

  # 下载单个图标集（推荐先试这个）
  python download_svg_from_Iconify.py --prefix material-symbols
  python download_svg_from_Iconify.py --prefix tabler --prefix lucide

  # 下载全部 212 个图标集（约 29 万个图标，谨慎使用）
  python download_svg_from_Iconify.py --all

  # 指定输出目录（每个图标集单独一个子目录）
  python download_svg_from_Iconify.py --prefix tabler -o D:/Icons

  # 断点续传（跳过已下载的文件）
  python download_svg_from_Iconify.py --prefix tabler --resume

  # 限制并发线程数
  python download_svg_from_Iconify.py --prefix tabler --workers 16

输出目录结构（文件夹名为图标集在网站上的显示名，如 "Tabler Icons"）：
  <output>/<显示名>/<icon>.svg
  例如：./iconify-svg/Tabler Icons/home.svg
       ./iconify-svg/Material Symbols/home-rounded.svg
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple
from urllib.request import urlopen, Request
from urllib.error import HTTPError

API_BASE = "https://api.iconify.design"
WORKERS = 8

socket.setdefaulttimeout(20)


def log(msg: str):
    print(msg, flush=True)


def fetch_json(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "IconifyDownloader/1.0"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                log(f"  请求失败 ({e})，{wait}s 后重试...")
                time.sleep(wait)
            else:
                raise


def fetch_bytes(url: str, retries: int = 2) -> bytes | None:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "IconifyDownloader/1.0"})
            with urlopen(req, timeout=15) as resp:
                return resp.read()
        except HTTPError as e:
            if e.code == 404:
                return None
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return None
    return None


def get_collection_info(prefixes: List[str] | None = None) -> dict:
    """返回 {prefix: 显示名}。

    prefixes=None 表示获取全部图标集（约 212 个）；
    否则只查询指定的前缀。显示名取自网站 /collections 接口的 name 字段，
    取不到时退化为首字母大写的前缀。
    """
    if prefixes is None:
        log("正在获取图标集清单...")
        url = f"{API_BASE}/collections"
    else:
        url = f"{API_BASE}/collections?prefixes={','.join(prefixes)}"
    data = fetch_json(url)
    return {p: (info.get("name") or p.capitalize()) for p, info in data.items()}


def get_icon_names(prefix: str) -> List[str]:
    """获取指定图标集内的全部图标名。"""
    data = fetch_json(f"{API_BASE}/collection?prefix={prefix}")

    icons = set()
    for name in data.get("uncategorized", []):
        icons.add(name)
    for cat_icons in data.get("categories", {}).values():
        icons.update(cat_icons)
    for name in data.get("hidden", []):
        icons.add(name)
    for alias in data.get("aliases", {}):
        icons.add(alias)

    return sorted(icons)


def download_one(prefix: str, icon_name: str, output_dir: Path) -> Tuple[str, bool]:
    safe_name = icon_name.replace("/", "--")
    out_path = output_dir / f"{safe_name}.svg"
    if out_path.exists():
        return (icon_name, True)

    url = f"{API_BASE}/{prefix}/{icon_name}.svg"
    data = fetch_bytes(url)
    if data is None:
        return (icon_name, False)
    out_path.write_bytes(data)
    return (icon_name, True)


def download_prefix(prefix: str, folder_name: str, output_root: Path,
                    workers: int, resume: bool) -> Tuple[int, int, int]:
    """下载一个图标集。返回 (downloaded, skipped, failed)。

    prefix      图标集前缀（用于拼接 API URL）
    folder_name 输出子目录名（通常为网站显示名，如 "Tabler Icons"）
    """
    output_dir = output_root / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 获取图标列表
    try:
        icons = get_icon_names(prefix)
    except Exception as e:
        log(f"  [{prefix}] 获取图标列表失败：{e}")
        return (0, 0, 0)

    if not icons:
        log(f"  [{prefix}] 未获取到任何图标，跳过。")
        return (0, 0, 0)

    total = len(icons)
    log(f"[{prefix}] 共 {total} 个图标")

    # 2. resume 过滤
    skipped = 0
    if resume:
        todo = []
        for name in icons:
            safe = name.replace("/", "--")
            if (output_dir / f"{safe}.svg").exists():
                skipped += 1
            else:
                todo.append(name)
        icons = todo
    else:
        icons = list(icons)

    if not icons:
        log(f"  [{prefix}] 全部已下载（跳过 {skipped}），无需操作。")
        return (0, skipped, 0)

    todo_count = len(icons)

    # 3. 多线程下载
    downloaded = 0
    failed = 0
    fail_names: List[str] = []
    last_report = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {}
        for name in icons:
            fut = pool.submit(download_one, prefix, name, output_dir)
            future_map[fut] = name

        for fut in as_completed(future_map):
            name = future_map[fut]
            _, ok = fut.result()
            if ok:
                downloaded += 1
            else:
                failed += 1
                fail_names.append(name)

            done = downloaded + failed
            now = time.time()
            if done <= 3 or now - last_report >= 0.5 or done == todo_count:
                last_report = now
                pct = done / todo_count * 100
                log(f"  [{prefix}] [{pct:5.1f}%] {done}/{todo_count}  "
                    f"下载 {downloaded}  失败 {failed}")

    log(f"  [{prefix}] 完成：成功 {downloaded + skipped}（含跳过 {skipped}），失败 {failed}")
    if fail_names and len(fail_names) <= 20:
        log(f"  [{prefix}] 失败图标: {', '.join(fail_names[:20])}")
    elif fail_names:
        log(f"  [{prefix}] 前 20 个失败: {', '.join(fail_names[:20])}...")

    return (downloaded, skipped, failed)


def rebuild_preview_index(output_root: Path):
    """下载完成后自动重建本地预览索引（_build_index.py）。

    仅当输出目录里存在 _build_index.py 时才执行——即只对 SvgResources 预览项目生效。
    _build_index.py 会自动发现新增的图标集目录（见其中的 discover_extra_themes），
    所以新下载的主题无需任何手工登记即可出现在预览页。
    """
    build = output_root / "_build_index.py"
    if not build.exists():
        return
    log("\n正在重建预览索引 (_build_index.py)...")
    try:
        subprocess.run([sys.executable, str(build)], check=True,
                       cwd=str(output_root))
    except subprocess.CalledProcessError as e:
        log(f"  重建索引失败（不影响下载结果）：退出码 {e.returncode}")
    except Exception as e:
        log(f"  重建索引失败（不影响下载结果）：{e}")


def main():
    parser = argparse.ArgumentParser(description="下载 Iconify SVG 图标集")
    parser.add_argument("--output", "-o", default="./iconify-svg",
                        help="输出根目录（每个图标集单独建子目录）")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--prefix", "-p", action="append", metavar="PREFIX",
                     help="要下载的图标集前缀，可重复指定多个 "
                          "（如 --prefix tabler --prefix lucide）")
    src.add_argument("--all", action="store_true",
                     help="下载全部图标集（约 212 个，29 万图标，谨慎使用）")
    parser.add_argument("--workers", "-w", type=int, default=WORKERS,
                        help=f"单个图标集的并发线程数（默认 {WORKERS}）")
    parser.add_argument("--resume", action="store_true",
                        help="跳过已存在的文件")
    parser.add_argument("--no-rebuild", action="store_true",
                        help="下载后不自动重建预览索引（_build_index.py）")
    args = parser.parse_args()

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    # 确定要下载的图标集清单，并查询每个前缀对应的网站显示名作为文件夹名
    if args.all:
        prefix_map = get_collection_info(None)  # {prefix: 显示名}
    else:
        prefix_map = get_collection_info(args.prefix)
        # 用户传入的前缀若接口未返回，退化为首字母大写
        for p in args.prefix:
            prefix_map.setdefault(p, p.capitalize())

    # 按前缀排序，保证下载顺序稳定
    items = sorted(prefix_map.items())

    log(f"\n将下载 {len(items)} 个图标集，输出到 {output_root.resolve()}")
    for prefix, name in items:
        log(f"  · {prefix}  →  {name}/")
    log("")

    total_dl = total_skip = total_fail = 0
    start = time.time()
    for idx, (prefix, folder_name) in enumerate(items, 1):
        log(f"========== [{idx}/{len(items)}] {prefix} ({folder_name}) ==========")
        dl, skip, fail = download_prefix(
            prefix, folder_name, output_root, args.workers, args.resume)
        total_dl += dl
        total_skip += skip
        total_fail += fail

    elapsed = time.time() - start
    log(f"\n全部完成（用时 {elapsed:.0f}s）")
    log(f"  总成功 {total_dl + total_skip}（含跳过 {total_skip}），总失败 {total_fail}")
    log(f"  文件保存在: {output_root.resolve()}")

    # 下载完成后自动重建预览索引，让新图标集立即出现在预览页
    if not args.no_rebuild:
        rebuild_preview_index(output_root)


if __name__ == "__main__":
    main()
