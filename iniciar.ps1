# PSKloud Prospector - Lanzador PowerShell
# Derecho clic → "Run with PowerShell" si el .bat no funciona

$ErrorActionPreference = "Stop"
$ProjectDir = "C:\Users\fabio\prospeccion-pskloud"
$AppFile = Join-Path $ProjectDir "app.py"

Write-Host ""
Write-Host "  PSKloud Prospector v2.3" -ForegroundColor Cyan
Write-Host "  Proyecto: $ProjectDir" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $AppFile)) {
    Write-Host "  ERROR: No se encuentra $AppFile" -ForegroundColor Red
    Read-Host "  Presiona Enter para salir"
    exit 1
}

Write-Host "  Iniciando servidor Streamlit..." -ForegroundColor Yellow
Write-Host "  Abrira en: http://localhost:8501" -ForegroundColor Green
Write-Host ""
Write-Host "  IMPORTANTE: Manten esta ventana ABIERTA" -ForegroundColor DarkGray
Write-Host "  Para cerrar: cierra esta ventana o presiona Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

Set-Location $ProjectDir
& streamlit run app.py
