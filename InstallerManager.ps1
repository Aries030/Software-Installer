Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)

$script:AppName = "Software Installer"
$script:AppVersion = "1.1.0"
$script:ScriptPath = $MyInvocation.MyCommand.Path
$script:RootDir = Split-Path -Parent $script:ScriptPath
$script:Packages = @()
$script:CustomArgs = @{}

$script:Colors = @{
    Background = [Drawing.Color]::FromArgb(11, 18, 32)
    Surface = [Drawing.Color]::FromArgb(17, 27, 46)
    SurfaceAlt = [Drawing.Color]::FromArgb(22, 35, 58)
    Border = [Drawing.Color]::FromArgb(44, 62, 91)
    Accent = [Drawing.Color]::FromArgb(0, 120, 212)
    AccentHover = [Drawing.Color]::FromArgb(24, 144, 255)
    Text = [Drawing.Color]::FromArgb(236, 244, 255)
    Muted = [Drawing.Color]::FromArgb(148, 163, 184)
    Success = [Drawing.Color]::FromArgb(45, 212, 191)
    Warning = [Drawing.Color]::FromArgb(245, 158, 11)
    Error = [Drawing.Color]::FromArgb(248, 113, 113)
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-Font {
    param(
        [float]$Size,
        [Drawing.FontStyle]$Style = [Drawing.FontStyle]::Regular
    )
    return New-Object Drawing.Font("Segoe UI", $Size, $Style)
}

function Set-FlatButton {
    param(
        [Windows.Forms.Button]$Button,
        [Drawing.Color]$BackColor = $script:Colors.SurfaceAlt,
        [Drawing.Color]$ForeColor = $script:Colors.Text
    )

    $Button.FlatStyle = [Windows.Forms.FlatStyle]::Flat
    $Button.FlatAppearance.BorderSize = 1
    $Button.FlatAppearance.BorderColor = $script:Colors.Border
    $Button.BackColor = $BackColor
    $Button.ForeColor = $ForeColor
    $Button.Font = New-Font 9.0 ([Drawing.FontStyle]::Bold)
    $Button.Cursor = [Windows.Forms.Cursors]::Hand
    $Button.UseVisualStyleBackColor = $false
}

function New-Button {
    param(
        [string]$Text,
        [Drawing.Color]$BackColor = $script:Colors.SurfaceAlt,
        [Drawing.Color]$ForeColor = $script:Colors.Text
    )

    $button = New-Object Windows.Forms.Button
    $button.Text = $Text
    $button.Height = 34
    Set-FlatButton $button $BackColor $ForeColor
    return $button
}

function New-Label {
    param(
        [string]$Text,
        [float]$Size = 9.0,
        [Drawing.Color]$Color = $script:Colors.Text,
        [Drawing.FontStyle]$Style = [Drawing.FontStyle]::Regular
    )

    $label = New-Object Windows.Forms.Label
    $label.Text = $Text
    $label.ForeColor = $Color
    $label.Font = New-Font $Size $Style
    $label.AutoSize = $true
    return $label
}

function Style-TextBox {
    param([Windows.Forms.TextBox]$TextBox)

    $TextBox.BackColor = [Drawing.Color]::FromArgb(8, 14, 25)
    $TextBox.ForeColor = $script:Colors.Text
    $TextBox.BorderStyle = [Windows.Forms.BorderStyle]::FixedSingle
    $TextBox.Font = New-Font 9.0
}

function Get-InstallerFiles {
    param([string]$Root)

    $extensions = @(".exe", ".msi", ".msu", ".msp", ".bat", ".cmd")
    $ignoredDirs = @(".git", ".github", "__pycache__", "dist", "release", "venv", ".venv", "env", "node_modules", "installer_manager")
    $ignoredFiles = @(
        "InstallerManager.ps1",
        "Build-Release.ps1",
        "Start-SoftwareInstaller.bat",
        "启动安装包管理器.bat"
    )

    Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $file = $_
            if ($extensions -notcontains $file.Extension.ToLowerInvariant()) {
                return $false
            }
            if ($ignoredFiles -contains $file.Name) {
                return $false
            }
            foreach ($part in $file.FullName.Substring($Root.Length).Split([IO.Path]::DirectorySeparatorChar)) {
                if ($ignoredDirs -contains $part -or $part.StartsWith(".")) {
                    return $false
                }
            }
            return $true
        } |
        Sort-Object DirectoryName, Name
}

