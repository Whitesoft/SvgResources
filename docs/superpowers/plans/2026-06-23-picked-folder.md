# 备选目录功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图标详情条为每个形态独立提供"添加至备选"按钮，并支持"打开备选目录"，把选中 SVG 拷贝到项目根目录下的 `Picked/`。

**Architecture:** 新增一个零依赖 Python `server.py`（基于 `http.server`）取代 `python -m http.server`：保留静态文件能力，新增两个 POST 端点 `/api/pick`（带路径白名单校验，`shutil.copy2` 覆盖）和 `/api/open-folder`（跨平台打开目录）。`index.html` 详情条把单一 `.preview` 改为多个 `.preview-item`，每个预览图下方放一个"添加"按钮；右侧现有 `复制文件名` 旁新增 `打开备选目录` 按钮。

**Tech Stack:** Python 3 标准库（`http.server`、`shutil`、`subprocess`）；纯浏览器 JS（fetch POST）。

**测试策略说明：** 项目无测试框架（见 `CLAUDE.md`），TDD 改为：
- 后端：`curl` 写命令、运行看失败、实现、再看通过。
- 前端：手动验证清单（启动 server + 浏览器人肉点击）。

---

## File Structure

| 文件 | 操作 | 责任 |
| --- | --- | --- |
| `server.py` | 新建 | HTTP 服务器；静态文件 + 两个 POST 端点 |
| `预览.bat` | 修改 | 启动 `server.py` 而非 `python -m http.server` |
| `.gitignore` | 修改 | 新增 `Picked/` 规则 |
| `index.html` | 修改 | 详情条改造 + 两个新按钮的渲染与事件 |
| `Picked/` | 新建（运行时） | `server.py` 启动时 `makedirs(exist_ok=True)` 自动创建 |

---

### Task 1: 新建 `server.py`，提供静态服务 + `/api/pick` + `/api/open-folder`

**Files:**
- Create: `server.py`

- [ ] **Step 1: 写失败用例 — 启动前确认端口未占用、文件不存在**

Run: `ls server.py 2>/dev/null; echo "---"; curl -s -X POST http://127.0.0.1:8765/api/pick -H "Content-Type: application/json" -d '{"file":"Material Symbols/add-rounded.svg"}'`
Expected: 第一行空（`server.py` 还不存在）；curl 报 connection refused。

- [ ] **Step 2: 实现 `server.py`**

完整内容：

```python
"""SVG 备选目录本地预览服务器。

基于 http.server，提供：
- 静态文件服务（取代 `python -m http.server`）
- POST /api/pick        把项目根下某个 SVG 拷贝到 Picked/
- POST /api/open-folder 在系统资源管理器中打开 Picked/
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PICKED_DIR = ROOT / "Picked"
HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 65536


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return None

    def do_POST(self):
        if self.path == "/api/pick":
            self._handle_pick()
        elif self.path == "/api/open-folder":
            self._handle_open_folder()
        else:
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})

    def _handle_pick(self):
        data = self._read_json()
        if not isinstance(data, dict) or not data.get("file"):
            self._send_json(400, {"ok": False, "error": "missing 'file' field"})
            return
        rel = data["file"]
        src = (ROOT / rel).resolve()
        try:
            src.relative_to(ROOT)
        except ValueError:
            self._send_json(400, {"ok": False, "error": "path is outside project root"})
            return
        if not src.is_file():
            self._send_json(404, {"ok": False, "error": "source file not found"})
            return
        try:
            PICKED_DIR.mkdir(exist_ok=True)
            dest = PICKED_DIR / src.name
            shutil.copy2(src, dest)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(200, {"ok": True, "dest": "Picked/" + src.name})

    def _handle_open_folder(self):
        try:
            PICKED_DIR.mkdir(exist_ok=True)
            path = str(PICKED_DIR)
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(200, {"ok": True})


def main():
    PICKED_DIR.mkdir(exist_ok=True)
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving {ROOT} at http://{HOST}:{PORT}/")
    print(f"Picked dir: {PICKED_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 启动 server**

Run: `python server.py`
Expected: 终端打印 `Serving ... at http://127.0.0.1:8765/` 与 `Picked dir: ...`；进程阻塞。

- [ ] **Step 4: 用 curl 验证 `/api/pick` 正常拷贝**

新开终端：

