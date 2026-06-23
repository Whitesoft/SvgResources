# 多主题图标预览（主题切换）

- 日期：2026-06-24
- 状态：已通过设计评审，待写实现计划
- 范围：在现有单主题（Material Symbols）预览应用上，增加按主题切换浏览的能力，覆盖新增的 Lucide / Solar / Tabler Icons 三套主题。

## 背景

仓库新增了三套图标主题目录：`Lucide/`、`Solar/`、`Tabler Icons/`（原有 `Material Symbols/`）。四套主题的命名约定与「形态」模型差异很大：

| 主题 | 形态数 | 命名样例 |
|------|--------|----------|
| Material Symbols | 2 | `foo-rounded.svg`（填充）/ `foo-outline-rounded.svg`（描边） |
| Solar | 6 | `foo-bold` / `-bold-duotone` / `-broken` / `-linear` / `-line-duotone` / `-outline` |
| Lucide | 1 | `foo.svg`（单一描边） |
| Tabler Icons | 1 | `foo.svg`（单一描边） |

当前 `_build_index.py` 只扫描 Material Symbols（`THEME_DIRS` 仅一项），`index.html` 顶部的「填充 / 描边 / 双形态」切换器硬编码了 Material 的 filled/outline 二分。无法直接承载其他主题。

## 目标 / 非目标

**目标**

- 预览时可在四套主题间切换。
- 形态切换器按主题动态生成，忠实反映该主题真实拥有的形态；单形态主题隐藏切换器。
- 每主题一份 JSON，切换时按需加载，首屏只加载默认主题。
- 主题分类关键词支持每主题单独配置（默认复用现有 Material 关键词）。

**非目标（YAGNI）**

- 不做跨主题搜索、不把多主题合并到同一屏。
- 不做主题收藏 / 上次选择记忆（不引入 localStorage 持久化）。
- 不在本次预先为 Lucide/Solar/Tabler 调优分类关键词——先把架子搭好，准确率留待后续单独迭代。

## 已确认的关键决策

1. 形态切换器**按主题动态生成**。
2. 数据组织为**每主题一份 JSON，切换时按需加载**（而非合并成一份大 JSON）。
3. 分类关键词**每主题可单独配置**，缺省复用 Material 的 `CATEGORIES`。
4. 默认主题 = **Material Symbols**。

## 设计

### 一、构建脚本 `_build_index.py`

把扁平的 `THEME_DIRS` 列表升级为 `THEMES`，每项是一个主题配置字典：

```python
THEMES = [
  {
    "dir": "Material Symbols", "name": "Material Symbols",
    "file": "icons-material.json", "default": True,
    "variants": [   # (key, 中文标签, 结尾后缀正则)——顺序重要，长后缀在前
        ("outline", "描边", r"-outline-rounded\.svg$"),
        ("filled",  "填充", r"-rounded\.svg$"),
    ],
    "fallback_variant": "filled",
    "categories": None,   # None = 复用默认 CATEGORIES；可给一份专属关键词
  },
  {
    "dir": "Lucide", "name": "Lucide", "file": "icons-lucide.json",
    "variants": [("default", "默认", r"\.svg$")],
    "fallback_variant": "default", "categories": None,
  },
  {
    "dir": "Solar", "name": "Solar", "file": "icons-solar.json",
    "variants": [
        ("bold-duotone", "粗体双色", r"-bold-duotone\.svg$"),
        ("line-duotone", "线性双色", r"-line-duotone\.svg$"),
        ("bold",    "粗体", r"-bold\.svg$"),
        ("broken",  "破碎", r"-broken\.svg$"),
        ("linear",  "线性", r"-linear\.svg$"),
        ("outline", "描边", r"-outline\.svg$"),
    ],
    "fallback_variant": "linear", "categories": None,
  },
  {
    "dir": "Tabler Icons", "name": "Tabler Icons", "file": "icons-tabler.json",
    "variants": [("default", "默认", r"\.svg$")],
    "fallback_variant": "default", "categories": None,
  },
]
```

**通用解析算法**（取代 Material 专用的 `normalize()` + filled/outline 配对逻辑）：

- 对该主题目录下每个 `.svg`，按 `variants` 顺序尝试每个后缀正则（结尾匹配）。
- 第一个命中的后缀 → 该文件归属对应 `variant_key`，图标名 = 剥掉该后缀后的剩余部分。
- 全都不命中 → 归 `fallback_variant`，图标名 = 去掉 `.svg`。
- 同一图标名的多份文件聚合成一个 item。

`match_categories()` 与 `CATEGORIES` 关键词逻辑**保持不变**（前缀型 `-` 结尾、完整词元匹配），它本来就作用于规范化后的图标名，对四套主题（均为英文 kebab-case 名）同样适用。每个主题用 `theme["categories"] or CATEGORIES` 作为自己的关键词集。