function Split-Args {
    param([string]$Raw)

    if ([string]::IsNullOrWhiteSpace($Raw)) {
        return @()
    }

    $matches = [regex]::Matches($Raw, '("[^"]*"|\S+)')
    $items = @()
    foreach ($match in $matches) {
        $item = $match.Value
        if ($item.StartsWith('"') -and $item.EndsWith('"') -and $item.Length -ge 2) {
            $item = $item.Substring(1, $item.Length - 2)
        }
        $items += $item
    }
    return $items
}

function Get-CommandParts {
    param(
        [string]$Path,
        [string]$Args
    )

    $ext = [IO.Path]::GetExtension($Path).ToLowerInvariant()
    $custom = Split-Args $Args

    if ($custom.Count -gt 0) {
        switch ($ext) {
            ".msi" { return @{ File = "msiexec"; Args = @("/i", $Path) + $custom } }
            ".msp" { return @{ File = "msiexec"; Args = @("/p", $Path) + $custom } }
            ".msu" { return @{ File = "wusa"; Args = @($Path) + $custom } }
            ".bat" { return @{ File = "cmd"; Args = @("/c", $Path) + $custom } }
            ".cmd" { return @{ File = "cmd"; Args = @("/c", $Path) + $custom } }
            default { return @{ File = $Path; Args = $custom } }
        }
    }

    switch ($ext) {
        ".msi" { return @{ File = "msiexec"; Args = @("/i", $Path, "/qn", "/norestart") } }
        ".msp" { return @{ File = "msiexec"; Args = @("/p", $Path, "/qn", "/norestart") } }
        ".msu" { return @{ File = "wusa"; Args = @($Path, "/quiet", "/norestart") } }
        ".bat" { return @{ File = "cmd"; Args = @("/c", $Path) } }
        ".cmd" { return @{ File = "cmd"; Args = @("/c", $Path) } }
        default { return @{ File = $Path; Args = @("/S") } }
    }
}

function Quote-ProcessArg {
    param([string]$Text)

    if ($null -eq $Text -or $Text -eq "") {
        return '""'
    }
    if ($Text -match '[\s"]') {
        return '"' + $Text.Replace('"', '\"') + '"'
    }
    return $Text
}

function Join-Preview {
    param($Parts)

    $all = @($Parts.File) + @($Parts.Args)
    return ($all | ForEach-Object { Quote-ProcessArg $_ }) -join " "
}

