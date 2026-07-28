Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:ScriptPath = $MyInvocation.MyCommand.Path
$script:RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:Packages = @()
$script:CustomArgs = @{}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-InstallerFiles {
    param([string]$Root)

    $extensions = @(".exe", ".msi", ".msu", ".msp", ".bat", ".cmd")
    $ignored = @(".git", "__pycache__", "venv", ".venv", "env", "node_modules", "installer_manager")

    Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $file = $_
            if ($extensions -notcontains $file.Extension.ToLowerInvariant()) {
                return $false
            }
            foreach ($part in $file.FullName.Substring($Root.Length).Split([IO.Path]::DirectorySeparatorChar)) {
                if ($ignored -contains $part -or $part.StartsWith(".")) {
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

function Join-Preview {
    param($Parts)

    $all = @($Parts.File) + @($Parts.Args)
    return ($all | ForEach-Object { Quote-ProcessArg $_ }) -join " "
}

function Quote-ProcessArg {
    param([string]$Text)

    if ($null -eq $Text) {
        return '""'
    }
    if ($Text -eq "") {
        return '""'
    }
    if ($Text -match '[\s"]') {
        return '"' + $Text.Replace('"', '\"') + '"'
    }
    return $Text
}

function Join-ProcessArgs {
    param([object[]]$Args)

    return ($Args | ForEach-Object {
        $text = [string]$_
        Quote-ProcessArg $text
    }) -join " "
}

function Write-Log {
    param([string]$Message)

    $logBox.AppendText($Message + [Environment]::NewLine)
    $logBox.SelectionStart = $logBox.Text.Length
    $logBox.ScrollToCaret()
}

function Update-Status {
    $mode = "standard"
    if (Test-IsAdmin) {
        $mode = "administrator"
    }
    $statusLabel.Text = "Showing {0}, selected {1}, mode: {2}" -f $grid.Rows.Count, (Get-SelectedRows).Count, $mode
}

function Refresh-Grid {
    $keyword = $filterBox.Text.Trim().ToLowerInvariant()
    $grid.Rows.Clear()

    foreach ($file in $script:Packages) {
        $relativeFolder = "."
        if ($file.DirectoryName.Length -gt $script:RootDir.Length) {
            $relativeFolder = $file.DirectoryName.Substring($script:RootDir.Length).TrimStart("\")
        }

        $haystack = ($file.Name + " " + $relativeFolder + " " + $file.Extension).ToLowerInvariant()
        if ($keyword -and -not $haystack.Contains($keyword)) {
            continue
        }

        $row = $grid.Rows.Add($false, $file.Name, $file.Extension, ("{0:N1} MB" -f ($file.Length / 1MB)), $relativeFolder, $file.FullName)
        $grid.Rows[$row].Tag = $file
    }

    Update-Status
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
        $argsBox.Text = ""
        $previewBox.Text = ""
        return
    }

    $path = $grid.CurrentRow.Tag.FullName
    if ($script:CustomArgs.ContainsKey($path)) {
        $argsBox.Text = $script:CustomArgs[$path]
    } else {
        $argsBox.Text = ""
    }
    $previewBox.Text = Join-Preview (Get-CommandParts $path $argsBox.Text)
}

function Scan-Packages {
    $script:Packages = @(Get-InstallerFiles $script:RootDir)
    Refresh-Grid
    Write-Log ("Scanned {0} installer package(s)." -f $script:Packages.Count)
}

$form = New-Object Windows.Forms.Form
$form.Text = "Installer Package Manager"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object Drawing.Size(1080, 720)
$form.MinimumSize = New-Object Drawing.Size(900, 580)

$topPanel = New-Object Windows.Forms.Panel
$topPanel.Dock = "Top"
$topPanel.Height = 76
$form.Controls.Add($topPanel)

$dirLabel = New-Object Windows.Forms.Label
$dirLabel.Text = "Scan folder"
$dirLabel.Location = New-Object Drawing.Point(12, 14)
$dirLabel.AutoSize = $true
$topPanel.Controls.Add($dirLabel)

$dirBox = New-Object Windows.Forms.TextBox
$dirBox.Location = New-Object Drawing.Point(92, 10)
$dirBox.Size = New-Object Drawing.Size(700, 24)
$dirBox.ReadOnly = $true
$dirBox.Text = $script:RootDir
$topPanel.Controls.Add($dirBox)

$chooseButton = New-Object Windows.Forms.Button
$chooseButton.Text = "Choose"
$chooseButton.Location = New-Object Drawing.Point(804, 8)
$chooseButton.Size = New-Object Drawing.Size(80, 28)
$topPanel.Controls.Add($chooseButton)

$scanButton = New-Object Windows.Forms.Button
$scanButton.Text = "Rescan"
$scanButton.Location = New-Object Drawing.Point(894, 8)
$scanButton.Size = New-Object Drawing.Size(80, 28)
$topPanel.Controls.Add($scanButton)

$adminButton = New-Object Windows.Forms.Button
$adminButton.Text = "Run admin"
$adminButton.Location = New-Object Drawing.Point(984, 8)
$adminButton.Size = New-Object Drawing.Size(86, 28)
$adminButton.Enabled = -not (Test-IsAdmin)
$topPanel.Controls.Add($adminButton)

$filterLabel = New-Object Windows.Forms.Label
$filterLabel.Text = "Filter"
$filterLabel.Location = New-Object Drawing.Point(12, 47)
$filterLabel.AutoSize = $true
$topPanel.Controls.Add($filterLabel)

$filterBox = New-Object Windows.Forms.TextBox
$filterBox.Location = New-Object Drawing.Point(92, 43)
$filterBox.Size = New-Object Drawing.Size(700, 24)
$topPanel.Controls.Add($filterBox)

$selectAllButton = New-Object Windows.Forms.Button
$selectAllButton.Text = "Select all"
$selectAllButton.Location = New-Object Drawing.Point(804, 41)
$selectAllButton.Size = New-Object Drawing.Size(80, 28)
$topPanel.Controls.Add($selectAllButton)

$clearButton = New-Object Windows.Forms.Button
$clearButton.Text = "Clear"
$clearButton.Location = New-Object Drawing.Point(894, 41)
$clearButton.Size = New-Object Drawing.Size(80, 28)
$topPanel.Controls.Add($clearButton)

$statusLabel = New-Object Windows.Forms.Label
$statusLabel.Dock = "Bottom"
$statusLabel.Height = 24
$statusLabel.Text = "Ready"
$form.Controls.Add($statusLabel)

$split = New-Object Windows.Forms.SplitContainer
$split.Dock = "Fill"
$split.SplitterDistance = 660
$form.Controls.Add($split)

$grid = New-Object Windows.Forms.DataGridView
$grid.Dock = "Fill"
$grid.AllowUserToAddRows = $false
$grid.AllowUserToDeleteRows = $false
$grid.SelectionMode = "FullRowSelect"
$grid.MultiSelect = $false
$grid.AutoSizeColumnsMode = "Fill"
$split.Panel1.Controls.Add($grid)

$checkColumn = New-Object Windows.Forms.DataGridViewCheckBoxColumn
$checkColumn.HeaderText = "Install"
$checkColumn.Width = 60
$checkColumn.FillWeight = 14
$grid.Columns.Add($checkColumn) | Out-Null

foreach ($column in @(
    @{ Name = "Name"; Weight = 42 },
    @{ Name = "Type"; Weight = 12 },
    @{ Name = "Size"; Weight = 16 },
    @{ Name = "Folder"; Weight = 36 },
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
$rightPanel.RowCount = 7
$rightPanel.Padding = New-Object Windows.Forms.Padding(10)
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 24)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 32)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 24)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 92)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 42)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute, 24)))
$rightPanel.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent, 100)))
$split.Panel2.Controls.Add($rightPanel)

