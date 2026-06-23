# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

一个**搜集主题 SVG 图标并提供本地预览**的自包含工具集。当前内置 Google Material Symbols（5931 个 SVG 文件 ≈ 2965 个图标 × 填充/描边两种形态）。运行时是纯静态的 HTML/JS，唯一的构建步骤是一个 Python 脚本，把 SVG 目录扫描成一份 JSON 索引。

## 常用命令

```bash
# 重建图标索引（新增/删除/重命名 SVG 文件，或修改 CATEGORIES 后都要跑一次）
python _build_index.py

# 启动预览服务器（必须走 HTTP —— index.html 用了 fetch()，直接用 file:// 打开会被浏览器拦截）
python server.py
# Windows 下的等价一键脚本：预览.bat
```

`server.py` 监听 `127.0.0.1:8765`，承担两件事：

1. 静态文件服务（取代 `python -m http.server`）。
2. 两个 POST 端点供前端调用：
   - `POST /api/pick` — body `{ "file": "<项目根相对路径>" }`，把该 SVG 拷贝到 `Picked/`（运行时由 server 启动时创建，已在 `.gitignore` 中）。带路径白名单校验：`(ROOT / rel).resolve()` 后必须仍位于项目根下，否则 400。
   - `POST /api/open-folder` — 用 `os.startfile` / `open` / `xdg-open` 在系统资源管理器里打开 `Picked/`。

只想纯浏览、不需要备选功能时，仍可退回 `python -m http.server 8765 --bind 127.0.0.1`。

没有测试、没有 lint、没有包管理器。`index.html`、`_build_index.py`、`server.py` 都零依赖。

## 架构

整体是一条单向的 **文件 → JSON → 浏览器** 流水线，由三个松耦合的组件组成：

1. **`Material Symbols/*.svg`** —— 数据源。文件名约定是核心：
   - `<name>-rounded.svg` → 填充形态
   - `<name>-outline-rounded.svg` → 描边形态
   - 其他命名兜底归入填充。

   `normalize()` 剥掉这些后缀，得到规范化的图标名，并把同名的两种形态配对到一起。

2. **`_build_index.py` → `icons.json`** —— 构建步骤。两件事必须理解：
   - `THEME_DIRS`：扩展新图标主题的入口，每项是一个被扫描 `.svg` 的子目录。
   - `CATEGORIES`：一份硬编码的 `(中文分类名, 关键词列表, 匹配模式)` 列表。一个图标可以同时落到**多个**分类（多标签）。匹配由 `match_categories()` 完成：
     - 以 `-` 结尾的关键词按前缀匹配词元（如 `ev-`、`key-`）；
     - 其他关键词按**完整词元**匹配（前后用 `-` 边界包裹），刻意规避子串误命中（例如不让 `ear` 命中 `gear`）；
     - 顺序重要：分类按定义顺序逐个判定，每个分类内部命中即归属。

   输出 JSON 结构：`total_icons`、`total_files`、`categories[]`（每项含 `items`）、`alphabet[]`（A–Z/# 分组，供「全部」视图使用）、扁平的 `all[]`。

3. **`index.html`** —— 整个预览应用是单个 HTML 文件，CSS/JS 全部内联。它只 `fetch` 一次 `icons.json`，之后所有渲染都在客户端完成；用户在详情条点击「添加备选 / 打开备选目录」时再向 `server.py` 的两个端点发 POST。需要注意的点：
   - **懒渲染**用 `IntersectionObserver`（`rootMargin: "200px"`）—— 这是必须的，因为网格里可能装下数千张卡片。每次 `renderGrid()` 重新渲染前都要 `io.disconnect()`。
   - **详情条**是独立的 sticky 元素，**不**插入网格 —— 这样才不会干扰 IntersectionObserver 对卡片的观察。
   - **sticky 高度同步**：`syncStickyHeight()` 把 sticky 容器的实际高度写入 CSS 变量 `--sticky-h`，让卡片的 `scroll-margin-top` 配合字母索引点击滚动后不会被遮挡。任何改变布局的操作后都要调用它。
   - **形态切换**（填充/描边/双形态）是**就地重新填充**已有卡片，而不是重建网格 —— 这是为了避免滚动位置跳变。

## 改这个仓库时

- **新增图标**：把 `.svg` 按命名约定放进 `Material Symbols/`，然后 `python _build_index.py`。
- **新增一种分类**：编辑 `_build_index.py` 的 `CATEGORIES`，**不要**手改 `icons.json` —— 它每次都会被整体重写。
- **JSON 里的路径用正斜杠**（`Material Symbols/foo-rounded.svg`），这样能直接和文档基址 URL 拼接 —— 改构建脚本时要保留这一点。
- `index.html`、`icons.json`、`预览.bat` 都已纳入版本管理，这样一份全新 checkout 不用跑构建就能预览；结构变化后要同步更新。