Run: `curl -s -X POST http://127.0.0.1:8765/api/pick -H "Content-Type: application/json" -d '{"file":"Material Symbols/add-rounded.svg"}'`
Expected: 输出类似 `{"ok": true, "dest": "Picked/add-rounded.svg"}`。

验证 `Picked/` 出现文件：
Run: `ls Picked/`
Expected: 列出 `add-rounded.svg`。

- [ ] **Step 5: 用 curl 验证路径穿越被拒绝**

Run: `curl -s -o - -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8765/api/pick -H "Content-Type: application/json" -d '{"file":"../../../../Windows/win.ini"}'`
Expected: `HTTP 400`，body 含 `"path is outside project root"`，且 `Picked/` 下未新增 `win.ini`。

- [ ] **Step 6: 用 curl 验证源文件不存在返回 404**

Run: `curl -s -o - -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8765/api/pick -H "Content-Type: application/json" -d '{"file":"Material Symbols/no-such-icon-rounded.svg"}'`
Expected: `HTTP 404`，body 含 `"source file not found"`。

- [ ] **Step 7: 用 curl 验证 `/api/open-folder`**

Run: `curl -s -X POST http://127.0.0.1:8765/api/open-folder -w "\nHTTP %{http_code}\n"`
Expected: 系统资源管理器弹出并定位到 `Picked/`；`HTTP 200` + `{"ok": true}`。

- [ ] **Step 8: 停止 server**

在 server 终端按 Ctrl+C；确认退出。

- [ ] **Step 9: Commit**

```bash
git add server.py
git commit -m "新增 server.py：静态服务 + /api/pick + /api/open-folder"
```

---

### Task 2: 把 `Picked/` 加入 `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 在 `.gitignore` 末尾追加规则**

打开 `.gitignore`，在文件末尾追加：

```
# 备选目录（运行时由 server.py 创建，存放用户挑选的 SVG）
Picked/
```

- [ ] **Step 2: 验证 git 忽略生效**

Run: `git check-ignore -v Picked/`
Expected: 输出 `.gitignore:N:Picked/`（N 为行号），确认被忽略。

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "gitignore 新增 Picked/ 忽略规则"
```

---

### Task 3: 更新 `预览.bat` 启动 `server.py`

**Files:**
- Modify: `预览.bat`

- [ ] **Step 1: 替换启动命令**

打开 `预览.bat`，把最后一行：

```bat
python -m http.server 8765 --bind 127.0.0.1
```

改为：

```bat
python server.py
```

完整文件：

```bat
@echo off
cd /d "%~dp0"
title SVG 图标预览 - http://127.0.0.1:8765
echo.
echo  正在启动 HTTP 服务...
echo  访问地址: http://127.0.0.1:8765/
echo  关闭此窗口即可停止服务
echo.
start "" http://127.0.0.1:8765/
python server.py
```

> 注意：原文件中的中文显示乱码是 GBK/UTF-8 混淆问题，按上面这一版整体重写（用 UTF-8 保存）。如果重写后 cmd 窗口仍乱码，可改为 `chcp 65001 > nul` 后再加 echo，但优先按上面简洁版本走。

- [ ] **Step 2: 双击 `预览.bat` 验证启动**

Run: 双击 `预览.bat`
Expected: 浏览器自动打开 `http://127.0.0.1:8765/`，页面正常加载图标库（说明静态服务还在工作）。

- [ ] **Step 3: Commit**

```bash
git add 预览.bat
git commit -m "预览.bat 改为启动 server.py"
```

---

### Task 4: 改造详情条 — 每个形态独立预览 + 单独添加按钮

**Files:**
- Modify: `index.html` （`<style>` 段新增 `.preview-item` 相关样式；`toggleDetail()` 重写预览块构造）

- [ ] **Step 1: 在 `<style>` 段追加 `.preview-item` 样式**

定位到 `index.html` 中 `.detail-row .preview img` 规则附近（约 298-308 行），在原有 `.preview` 相关规则之后追加：

```css
  .detail-row .preview {
    flex-direction: column;
    gap: 0;
    align-items: stretch;
  }
  .detail-row .preview-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
  }
  .detail-row .preview-item:last-child { margin-bottom: 0; }
  .detail-row .preview-item img {
    width: 56px;
    height: 56px;
    object-fit: contain;
  }
  .detail-row .preview-item .variant-tag {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .detail-row .preview-item .add-pick-btn {
    padding: 4px 10px;
    background: var(--hover);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 11px;
    color: var(--muted);
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.12s;
  }
  .detail-row .preview-item .add-pick-btn:hover {
    background: var(--accent-soft);
    color: var(--accent);
    border-color: var(--accent);
  }
  .detail-row .preview-item .add-pick-btn.ok {
    background: #dcfce7;
    color: #15803d;
    border-color: #15803d;
  }
  .detail-row .preview-item .add-pick-btn.err {
    background: #fee2e2;
    color: #b91c1c;
    border-color: #b91c1c;
  }
```

