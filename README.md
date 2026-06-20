# SvgResources · 主题 SVG 图标浏览库

一个用于**搜集主题 SVG 图标并提供本地预览**的小工具集。当前内置 Google [Material Symbols](https://fonts.google.com/icons) 图标集，配套一个零依赖的纯静态浏览器界面与一个 Python 构建脚本。

- 5931 个 SVG 文件（约 2965 个图标 × 填充 / 描边两种形态）
- 按主题关键词自动归类（50+ 分类，单图标可属多分类）
- 支持按字母索引、按分类、按名称搜索浏览
- 点击图标查看详情、复制文件名、在分类间跳转

## 目录结构

```
SvgResources/
├── Material Symbols/      # 主题图标源文件（.svg）
│   ├── add-rounded.svg
│   ├── add-outline-rounded.svg
│   └── ...
├── _build_index.py        # 扫描 SVG 目录，生成 icons.json
├── icons.json             # 构建产物：图标元数据，供 index.html 懒加载
├── index.html             # 纯静态预览界面（HTML + 内联 JS/CSS，无外部依赖）
└── 预览.bat               # 一键启动本地 HTTP 服务器并打开浏览器
```

## 快速开始

### 方式一：一键启动（Windows）

双击 `预览.bat`，脚本会在 `http://127.0.0.1:8765/` 启动一个本地 HTTP 服务器并自动打开浏览器。

> 必须通过 HTTP 服务器访问，直接双击 `index.html` 打开（`file://` 协议）会被浏览器拦截 `icons.json` 的 `fetch` 请求。

### 方式二：手动启动

```bash
python -m http.server 8765 --bind 127.0.0.1
```

然后浏览器访问 <http://127.0.0.1:8765/>。

## 重新构建索引

当你新增、删除或重命名 `Material Symbols/` 下的 SVG 文件后，需要重新生成 `icons.json`：

```bash
python _build_index.py
```

构建脚本会：

1. 扫描 `Material Symbols/` 下所有 `.svg` 文件；
2. 通过文件名归一化（去掉 `-rounded` / `-outline-rounded` / `.svg` 后缀）将「填充」和「描边」两种形态合并为同一图标；
3. 根据 `_build_index.py` 中预定义的关键词分类表 `CATEGORIES`，把每个图标打上**一个或多个**分类标签；
4. 按图标名首字母生成 A–Z 字母索引；
5. 输出 `icons.json`（包含 `total_icons`、`categories`、`alphabet`、`all` 等字段）。

## 添加新图标

1. 把 SVG 文件按命名规范放入 `Material Symbols/`：
   - 填充形态：`<name>-rounded.svg`
   - 描边形态：`<name>-outline-rounded.svg`
2. 运行 `python _build_index.py` 重建索引。
3. 刷新浏览器即可看到新图标。

如果希望新图标被归类到某一主题，编辑 `_build_index.py` 的 `CATEGORIES` 列表，在对应分类的关键词数组里追加匹配词。匹配规则（见 `match_categories`）：

- 以 `-` 结尾的关键词按前缀匹配（如 `ev-`、`key-`）；
- 普通关键词按完整词元匹配（前后以 `-` 或字符串边界包裹），避免 `ear` 命中 `gear` 这类子串误匹配；
- 分类按 `CATEGORIES` 定义顺序匹配，先命中先归属，且**一个图标可同时进入多个分类**。

## 添加新的图标主题

`_build_index.py` 中的 `THEME_DIRS` 预留了多主题扩展位。把新主题目录加入该列表，并确保其 SVG 文件遵循与 Material Symbols 一致的命名规范，重建索引即可：

```python
THEME_DIRS = [
    ("Material Symbols", "Material Symbols"),
    # ("Tabler Icons", "Tabler Icons"),
]
```

## 浏览器界面特性

- **懒加载**：使用 `IntersectionObserver` 仅渲染进入视口的图标 `<img>`，应对数千张图标也能流畅滚动。
- **三种形态切换**：填充 / 描边 / 双形态同卡对比。
- **搜索**：实时按图标名子串过滤（带 120ms 防抖）。
- **字母索引条**：浏览「全部」时显示 A–Z 跳转按钮（搜索时不显示，避免字母不全）。
- **详情条**：点击图标在顶部展开详情，显示文件路径、所属分类、复制文件名按钮，并支持在 sticky 状态下随滚动冻结。

## 依赖

- 运行预览：任意现代浏览器 + Python 3（仅用于启动 `http.server`）。
- 构建脚本：Python 3 标准库，无第三方依赖。

## 许可

图标文件来源于 Google Material Symbols，遵循 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)。
本仓库的构建脚本与预览界面代码可按需自行修改使用。
