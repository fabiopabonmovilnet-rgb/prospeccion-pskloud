@echo off
chcp 65001 >nul 2>&1
title PSKloud - Setup Docker Portable (Solo 1 vez)

echo ============================================
echo   PSKloud Prospector - Setup Docker Portable
echo   (Ejecutar como ADMINISTRADOR, solo 1 vez)
echo ============================================
echo.

REM --- Verificar que se ejecuto como admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Este script necesita permisos de Administrador.
    echo     Clic derecho ^> "Ejecutar como administrador"
    echo.
    pause
    exit /b 1
)

echo [1/5] Verificando WSL2...

REM --- Verificar si WSL ya esta habilitado ---
wsl --status >nul 2>&1
if %errorlevel% equ 0 (
    echo      WSL2 ya esta habilitado.
) else (
    echo      Habilitando WSL2...
    wsl --install --no-distribution
    if %errorlevel% neq 0 (
        echo      [!] Error habilitando WSL2.
        echo      Intenta habilitarlo manualmente:
        echo      dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
        echo      dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
        echo.
        echo      Despues REINICIA el PC y vuelve a ejecutar este script.
        pause
        exit /b 1
    )
    echo      WSL2 habilitado.
    echo.
    echo      *** IMPORTANTE: Necesitas REINICIA el PC ahora ***
    echo      Despues del reinicio, vuelve a ejecutar este script.
    echo.
    pause
    exit /b 0
)

echo.
echo [2/5] Verificando docker-ce en WSL...

REM --- Verificar si ya hay docker en WSL ---
wsl -d Ubuntu -- bash -c "docker --version" >nul 2>&1
if %errorlevel% equ 0 (
    echo      Docker ya instalado en WSL.
    goto :skip_docker_install
)

echo      Instalando Docker en WSL...
wsl -d Ubuntu -- bash -c "sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg && sudo mkdir -p /etc/apt/keyrings && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg && echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu jammy stable' | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null && sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin"
if %errorlevel% neq 0 (
    echo      [!] Error instalando Docker en WSL.
    pause
    exit /b 1
)

:skip_docker_install
echo.
echo [3/5] Verificando que Docker funcione en WSL...
wsl -d Ubuntu -- bash -c "sudo service docker start && docker --version"
echo      OK

echo.
echo [4/5] Copiando imagenes Docker al WSL...

REM --- Crear carpeta en WSL para las imagenes ---
wsl -d Ubuntu -- bash -c "mkdir -p /mnt/prospeccion/images"

REM --- Las imagenes ya estan en el pendrive en images/ ---
REM --- Se acceden via /mnt/letra_del_pendrive/ ---
echo      Las imagenes se cargaran al iniciar el prospector.

echo.
echo [5/5] Creando script de inicio en WSL...
wsl -d Ubuntu -- bash -c "cat > /mnt/prospeccion/iniciar_wsl.sh << 'WSLEOF'
#!/bin/bash
cd /mnt/prospeccion
echo 'Cargando imagenes Docker...'
for f in images/*.tar; do
    if [ -f \"\$f\" ]; then
        echo \"  Cargando \$(basename \$f)...\"
        docker load -i \"\$f\"
    fi
done
echo 'Levantando servicios...'
docker compose up -d
echo 'Esperando...'
sleep 15
docker compose ps
echo ''
echo '============================================'
echo '  PROSPECTOR CORRIENDO'
echo '  Dashboard: http://localhost:9000'
echo '  Streamlit: http://localhost:8501'
echo '============================================'
WSLEOF"
wsl -d Ubuntu -- bash -c "chmod +x /mnt/prospeccion/iniciar_wsl.sh"

echo.
echo ============================================
echo   SETUP COMPLETADO!
echo ============================================
echo.
echo   Ahora puedes:
echo   1. Doble clic en "iniciar_prospector.bat"
echo   2. O abrir WSL y ejecutar: bash /mnt/LETRA/iniciar_wsl.sh
echo.
echo   NOTA: Si reiniciaste el PC, Docker puede tardar
echo   unos segundos en arrancar la primera vez.
echo.
pause
