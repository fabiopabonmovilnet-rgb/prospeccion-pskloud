# =============================================================================
# PSKloud Prospector - Iniciar Docker (OpenClaw + Evolution API)
# =============================================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PSKloud Prospector - OpenClaw Engine" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar que .env existe
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: No se encontro el archivo .env" -ForegroundColor Red
    Write-Host "Copia .env.example como .env y configura tus API keys" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  cp .env.example .env" -ForegroundColor White
    Write-Host "  notepad .env" -ForegroundColor White
    exit 1
}

Write-Host "Verificando Docker..." -ForegroundColor Yellow
$dockerOk = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker no esta corriendo. Abre Docker Desktop primero." -ForegroundColor Red
    exit 1
}

Write-Host "Docker OK" -ForegroundColor Green
Write-Host ""
Write-Host "Levantando servicios..." -ForegroundColor Yellow
docker-compose up -d --build

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Servicios levantados!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Evolution API:  http://localhost:8080" -ForegroundColor White
Write-Host "  OpenClaw:       http://localhost:9000" -ForegroundColor White
Write-Host ""
Write-Host "Pasos siguientes:" -ForegroundColor Yellow
Write-Host "  1. Abre http://localhost:8080 para configurar tu instancia" -ForegroundColor White
Write-Host "  2. Escanea el QR con tu WhatsApp Business" -ForegroundColor White
Write-Host "  3. Verifica conexion: curl http://localhost:9000/health" -ForegroundColor White
Write-Host ""
Write-Host "Ver logs en tiempo real:" -ForegroundColor Yellow
Write-Host "  docker-compose logs -f openclaw" -ForegroundColor White
Write-Host ""
