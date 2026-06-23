# 多主题图标预览 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让预览应用在 Material Symbols / Lucide / Solar / Tabler Icons 四套主题间切换浏览，形态切换器按主题动态生成。

**Architecture:** 构建脚本从「单主题扁平扫描」升级为「按 `THEMES` 配置逐主题解析」，每个主题用通用的「后缀优先」算法提取图标名与形态，输出 `themes.json` 清单 + 每主题一份 `icons-*.json`（item 形态从 `filled/outline` 泛化为 `files: {variantKey: path}`）。前端先加载清单建主题 `<select>`，切换时按需 fetch 对应 JSON 并动态重建形态切换器与网格。

**Tech Stack:** Python 3 标准库（零依赖构建脚本）、单文件 HTML/CSS/JS（零依赖前端）、`server.py` 静态服务。无测试框架、无包管理器。

**测试策略说明：** 本仓库无测试框架（见 CLAUDE.md），故不引入 pytest。脚本任务用 `python -c` 内联断言做可重复的自动化校验；前端任务用明确的手动浏览器清单校验。

**参考设计：** `docs/superpowers/specs/2026-06-24-multi-theme-preview-design.md`

**关键约束（务必遵守）：**
- 路径用正斜杠（`Material Symbols/foo-rounded.svg`），可直接拼接文档基址 URL。
- `variants` 后缀正则顺序：**长后缀必须在前**（否则 `-rounded.svg` 会先吃掉 `-outline-rounded.svg`，`-bold.svg` 会先吃掉 `-bold-duotone.svg`）。
- 保留现有机制：IntersectionObserver 懒渲染（`renderGrid` 前 `io.disconnect()`）、`syncStickyHeight()`、`/api/pick`、`/api/open-folder`。
- 每个主题产物（`themes.json` + 各 `icons-*.json`）都要纳入版本管理，新 checkout 免构建。

**文件结构：**
- `_build_index.py`（改写）：`THEME_DIRS` → `THEMES`；新增通用 `extract_variant()`、`build_theme()`；`match_categories()` 增加 `categories` 参数；`main()` 逐主题输出 + 写 `themes.json`。
- `index.html`（改写）：header 加主题 `<select>`；形态切换器动态化；item 改读 `files`。
- `icons.json`（删除）：被 `themes.json` + `icons-*.json` 取代。
- `CLAUDE.md` / `README.md`（更新）：同步新结构与主题列表。

---

## Task 1: 改写构建脚本为多主题

**Files:**
- Modify: `_build_index.py`（整体改写 `THEME_DIRS`→`THEMES`、`normalize()`→`extract_variant()`、`match_categories()` 加参数、`main()` 逐主题输出）

本任务后旧 `icons.json` 暂留在磁盘（前端仍读它，预览不中断），到 Task 3 才删除。即：本任务提交后预览仍可用（显示旧的 Material 数据），Task 2 完成后前端才切到新数据。

- [ ] **Step 1: 替换 `THEME_DIRS` 为 `THEMES` 配置**

在 `_build_index.py` 中，删除现有的 `THEME_DIRS` 块（约第 12–16 行），替换为：

```python
# 主题配置：每项描述一个图标主题如何被解析。
#   dir              — 子目录名
#   name             — 显示用主题名
#   file             — 输出 JSON 文件名
#   default          — 是否默认主题（前端首次加载它）
#   variants         — [(key, 中文标签, 结尾后缀正则)]；顺序重要：长后缀必须在前，
#                      否则 -rounded.svg 会先吃掉 -outline-rounded.svg，
#                      -bold.svg 会先吃掉 -bold-duotone.svg
#   fallback_variant — 命中不了任何后缀时（如裸 foo.svg）归到这里
#   categories       — None = 复用下面的 CATEGORIES；否则给一份该主题专属关键词
THEMES = [
    {
        "dir": "Material Symbols", "name": "Material Symbols",
        "file": "icons-material.json", "default": True,
        "variants": [
            ("outline", "描边", r"-outline-rounded\.svg$"),
            ("filled",  "填充", r"-rounded\.svg$"),
        ],
        "fallback_variant": "filled",
        "categories": None,
    },
    {
        "dir": "Lucide", "name": "Lucide", "file": "icons-lucide.json",
        "variants": [("default", "默认", r"\.svg$")],
        "fallback_variant": "default",
        "categories": None,
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
        "fallback_variant": "linear",
        "categories": None,
    },
    {
        "dir": "Tabler Icons", "name": "Tabler Icons", "file": "icons-tabler.json",
        "variants": [("default", "默认", r"\.svg$")],
        "fallback_variant": "default",
        "categories": None,
    },
]
```

