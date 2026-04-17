@echo off
REM Soul Flow Apparel - hourly blog post generator.
REM Registered with Windows Task Scheduler; see scripts\install_schedule.bat.

setlocal
set "PROJECT_DIR=C:\Users\Techie Buddy\Desktop\Agents\Soul Flow\soul-flow"
set "PYTHONIOENCODING=utf-8"
cd /d "%PROJECT_DIR%"

python "%PROJECT_DIR%\scripts\run_hourly.py"
set "RC=%ERRORLEVEL%"

echo.
echo Hourly run finished with exit code %RC%
exit /b %RC%
