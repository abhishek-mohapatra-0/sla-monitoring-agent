@echo off
REM One-click launcher for the SLA dashboard (Windows)
setlocal
cd /d "%~dp0app"
if exist ".venv\Scripts\python.exe" goto run

REM ---- find a real Python (skip the Microsoft Store alias)
set "PYEXE="
set "PYARG="
where py >nul 2>nul && (set "PYEXE=py" & set "PYARG=-3")
if not defined PYEXE for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%~D\python.exe" set "PYEXE=%%~D\python.exe"
if not defined PYEXE for %%P in ("%UserProfile%\anaconda3\python.exe" "%UserProfile%\miniconda3\python.exe" "%ProgramData%\anaconda3\python.exe" "%ProgramFiles%\Python313\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe" "%ProgramFiles%\Python310\python.exe") do if exist "%%~P" set "PYEXE=%%~P"
if not defined PYEXE (
    python -c "import sys" >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
    echo.
    echo  Python was not found on this PC.
    echo  Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
    echo  then double-click run_dashboard.bat again.
    echo.
    pause
    exit /b 1
)

echo First run: creating a virtual environment with "%PYEXE%" %PYARG% ...
"%PYEXE%" %PYARG% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
    echo Could not create the virtual environment. See the message above.
    pause
    exit /b 1
)
echo Installing Flask + pandas (one time, needs internet)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt

:run
".venv\Scripts\python.exe" app.py
pause