`CATEGORIES` 列表本身**保持不动**。

- [ ] **Step 2: 给 `match_categories()` 增加 `categories` 参数**

把现有的 `def match_categories(name):` 改为接受可选的关键词集，并把内部循环从写死的 `CATEGORIES` 改为参数：

```python
def match_categories(name, categories=CATEGORIES):
    """返回该 name 所属的所有分类中文名列表（多标签，去重保序）。未匹配返回空列表。

    匹配规则：
    - 前缀型关键词（以 '-' 结尾，如 'ev-'、'key-'、'sd-'）：要求词元以该前缀开头
    - 普通关键词：要求作为完整词元出现（前后都被 '-' 或字符串边界包裹）
      这样可避免 'ear' 命中 'gear'、'light' 命中 'flight'、'air' 命中 'airplane' 等子串误匹配
    """
    matched = []
    seen = set()
    wrapped = f"-{name}-"
    for cat_name, keywords, mode in categories:
        hit = False
        if mode == "startswith_digit":
            if name and name[0].isdigit():
                hit = True
        else:
            for kw in keywords:
                if kw.endswith("-"):
                    # 前缀型：词元以 kw 开头
                    if name.startswith(kw) or f"-{kw}" in wrapped:
                        hit = True
                        break
                else:
                    # 完整词元：前后都加边界，杜绝子串误命中
                    if f"-{kw}-" in wrapped or name == kw:
                        hit = True
                        break
        if hit and cat_name not in seen:
            seen.add(cat_name)
            matched.append(cat_name)
    return matched
```

- [ ] **Step 3: 用 `extract_variant()` + `build_theme()` 替换 `normalize()` 与旧 `main()`**

删除旧的 `normalize()` 函数（约第 100–106 行）和整个旧 `main()`（约第 143–234 行），替换为下面两个函数 + 新 `main()`：

