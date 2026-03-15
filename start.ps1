$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = $projectRoot
$frontendDir = Join-Path $projectRoot "web"
$venvActivate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"

if (-not (Test-Path $frontendDir)) {
    throw "Diretorio do frontend nao encontrado: $frontendDir"
}

if (-not (Test-Path $venvActivate)) {
    throw "Virtualenv nao encontrado em $venvActivate"
}

foreach ($dir in @("data", "uploads", "artifacts", "docs")) {
    $path = Join-Path $projectRoot $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

$backendCommand = @"
Set-Location '$backendDir'
. '$venvActivate'
python -m uvicorn docops.api.app:app --reload
"@

$frontendCommand = @"
Set-Location '$frontendDir'
npm run dev
"@

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    $backendCommand
)

Start-Sleep -Seconds 1

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    $frontendCommand
)

Write-Host "Backend e frontend iniciados em janelas separadas."
Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"
