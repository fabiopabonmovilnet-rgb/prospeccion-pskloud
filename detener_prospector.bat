@echo off
chcp 65001 >nul 2>&1
title PSKloud - Deteniendo...

echo Deteniendo PSKloud Prospector...

REM --- Intentar con docker-compose primero ---
docker-compose down 2>nul

REM --- Si no funciona, intentar via WSL ---
wsl -d Ubuntu -- bash -c "cd /mnt/prospeccion && docker compose down" 2>nul

echo.
echo Prospector detenido.
pause