```python
def extract_variant(basename, variants, fallback_variant):
    """返回 (variant_key, icon_name)。

    按 variants 顺序试每个结尾后缀正则；第一个命中者决定 variant，
    图标名 = 命中位置之前的子串（已同时去掉后缀与 .svg）。
    都不命中则 variant=fallback_variant，图标名 = 去掉 .svg。
    """
    for key, _label, suffix_re in variants:
        m = re.search(suffix_re, basename)
        if m:
            return key, basename[:m.start()]
    return fallback_variant, re.sub(r"\.svg$", "", basename)


def build_theme(theme):
    """扫描单个主题目录，返回与原 icons.json 同构（但泛化）的结果字典。"""
    sub_dir = os.path.join(SVG_DIR, theme["dir"])
    variants_cfg = theme["variants"]
    cats_cfg = theme["categories"] if theme["categories"] is not None else CATEGORIES

    # 收集相对路径（正斜杠）
    files = []
    if os.path.isdir(sub_dir):
        for f in os.listdir(sub_dir):
            if f.endswith(".svg"):
                files.append(f"{theme['dir']}/{f}")

    # name -> {variant_key: relpath}
    by_name = defaultdict(dict)
    for rel in files:
        base = os.path.basename(rel)
        vkey, name = extract_variant(base, variants_cfg, theme["fallback_variant"])
        by_name[name][vkey] = rel

    # 分类（多标签）
    categorized = defaultdict(list)
    uncategorized = []
    for name in sorted(by_name.keys()):
        cats = match_categories(name, cats_cfg)
        item = {"name": name, "files": by_name[name]}
        for c in cats:
            categorized[c].append(item)
        if not cats:
            uncategorized.append(item)

    # 按首字母分组（用于 All 索引）
    alpha_groups = defaultdict(list)
    for name in sorted(by_name.keys()):
        first = name[0].upper()
        if first.isdigit():
            first = "#"
        alpha_groups[first].append({"name": name, "files": by_name[name]})

    # 整理 categories 顺序，按 cats_cfg 定义顺序，附加未分类
    cat_order = [c[0] for c in cats_cfg]
    cats_out = []
    for cn in cat_order:
        items = categorized.get(cn, [])
        if items:
            cats_out.append({"name": cn, "count": len(items), "items": items})
    if uncategorized:
        cats_out.append({"name": "其他", "count": len(uncategorized), "items": uncategorized})

    alpha = [{"letter": k, "count": len(v), "items": v} for k, v in sorted(alpha_groups.items())]

    return {
        "total_icons": len(by_name),
        "total_files": len(files),
        "total_labels": sum(len(v) for v in categorized.values()),
        "variants": [{"key": k, "label": l} for k, l, _r in variants_cfg],
        "categories": cats_out,
        "alphabet": alpha,
        "all": [{"name": n, "files": by_name[n]} for n in sorted(by_name.keys())],
    }


def main():
    manifest = []
    for theme in THEMES:
        result = build_theme(theme)
        out_path = os.path.join(SVG_DIR, theme["file"])
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        manifest.append({
            "name": theme["name"],
            "file": theme["file"],
            "default": bool(theme.get("default", False)),
        })
        sz = os.path.getsize(out_path)
        print(f"[{theme['name']}] icons={result['total_icons']} files={result['total_files']} "
              f"variants={len(result['variants'])} labels={result['total_labels']} "
              f"-> {theme['file']} ({sz/1024:.1f} KB)")

    manifest_path = os.path.join(SVG_DIR, "themes.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    print(f"Wrote {len(manifest)} themes -> themes.json")
```

- [ ] **Step 4: 运行构建脚本，确认无报错**

Run: `python _build_index.py`

Expected: 打印 4 行 `[<主题>] icons=... files=... variants=...`，再加一行 `Wrote 4 themes -> themes.json`，无异常退出。

- [ ] **Step 5: 自动化断言校验各主题产物**

Run（一条命令，逐主题校验结构与已知计数）：

```bash
python -c "
import json
m = json.load(open('themes.json', encoding='utf-8'))
assert len(m) == 4, m
assert sum(1 for t in m if t.get('default')) == 1, m

mat = json.load(open('icons-material.json', encoding='utf-8'))
assert mat['total_files'] == 5931, mat['total_files']
assert [v['key'] for v in mat['variants']] == ['outline', 'filled'], mat['variants']
assert mat['all'][0]['files'], 'material item missing files'
assert all('/' in v for it in mat['all'] for v in it['files'].values()), 'paths must use forward slash'

sol = json.load(open('icons-solar.json', encoding='utf-8'))
assert sol['total_files'] == 7410, sol['total_files']
assert len(sol['variants']) == 6, sol['variants']
assert sol['total_icons'] == 1235, sol['total_icons']

luc = json.load(open('icons-lucide.json', encoding='utf-8'))
assert luc['total_files'] == 2019, luc['total_files']
assert len(luc['variants']) == 1, luc['variants']

tab = json.load(open('icons-tabler.json', encoding='utf-8'))
assert tab['total_files'] == 6378, tab['total_files']
assert len(tab['variants']) == 1, tab['variants']

print('ALL BUILD ASSERTIONS PASSED')
"
```

Expected: `ALL BUILD ASSERTIONS PASSED`

- [ ] **Step 6: 抽查 Material 形态配对未退化**

Run（确认同一个图标名同时拿到 filled 与 outline，证明后缀顺序正确）：

```bash
python -c "
import json
d = json.load(open('icons-material.json', encoding='utf-8'))
hit = next(it for it in d['all'] if it['name'] == 'add-circle')
assert 'filled' in hit['files'] and 'outline' in hit['files'], hit
assert hit['files']['filled'].endswith('add-circle-rounded.svg'), hit
assert hit['files']['outline'].endswith('add-circle-outline-rounded.svg'), hit
print('material pairing OK')
"
```

