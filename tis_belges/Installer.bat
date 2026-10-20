@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Installation TIS Belges ===
echo.

call :find_python
if not defined PY goto :no_python
echo Python trouve : %PY%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement Python...
    %PY% -m venv .venv
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

:find_python
set PY=
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set PY=py -3
if defined PY exit /b 0
python -c "import sys" >nul 2>&1
if not errorlevel 1 set PY=python
exit /b 0

:no_python
echo Python n'a pas ete trouve sur ce poste (ni "py" ni "python" ne fonctionnent).
echo.
echo Cas le plus frequent : Python est installe mais le PATH n'est pas enregistre.
echo  1. Relancer le programme d'installation de Python depuis https://www.python.org/downloads/
echo     et choisir "Modify" ou "Repair", en cochant "Add python.exe to PATH".
echo  2. Ou installer Python depuis le Microsoft Store.
echo  3. Si "python" renvoie vers le Microsoft Store : Parametres Windows ^> Applications ^>
echo     Parametres avances ^> Alias d'execution d'applications, puis desactiver python.exe.
echo.
echo Ouvrir ensuite une NOUVELLE fenetre de commandes et taper : py --version
echo Puis relancer Installer.bat.
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
