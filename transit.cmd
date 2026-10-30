@echo off
rem Aufruf: transit <befehl> <messordner> [optionen]   (transit hilfe = deutsche Hilfe)
rem Portables Paket: mitgeliefertes python\python.exe, sonst das installierte Python.
setlocal
set "PY=python"
if exist "%~dp0python\python.exe" (
    set "PY=%~dp0python\python.exe"
    set PYTHONNOUSERSITE=1
    if not exist "%~dp0config.local.toml" copy "%~dp0config.example.toml" "%~dp0config.local.toml" >nul
)
set PYTHONPATH=%~dp0;%PYTHONPATH%
"%PY%" -m transit %*
