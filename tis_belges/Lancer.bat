@echo off
chcp 65001 >nul
cd /d "%~dp0"
set URL=http://127.0.0.1:8765

if not exist ".venv\Scripts\pythonw.exe" (
    echo L'installation n'est pas faite. Lancez Installer.bat d'abord.
    pause
    exit /b 1
)

rem Le serveur tourne en arriere-plan (sans fenetre). S'il tourne deja, il ne redemarre pas.
start "" /min ".venv\Scripts\pythonw.exe" dashboard\server.py
timeout /t 2 /nobreak >nul

rem Fenetre dediee : Edge en mode application, sinon Chrome, sinon le navigateur par defaut.
start "" msedge --app=%URL% --window-size=1280,860 >nul 2>&1
if not errorlevel 1 exit /b 0
start "" chrome --app=%URL% --window-size=1280,860 >nul 2>&1
if not errorlevel 1 exit /b 0
start "" %URL%
exit /b 0