function Join-ProcessArgs {
    param([object[]]$Args)

    return ($Args | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "
}

function Get-RelativeFolder {
    param([IO.FileInfo]$File)

    if ($File.DirectoryName.Length -gt $script:RootDir.Length) {
        return $File.DirectoryName.Substring($script:RootDir.Length).TrimStart("\")
    }
    return "."
}

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "HH:mm:ss"
    $logBox.AppendText("[{0}] [{1}] {2}{3}" -f $timestamp, $Level, $Message, [Environment]::NewLine)
    $logBox.SelectionStart = $logBox.Text.Length
    $logBox.ScrollToCaret()
}

function Update-Status {
    $mode = "Standard"
    $modeColor = $script:Colors.Warning
    if (Test-IsAdmin) {
        $mode = "Administrator"
        $modeColor = $script:Colors.Success
    }

    $statusValue.Text = $mode
    $statusValue.ForeColor = $modeColor
    $packageCountValue.Text = [string]$script:Packages.Count
    $visibleCountValue.Text = [string]$grid.Rows.Count
    $selectedCountValue.Text = [string](Get-SelectedRows).Count
    $footerLabel.Text = "Ready. Root: {0}" -f $script:RootDir
}

function Refresh-Grid {
    $keyword = $filterBox.Text.Trim().ToLowerInvariant()
    $grid.Rows.Clear()

    foreach ($file in $script:Packages) {
        $relativeFolder = Get-RelativeFolder $file
        $haystack = ($file.Name + " " + $relativeFolder + " " + $file.Extension).ToLowerInvariant()
        if ($keyword -and -not $haystack.Contains($keyword)) {
            continue
        }

        $rowIndex = $grid.Rows.Add($false, $file.Name, $file.Extension.ToUpperInvariant().TrimStart("."), ("{0:N1} MB" -f ($file.Length / 1MB)), $relativeFolder, $file.FullName)
        $grid.Rows[$rowIndex].Tag = $file
    }

    Update-Status
    Show-CurrentPreview
}

function Get-SelectedRows {
    $rows = @()
    foreach ($row in $grid.Rows) {
        if ($row.Cells[0].Value -eq $true) {
            $rows += $row
        }
    }
    return $rows
}

function Save-ArgsForCurrentRow {
    if ($grid.CurrentRow -eq $null -or $grid.CurrentRow.Tag -eq $null) {
        return
    }
    $path = $grid.CurrentRow.Tag.FullName
    if ([string]::IsNullOrWhiteSpace($argsBox.Text)) {
        $script:CustomArgs.Remove($path)
    } else {
        $script:CustomArgs[$path] = $argsBox.Text.Trim()
    }
}

function Show-CurrentPreview {
    if ($grid.CurrentRow -eq $null -or $grid.CurrentRow.Tag -eq $null) {
        $fileNameValue.Text = "No package selected"
        $folderValue.Text = "-"
        $argsBox.Text = ""
        $previewBox.Text = ""
        return
    }

    $file = $grid.CurrentRow.Tag
    $path = $file.FullName
    $fileNameValue.Text = $file.Name
    $folderValue.Text = Get-RelativeFolder $file

    if ($script:CustomArgs.ContainsKey($path)) {
        if ($argsBox.Text -ne $script:CustomArgs[$path]) {
            $argsBox.Text = $script:CustomArgs[$path]
        }
    } else {
        if ($argsBox.Text -ne "") {
            $argsBox.Text = ""
        }
    }
    $previewBox.Text = Join-Preview (Get-CommandParts $path $argsBox.Text)
}

function Scan-Packages {
    $script:Packages = @(Get-InstallerFiles $script:RootDir)
    Refresh-Grid
    Write-Log ("Scanned {0} installer package(s)." -f $script:Packages.Count)
}

function Restart-AsAdmin {
    try {
        Start-Process -FilePath "powershell" -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"' + $script:ScriptPath + '"')
        ) -Verb RunAs
        $form.Close()
    } catch {
        [Windows.Forms.MessageBox]::Show(("Failed to restart as administrator: " + $_.Exception.Message), "Run as administrator") | Out-Null
    }
}

$form = New-Object Windows.Forms.Form
$form.Text = "{0} {1}" -f $script:AppName, $script:AppVersion
$form.StartPosition = "CenterScreen"
$form.Size = New-Object Drawing.Size(1240, 760)
$form.MinimumSize = New-Object Drawing.Size(1040, 640)
$form.BackColor = $script:Colors.Background
$form.ForeColor = $script:Colors.Text
$form.Font = New-Font 9.0

$root = New-Object Windows.Forms.TableLayoutPanel
$root.Dock = "Fill"
$root.ColumnCount = 1
$root.RowCount = 4
$root.BackColor = $script:Colors.Background
$root.Padding = New-Object Windows.Forms.Padding(16)
$root.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 96)))
$root.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 58)))
$root.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent, 100)))
$root.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 28)))
$form.Controls.Add($root)

$header = New-Object Windows.Forms.TableLayoutPanel
$header.Dock = "Fill"
$header.ColumnCount = 2
$header.RowCount = 1
$header.BackColor = $script:Colors.Background
$header.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 58)))
$header.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 42)))
$root.Controls.Add($header, 0, 0)

