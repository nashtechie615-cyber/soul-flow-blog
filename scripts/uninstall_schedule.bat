@echo off
REM Remove the Soul Flow hourly poster from Windows Task Scheduler.

set "TASK_NAME=SoulFlowHourlyPost"
schtasks /delete /tn "%TASK_NAME%" /f
exit /b %ERRORLEVEL%
