@echo off
REM A股情绪轮动终端 启动器（使用隔离 venv 的 python，已含 flask）
cd /d "%~dp0"
"..\..\.workbuddy\binaries\python\envs\default\Scripts\python.exe" app.py
pause
