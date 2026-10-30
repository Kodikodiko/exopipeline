@echo off
rem Doppelklick: startet die transit-Bedienoberflaeche im Browser (http://127.0.0.1:8765).
rem Dieses Fenster offen lassen, solange die Oberflaeche benutzt wird. Schliessen = beenden.
rem Portables Paket: mitgeliefertes python\python.exe, sonst das installierte Python.
title Transit GUI
cd /d "%~dp0"
set "PY=python"
if exist "%~dp0python\python.exe" (
    set "PY=%~dp0python\python.exe"
    set PYTHONNOUSERSITE=1
    if not exist "%~dp0config.local.toml" copy "%~dp0config.example.toml" "%~dp0config.local.toml" >nul
)
set PYTHONPATH=%~dp0;%PYTHONPATH%
"%PY%" -m transit gui
if errorlevel 1 pause
