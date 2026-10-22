@echo off
cd /d "%~dp0"
title 日式女仆咖啡馆 - 本地预览
echo.
echo ==================================================
echo    日式女仆咖啡馆 - 本地预览服务器
echo ==================================================
echo.
echo   index.html 使用 ES module + fetch 加载 3D 模型，
echo   浏览器的 file:// 协议会拒绝这些请求（CORS），
echo   所以必须通过本地 HTTP 服务器打开。
echo.
echo   正在启动...
echo.

rem 优先用 Python（本项目路径已配好）
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0serve.py" %1
  goto :done
)

rem 退回 py launcher
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0serve.py" %1
  goto :done
)

rem 退回 Node
where node >nul 2>nul
if %errorlevel%==0 (
  node "%~dp0server.js" %1
  goto :done
)

echo   [错误] 没找到 Python 或 Node.js。
echo.
echo   请手动执行以下任一命令（需先安装 Python 或 Node.js）：
echo       python serve.py
echo       node server.js
echo.
pause

:done