Expected: `material pairing OK`

- [ ] **Step 7: 提交构建脚本与新产物**

```bash
git add _build_index.py themes.json icons-material.json icons-lucide.json icons-solar.json icons-tabler.json
git commit -m "$(cat <<'EOF'
构建脚本支持多主题：THEMES 配置 + 通用形态解析

每主题输出 icons-<theme>.json（item 形态泛化为 files: {variant: path}），
并生成 themes.json 清单。旧 icons.json 暂留，待前端切换后移除。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

注：此处**不要** `git add icons.json`，也不要删除它——它仍被旧前端读取，保持预览可用。

---

## Task 2: 前端改为多主题 + 动态形态切换

**Files:**
- Modify: `index.html`（header、`<style>`、`<script>` 多处）

完成后前端读取 `themes.json` + `icons-*.json`，旧 `icons.json` 不再被引用（但仍留盘，Task 3 删除）。

- [ ] **Step 1: header 加主题 `<select>`，标题加 id**

把 `index.html` 中现有的 header 块：

```html
  <header>
    <h1>Material Symbols 图标库</h1>
    <div class="search-wrap">
```

替换为：

```html
  <header>
    <h1 id="brand">图标库</h1>
    <select id="themeSelect" class="theme-select"></select>
    <div class="search-wrap">
```

并把形态切换器容器清空（删除其内部三个静态 `<button>`，保留容器），即把：

```html
    <div class="variant-switch" id="variantSwitch">
      <button data-variant="filled" class="active">填充</button>
      <button data-variant="outline">描边</button>
      <button data-variant="both">双形态</button>
    </div>
```

替换为：

```html
    <div class="variant-switch" id="variantSwitch"></div>
```

- [ ] **Step 2: 增补 CSS（主题下拉框 + 多形态卡片自适应）**

在 `index.html` 的 `<style>` 中，紧跟 `.variant-switch button.active { ... }` 规则之后，插入：

```css
  .theme-select {
    height: 32px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    font-size: 13px;
    padding: 0 8px;
    color: var(--text);
    cursor: pointer;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
  }
  .theme-select:focus { border-color: var(--accent); background: var(--panel); }
```

把现有的 `.card.both` 两条规则（固定 72px / 32px，仅适合 2 形态）：

```css
  .card.both .icon-frame {
    width: 72px;
    gap: 4px;
    flex-direction: row;
  }
  .card.both .icon-frame img,
  .card.both .icon-frame .placeholder {
    width: 32px;
    height: 32px;
    object-fit: contain;
  }
```

替换为（可换行，适配 Solar 的 6 形态）：

```css
  .card.both .icon-frame {
    width: 88px;
    gap: 3px;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
  }
  .card.both .icon-frame img,
  .card.both .icon-frame .placeholder {
    width: 26px;
    height: 26px;
    object-fit: contain;
  }
```

并把详情条预览区改为可换行（适配多形态并排）：

```css
  .detail-row .preview {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-shrink: 0;
  }
```

改为：

```css
  .detail-row .preview {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    flex-shrink: 0;
    flex-wrap: wrap;
    max-width: 320px;
  }
```

- [ ] **Step 3: 改 `<script>` 顶部常量与 state**

把：

```js
const DATA_URL = "icons.json";
```

替换为：

```js
const THEMES_URL = "themes.json";
```

把 `state` 对象：

```js
const state = {
  data: null,
  mode: "all",       // "all" | "category:<name>"
  variant: "filled", // "filled" | "outline" | "both"
  query: "",
  filtered: [],
};
```

替换为：

```js
const state = {
  themes: [],        // themes.json 清单
  theme: "",         // 当前主题显示名
  data: null,        // 当前主题的 icons-<theme>.json
  mode: "all",       // "all" | "category:<name>"
  variant: null,     // 当前选中的 variant key；"all" = 显示全部形态
  query: "",
  filtered: [],
};
```

- [ ] **Step 4: 扩充 `el` 对象**

把 `el` 对象里的：

```js
  variantSwitch: document.getElementById("variantSwitch"),
  stats: document.getElementById("stats"),