> 注意：原 `.detail-row .preview img` 规则会和新的 `.preview-item img` 冲突，但后者优先级（更具体）会覆盖；如果观察到样式没生效，把原 `.detail-row .preview img` 整条删掉。

- [ ] **Step 2: 重写 `toggleDetail()` 中构造 `.preview` 的代码段**

定位 `index.html` 中 `toggleDetail()` 函数内的 "// 大图预览" 段落（约 611-627 行），把它整体替换为：

```javascript
  // 大图预览（每个形态一个独立 item，各自带"添加备选"按钮）
  const preview = document.createElement("div");
  preview.className = "preview";
  const variants = [];
  if (item.filled) variants.push({ file: item.filled, label: item.outline ? "填充" : "" });
  if (item.outline) variants.push({ file: item.outline, label: item.filled ? "描边" : "" });
  for (const v of variants) {
    const item_block = document.createElement("div");
    item_block.className = "preview-item";

    const img = document.createElement("img");
    img.src = v.file;
    img.alt = item.name + (v.label ? " (" + v.label + ")" : "");
    if (v.label === "描边") img.classList.add("is-outline");
    item_block.appendChild(img);

    if (v.label) {
      const tag = document.createElement("div");
      tag.className = "variant-tag";
      tag.textContent = v.label;
      item_block.appendChild(tag);
    }

    const addBtn = document.createElement("button");
    addBtn.className = "add-pick-btn";
    addBtn.textContent = v.label ? `添加${v.label}` : "添加备选";
    addBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (addBtn.classList.contains("ok") || addBtn.classList.contains("err")) return;
      const original = addBtn.textContent;
      addBtn.textContent = "添加中...";
      try {
        const res = await fetch("/api/pick", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file: v.file }),
        });
        const data = await res.json();
        if (res.ok && data.ok) {
          addBtn.classList.add("ok");
          addBtn.textContent = "已添加 ✓";
        } else {
          addBtn.classList.add("err");
          addBtn.textContent = "失败";
          console.error("pick failed:", data);
        }
      } catch (err) {
        addBtn.classList.add("err");
        addBtn.textContent = "失败";
        console.error(err);
      }
      setTimeout(() => {
        addBtn.classList.remove("ok", "err");
        addBtn.textContent = original;
      }, 1400);
    });
    item_block.appendChild(addBtn);

    preview.appendChild(item_block);
  }
  detailBar.appendChild(preview);
```

- [ ] **Step 3: 启动并手动验证详情条改造**

Run: 双击 `预览.bat`，浏览器打开页面。

验证：
- 点开一个**双形态**图标（如 `add`）→ 详情条出现两个并排预览，每个下方各有按钮，文案分别为 `添加填充`、`添加描边`，上方有 `填充` / `描边` 小标签。
- 点开一个**单形态**图标 → 详情条出现一个预览，按钮文案为 `添加备选`，无小标签。
- 点击任一 `添加...` 按钮 → 文案临时变 `已添加 ✓`，约 1.4s 还原。
- 检查 `Picked/` 目录，确认对应 SVG 出现。

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "详情条改造：每个形态独立预览 + 单独添加备选按钮"
```

---

### Task 5: 详情条新增 `打开备选目录` 全局按钮

**Files:**
- Modify: `index.html` （`<style>` 段新增 `.open-folder-btn` 样式；`toggleDetail()` 在 `复制文件名` 之后插入新按钮）

- [ ] **Step 1: 在 `<style>` 段追加 `.open-folder-btn` 样式**

定位到 `.detail-row .copy-btn:hover` 规则之后（约 368 行附近），追加：

```css
  .detail-row .open-folder-btn {
    padding: 4px 10px;
    background: var(--hover);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 11px;
    color: var(--muted);
    cursor: pointer;
    white-space: nowrap;
  }
  .detail-row .open-folder-btn:hover {
    background: var(--accent-soft);
    color: var(--accent);
    border-color: var(--accent);
  }
  .detail-row .open-folder-btn.ok {
    background: #dcfce7;
    color: #15803d;
    border-color: #15803d;
  }
  .detail-row .open-folder-btn.err {
    background: #fee2e2;
    color: #b91c1c;
    border-color: #b91c1c;
  }
