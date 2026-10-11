@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-LocalAgent.ps1"
if errorlevel 1 pause