```

替换为：

```js
  brand: document.getElementById("brand"),
  themeSelect: document.getElementById("themeSelect"),
  variantSwitch: document.getElementById("variantSwitch"),
  stats: document.getElementById("stats"),
```

- [ ] **Step 5: 改 `fillCard()` 读 `files` 映射**

把现有整个 `fillCard(card)` 函数替换为：

```js
function fillCard(card) {
  const name = card.dataset.name;
  const files = JSON.parse(card.dataset.files || "{}");
  const variant = state.variant;
  const frame = card.querySelector(".icon-frame");
  frame.innerHTML = "";

  function makeImg(file, isOutline) {
    const img = document.createElement("img");
    img.src = file;
    img.alt = name;
    img.title = name;
    img.loading = "lazy";
    img.decoding = "async";
    if (isOutline) img.classList.add("is-outline");
    return img;
  }

  const variantKeys = (state.data && state.data.variants || []).map(v => v.key);

  if (variant === "all") {
    for (const k of variantKeys) {
      if (files[k]) frame.appendChild(makeImg(files[k], k === "outline"));
    }
  } else if (files[variant]) {
    frame.appendChild(makeImg(files[variant], variant === "outline"));
  } else {
    // 当前形态不可用时回退到任意可用形态
    const fb = variantKeys.find(k => files[k]);
    if (fb) frame.appendChild(makeImg(files[fb], fb === "outline"));
  }
}
```

- [ ] **Step 6: 改 `renderGrid()` 的卡片创建段读 `files`**

把 `renderGrid()` 里创建卡片的循环体：

```js
  for (const it of items) {
    const card = document.createElement("div");
    card.className = "card";
    if (state.variant === "both") card.classList.add("both");
    card.dataset.name = it.name;
    card.dataset.filled = it.filled ? "1" : "0";
    card.dataset.outline = it.outline ? "1" : "0";
    card.dataset.filledFile = it.filled || "";
    card.dataset.outlineFile = it.outline || "";
    card.dataset.loaded = "0";
    card.title = it.name + (it.filled ? "" : " (仅描边)") + (it.outline ? "" : " (仅填充)");
```

替换为：

```js
  for (const it of items) {
    const card = document.createElement("div");
    card.className = "card";
    if (state.variant === "all") card.classList.add("both");
    card.dataset.name = it.name;
    card.dataset.files = JSON.stringify(it.files || {});
    card.dataset.loaded = "0";
    card.title = it.name;
```

（该循环其余部分——`frame`/`placeholder`/`label`/`appendChild`/`addEventListener`——保持不变。）

- [ ] **Step 7: 改 `toggleDetail()` 的预览区与文件名区读 `files`**

在 `toggleDetail(card, item)` 中，把构建 variants 与预览的这段：

```js
  const preview = document.createElement("div");
  preview.className = "preview";
  const variants = [];
  if (item.filled) variants.push({ file: item.filled, label: item.outline ? "填充" : "" });
  if (item.outline) variants.push({ file: item.outline, label: item.filled ? "描边" : "" });
  for (const v of variants) {
```

替换为：

```js
  const preview = document.createElement("div");
  preview.className = "preview";
  const allVariants = state.data.variants || [];
  const showLabels = allVariants.length > 1;
  const variants = allVariants
    .map(v => ({ file: (item.files && item.files[v.key]) || null, label: v.label }))
    .filter(v => v.file);
  for (const v of variants) {
```

并把循环内决定是否显示形态标签的条件：

```js
    if (v.label) {
      const tag = document.createElement("div");
```

替换为（多形态才显示标签）：

```js
    if (showLabels && v.label) {
      const tag = document.createElement("div");
```

再把「复制文件名」按钮里取默认文件的那行：

```js
    const text = item.filled || item.outline || item.name;
```

替换为：

```js
    const text = (item.files && Object.values(item.files)[0]) || item.name;
```

（`toggleDetail` 其余逻辑——`add-pick-btn` 的 fetch、路径目录前缀显示、分类 chips、关闭/打开备选目录按钮——保持不变；它们用的是 `v.file` 与 `item.name`，无需改动。）

- [ ] **Step 8: 新增 `renderVariantSwitcher()` 并改写形态切换事件**

在 `renderSidebar()` 函数定义之前，新增：

```js
// 形态切换器：按当前主题 data.variants 动态生成；末尾「全部」= 并排显示所有形态。
// 单形态主题（variants.length <= 1）隐藏整个切换器。
function renderVariantSwitcher() {
  el.variantSwitch.innerHTML = "";
  const variants = (state.data && state.data.variants) || [];
  if (variants.length <= 1) {
    el.variantSwitch.style.display = "none";
    state.variant = variants[0] ? variants[0].key : "all";
    return;
  }
  el.variantSwitch.style.display = "";
  for (const v of variants) {
    const b = document.createElement("button");
    b.dataset.variant = v.key;
    b.textContent = v.label;
    el.variantSwitch.appendChild(b);
  }
  const allBtn = document.createElement("button");
  allBtn.dataset.variant = "all";
  allBtn.textContent = "全部";
  el.variantSwitch.appendChild(allBtn);
  // 选中：优先沿用 state.variant，否则默认第一个
  let target = state.variant;
  if (target !== "all" && !variants.some(v => v.key === target)) target = null;
  const pick = target || variants[0].key;
  state.variant = pick;
  const btn = el.variantSwitch.querySelector(`button[data-variant="${pick}"]`);
  if (btn) btn.classList.add("active");
}
```

把现有形态切换的点击处理器：

```js
el.variantSwitch.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-variant]");
  if (!btn) return;
  state.variant = btn.dataset.variant;
  el.variantSwitch.querySelectorAll("button").forEach(b => {
    b.classList.toggle("active", b === btn);
  });
  // 变体变化后重新填充已渲染的卡片（不重建 DOM，避免抖动）
  for (const card of el.grid.children) {
    card.classList.toggle("both", state.variant === "both");
    card.dataset.loaded = "0";
    const frame = card.querySelector(".icon-frame");
    frame.innerHTML = "";
    const ph = document.createElement("div");
    ph.className = "placeholder";
    frame.appendChild(ph);
    io.observe(card);
  }
});
```

替换为：

```js
el.variantSwitch.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-variant]");
  if (!btn) return;
  state.variant = btn.dataset.variant;
  el.variantSwitch.querySelectorAll("button").forEach(b => {
    b.classList.toggle("active", b === btn);
  });
  // 形态变化后重新填充已渲染的卡片（不重建 DOM，避免抖动）
  for (const card of el.grid.children) {
    card.classList.toggle("both", state.variant === "all");
    card.dataset.loaded = "0";
    const frame = card.querySelector(".icon-frame");
    frame.innerHTML = "";
    const ph = document.createElement("div");
    ph.className = "placeholder";
    frame.appendChild(ph);
    io.observe(card);
  }
});
```

- [ ] **Step 9: 新增 `loadTheme()`，改写 `init()`，加主题下拉事件**

把现有整个 `init()` 函数替换为下面三个函数（`init` + `loadTheme` + 主题切换事件）：

```js
async function loadTheme(file, themeName) {
  el.loading.classList.add("visible");
  el.loading.textContent = "正在加载图标数据...";
  el.loading.style.background = "";
  el.loading.style.color = "";
  try {
    const res = await fetch(file);
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.data = await res.json();
    state.theme = themeName;
    el.brand.textContent = `${themeName} 图标库`;
    el.stats.textContent = `${state.data.total_icons} 个图标 · ${state.data.total_files} 个 SVG 文件 · 多标签`;
    state.variant = null;
    renderVariantSwitcher();
    renderSidebar();
    selectMode("all");
  } catch (err) {
    el.loading.classList.add("visible");
    el.loading.textContent = "加载失败: " + err.message;
    el.loading.style.background = "#fee2e2";
    el.loading.style.color = "#dc2626";
    console.error(err);
  } finally {
    el.loading.classList.remove("visible");
  }
}

