@echo off
rem install.bat — Windows entry point for the Odysseus native app installer.
rem Calls build-windows-app.ps1 via PowerShell.
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0build-windows-app.ps1" %*
