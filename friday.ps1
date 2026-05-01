Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\bin\python.exe")) {
    Write-Host "Local venv not found at .venv/bin/python.exe"
    Write-Host "Create it first: python -m venv .venv"
    exit 1
}

.\.venv\bin\python.exe -m app.cli
