@echo off
chcp 65001 >nul 2>&1
title PSKloud Prospector - Iniciando...

echo ============================================
echo    PSKloud Prospector - Portable
echo ============================================
echo.

REM --- Verificar si Docker Desktop esta corriendo ---
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo Docker Desktop detectado.
    goto :start_compose
)

REM --- Si no, intentar via WSL ---
wsl -d Ubuntu -- bash -c "docker info" >nul 2>&1
if %errorlevel% equ 0 (
    echo Docker via WSL detectado.
    goto :start_wsl
)

REM --- Nada disponible ---
echo [!] Docker no encontrado.
echo     Ejecuta "setup_docker.bat" como administrador (solo 1 vez).
echo.
pause
exit /b 1

:start_compose
if not exist ".env" (
    echo Creando .env desde plantilla...
    copy .env.example .env >nul
    notepad .env
    pause
)
if not exist "data" mkdir data

echo Importando imagenes...
if exist "images\*.tar" (
    for %%F in (images\*.tar) do (
        echo   %%~nxF...
        docker load -i "%%F"
    )
)

echo Levantando servicios...
docker-compose up -d
timeout /t 15 /nobreak >nul
docker-compose ps
start http://localhost:9000
goto :done

:start_wsl
REM --- Detectar letra del pendrive ---
set "PENDRIVE=%~d0"
echo Usando pendrive en %PENDRIVE%\

REM --- Crear script WSL temporal ---
(
    echo #!/bin/bash
    echo cd /mnt/%PENDRIVE%/prospeccion-pskloud
    echo for f in images/*.tar; do
    echo     if [ -f "$f" ]; then
    echo         echo "Cargando $(basename $f)..."
    echo         docker load -i "$f"
    echo     fi
    echo done
    echo if [ ! -f .env ]; then cp .env.example .env 2^>/dev/null; fi
    echo mkdir -p data
    echo docker compose up -d
    echo sleep 15
    echo docker compose ps
    echo xdg-open http://localhost:9000 2^>/dev/null ^|^| true
) > "%TEMP%\pskloud_start.sh"

wsl -d Ubuntu -- bash -c "bash /mnt/c/Users/fabio/AppData/Local/Temp/pskloud_start.sh"
start http://localhost:9000

:done
echo.
echo ============================================
echo    PROSPECTOR CORRIENDO
echo    Dashboard:  http://localhost:9000
echo    Streamlit:  http://localhost:8501
echo ============================================
echo    Detener: detener_prospector.bat
echo.
pause
