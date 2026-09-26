[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$blankRoot = Split-Path $workspaceRoot -Parent

$forbidden = @(
    (Join-Path $workspaceRoot ".env"),
    (Join-Path $workspaceRoot ".openclaw\openclaw.json")
)
foreach ($path in $forbidden) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to package secret-bearing runtime file: $path"
    }
}

if (-not $OutputPath) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $blankRoot "dist\creator-agent-workspace-$timestamp.tar.gz"
}
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
if (Test-Path -LiteralPath $outputFullPath) {
    throw "Refusing to overwrite existing artifact: $outputFullPath"
}

$outputDirectory = Split-Path $outputFullPath -Parent
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

Push-Location $blankRoot
try {
    tar -czf $outputFullPath `
        --exclude="workspace/__pycache__" `
        --exclude="workspace/**/__pycache__" `
        --exclude="workspace/.pytest_cache" `
        --exclude="workspace/tests" `
        workspace
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $outputFullPath
Write-Output "Package: $outputFullPath"
Write-Output "SHA256: $($hash.Hash)"
