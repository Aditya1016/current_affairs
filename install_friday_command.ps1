$repoPath = $PSScriptRoot.Replace("'", "''")
$profilePath = $PROFILE.CurrentUserAllHosts

if (-not (Test-Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}

$functionBlock = @"
function global:friday {
    & '$repoPath\\friday.ps1'
}
"@

$current = Get-Content -Path $profilePath -Raw -ErrorAction SilentlyContinue
if (-not $current) {
    $current = ""
}

if ($current -notmatch '(?m)^function\s+(global:)?friday\s*\{') {
    Add-Content -Path $profilePath -Value "`r`n$functionBlock"
    Write-Host "Installed 'friday' command in profile: $profilePath"
} else {
    Write-Host "'friday' command already exists in profile: $profilePath"
}

Write-Host "Restart terminal or run: . $profilePath"
