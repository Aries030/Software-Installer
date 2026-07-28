param(
    [string]$Version = "1.1.0",
    [string]$OutputRoot = "dist"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stagingRoot = Join-Path $repoRoot $OutputRoot
$packageName = "Software-Installer-$Version"
$stagingDir = Join-Path $stagingRoot $packageName
$zipPath = Join-Path $stagingRoot "$packageName.zip"

if (Test-Path $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

$files = @(
    "InstallerManager.ps1",
    "Start-SoftwareInstaller.bat",
    "README.md",
    "README_InstallerManager.md"
)

foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $repoRoot $file) -Destination $stagingDir -Force
}

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

$packageItems = @(Get-ChildItem -LiteralPath $stagingDir -Force | Select-Object -ExpandProperty FullName)
Compress-Archive -LiteralPath $packageItems -DestinationPath $zipPath -Force
Write-Host "Created $zipPath"
