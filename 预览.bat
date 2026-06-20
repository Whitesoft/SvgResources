@echo off
cd /d "%~dp0"
title SVG 图像预览 - http://127.0.0.1:8765
echo.
echo  启动本地 HTTP 服务...
echo  访问地址: http://127.0.0.1:8765/
echo  关闭此窗口即可停止服务。
echo.
start "" http://127.0.0.1:8765/
python -m http.server 8765 --bind 127.0.0.1