$argsLabel = New-Object Windows.Forms.Label
$argsLabel.Text = "Install arguments"
$argsLabel.Dock = "Fill"
$rightPanel.Controls.Add($argsLabel, 0, 0)

$argsBox = New-Object Windows.Forms.TextBox
$argsBox.Dock = "Fill"
$rightPanel.Controls.Add($argsBox, 0, 1)

$previewLabel = New-Object Windows.Forms.Label
$previewLabel.Text = "Command preview"
$previewLabel.Dock = "Fill"
$rightPanel.Controls.Add($previewLabel, 0, 2)

$previewBox = New-Object Windows.Forms.TextBox
$previewBox.Dock = "Fill"
$previewBox.Multiline = $true
$previewBox.ReadOnly = $true
$previewBox.ScrollBars = "Vertical"
$rightPanel.Controls.Add($previewBox, 0, 3)

$installButton = New-Object Windows.Forms.Button
$installButton.Text = "Install selected"
$installButton.Dock = "Fill"
$rightPanel.Controls.Add($installButton, 0, 4)

$logLabel = New-Object Windows.Forms.Label
$logLabel.Text = "Log"
$logLabel.Dock = "Fill"
$rightPanel.Controls.Add($logLabel, 0, 5)

$logBox = New-Object Windows.Forms.TextBox
$logBox.Dock = "Fill"
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
$rightPanel.Controls.Add($logBox, 0, 6)

$chooseButton.Add_Click({
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    $dialog.SelectedPath = $script:RootDir
    if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        $script:RootDir = $dialog.SelectedPath
        $dirBox.Text = $script:RootDir
        Scan-Packages
    }
})

$adminButton.Add_Click({
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
        [Windows.Forms.MessageBox]::Show(("Failed to restart as administrator: " + $_.Exception.Message), "Run admin") | Out-Null
    }
})

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

$grid.Add_CellValueChanged({
    Update-Status
})

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
        [Windows.Forms.MessageBox]::Show("Select at least one installer first.", "No selection") | Out-Null
        return
    }

    $answer = [Windows.Forms.MessageBox]::Show(
        ("Install {0} selected package(s) in order?" -f $rows.Count),
        "Confirm",
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question
    )
    if ($answer -ne [Windows.Forms.DialogResult]::Yes) {
        return
    }

    $installButton.Enabled = $false
    try {
        for ($i = 0; $i -lt $rows.Count; $i++) {
            $file = $rows[$i].Tag
            $args = ""
            if ($script:CustomArgs.ContainsKey($file.FullName)) {
                $args = $script:CustomArgs[$file.FullName]
            }
            $parts = Get-CommandParts $file.FullName $args
            Write-Log ("[{0}/{1}] Installing: {2}" -f ($i + 1), $rows.Count, $file.FullName)
            Write-Log ("Command: " + (Join-Preview $parts))

            $process = Start-Process -FilePath $parts.File -ArgumentList (Join-ProcessArgs $parts.Args) -WorkingDirectory $file.DirectoryName -Wait -PassThru
            if (@(0, 3010, 1641) -notcontains $process.ExitCode) {
                Write-Log ("Exit code {0}. Stopped." -f $process.ExitCode)
                return
            }
            Write-Log "Done."
        }
        Write-Log "All selected packages finished."
    } catch {
        Write-Log ("Failed: " + $_.Exception.Message)
    } finally {
        $installButton.Enabled = $true
    }
})

Scan-Packages
[void]$form.ShowDialog()