$titlePanel = New-Object Windows.Forms.Panel
$titlePanel.Dock = "Fill"
$titlePanel.BackColor = $script:Colors.Background
$header.Controls.Add($titlePanel, 0, 0)

$titleLabel = New-Label $script:AppName 20.0 $script:Colors.Text ([Drawing.FontStyle]::Bold)
$titleLabel.Location = New-Object Drawing.Point(0, 8)
$titlePanel.Controls.Add($titleLabel)

$subtitleLabel = New-Label "Unattended package deployment console" 10.0 $script:Colors.Muted
$subtitleLabel.Location = New-Object Drawing.Point(2, 46)
$titlePanel.Controls.Add($subtitleLabel)

$versionLabel = New-Label ("Version {0}  |  Portable release" -f $script:AppVersion) 8.5 $script:Colors.Muted
$versionLabel.Location = New-Object Drawing.Point(2, 68)
$titlePanel.Controls.Add($versionLabel)

$metrics = New-Object Windows.Forms.TableLayoutPanel
$metrics.Dock = "Fill"
$metrics.ColumnCount = 4
$metrics.RowCount = 1
$metrics.BackColor = $script:Colors.Background
for ($i = 0; $i -lt 4; $i++) {
    $metrics.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 25)))
}
$header.Controls.Add($metrics, 1, 0)

function Add-Metric {
    param(
        [int]$Column,
        [string]$Label,
        [string]$Initial,
        [ref]$ValueRef
    )

    $panel = New-Object Windows.Forms.Panel
    $panel.Dock = "Fill"
    $panel.Margin = New-Object Windows.Forms.Padding(6, 6, 0, 10)
    $panel.BackColor = $script:Colors.Surface
    $metrics.Controls.Add($panel, $Column, 0)

    $caption = New-Label $Label 8.0 $script:Colors.Muted ([Drawing.FontStyle]::Bold)
    $caption.Location = New-Object Drawing.Point(12, 10)
    $panel.Controls.Add($caption)

    $value = New-Label $Initial 18.0 $script:Colors.Text ([Drawing.FontStyle]::Bold)
    $value.Location = New-Object Drawing.Point(12, 35)
    $panel.Controls.Add($value)
    $ValueRef.Value = $value
}

$packageCountValue = $null
$visibleCountValue = $null
$selectedCountValue = $null
$statusValue = $null
Add-Metric 0 "DISCOVERED" "0" ([ref]$packageCountValue)
Add-Metric 1 "VISIBLE" "0" ([ref]$visibleCountValue)
Add-Metric 2 "SELECTED" "0" ([ref]$selectedCountValue)
Add-Metric 3 "PRIVILEGE" "Standard" ([ref]$statusValue)

$toolbar = New-Object Windows.Forms.TableLayoutPanel
$toolbar.Dock = "Fill"
$toolbar.ColumnCount = 8
$toolbar.RowCount = 1
$toolbar.BackColor = $script:Colors.Surface
$toolbar.Padding = New-Object Windows.Forms.Padding(10, 10, 10, 8)
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, 84)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 46)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, 98)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, 98)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, 84)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 28)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, 104)))
$toolbar.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, 120)))
$root.Controls.Add($toolbar, 0, 1)

$folderLabel = New-Label "Folder" 9.0 $script:Colors.Muted ([Drawing.FontStyle]::Bold)
$folderLabel.Dock = "Fill"
$folderLabel.TextAlign = [Drawing.ContentAlignment]::MiddleLeft
$toolbar.Controls.Add($folderLabel, 0, 0)

$dirBox = New-Object Windows.Forms.TextBox
$dirBox.Dock = "Fill"
$dirBox.ReadOnly = $true
$dirBox.Text = $script:RootDir
Style-TextBox $dirBox
$toolbar.Controls.Add($dirBox, 1, 0)

$chooseButton = New-Button "Browse"
$chooseButton.Dock = "Fill"
$toolbar.Controls.Add($chooseButton, 2, 0)

$scanButton = New-Button "Rescan" $script:Colors.Accent
$scanButton.Dock = "Fill"
$toolbar.Controls.Add($scanButton, 3, 0)