async function init() {
  el.loading.classList.add("visible");
  try {
    const res = await fetch(THEMES_URL);
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.themes = await res.json();
    el.themeSelect.innerHTML = "";
    for (const t of state.themes) {
      const opt = document.createElement("option");
      opt.value = t.file;
      opt.textContent = t.name;
      if (t.default) opt.selected = true;
      el.themeSelect.appendChild(opt);
    }
    const def = state.themes.find(t => t.default) || state.themes[0];
    await loadTheme(def.file, def.name);
  } catch (err) {
    el.loading.classList.add("visible");
    el.loading.textContent = "加载失败: " + err.message + "（请通过本地 HTTP 服务器打开，例如 python -m http.server）";
    el.loading.style.background = "#fee2e2";
    el.loading.style.color = "#dc2626";
    console.error(err);
  }
}

el.themeSelect.addEventListener("change", (e) => {
  const file = e.target.value;
  const t = state.themes.find(x => x.file === file);
  loadTheme(file, t ? t.name : file);
});

init();
```

（这同时移除了文件末尾原先单独的 `init();` 调用——它已包含在上块末尾。）

- [ ] **Step 10: 浏览器手动校验**

启动服务：`python server.py`，浏览器打开 `http://127.0.0.1:8765/`，逐项确认：

