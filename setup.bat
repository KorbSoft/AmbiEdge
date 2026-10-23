@echo off
rem One-time setup for running AmbiEdge from source: creates .venv and installs dependencies.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set "PY=py -3"
%PY% -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
echo.
echo Done. Double-click start.bat to run AmbiEdge.
pause
exit /b 0
:error
echo.
echo Setup failed. Make sure Python 3.9 or newer is installed from python.org (tick "Add to PATH").
pause
exit /b 1