```

- [ ] **Step 2: 在 `toggleDetail()` 的 `复制文件名` 按钮之后构造新按钮**

定位 `index.html` 中 `toggleDetail()` 内 `// 复制文件名按钮` 段（约 691-705 行），在其 `detailBar.appendChild(copyBtn);` 之后、`// 关闭按钮` 之前，插入：

```javascript
  // 打开备选目录按钮
  const openBtn = document.createElement("button");
  openBtn.className = "open-folder-btn";
  openBtn.textContent = "打开备选目录";
  openBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (openBtn.classList.contains("ok") || openBtn.classList.contains("err")) return;
    const original = openBtn.textContent;
    openBtn.textContent = "打开中...";
    try {
      const res = await fetch("/api/open-folder", { method: "POST" });
      const data = await res.json();
      if (res.ok && data.ok) {
        openBtn.classList.add("ok");
        openBtn.textContent = "已打开 ✓";
      } else {
        openBtn.classList.add("err");
        openBtn.textContent = "失败";
        console.error("open-folder failed:", data);
      }
    } catch (err) {
      openBtn.classList.add("err");
      openBtn.textContent = "失败";
      console.error(err);
    }
    setTimeout(() => {
      openBtn.classList.remove("ok", "err");
      openBtn.textContent = original;
    }, 1400);
  });
  detailBar.appendChild(openBtn);
```

- [ ] **Step 3: 启动并手动验证**

Run: 双击 `预览.bat`，浏览器打开页面。

验证：
- 点开任意图标 → 详情条右侧依次出现 `复制文件名`、`打开备选目录`、`×`。
- 点击 `打开备选目录` → 系统资源管理器弹出并定位到 `Picked/`；按钮临时变 `已打开 ✓`，1.4s 还原。

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "详情条新增「打开备选目录」按钮"
```

---

### Task 6: 端到端验证

**Files:** 无修改。

- [ ] **Step 1: 重启 server，全新会话走查**

Run: 双击 `预览.bat`。

逐项验证：
- 浏览器打开 `http://127.0.0.1:8765/`，图标库正常加载。
- 选一个双形态图标，点 `添加填充` → `Picked/` 出现对应文件。
- 点 `添加描边` → 出现另一个文件。
- 同名再次点击 → 文件被覆盖（mtime 刷新，用 `ls -l Picked/` 确认）。
- 点 `打开备选目录` → 资源管理器弹出并定位到 `Picked/`。
- 切到搜索框过滤出无描边形态的图标，确认只出现一个预览 + `添加备选` 按钮。
- 关闭浏览器，server 终端按 Ctrl+C，确认能正常退出。

- [ ] **Step 2: 清理测试残留**

Run: `rm -rf Picked/`
Expected: 删除测试期间产生的文件（`Picked/` 在 `.gitignore` 中，无需关心 git）。

> 若 `Picked/` 此刻非空且你想保留之前确实挑选的图标，跳过这步即可。

---

## Self-Review

**Spec coverage：**
- 详情条每形态独立预览 + 单独添加按钮 → Task 4 ✓
- 详情条级别"打开备选目录" → Task 5 ✓
- 项目根目录 `Picked/` → Task 1 (makedirs) + Task 2 (.gitignore) ✓
- 拷贝 SVG 到该目录 → Task 1 (`/api/pick`) ✓
- 重名覆盖 → Task 1 (`shutil.copy2`)，Step 4 + Task 6 Step 1 验证 ✓
- 路径白名单校验 → Task 1 Step 5 验证 ✓
- 跨平台打开目录 → Task 1 实现 + Step 7 验证 ✓

**Placeholder scan：** 无 TBD / TODO / "appropriate error handling" 等。所有代码块完整。

**Type consistency：**
- `/api/pick` 请求字段：`file`（string）；响应 `{ ok, dest? / error? }` —— 后端与前端一致。
- `/api/open-folder` 无 body；响应 `{ ok }` —— 一致。
- CSS class 名：`.preview-item`、`.variant-tag`、`.add-pick-btn`、`.open-folder-btn`、`.ok`、`.err` —— 前后端代码引用一致。
