@echo off
setlocal
cd /d "%~dp0..\.."
echo.
echo VeriDemand extraction acceptance review
echo URL: http://127.0.0.1:8765/
echo Bind: 127.0.0.1 only — do not use file:///
echo.
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" scripts\extraction_acceptance\start_review_server.py %*
) else (
  python scripts\extraction_acceptance\start_review_server.py %*
)
