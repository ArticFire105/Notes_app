@echo off
rem Start the local Notes App from a double-click.
rem This file is the Windows entry point.
rem The PowerShell script does the actual process management.
rem It starts a separate window for each service.
rem Those windows keep their logs visible.
rem The controller window explains how to stop them.
rem Press Enter in that window to stop the launched services.
rem The script uses this file's location as the project root.
rem It works even when opened from another directory.
rem PowerShell is supplied with Windows.
rem No separate terminal is needed to start this file.
rem The backend and frontend use their existing commands.
rem Handwriting is transcribed by Gemini through the backend.
rem The frontend builds before it starts.
rem Build and service errors remain visible in their windows.
rem The controller stops only the processes it started.
rem Existing unrelated servers are not intentionally stopped.
rem Do not close the controller before stopping the services.
rem A second controller for the same project is rejected.
rem The script never reads configuration files.
rem It does not display secret environment variables.
rem It does not modify user data.
rem Install dependencies before using this launcher.
rem See the README for setup and testing.
rem This wrapper bypasses script policy for this invocation only.
rem The project source remains unchanged by the launcher.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
