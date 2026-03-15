$ErrorActionPreference = "SilentlyContinue"

$targets = @(
    "uvicorn",
    "node"
)

foreach ($name in $targets) {
    Get-Process -Name $name | Stop-Process -Force
}

Write-Host "Processos uvicorn/node encerrados."
