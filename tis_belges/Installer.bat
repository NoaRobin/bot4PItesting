@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Installation TIS Belges ===
echo.

where py >nul 2>&1
if errorlevel 1 goto :no_python

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement Python...
    py -3 -m venv .venv
    if errorlevel 1 goto :error
)

echo Installation des composants...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 goto :error

echo.
echo Controle de l'installation...
".venv\Scripts\python.exe" tis_belges.py check
if errorlevel 1 goto :check_failed

echo.
echo Creation de la tache planifiee...
".venv\Scripts\python.exe" tis_belges.py install-task
if errorlevel 1 goto :error

echo.
echo Installation terminee. Lire la section "Premiere execution" du README.
pause
exit /b 0

:no_python
echo Python n'est pas installe sur ce poste.
echo Installez-le depuis https://www.python.org/downloads/ en cochant
echo "Add python.exe to PATH", puis relancez Installer.bat.
pause
exit /b 1

:check_failed
echo.
echo Des points bloquants ont ete trouves ci-dessus. Corrigez-les puis relancez Installer.bat.
pause
exit /b 1

:error
echo.
echo ERREUR pendant l'installation. Copiez le message ci-dessus et envoyez-le.
pause
exit /b 1
