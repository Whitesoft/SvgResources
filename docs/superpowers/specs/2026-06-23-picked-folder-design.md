# 备选目录功能设计

日期：2026-06-23
主题：在图标详情条增加"添加至备选"与"打开备选目录"功能

## 背景与目标

当前预览应用（`index.html` + `python -m http.server`）只能浏览图标。用户希望在浏览过程中把心仪的 SVG 收集到一个本地目录，便于后续挑选、交给设计师或导入到其他工具。

核心诉求：

1. 详情条中，对每个可用的形态（填充 / 描边）独立提供"添加备选"入口。
2. 详情条级别提供"打开备选目录"全局入口。
3. 拷贝目标目录位于项目根目录下，命名 `Picked/`。
4. 该目录纳入 `.gitignore`，不进版本库。
5. 重名时直接覆盖，候选集保持干净。

## 约束

- 浏览器 JS 不能直接写磁盘，也不能打开 OS 资源管理器 —— 必须由本地后端完成。
- 项目风格为零依赖 Python + 单文件 HTML/JS，新功能不能引入 npm / pip 依赖。
- 不能破坏现有"全新 checkout 不跑构建就能预览"的体验（即前端仍然零安装、开箱即用）。

## 架构

整体由四个改动组成：

| 改动 | 类型 | 说明 |
| --- | --- | --- |
| `server.py` | 新增 | 基于 `http.server` 的本地服务器；既伺服静态文件，又提供两个 POST 端点 |
| `预览.bat` | 修改 | 启动命令由 `python -m http.server` 改为 `python server.py` |
| `index.html` | 修改 | 详情条 UI 改造 + 新增按钮交互 |
| `Picked/` | 新增目录 | 由 server 启动时 `makedirs(exist_ok=True)` 自动创建 |

`Picked/` 加入 `.gitignore`，不入版本库。

## 后端 API

### `POST /api/pick`

请求体（JSON）：

```json
{ "file": "Material Symbols/add-rounded.svg" }
```

处理流程：

1. 解析 `body.file` 为相对项目根的路径。
2. **路径校验**：`os.path.realpath` 后的绝对路径必须仍以项目根目录开头；不通过返回 400。
3. 校验源文件存在；不存在返回 404。
4. 目标路径 = `Picked/<basename>`（剥掉所有目录前缀，所有主题 SVG 平铺到 `Picked/` 下）。
5. `shutil.copy2(src, dest)` 直接覆盖。
6. 返回 `{ "ok": true, "dest": "Picked/add-rounded.svg" }`。

失败响应统一为 `{ "ok": false, "error": "<message>" }`，HTTP 状态码非 2xx。

### `POST /api/open-folder`

无请求体。跨平台打开 `Picked/` 目录：

- Windows：`os.startfile(path)`
- macOS：`subprocess.run(["open", path])`
- Linux：`subprocess.run(["xdg-open", path])`

返回 `{ "ok": true }`。

### 安全

- 只允许 `POST`，且路径白名单限定为项目根目录下。
- `realpath` 后再 `startswith` 检查，防止符号链接或 `../` 穿越。
- 服务监听 `127.0.0.1`，不接受外部连接（与现状一致）。

## 前端 UI 改造

### 详情条布局

现有 `.preview` 容器从"一行多个 `<img>`"改为"一行多个 `.preview-item`"。每个 `.preview-item` 结构：

```
┌─────┐
│ img │
└─────┘
[ 添加备选 ]   ← 小按钮；若有双形态，文案区分为 "添加填充" / "添加描边"
```

单形态图标：一个 item 一个按钮。
双形态图标：两个 item 并排，各自带按钮。

### 全局按钮

详情条右侧（现有 `复制文件名` 按钮旁）新增 **`打开备选目录`** 按钮，使用现有 `.copy-btn` 视觉风格。

### 点击反馈

沿用现有 `copy-btn` 的视觉范式（成功 → 文案临时变绿 `已添加 ✓`，1.2s 还原；失败 → 变红 `失败`）。

`打开备选目录` 按钮点击后：成功则按钮文案临时变 `已打开 ✓`，失败则变红。

## 错误处理

| 场景 | 行为 |
| --- | --- |
| 路径穿越 / 不在项目根下 | HTTP 400，前端按钮变红 |
| 源文件不存在 | HTTP 404，前端按钮变红 |
| 拷贝 IO 失败 | HTTP 500，前端按钮变红 |
| `打开备选目录` 调用失败 | HTTP 500，前端按钮变红 |
| 网络错误 / server 挂了 | 前端 `fetch` catch，按钮变红 + `console.error` |

## 测试方式

启动 `预览.bat` 后手动验证：

1. 双形态图标详情条出现两个独立 `.preview-item`，每个下面都有"添加"按钮。
2. 点击后 `Picked/` 出现对应 SVG 文件。
3. 同名二次点击 → `Picked/` 内文件 mtime 更新（覆盖成功）。
4. "打开备选目录" → 系统资源管理器弹出并定位到 `Picked/`。
5. 单形态图标 → 详情条只出现一个预览一个按钮。
6. 安全验证：`curl -X POST http://127.0.0.1:8765/api/pick -d '{"file":"../../../etc/passwd"}'` 返回 400。
