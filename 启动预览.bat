@echo off
cd /d "%~dp0"
title Maid Cafe - Local Preview
echo.
echo ==================================================
echo    Maid Cafe - Local Preview Server
echo ==================================================
echo.
echo   index.html uses ES module + fetch to load the 3D model.
echo   The file:// protocol will be blocked by CORS,
echo   so a local HTTP server is required.
echo.
echo   Starting...
echo.

rem Prefer Python
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0serve.py" %1
  goto :done
)

rem Fallback: py launcher
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0serve.py" %1
  goto :done
)

rem Fallback: Node.js
where node >nul 2>nul
if %errorlevel%==0 (
  node "%~dp0tools\web\serve.mjs" %1
  goto :done
)

echo   [ERROR] Python or Node.js not found.
echo.
echo   Please run one of the following (install Python or Node.js first):
echo       python serve.py
echo       node tools\web\serve.mjs
echo.
pause

:done
