# NEXOS - empacota o app em um unico executavel (dist\NEXOS.exe)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual..." -ForegroundColor Cyan
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

Write-Host "Instalando PyInstaller..." -ForegroundColor Cyan
& ".venv\Scripts\python.exe" -m pip install --quiet pyinstaller

Write-Host "Empacotando (leva alguns minutos)..." -ForegroundColor Cyan
& ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --log-level WARN NEXOS.spec

$exe = Join-Path $PSScriptRoot "dist\NEXOS.exe"
if (Test-Path $exe) {
    $mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "OK: dist\NEXOS.exe ($mb MB)" -ForegroundColor Green
} else {
    Write-Error "A build nao gerou dist\NEXOS.exe"
}
