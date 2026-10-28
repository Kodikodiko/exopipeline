@echo off
rem Aufruf: transit <befehl> <messordner> [optionen]   (transit hilfe = deutsche Hilfe)
set PYTHONPATH=%~dp0;%PYTHONPATH%
python -m transit %*
