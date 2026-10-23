@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Installation TIS Belges

rem Installation depuis ce dossier (deja telecharge). Pour tout telecharger
rem automatiquement, utiliser plutot Installer_TIS_Belges.bat.

call :find_python
if not defined PY goto :no_python
echo Python trouve : %PY%

%PY% -I deploy.py --source "%~dp0." --target "%~dp0."
if errorlevel 1 goto :error
timeout /t 10 >nul
exit /b 0

:find_python
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY exit /b 0
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
exit /b 0

:no_python
echo Python 3.9 ou plus recent n'a pas ete trouve sur ce poste.
echo Installez-le depuis https://www.python.org/downloads/ en cochant
echo "Add python.exe to PATH", puis relancez Installer.bat.
pause
exit /b 1

:error
echo.
echo ERREUR pendant l'installation. Faites une capture de cette fenetre et envoyez-la.
pause
exit /b 1
