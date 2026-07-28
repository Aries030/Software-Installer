<#
.SYNOPSIS
    Build a portable Software Installer release ZIP.

.DESCRIPTION
    1. (Optional) Re-build SoftwareInstaller.exe with PyInstaller.
    2. Stage the launch artifacts into a version-named folder.
    3. Compress the folder into a ZIP at dist\Software-Installer-<version>.zip.

.PARAMETER Version
    Release version, e.g. 1.2.0.

.PARAMETER OutputRoot
    Output root folder. Default: dist

.PARAMETER SkipExeBuild
    Skip PyInstaller step (use the existing SoftwareInstaller.exe).
#>
param(
    [string]$Version = "1.2.0",
    [string]$OutputRoot = "dist",
    [switch]$SkipExeBuild
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stagingRoot = Join-Path $repoRoot $OutputRoot
$packageName = "Software-Installer-$Version"
$stagingDir = Join-Path $stagingRoot $packageName
$zipPath = Join-Path $stagingRoot "$packageName.zip"

# --- 1. Build exe (optional) ---
if (-not $SkipExeBuild) {
    Write-Host "==> Step 1/3: Build SoftwareInstaller.exe with PyInstaller"
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "[错误] 未检测到 python,请安装 Python 3.10+ 或使用 -SkipExeBuild 复用已有 exe。" -ForegroundColor Red
        exit 1
    }

    # 探测依赖
    try {
        & python -c "import customtkinter, PIL, PyInstaller" 2>$null
    } catch {
        Write-Host "[错误] 缺少依赖 customtkinter / pillow / pyinstaller。" -ForegroundColor Red
        Write-Host "运行: pip install customtkinter pillow pyinstaller" -ForegroundColor Yellow
        exit 1
    }

    # 清理旧的 build/dist
    Remove-Item -LiteralPath (Join-Path $repoRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $repoRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue

    & python -m PyInstaller `
        --noconfirm --clean --windowed --onefile `
        --name "SoftwareInstaller" `
        --icon (Join-Path $repoRoot "assets\logo.ico") `
        --add-data (Join-Path $repoRoot "assets\logo.ico;assets") `
        --add-data (Join-Path $repoRoot "assets\logo.png;assets") `
        --add-data (Join-Path $repoRoot "assets\logo_256.png;assets") `
        --collect-all customtkinter `
        --hidden-import PIL._tkinter_finder `
        --hidden-import tkinter `
        (Join-Path $repoRoot "run_installer_app.py")

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] PyInstaller 打包失败。" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} else {
    Write-Host "==> Step 1/3: 跳过 exe 构建(使用已有 SoftwareInstaller.exe)"
}

# --- 2. Stage files ---
Write-Host "==> Step 2/3: Stage release files into $stagingDir"
if (Test-Path $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

# PyInstaller --onefile 默认输出到 dist\ 目录
$executable = Join-Path $repoRoot "dist\SoftwareInstaller.exe"
if (-not (Test-Path $executable)) {
    Write-Host "[错误] 找不到 $executable,请先运行打包步骤或删除 -SkipExeBuild。" -ForegroundColor Red
    exit 1
}

# exe 单独处理(在 dist\ 下),其他文件在项目根
Copy-Item -LiteralPath $executable -Destination $stagingDir -Force

$launchFiles = @(
    "Start-SoftwareInstaller.bat",
    "启动安装包管理器.bat",
    "README.md",
    "README_InstallerManager.md"
)

foreach ($file in $launchFiles) {
    $src = Join-Path $repoRoot $file
    if (Test-Path $src) {
        Copy-Item -LiteralPath $src -Destination $stagingDir -Force
    } else {
        Write-Host "  [跳过] 缺失文件: $file"
    }
}

# --- 3. Zip ---
Write-Host "==> Step 3/3: Compress to $zipPath"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
$packageItems = @(Get-ChildItem -LiteralPath $stagingDir -Force | Select-Object -ExpandProperty FullName)
Compress-Archive -LiteralPath $packageItems -DestinationPath $zipPath -Force

$sizeMb = [Math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host ""
Write-Host "✓ 发布包已生成: $zipPath ($sizeMb MB)" -ForegroundColor Green
Write-Host ""
Write-Host "使用方式:"
Write-Host "  1. 解压 zip 到任意目录"
Write-Host "  2. 把要部署的安装包放在该目录下(可放子目录)"
Write-Host "  3. 双击 `Start-SoftwareInstaller.bat`(或 `启动安装包管理器.bat`)"
Write-Host ""