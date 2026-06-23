# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

一个**搜集主题 SVG 图标并提供本地预览**的自包含工具集。内置六套主题：Google Material Symbols、Lucide、Solar、Tabler Icons、Carbon、Fluent UI System Icons。运行时是纯静态的 HTML/JS，唯一的构建步骤是一个 Python 脚本，把各主题 SVG 目录扫描成多份 JSON 索引（每主题一份，外加一份主题清单）。

`download_svg_from_Iconify.py` 负责从 Iconify 拉取图标集（文件夹名取网站显示名）；下载完成后**自动调用 `_build_index.py` 重建索引**（加 `--no-rebuild` 可跳过），所以新下载的图标集会立即出现在预览页，无需手工登记。

## 常用命令

```bash
# 重建图标索引（新增/删除/重命名 SVG 文件，或修改 THEMES/CATEGORIES 后都要跑一次）
# 产物：themes.json（主题清单）+ 各 icons-<theme>.json；不再生成单一 icons.json
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

1. **主题目录里的 `*.svg`** —— 数据源。各主题有自己的命名约定，例如 Material Symbols：
   - `<name>-rounded.svg` → 填充形态
   - `<name>-outline-rounded.svg` → 描边形态
   - 其他命名兜底归入填充。
   其他主题（Lucide/Solar/Tabler）各有自己的后缀约定。具体怎么从文件名解析出图标名与形态，见下面第 2 点的 `THEMES` 配置与「后缀优先」算法。

2. **`_build_index.py` → `themes.json` + 各 `icons-<theme>.json`** —— 构建步骤。三件事必须理解：
   - `THEMES`：扩展新图标主题的入口，每项是一个主题配置（目录、显示名、输出文件名、形态后缀列表 `variants`、兜底形态、可选专属分类关键词）。形态由通用的「后缀优先」算法解析，item 形态泛化为 `files: {variantKey: 路径}`。**仅多形态主题**（Material/Solar/Fluent 等）需要在此显式配置。
   - `discover_extra_themes()`：**自动发现**——扫描项目根下未被 `THEMES` 收录、排除 `Picked`/`docs`/`.git`/`.claude` 且含 `.svg` 的子目录，作为**单形态默认主题**登记。因此下载任何单形态图标集（如 Lucide/Tabler/Carbon 风格）只需放进目录再重建索引即可出现，无需改 `THEMES`。
   - `CATEGORIES`：默认分类关键词 `(中文分类名, 关键词列表, 匹配模式)`；各主题可在 `THEMES` 里用 `categories` 覆盖。一个图标可以同时落到**多个**分类（多标签）。匹配由 `match_categories()` 完成：
     - 以 `-` 结尾的关键词按前缀匹配词元（如 `ev-`、`key-`）；
     - 其他关键词按**完整词元**匹配（前后用 `-` 边界包裹），刻意规避子串误命中（例如不让 `ear` 命中 `gear`）；
     - 顺序重要：分类按定义顺序逐个判定，每个分类内部命中即归属。

   输出 JSON 结构：`total_icons`、`total_files`、`categories[]`（每项含 `items`）、`alphabet[]`（A–Z/# 分组，供「全部」视图使用）、扁平的 `all[]`。

3. **`index.html`** —— 整个预览应用是单个 HTML 文件，CSS/JS 全部内联。启动时先 `fetch` 一次 `themes.json` 建主题下拉，切换主题时再 `fetch` 对应的 `icons-<theme>.json`；之后所有渲染都在客户端完成；用户在详情条点击「添加备选 / 打开备选目录」时再向 `server.py` 的两个端点发 POST。需要注意的点：
   - **懒渲染**用 `IntersectionObserver`（`rootMargin: "200px"`）—— 这是必须的，因为网格里可能装下数千张卡片。每次 `renderGrid()` 重新渲染前都要 `io.disconnect()`。
   - **详情条**是独立的 sticky 元素，**不**插入网格 —— 这样才不会干扰 IntersectionObserver 对卡片的观察。
   - **sticky 高度同步**：`syncStickyHeight()` 把 sticky 容器的实际高度写入 CSS 变量 `--sticky-h`，让卡片的 `scroll-margin-top` 配合字母索引点击滚动后不会被遮挡。任何改变布局的操作后都要调用它。
   - **形态切换**按主题动态生成（Material 显示填充/描边，Solar 显示 6 种形态，单形态主题隐藏切换器），是**就地重新填充**已有卡片，而不是重建网格 —— 这是为了避免滚动位置跳变。

## 改这个仓库时

- **新增图标**：把 `.svg` 按命名约定放进对应主题目录（如 `Material Symbols/`、`Lucide/`），然后 `python _build_index.py`。若用 `download_svg_from_Iconify.py` 下载，这一步会自动完成。
- **新增一种主题**：**单形态**主题无需任何配置——新建目录、放入 `.svg`、跑构建即可（`discover_extra_themes` 会自动收录）。**多形态**主题（文件名带形态/尺寸后缀，需归并）才编辑 `_build_index.py` 的 `THEMES`，加一项（含 `dir`/`name`/`file`/`variants`/`fallback_variant`），然后 `python _build_index.py`。
- **新增一种分类**：编辑 `_build_index.py` 的 `CATEGORIES`，**不要**手改各 `icons-<theme>.json` —— 它们每次都会被整体重写。
- **JSON 里的路径用正斜杠**（`Material Symbols/foo-rounded.svg`），这样能直接和文档基址 URL 拼接 —— 改构建脚本时要保留这一点。
- `index.html`、`themes.json`、各 `icons-<theme>.json`、`预览.bat` 都已纳入版本管理，这样一份全新 checkout 不用跑构建就能预览；结构变化后要同步更新。
