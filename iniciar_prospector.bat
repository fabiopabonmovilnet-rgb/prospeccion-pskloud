@echo off
chcp 65001 >nul 2>&1
title PSKloud Prospector - Iniciando...

echo ============================================
echo    PSKloud Prospector - Inicio Automatico
echo ============================================
echo.

REM Verificar Docker Desktop
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Docker Desktop no responde.
    echo     Abre "Docker Desktop" desde el menu Inicio y espera a que cargue.
    echo     Luego vuelve a ejecutar este acceso directo.
    echo.
    pause
    exit /b 1
)

cd /d "C:\Users\psklo\prospeccion-pskloud"

echo [1/3] Levantando contenedores (Docker Desktop)...
docker compose up -d
if %errorlevel% neq 0 (
    echo [!] Error al levantar contenedores.
    pause
    exit /b 1
)

echo [2/3] Esperando servicios (30 seg)...
echo      Evolution API corre migraciones automaticas...
timeout /t 30 /nobreak >nul

echo [3/3] Verificando dashboard...
for /l %%i in (1,1,10) do (
    curl -s -o nul http://localhost:9000
    if %errorlevel% equ 0 (
        echo Dashboard OK
        goto ok
    )
    timeout /t 3 /nobreak >nul
)
echo [!] Dashboard no responde. Revisa Docker Desktop.
pause
exit /b 1

:ok
echo.
echo ============================================
echo    PROSPECTOR CORRIENDO
echo    Dashboard:  http://localhost:9000
echo    Streamlit:  http://localhost:8501
echo    WhatsApp:   http://localhost:8080
echo ============================================
echo.

start "" "http://localhost:9000"
echo Listo. Puedes cerrar esta ventana.
timeout /t 3 /nobreak >nul