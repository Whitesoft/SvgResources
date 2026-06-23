"""
下载 Material Symbols SVG 图标集（来自 Iconify）

使用方法：

  # 下载全部图标（所有变体）
  python download_material_symbols.py

  # 只下载 rounded 变体
  python download_material_symbols.py --variant rounded

  # 指定输出目录
  python download_material_symbols.py -o D:/Icons/material-symbols

  # 断点续传（跳过已下载的文件）
  python download_material_symbols.py --resume

"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

API_BASE = "https://api.iconify.design"
PREFIX = "material-symbols"
WORKERS = 8

socket.setdefaulttimeout(20)


def log(msg: str):
    print(msg, flush=True)


def fetch_json(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "MaterialSymbolsDownloader/1.0"})
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
            req = Request(url, headers={"User-Agent": "MaterialSymbolsDownloader/1.0"})
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


def get_all_icon_names() -> List[str]:
    log("正在获取图标列表...")
    url = f"{API_BASE}/collection?prefix={PREFIX}"
    data = fetch_json(url)

    icons = set()
    for name in data.get("uncategorized", []):
        icons.add(name)
    for cat_icons in data.get("categories", {}).values():
        icons.update(cat_icons)
    for name in data.get("hidden", []):
        icons.add(name)
    for alias in data.get("aliases", {}):
        icons.add(alias)

    result = sorted(icons)
    log(f"  共获取 {len(result)} 个图标名")
    return result


def download_one(icon_name: str, output_dir: Path) -> Tuple[str, bool]:
    safe_name = icon_name.replace("/", "--")
    out_path = output_dir / f"{safe_name}.svg"
    if out_path.exists():
        return (icon_name, True)

    url = f"{API_BASE}/{PREFIX}/{icon_name}.svg"
    data = fetch_bytes(url)
    if data is None:
        return (icon_name, False)
    out_path.write_bytes(data)
    return (icon_name, True)


def main():
    parser = argparse.ArgumentParser(description="下载 Material Symbols SVG 图标")
    parser.add_argument("--output", "-o", default="./material-symbols-svg",
                        help="输出目录")
    parser.add_argument("--variant", "-v", default="",
                        choices=["", "rounded", "sharp", "outlined"],
                        help="只下载指定变体（图标名已含变体后缀，如 home-rounded）")
    parser.add_argument("--workers", "-w", type=int, default=WORKERS,
                        help=f"并发线程数（默认 {WORKERS}）")
    parser.add_argument("--resume", action="store_true",
                        help="跳过已存在的文件")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 获取图标列表
    icons = get_all_icon_names()
    if not icons:
        log("未获取到任何图标，退出。")
        sys.exit(1)

    # 2. 按变体过滤（图标名已自带后缀，如 home-rounded）
    if args.variant:
        suffix = f"-{args.variant}"
        icons = [n for n in icons if n.endswith(suffix)]
        log(f"  过滤变体 '{args.variant}': 匹配 {len(icons)} 个\n")
        if not icons:
            log("没有匹配的图标，退出。")
            sys.exit(1)

    total = len(icons)

    # 3. resume 过滤
    skipped = 0
    if args.resume:
        todo = []
        for name in icons:
            safe = name.replace("/", "--")
            if (output_dir / f"{safe}.svg").exists():
                skipped += 1
            else:
                todo.append(name)
        if skipped:
            log(f"跳过已存在 {skipped} 个，剩余 {len(todo)} 个待下载。")
        icons = todo

    if not icons:
        log("全部已下载，无需操作。")
        return

    todo_count = len(icons)
    log(f"开始下载 {todo_count} 个图标，{args.workers} 线程并发 → {output_dir.resolve()}\n")

    # 4. 多线程下载
    downloaded = 0
    failed = 0
    fail_names: List[str] = []
    last_report = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {}
        for name in icons:
            fut = pool.submit(download_one, name, output_dir)
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
                log(f"  [{pct:5.1f}%] {done}/{todo_count}  "
                    f"下载 {downloaded}  失败 {failed}")

    log(f"\n完成！成功 {downloaded + skipped}（含跳过 {skipped}），失败 {failed}")
    if fail_names and len(fail_names) <= 20:
        log(f"失败图标: {', '.join(fail_names[:20])}")
    elif fail_names:
        log(f"前 20 个失败: {', '.join(fail_names[:20])}...")
    log(f"文件保存在: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
