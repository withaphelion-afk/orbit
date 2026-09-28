@echo off
rem Double-click to start Orbit on Windows. Same as: python scripts\start_orbit.py
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\start_orbit.py %*
) else (
  uv run python scripts\start_orbit.py %*
)
if errorlevel 1 pause