**输出**：

- 每主题一份 `icons-<theme>.json`，结构与现有 `icons.json` 一致，但 item 泛化：

  ```json
  {
    "total_icons": 2965,
    "total_files": 5931,
    "total_labels": 12345,
    "variants": [{"key":"filled","label":"填充"},{"key":"outline","label":"描边"}],
    "categories": [{"name":"...","count":N,"items":[{"name":"...","files":{"filled":"...","outline":"..."}}]}],
    "alphabet":   [{"letter":"A","count":N,"items":[...]}],
    "all":        [{"name":"...","files":{"filled":"...","outline":"..."}}]
  }
  ```

  即 item 从 `{name, filled, outline}` 改为 `{name, files: {<variant_key>: <相对路径>}}`，并新增顶层 `variants`（key + 中文标签，供前端动态建切换器）。

- 一份轻量清单 `themes.json`：

  ```json
  [
    {"name":"Material Symbols","file":"icons-material.json","default":true},
    {"name":"Lucide","file":"icons-lucide.json"},
    {"name":"Solar","file":"icons-solar.json"},
    {"name":"Tabler Icons","file":"icons-tabler.json"}
  ]
  ```

- 不再生成旧的单份 `icons.json`。

- 路径继续用正斜杠（`Material Symbols/foo-rounded.svg`），便于直接拼接文档基址 URL。

### 二、前端 `index.html`

- **主题 ComboBox**：header 内加一个 `<select>`，位置在标题右侧、搜索框左侧（左上角区）。启动时先 `fetch("themes.json")` 填充选项，标记 `default` 项为选中。
- **加载流程**：`themes.json` → 选定（默认）主题 → `fetch` 对应 `icons-*.json` → 渲染侧栏 / 形态切换器 / 网格。切换主题时重新走「fetch 该主题 JSON → 重建」流程，期间复用顶部 `.loading` 提示。
- **形态切换器动态化**：
  - 按钮由当前主题 `data.variants` 生成（label 用中文标签，`data-variant` 用 key）。
  - 末尾追加一个「全部」按钮（即现有「双形态」的泛化：把该图标所有形态并排显示在卡片内）。
  - 单形态主题（`data.variants.length <= 1`）整个切换器隐藏。
- **卡片 / 详情读取泛化**：`it.files[variantKey]` 取代硬编码的 `it.filled` / `it.outline`。
  - 网格：当前选中形态展示该形态文件；「全部」模式下把该 item 所有形态并排（沿用现有 `.card.both` 加宽样式，多形态时按等比缩放）。
  - 详情条：对该图标**所有**形态各给一个大图 + 独立的「添加备选」按钮（沿用现有 `/api/pick` 逻辑）。
- **默认主题 = Material Symbols**；header `<h1>` 标题与 stats 文案随当前主题更新（如 `Lucide 图标库`、`{total_icons} 个图标 · {total_files} 个 SVG 文件`）。
- **保留现有机制不动**：IntersectionObserver 懒渲染（含 `renderGrid` 前的 `io.disconnect()`）、`syncStickyHeight()` sticky 高度同步、字母索引、`scroll-margin-top`、`/api/pick`、`/api/open-folder`、形态切换的就地重填（不重建 DOM 以免滚动跳变）。
- 状态 `state` 新增 `theme`（当前主题名）与 `themes`（清单），`variant` 改存 variant key 字符串（单形态主题固定为其唯一 key）。

### 三、文档

- `CLAUDE.md`：`THEME_DIRS` → `THEMES` 说明；新增 `themes.json`；产物由 `icons.json` 改为 `themes.json` + 各 `icons-*.json`；说明形态切换器按主题动态生成、ComboBox 用法。
- `README.md`：同步主题列表与切换说明。
- `Picked/`、`/api/pick`、`/api/open-folder` 行为不变。

## 风险 / 注意点

- **后缀顺序**：变体后缀正则必须「长后缀在前」，否则 `-rounded.svg` 会先吃掉 `-outline-rounded.svg`（outline 含 `-rounded` 结尾）。同理 Solar 的 `-bold-duotone` 必须在 `-bold` 之前。构建脚本里加注释强调。
- **旧 `icons.json` 删除**：是破坏性改动，但 `index.html` 同步改为读 `themes.json`，且产物纳入版本管理，新 checkout 免构建。需在提交信息与文档中说明。
- **Solar「全部」模式密度**：6 形态并排显示在卡片内会偏密。可接受（与现有「双形态」一致的行为），若后续觉得过密再单独迭代（如卡片只显示选中形态、「全部」仅用于详情条）。本次不做。
- **分类准确率**：非 Material 主题复用 Material 关键词，会有较多图标落到「其他」。本次接受，后续按主题单独调 `categories`。
