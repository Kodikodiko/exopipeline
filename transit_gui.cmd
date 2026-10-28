@echo off
rem Doppelklick: startet die transit-Bedienoberflaeche im Browser (http://127.0.0.1:8765).
rem Dieses Fenster offen lassen, solange die Oberflaeche benutzt wird. Schliessen = beenden.
title Transit GUI
cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%
python -m transit gui
if errorlevel 1 pause
