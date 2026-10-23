@echo off
rem Starts AmbiEdge from a source checkout. Run setup.bat once first.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Python environment not found. Run setup.bat first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "AmbiEdge.pyw"
