@echo off
rem Legt auf dem Desktop eine Verknuepfung "Transit GUI" an, die transit_gui.cmd in diesem Ordner startet.
rem Nach dem Verschieben des Ordners einfach noch einmal doppelklicken.
setlocal
set "ZIEL=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w = New-Object -ComObject WScript.Shell; $l = $w.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Transit GUI.lnk'); $l.TargetPath = $env:ZIEL + 'transit_gui.cmd'; $l.WorkingDirectory = $env:ZIEL; $l.IconLocation = $env:ZIEL + 'python\pythonw.exe,0'; $l.Description = 'transit - Exoplaneten-Transits auswerten'; $l.Save()"
if errorlevel 1 (
    echo Die Verknuepfung konnte nicht angelegt werden. transit_gui.cmd laesst sich auch direkt per Doppelklick starten.
) else (
    echo Auf dem Desktop liegt jetzt die Verknuepfung "Transit GUI".
)
pause
