@echo off
setlocal
chcp 65001 >nul
title Installation TIS Belges

rem ============================================================================
rem  TIS Belges : installation et mise a jour en un double-clic.
rem  Seul prerequis : Python 3.9 ou plus recent. Ce fichier peut etre lance
rem  depuis n'importe ou (bureau, Telechargements, directement dans le zip).
rem  Le relancer met l'application a jour en conservant config.json.
rem ============================================================================

set "REPO=NoaRobin/bot4PItesting"
set "BRANCH=automatisation-stephanie"
set "URL=https://codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%"
set "APP=%LOCALAPPDATA%\TISBelges\app"
set "WORK=%TEMP%\tis_belges_install"

echo.
echo  ==========================================
echo    TIS BELGES - Installation / mise a jour
echo  ==========================================
echo.

rem ---------------------------------------------------------------- Python
call :find_python
if not defined PY goto :no_python
echo Python trouve : %PY%

rem ---------------------------------------------------------------- Telechargement
if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%"

echo.
echo Telechargement de l'application...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; [Net.WebRequest]::DefaultWebProxy.Credentials=[Net.CredentialCache]::DefaultNetworkCredentials; Invoke-WebRequest -UseBasicParsing -Uri $env:URL -OutFile (Join-Path $env:WORK 'app.zip')" >nul 2>&1
if not exist "%WORK%\app.zip" (
    echo Nouvel essai avec Python...
    %PY% -I -c "import os,urllib.request;urllib.request.urlretrieve(os.environ['URL'],os.path.join(os.environ['WORK'],'app.zip'))"
)
if not exist "%WORK%\app.zip" goto :download_failed

rem ---------------------------------------------------------------- Extraction
%PY% -I -m zipfile -e "%WORK%\app.zip" "%WORK%\src"
if errorlevel 1 goto :download_failed
set "SRC="
for /d %%D in ("%WORK%\src\*") do set "SRC=%%D\tis_belges"
if not defined SRC goto :download_failed
if not exist "%SRC%\deploy.py" goto :download_failed

rem ---------------------------------------------------------------- Installation
%PY% -I "%SRC%\deploy.py" --source "%SRC%" --target "%APP%" --archive "%WORK%\app.zip"
if errorlevel 1 goto :install_failed

rmdir /s /q "%WORK%" >nul 2>&1
echo.
echo L'application TIS Belges s'ouvre. Ensuite : raccourci "TIS Belges" sur le bureau.
echo Cette fenetre se fermera dans 15 secondes.
timeout /t 15 >nul
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
echo Puis relancer ce fichier.
pause
exit /b 1

:download_failed
echo.
echo ERREUR : impossible de telecharger l'application depuis GitHub.
echo Verifiez la connexion Internet (ou le proxy de l'entreprise) puis relancez.
echo Adresse : %URL%
pause
exit /b 1

:install_failed
echo.
echo ERREUR pendant l'installation. Faites une capture de cette fenetre et envoyez-la.
pause
exit /b 1