$filterLabel = New-Label "Filter" 9.0 $script:Colors.Muted ([Drawing.FontStyle]::Bold)
$filterLabel.Dock = "Fill"
$filterLabel.TextAlign = [Drawing.ContentAlignment]::MiddleLeft
$toolbar.Controls.Add($filterLabel, 4, 0)

$filterBox = New-Object Windows.Forms.TextBox
$filterBox.Dock = "Fill"
Style-TextBox $filterBox
$toolbar.Controls.Add($filterBox, 5, 0)

$selectAllButton = New-Button "Select all"
$selectAllButton.Dock = "Fill"
$toolbar.Controls.Add($selectAllButton, 6, 0)

$adminButton = New-Button "Run admin" $script:Colors.SurfaceAlt
$adminButton.Dock = "Fill"
$adminButton.Enabled = -not (Test-IsAdmin)
$toolbar.Controls.Add($adminButton, 7, 0)

$split = New-Object Windows.Forms.SplitContainer
$split.Dock = "Fill"
$split.SplitterDistance = 760
$split.BackColor = $script:Colors.Background
$split.Panel1.BackColor = $script:Colors.Surface
$split.Panel2.BackColor = $script:Colors.Surface
$root.Controls.Add($split, 0, 2)

$grid = New-Object Windows.Forms.DataGridView
$grid.Dock = "Fill"
$grid.AllowUserToAddRows = $false
$grid.AllowUserToDeleteRows = $false
$grid.SelectionMode = "FullRowSelect"
$grid.MultiSelect = $false
$grid.AutoSizeColumnsMode = "Fill"
$grid.BackgroundColor = $script:Colors.Surface
$grid.BorderStyle = [Windows.Forms.BorderStyle]::None
$grid.CellBorderStyle = [Windows.Forms.DataGridViewCellBorderStyle]::SingleHorizontal
$grid.GridColor = $script:Colors.Border
$grid.RowHeadersVisible = $false
$grid.EnableHeadersVisualStyles = $false
$grid.ColumnHeadersBorderStyle = [Windows.Forms.DataGridViewHeaderBorderStyle]::Single
$grid.ColumnHeadersDefaultCellStyle.BackColor = [Drawing.Color]::FromArgb(9, 20, 38)
$grid.ColumnHeadersDefaultCellStyle.ForeColor = $script:Colors.Text
$grid.ColumnHeadersDefaultCellStyle.Font = New-Font 8.5 ([Drawing.FontStyle]::Bold)
$grid.ColumnHeadersDefaultCellStyle.SelectionBackColor = [Drawing.Color]::FromArgb(9, 20, 38)
$grid.DefaultCellStyle.BackColor = $script:Colors.Surface
$grid.DefaultCellStyle.ForeColor = $script:Colors.Text
$grid.DefaultCellStyle.SelectionBackColor = [Drawing.Color]::FromArgb(0, 86, 160)
$grid.DefaultCellStyle.SelectionForeColor = [Drawing.Color]::White
$grid.AlternatingRowsDefaultCellStyle.BackColor = [Drawing.Color]::FromArgb(14, 24, 42)
$grid.RowTemplate.Height = 34
$split.Panel1.Controls.Add($grid)

$checkColumn = New-Object Windows.Forms.DataGridViewCheckBoxColumn
$checkColumn.HeaderText = ""
$checkColumn.Width = 44
$checkColumn.FillWeight = 8
$grid.Columns.Add($checkColumn) | Out-Null

foreach ($column in @(
    @{ Name = "Package"; Weight = 42 },
    @{ Name = "Type"; Weight = 10 },
    @{ Name = "Size"; Weight = 14 },
    @{ Name = "Folder"; Weight = 34 },
    @{ Name = "Path"; Weight = 1 }
)) {
    $textColumn = New-Object Windows.Forms.DataGridViewTextBoxColumn
    $textColumn.HeaderText = $column.Name
    $textColumn.FillWeight = $column.Weight
    if ($column.Name -eq "Path") {
        $textColumn.Visible = $false
    }
    $grid.Columns.Add($textColumn) | Out-Null
}

