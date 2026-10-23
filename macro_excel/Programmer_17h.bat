@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0TIS_Belges.xlsm" (
    echo TIS_Belges.xlsm est introuvable dans ce dossier.
    echo Placez Programmer_17h.bat et Lancement_17h.vbs a cote de TIS_Belges.xlsm.
    pause
    exit /b 1
)
schtasks /Create /TN "TIS Belges - envoi quotidien" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:00 /TR "wscript.exe \"%~dp0Lancement_17h.vbs\"" /F
if errorlevel 1 (
    echo La tache n'a pas pu etre creee.
) else (
    echo Envoi automatique programme du lundi au vendredi a 17h.
    echo Pour l'arreter : schtasks /Delete /TN "TIS Belges - envoi quotidien" /F
)
pause
