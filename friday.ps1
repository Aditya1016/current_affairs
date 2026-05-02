Set-Location $PSScriptRoot

$pythonExe = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} elseif (Test-Path ".venv\bin\python.exe") {
    ".venv\bin\python.exe"
} else {
    $null
}

if (-not $pythonExe) {
    Write-Host "Local venv not found at .venv\Scripts\python.exe or .venv\bin\python.exe"
    Write-Host "Create it first: python -m venv .venv"
    exit 1
}

& $pythonExe -m app.cli
