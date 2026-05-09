@echo off
title TAA Sandbox
setlocal EnableExtensions

REM ── Resolve python from python_path.txt (written by create_shortcut.py) ──
set "CFG=%~dp0python_path.txt"
set "PYEXE="
if exist "%CFG%" (
    for /f "usebackq tokens=* delims=" %%P in ("%CFG%") do set "PYEXE=%%P"
)

if "%PYEXE%"=="" (
    echo.
    echo [!] python_path.txt not found.  Run this once from Anaconda Prompt:
    echo     python "%~dp0create_shortcut.py"
    echo.
    pause
    exit /b 1
)
if not exist "%PYEXE%" (
    echo.
    echo [!] Configured python does not exist: %PYEXE%
    echo     Re-run "%~dp0create_shortcut.py" from the right env.
    echo.
    pause
    exit /b 1
)

REM ── cd to project root: this .bat sits at <root>\stock_engine\sandbox\taa_module
cd /d "%~dp0..\..\..\"
set "PYTHONPATH=%CD%"

echo.
echo  TAA Sandbox launcher
echo  ----------------------------------------------------
echo  python      : %PYEXE%
echo  workdir     : %CD%
echo  port        : 8502
echo  url         : http://localhost:8502
echo  ----------------------------------------------------
echo.
echo  (Streamlit auto-opens your browser. Ctrl+C in this window to stop.)
echo.

echo Checking port 8502...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c = Get-NetTCPConnection -LocalPort 8502 -State Listen -EA 0 | Select-Object -First 1; if ($c) { try { $p = Get-Process -Id $c.OwningProcess -EA Stop; if ($p.ProcessName -eq 'python') { Stop-Process -Id $p.Id -Force; Start-Sleep -Milliseconds 600; Write-Host '  Freed port 8502 (killed zombie python)' } } catch {} }"

"%PYEXE%" -m streamlit run "stock_engine\sandbox\taa_module\app_standalone.py" --server.port 8502 --browser.gatherUsageStats false

echo.
echo Server stopped.  Press any key to close.
pause >nul
endlocal
