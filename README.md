# Windows Installer Package Manager

This repository contains two small utilities:

- `InstallerManager.ps1`: a Windows GUI for scanning installer packages in the app folder, selecting packages, and installing them in order.
- `disk_hider`: a Kylin Linux terminal utility for hiding selected disk partitions from desktop file managers.

## Installer Package Manager

Use this tool when you have a folder full of software installers and want to choose which ones to install.

### Start On Windows

Double-click:

```bat
启动安装包管理器.bat
```

If the selected installers require administrator privileges, right-click the batch file and choose "Run as administrator", or click `Run admin` in the app.

### Supported Installer Files

The scanner searches the tool folder and its subfolders for:

```text
.exe .msi .msu .msp .bat .cmd
```

It ignores local development folders and generated bundles such as `.git`, virtual environments, `node_modules`, and `KylinDiskHider_USB`.

### Install Flow

1. Click `Rescan` to find installer packages.
2. Filter by file name, extension, or folder.
3. Select the packages to install.
4. Optionally edit the arguments for the selected installer.
5. Click `Install selected`.

The app starts each installer and waits for it to exit before continuing. If an installer needs manual clicks, the workflow naturally pauses until that installer process finishes.

### Default Silent Arguments

- `.msi`: `msiexec /i <file> /qn /norestart`
- `.msp`: `msiexec /p <file> /qn /norestart`
- `.msu`: `wusa <file> /quiet /norestart`
- `.exe`: `<file> /S`
- `.bat` / `.cmd`: `cmd /c <file>`

Different `.exe` installers use different silent flags. For example, Inno Setup installers often use:

```text
/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
```

## Python GUI Variant

There is also a Python/Tkinter implementation:

```powershell
python run_installer_app.py
```

The PowerShell version is the recommended default because it works on Windows without installing Python.

## Kylin Disk Hider

A small terminal utility for Kylin Linux. It hides selected disk partitions from udisks2-aware desktop tools by writing udev rules.

Run on Kylin:

```bash
sudo python3 main.py
```

The tool lists partitions in the terminal. Type numbers to add them to the hidden list, for example:

```text
1 3
```

Running the tool again and typing `2` keeps the already hidden partitions and adds partition 2. To unhide partitions, type `u 2 3`. To clear all hidden partitions, type `n`.

If you want a batch-file-like launcher on Kylin, run:

```bash
chmod +x run_admin.sh
./run_admin.sh
```

The tool reads partitions from:

```bash
lsblk -J -o NAME,PATH,FSTYPE,SIZE,UUID,LABEL,MOUNTPOINT,TYPE
```

When you apply the selection, it writes:

```text
/etc/udev/rules.d/99-kylin-disk-hider.rules
```

Each hidden partition is represented as:

```text
ENV{ID_FS_UUID}=="<partition-uuid>", ENV{UDISKS_IGNORE}="1", ENV{UDISKS_PRESENTATION_HIDE}="1"
```

After writing rules, the tool reloads udev and tries to unmount selected non-critical partitions so the file manager stops showing stale mounted entries.
