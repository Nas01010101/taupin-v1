@echo off
rem Windows (double-click): starts the local server and opens the browser. Needs Python 3.9+.
cd /d "%~dp0"
set PYTHONPATH=src
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m taupin %*) else (python -m taupin %*)
if errorlevel 1 pause
