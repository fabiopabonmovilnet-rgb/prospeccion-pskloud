@echo off
chcp 65001 >nul 2>&1
title PSKloud - Exportar Imagenes

echo Exportando imagenes Docker...
if not exist "images" mkdir images

echo [1/4] openclaw...
docker save -o images\prospeccion-pskloud-openclaw.tar prospeccion-pskloud-openclaw:latest
echo      OK

echo [2/4] postgres...
docker save -o images\postgres-15-alpine.tar postgres:15-alpine
echo      OK

echo [3/4] redis...
docker save -o images\redis-7-alpine.tar redis:7-alpine
echo      OK

echo [4/4] evolution-api...
docker save -o images\evolution-api.tar evoapicloud/evolution-api:latest
echo      OK

echo.
echo Imagenes exportadas a images/
dir images\*.tar
pause