- [ ] 默认加载 Material Symbols：标题为「Material Symbols 图标库」，stats 显示 `2965 个图标 · 5931 个 SVG 文件`，形态切换器有「描边 / 填充 / 全部」三个按钮，默认选中「填充」。
- [ ] 顶部「主题」下拉含 4 项，默认 Material。
- [ ] 切到 **Lucide**：标题变「Lucide 图标库」，stats ≈ `2019 个图标 · 2019 个 SVG 文件`，**形态切换器整条隐藏**，网格显示单一形态图标。
- [ ] 切到 **Solar**：形态切换器变为 6 个形态按钮 +「全部」；点不同形态，网格就地换图不抖动；点「全部」每张卡片并排显示 6 个小图标。
- [ ] 切到 **Tabler Icons**：单形态，切换器隐藏，stats ≈ `6378 个图标 · 6378 个 SVG 文件`。
- [ ] 任一主题点击卡片：详情条出现，列出该图标所有形态（多形态主题带形态标签），每个形态各有「添加备选」按钮；点「添加备选」变「已添加 ✓」，且 `Picked/` 里出现该 SVG。
- [ ] 搜索框在任意主题下都能按名字过滤；侧栏分类可点选并过滤。
- [ ] 切回 Material，字母索引仍可用，点字母能滚动定位且不被 sticky 遮挡。
- [ ] 控制台无报错。

- [ ] **Step 11: 提交前端**

```bash
git add index.html
git commit -m "$(cat <<'EOF'
前端支持多主题切换与动态形态切换器

加载 themes.json 建主题下拉，按需 fetch 各 icons-<theme>.json；
形态切换器按主题 variants 动态生成，item 改读 files 映射。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 清理旧产物 + 更新文档

**Files:**
- Delete: `icons.json`
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: 删除已被取代的旧 `icons.json`**

```bash
git rm icons.json
```

- [ ] **Step 2: 更新 `CLAUDE.md`**

把 `CLAUDE.md` 中「常用命令」段里这句：

```
# 重建图标索引（新增/删除/重命名 SVG 文件，或修改 CATEGORIES 后都要跑一次）
python _build_index.py
```

后面补一句说明产物变化（在该代码块内追加注释行）：

```
# 重建图标索引（新增/删除/重命名 SVG 文件，或修改 THEMES/CATEGORIES 后都要跑一次）
# 产物：themes.json（主题清单）+ 各 icons-<theme>.json；不再生成单一 icons.json
python _build_index.py
```

把「架构」第 2 节里描述构建脚本的两条要点：

```
   - `THEME_DIRS`：扩展新图标主题的入口，每项是一个被扫描 `.svg` 的子目录。
   - `CATEGORIES`：一份硬编码的 `(中文分类名, 关键词列表, 匹配模式)` 列表。
