# SvgResources · 主题 SVG 图标浏览库

一个用于**搜集主题 SVG 图标并提供本地预览**的小工具集。内置四套图标主题：Google [Material Symbols](https://fonts.google.com/icons)、[Lucide](https://lucide.dev/)、[Solar](https://www.figma.com/community/file/1165482076397295458)、[Tabler Icons](https://tabler.io/icons)，配套一个零依赖的纯静态浏览器界面与一个 Python 构建脚本。

- 多套主题，各主题独立的图标数量、形态数量与分类
- 顶部工具栏带**主题切换器**：切换主题即重新加载该主题的索引
- **形态切换器按主题动态生成**：Material 显示填充 / 描边；Solar 有 6 种形态；单形态主题（Lucide、Tabler）自动隐藏切换器
- 按主题关键词自动归类（单图标可属多分类）
- 支持按字母索引、按分类、按名称搜索浏览
- 点击图标查看详情、复制文件名、把图标添加到本地备选目录、在分类间跳转

## 目录结构

```
SvgResources/
├── Themes/                # 所有主题 SVG 源文件与构建产物 JSON 都收纳在此
│   ├── Material Symbols/  # Material Symbols 主题源文件（.svg）
│   ├── Lucide/            # Lucide 主题源文件（.svg）
│   ├── Solar/             # Solar 主题源文件（.svg）
│   ├── Tabler Icons/      # Tabler Icons 主题源文件（.svg）
│   ├── Carbon/            # Carbon 主题源文件（.svg）
│   ├── Fluent UI System Icons/  # Fluent UI 主题源文件（.svg）
│   ├── themes.json        # 构建产物：主题清单，供 index.html 建主题下拉
│   ├── icons-material.json   # 构建产物：Material Symbols 图标元数据
│   ├── icons-lucide.json     # 构建产物：Lucide 图标元数据
│   ├── icons-solar.json      # 构建产物：Solar 图标元数据
│   ├── icons-tabler.json     # 构建产物：Tabler Icons 图标元数据
│   ├── icons-carbon.json     # 构建产物：Carbon 图标元数据
│   └── icons-fluent.json     # 构建产物：Fluent UI 图标元数据
├── _build_index.py        # 扫描 Themes/ 下各主题 SVG，生成 Themes/themes.json + 各 icons-<theme>.json
├── index.html             # 纯静态预览界面（HTML + 内联 JS/CSS，无外部依赖）
├── server.py              # 本地预览服务器（静态服务 + /api/pick + /api/open-folder）
├── download_svg_from_Iconify.py  # 从 Iconify 下载图标集到 Themes/ 下，并自动重建索引
├── 预览.bat               # 一键启动本地 HTTP 服务器并打开浏览器
└── Picked/                # 运行时目录：用户挑选的 SVG（.gitignore 已忽略）
```

## 快速开始

### 方式一：一键启动（Windows）

双击 `预览.bat`，脚本会在 `http://127.0.0.1:8765/` 启动一个本地 HTTP 服务器并自动打开浏览器。

> 必须通过 HTTP 服务器访问，直接双击 `index.html` 打开（`file://` 协议）会被浏览器拦截 `Themes/themes.json` / `Themes/icons-<theme>.json` 的 `fetch` 请求。

### 方式二：手动启动

```bash
python server.py
```

`server.py` 监听 `127.0.0.1:8765`，提供静态文件服务，外加两个端点供前端"添加备选 / 打开备选目录"按钮调用：

- `POST /api/pick` — body `{ "file": "<主题目录>/<name>.svg" }`，把该 SVG 拷贝到 `Picked/`（同名直接覆盖）。
- `POST /api/open-folder` — 在系统资源管理器中打开 `Picked/`。

如果只想要纯静态浏览、不需要备选功能，也可以退回 `python -m http.server 8765 --bind 127.0.0.1`。

然后浏览器访问 <http://127.0.0.1:8765/>。

## 重新构建索引

当你新增、删除或重命名任意主题目录下的 SVG 文件后，需要重新生成索引：

```bash
python _build_index.py
```

构建脚本会：

1. 遍历 `THEMES` 中配置的每个主题目录，扫描其下所有 `.svg` 文件；
2. 按各主题的 `variants` 形态后缀列表做「后缀优先」解析，把同一图标的多个形态合并为一个 item（形态泛化为 `files: {variantKey: 路径}`）；
3. 根据分类关键词表（默认 `CATEGORIES`，各主题可用专属 `categories` 覆盖）把每个图标打上**一个或多个**分类标签；
4. 按图标名首字母生成 A–Z 字母索引；
5. 为每个主题输出一份 `Themes/icons-<theme>.json`，并汇总输出主题清单 `Themes/themes.json`。

> 不再生成单一 `icons.json`；前端启动时先读 `Themes/themes.json` 建主题下拉，切换主题时再读对应的 `Themes/icons-<theme>.json`。

## 添加新图标

1. 把 SVG 文件按对应主题的命名规范放入相应主题目录（如 `Themes/Material Symbols/`、`Themes/Lucide/`）。
2. 运行 `python _build_index.py` 重建索引。
3. 刷新浏览器即可看到新图标。

如果希望新图标被归类到某一主题，编辑 `_build_index.py` 的分类配置（默认 `CATEGORIES`，或某主题专属的 `categories`），在对应分类的关键词数组里追加匹配词。匹配规则（见 `match_categories`）：

- 以 `-` 结尾的关键词按前缀匹配（如 `ev-`、`key-`）；
- 普通关键词按完整词元匹配（前后以 `-` 或字符串边界包裹），避免 `ear` 命中 `gear` 这类子串误匹配；
- 分类按定义顺序匹配，先命中先归属，且**一个图标可同时进入多个分类**。

## 添加新的图标主题

`_build_index.py` 中的 `THEMES` 是多主题扩展入口。每项是一个主题配置（含 `dir` 目录、`name` 显示名、`file` 输出文件名、`variants` 形态后缀列表、`fallback_variant` 兜底形态、可选 `categories` 专属分类）。加好新主题目录并按其命名规范放入 SVG 后，重建索引即可。

## 浏览器界面特性

- **懒加载**：使用 `IntersectionObserver` 仅渲染进入视口的图标 `<img>`，应对数千张图标也能流畅滚动。
- **主题切换**：顶部下拉切换主题，切换时加载对应主题索引。
- **形态切换**：按主题动态生成（Material 填充 / 描边，Solar 6 种形态，单形态主题隐藏切换器），同卡可对比不同形态。
- **搜索**：实时按图标名子串过滤（带 120ms 防抖）。
- **字母索引条**：浏览「全部」时显示 A–Z 跳转按钮（搜索时不显示，避免字母不全）。
- **详情条**：点击图标在顶部展开详情，显示文件路径、所属分类、复制文件名按钮，并支持在 sticky 状态下随滚动冻结。
- **备选目录**：详情条中每个形态都有独立的「添加至备选」按钮，点击把对应 SVG 拷贝到项目根目录下的 `Picked/`（同名覆盖）；右侧「打开备选目录」按钮在系统资源管理器中打开该目录。

## 依赖

- 运行预览：任意现代浏览器 + Python 3（用于启动 `server.py`）。
- 构建脚本：Python 3 标准库，无第三方依赖。

## 许可

图标文件分别来源于各主题项目（Google Material Symbols、Lucide、Solar、Tabler Icons），遵循各自项目的开源许可。本仓库的构建脚本与预览界面代码可按需自行修改使用。