$rightPanel = New-Object Windows.Forms.TableLayoutPanel
$rightPanel.Dock = "Fill"
$rightPanel.ColumnCount = 1
$rightPanel.RowCount = 12
$rightPanel.BackColor = $script:Colors.Surface
$rightPanel.Padding = New-Object Windows.Forms.Padding(16)
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 28)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 28)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 22)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 28)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 30)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 86)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 48)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 12)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 24)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent, 100)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 4)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 1)))
$split.Panel2.Controls.Add($rightPanel)

$detailsTitle = New-Label "Deployment details" 11.0 $script:Colors.Text ([Drawing.FontStyle]::Bold)
$detailsTitle.Dock = "Fill"
$rightPanel.Controls.Add($detailsTitle, 0, 0)

$fileNameValue = New-Label "No package selected" 9.0 $script:Colors.Text
$fileNameValue.Dock = "Fill"
$rightPanel.Controls.Add($fileNameValue, 0, 1)

$folderCaption = New-Label "SOURCE FOLDER" 8.0 $script:Colors.Muted ([Drawing.FontStyle]::Bold)
$folderCaption.Dock = "Fill"
$rightPanel.Controls.Add($folderCaption, 0, 2)

$folderValue = New-Label "-" 9.0 $script:Colors.Text
$folderValue.Dock = "Fill"
$rightPanel.Controls.Add($folderValue, 0, 3)

$argsLabel = New-Label "INSTALL ARGUMENTS" 8.0 $script:Colors.Muted ([Drawing.FontStyle]::Bold)
$argsLabel.Dock = "Fill"
$rightPanel.Controls.Add($argsLabel, 0, 4)

$argsBox = New-Object Windows.Forms.TextBox
$argsBox.Dock = "Fill"
$argsBox.Multiline = $true
Style-TextBox $argsBox
$rightPanel.Controls.Add($argsBox, 0, 5)

$buttonPanel = New-Object Windows.Forms.TableLayoutPanel
$buttonPanel.Dock = "Fill"
$buttonPanel.ColumnCount = 2
$buttonPanel.RowCount = 1
$buttonPanel.BackColor = $script:Colors.Surface
$buttonPanel.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 68)))
$buttonPanel.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 32)))
$rightPanel.Controls.Add($buttonPanel, 0, 6)

$installButton = New-Button "Deploy selected" $script:Colors.Accent
$installButton.Dock = "Fill"
$buttonPanel.Controls.Add($installButton, 0, 0)

$clearButton = New-Button "Clear"
$clearButton.Dock = "Fill"
$buttonPanel.Controls.Add($clearButton, 1, 0)

$previewLabel = New-Label "COMMAND PREVIEW" 8.0 $script:Colors.Muted ([Drawing.FontStyle]::Bold)
$previewLabel.Dock = "Fill"
$rightPanel.Controls.Add($previewLabel, 0, 8)

$logTabs = New-Object Windows.Forms.TabControl
$logTabs.Dock = "Fill"
$logTabs.Appearance = [Windows.Forms.TabAppearance]::FlatButtons
$logTabs.BackColor = $script:Colors.Surface
$logTabs.ForeColor = $script:Colors.Text
$rightPanel.Controls.Add($logTabs, 0, 9)

$previewPage = New-Object Windows.Forms.TabPage
$previewPage.Text = "Command"
$previewPage.BackColor = $script:Colors.SurfaceAlt
$logTabs.TabPages.Add($previewPage) | Out-Null

$previewBox = New-Object Windows.Forms.TextBox
$previewBox.Dock = "Fill"
$previewBox.Multiline = $true
$previewBox.ReadOnly = $true
$previewBox.ScrollBars = "Vertical"
Style-TextBox $previewBox
$previewPage.Controls.Add($previewBox)

$logPage = New-Object Windows.Forms.TabPage
$logPage.Text = "Activity log"
$logPage.BackColor = $script:Colors.SurfaceAlt
$logTabs.TabPages.Add($logPage) | Out-Null

