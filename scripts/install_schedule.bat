@echo off
REM Register the Soul Flow hourly poster with Windows Task Scheduler.
REM Runs as the current interactive user, every hour starting 2026-04-16 at 20:45 local (CDT).
REM Re-run this file to update the schedule (uses /f to force replace).

set "TASK_NAME=SoulFlowHourlyPost"
set "BAT_PATH=%~dp0run_hourly.bat"

echo Registering scheduled task: %TASK_NAME%
echo Runs: %BAT_PATH%
echo.

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%BAT_PATH%\"" ^
  /sc HOURLY ^
  /mo 1 ^
  /st 20:45 ^
  /sd 04/16/2026 ^
  /f

if %ERRORLEVEL% EQU 0 (
  echo.
  echo Task registered successfully.
  echo First run: 2026-04-16 at 20:45 local time.
  echo Recurs hourly thereafter.
  echo.
  echo View it in Task Scheduler ^(taskschd.msc^) or list with:
  echo   schtasks /query /tn "%TASK_NAME%" /v /fo LIST
) else (
  echo.
  echo Task registration failed with exit code %ERRORLEVEL%.
)

exit /b %ERRORLEVEL%
