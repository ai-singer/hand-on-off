[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$blankRoot = Split-Path $workspaceRoot -Parent
$secretScanner = Join-Path $workspaceRoot "security\secret_scan.py"

# Relative directory prefixes the deployment artifact intentionally omits.
# The manifest must describe the same file set the archive ships, otherwise
# validation would report the omitted files as missing.
$artifactExcludes = @("tests")

# --- 1. Pre-package secret scan -------------------------------------------------
python $secretScanner $workspaceRoot
if ($LASTEXITCODE -ne 0) {
    throw "Pre-package secret scan failed with exit code $LASTEXITCODE"
}

# --- 2. Refuse secret-bearing runtime files -------------------------------------
$forbidden = @(
    (Join-Path $workspaceRoot ".env"),
    (Join-Path $workspaceRoot ".openclaw\openclaw.json")
)
foreach ($path in $forbidden) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to package secret-bearing runtime file: $path"
    }
}

# --- 3. Resolve the output artifact path ----------------------------------------
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

$manifestPath = "$outputFullPath.manifest.json"
$artifactTemp = $null

Push-Location $blankRoot
try {
    # --- 4. Package --------------------------------------------------------------
    tar -czf $outputFullPath `
        --exclude="workspace/__pycache__" `
        --exclude="workspace/**/__pycache__" `
        --exclude="workspace/.pytest_cache" `
        --exclude="workspace/tests" `
        workspace
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }

    python $secretScanner $outputFullPath
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged artifact secret scan failed with exit code $LASTEXITCODE"
    }

    # --- 5. Generate the artifact manifest ---------------------------------------
    Push-Location $workspaceRoot
    try {
        $excludeArguments = @()
        foreach ($entry in $artifactExcludes) {
            $excludeArguments += @("--exclude", $entry)
        }
        python -m artifact.manifest $workspaceRoot --manifest $manifestPath @excludeArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Artifact manifest generation failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    # --- 6. Validate the packaged artifact against the manifest ------------------
    # The archive is extracted and validated, so the gate proves that the bytes
    # actually shipped match the manifest rather than trusting the source tree.
    $artifactTemp = Join-Path ([System.IO.Path]::GetTempPath()) ("creator-agent-artifact-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $artifactTemp -Force | Out-Null
    tar -xzf $outputFullPath -C $artifactTemp
    if ($LASTEXITCODE -ne 0) {
        throw "Artifact extraction failed with exit code $LASTEXITCODE"
    }

    $artifactRoot = Join-Path $artifactTemp "workspace"
    Push-Location $workspaceRoot
    try {
        python -m artifact.validator $artifactRoot --manifest $manifestPath
        if ($LASTEXITCODE -ne 0) {
            throw "Artifact validation failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
catch {
    # A failed gate must not leave a deployable package behind.
    Remove-Item -LiteralPath $outputFullPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    throw
}
finally {
    Pop-Location
    if ($artifactTemp) {
        Remove-Item -LiteralPath $artifactTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $outputFullPath
Write-Output "Package: $outputFullPath"
Write-Output "SHA256: $($hash.Hash)"
Write-Output "Manifest: $manifestPath"
