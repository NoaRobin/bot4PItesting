@echo off
setlocal
chcp 65001 >nul
title TIS Belges

rem ============================================================================
rem  TIS Belges - un seul fichier pour tout :
rem    1er double-clic : installe ce qu'il faut (quelques minutes), puis ouvre l'app
rem    ensuite         : ouvre directement l'application
rem  Seul prerequis : Python 3.9 ou plus recent.
rem ============================================================================

set "APPDIR=%~dp0tis_belges"
if not exist "%APPDIR%\tis_belges.py" set "APPDIR=%~dp0."
if not exist "%APPDIR%\tis_belges.py" goto :no_app

set "VENV=%LOCALAPPDATA%\TISBelges\venv"
set "URL=http://127.0.0.1:8765"

rem ---------------------------------------------------------------- deja installe ?
if not exist "%VENV%\Scripts\python.exe" goto :setup
"%VENV%\Scripts\python.exe" -I "%APPDIR%\deploy.py" --is-ready
if errorlevel 1 goto :setup
goto :launch

rem ---------------------------------------------------------------- installation
:setup
echo.
echo  ==============================================
echo    TIS BELGES - premiere utilisation
echo    Installation en cours (quelques minutes)...
echo  ==============================================
call :find_python
if not defined PY goto :no_python
echo Python trouve : %PY%
%PY% -I "%APPDIR%\deploy.py" --setup --launcher "%~f0"
if errorlevel 1 goto :setup_failed
echo.
echo Ouverture de l'application...

rem ---------------------------------------------------------------- ouverture
:launch
start "" "%VENV%\Scripts\pythonw.exe" "%APPDIR%\dashboard\server.py"
"%VENV%\Scripts\python.exe" -I "%APPDIR%\deploy.py" --wait-server
if errorlevel 1 goto :server_failed

rem Fenetre dediee : Edge en mode application, sinon Chrome, sinon navigateur par defaut.
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1
if not errorlevel 1 (
    start "" msedge --app=%URL% --window-size=1280,860
    exit /b 0
)
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
if errorlevel 1 reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
if not errorlevel 1 (
    start "" chrome --app=%URL% --window-size=1280,860
    exit /b 0
)
start "" %URL%
exit /b 0

rem ============================================================================
:find_python
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY exit /b 0
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
exit /b 0

:no_app
echo.
echo Le dossier "tis_belges" est introuvable a cote de ce fichier.
echo Gardez TIS_Belges.bat dans le dossier extrait du zip, sans le deplacer seul.
pause
exit /b 1

:no_python
echo.
echo Python 3.9 ou plus recent n'a pas ete trouve sur ce poste.
echo.
echo  1. Installer Python depuis https://www.python.org/downloads/
echo     en cochant "Add python.exe to PATH".
echo  2. Si Python est deja installe : relancer son installateur, choisir
echo     "Modify", puis cocher "Add python.exe to PATH".
echo  3. Si "python" ouvre le Microsoft Store : Parametres Windows ^> Applications ^>
echo     Parametres avances ^> Alias d'execution d'applications : desactiver python.exe.
echo.
echo Puis relancer TIS_Belges.bat.
pause
exit /b 1

:server_failed
echo.
echo L'application ne demarre pas. Pour la reparer, supprimez le fichier
echo   %LOCALAPPDATA%\TISBelges\installation.json
echo puis relancez TIS_Belges.bat : l'installation sera refaite.
pause
exit /b 1

:setup_failed
echo.
echo ERREUR pendant l'installation. Faites une capture de cette fenetre et envoyez-la.
echo Vous pouvez relancer TIS_Belges.bat : l'installation reprendra.
pause
exit /b 1
