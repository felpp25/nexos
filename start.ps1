# NEXOS - cria o ambiente virtual (na primeira vez) e abre o app.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual..." -ForegroundColor Cyan
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

# pythonw abre o app sem janela de terminal; erros vao para data/nexos.log
$py = if (Test-Path ".venv\Scripts\pythonw.exe") { ".venv\Scripts\pythonw.exe" } else { ".venv\Scripts\python.exe" }
if ($args -contains "--web" -or $args -contains "--reload") { $py = ".venv\Scripts\python.exe" }
& $py run.py @args