$logBox = New-Object Windows.Forms.TextBox
$logBox.Dock = "Fill"
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
Style-TextBox $logBox
$logPage.Controls.Add($logBox)

$footerLabel = New-Label "Ready" 8.5 $script:Colors.Muted
$footerLabel.Dock = "Fill"
$footerLabel.TextAlign = [Drawing.ContentAlignment]::MiddleLeft
$root.Controls.Add($footerLabel, 0, 3)

$chooseButton.Add_Click({
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    $dialog.SelectedPath = $script:RootDir
    if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        $script:RootDir = $dialog.SelectedPath
        $dirBox.Text = $script:RootDir
        Scan-Packages
    }
})

$adminButton.Add_Click({ Restart-AsAdmin })
$scanButton.Add_Click({ Scan-Packages })
$filterBox.Add_TextChanged({ Refresh-Grid })

$selectAllButton.Add_Click({
    foreach ($row in $grid.Rows) {
        $row.Cells[0].Value = $true
    }
    Update-Status
})

$clearButton.Add_Click({
    foreach ($row in $grid.Rows) {
        $row.Cells[0].Value = $false
    }
    Update-Status
})

$grid.Add_CurrentCellDirtyStateChanged({
    if ($grid.IsCurrentCellDirty) {
        $grid.CommitEdit([Windows.Forms.DataGridViewDataErrorContexts]::Commit)
    }
})

$grid.Add_CellValueChanged({ Update-Status })
$grid.Add_SelectionChanged({ Show-CurrentPreview })

$argsBox.Add_TextChanged({
    if ($grid.CurrentRow -ne $null -and $grid.CurrentRow.Tag -ne $null) {
        $previewBox.Text = Join-Preview (Get-CommandParts $grid.CurrentRow.Tag.FullName $argsBox.Text)
    }
})
$argsBox.Add_Leave({ Save-ArgsForCurrentRow })

$installButton.Add_Click({
    Save-ArgsForCurrentRow
    $rows = @(Get-SelectedRows)
    if ($rows.Count -eq 0) {
        [Windows.Forms.MessageBox]::Show("Select at least one installer package first.", "No selection") | Out-Null
        return
    }

    $answer = [Windows.Forms.MessageBox]::Show(
        ("Deploy {0} selected package(s) in order? Interactive installers will pause the queue until they exit." -f $rows.Count),
        "Confirm deployment",
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question
    )
    if ($answer -ne [Windows.Forms.DialogResult]::Yes) {
        return
    }

    $installButton.Enabled = $false
    $logTabs.SelectedTab = $logPage
    try {
        for ($i = 0; $i -lt $rows.Count; $i++) {
            $file = $rows[$i].Tag
            $args = ""
            if ($script:CustomArgs.ContainsKey($file.FullName)) {
                $args = $script:CustomArgs[$file.FullName]
            }
            $parts = Get-CommandParts $file.FullName $args
            Write-Log ("[{0}/{1}] Starting: {2}" -f ($i + 1), $rows.Count, $file.FullName)
            Write-Log ("Command: " + (Join-Preview $parts))

            $process = Start-Process -FilePath $parts.File -ArgumentList (Join-ProcessArgs $parts.Args) -WorkingDirectory $file.DirectoryName -Wait -PassThru
            if (@(0, 3010, 1641) -notcontains $process.ExitCode) {
                Write-Log ("Exit code {0}. Queue stopped." -f $process.ExitCode) "ERROR"
                return
            }
            if (@(3010, 1641) -contains $process.ExitCode) {
                Write-Log ("Completed with restart-required code {0}." -f $process.ExitCode) "WARN"
            } else {
                Write-Log "Completed."
            }
        }
        Write-Log "All selected packages finished." "OK"
    } catch {
        Write-Log ("Failed: " + $_.Exception.Message) "ERROR"
    } finally {
        $installButton.Enabled = $true
    }
})

Scan-Packages
[void]$form.ShowDialog()