```

替换为：

```
   - `THEMES`：扩展新图标主题的入口，每项是一个主题配置（目录、显示名、输出文件名、形态后缀列表 `variants`、兜底形态、可选专属分类关键词）。形态由通用的「后缀优先」算法解析，item 形态泛化为 `files: {variantKey: 路径}`。
   - `CATEGORIES`：默认分类关键词 `(中文分类名, 关键词列表, 匹配模式)`；各主题可在 `THEMES` 里用 `categories` 覆盖。
```

在「架构」第 3 节 `index.html` 要点列表里，把首句：

```
   3. **`index.html`** —— 整个预览应用是单个 HTML 文件，CSS/JS 全部内联。它只 `fetch` 一次 `icons.json`，之后所有渲染都在客户端完成；
```

替换为：

```
   3. **`index.html`** —— 整个预览应用是单个 HTML 文件，CSS/JS 全部内联。启动时先 `fetch` 一次 `themes.json` 建主题下拉，切换主题时再 `fetch` 对应的 `icons-<theme>.json`；之后所有渲染都在客户端完成；
```

并在「改这个仓库时」段，把：

```
- **新增图标**：把 `.svg` 按命名约定放进 `Material Symbols/`，然后 `python _build_index.py`。
```

替换为：

```
- **新增图标**：把 `.svg` 按命名约定放进对应主题目录（如 `Material Symbols/`、`Lucide/`），然后 `python _build_index.py`。
- **新增一种主题**：编辑 `_build_index.py` 的 `THEMES`，加一项（含 `dir`/`name`/`file`/`variants`/`fallback_variant`），然后 `python _build_index.py`。
```

把该段最后一条关于 `icons.json` 的：

```
- `index.html`、`icons.json`、`预览.bat` 都已纳入版本管理，这样一份全新 checkout 不用跑构建就能预览；结构变化后要同步更新。
```

替换为：

```
- `index.html`、`themes.json`、各 `icons-<theme>.json`、`预览.bat` 都已纳入版本管理，这样一份全新 checkout 不用跑构建就能预览；结构变化后要同步更新。
```

- [ ] **Step 3: 更新 `README.md`**

先读 `README.md` 确认现有措辞，然后把任何「内置 Google Material Symbols（…）」之类的单主题描述，更新为四主题列表（Material Symbols / Lucide / Solar / Tabler Icons），并加一句「顶部可切换主题，形态切换器随主题变化」。具体替换文本以 README 现状为准（保持其原有语气与结构），不要改动与主题无关的段落。

- [ ] **Step 4: 重新构建确保产物一致**

Run: `python _build_index.py`

Expected: 4 行主题输出 + `Wrote 4 themes -> themes.json`，且不应再生成 `icons.json`。

- [ ] **Step 5: 全流程回归校验**

启动 `python server.py`，浏览器确认：默认 Material 正常 → 切换四主题均正常 → 详情条添加备选正常 → 关闭后 `icons.json` 已不存在、无 404（控制台干净）。

- [ ] **Step 6: 提交清理与文档**

```bash
git add -A
git commit -m "$(cat <<'EOF'
移除旧 icons.json，同步 CLAUDE.md/README 为多主题结构

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review 记录

- **Spec 覆盖**：构建脚本 THEMES/通用解析（Task 1）、themes.json+icons-*.json+files 泛化（Task 1）、前端 ComboBox+动态形态切换器+files 读取（Task 2）、默认 Material（Task 2 Step 9/10）、文档同步与旧产物删除（Task 3）——spec 各节均有对应任务。
- **占位符扫描**：无 TBD/TODO；每个代码步骤都给了完整代码。
- **类型/命名一致性**：variant key 用 `"all"` 作为「全部」哨兵贯穿 fillCard/renderGrid/renderVariantSwitcher/事件处理；item 统一用 `it.files`（构建侧 `files`）与 `card.dataset.files`；`state.variant` 在 loadTheme 中置 null 由 renderVariantSwitcher 落定——前后一致。
- **顺序陷阱**：THEMES 各 `variants` 已按长后缀在前排列，构建 Step 6 单独验证 Material 配对未退化。
