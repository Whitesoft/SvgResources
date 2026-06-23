@echo off
chcp 65001 > nul
cd /d "%~dp0"
title SVG 图标预览 - http://127.0.0.1:8765
echo.
echo  正在启动 HTTP 服务...
echo  访问地址: http://127.0.0.1:8765/
echo  关闭此窗口即可停止服务
echo.
start "" http://127.0.0.1:8765/
python server.py
