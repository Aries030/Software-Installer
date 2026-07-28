# Windows Installer Package Manager

This repository contains a Windows GUI for scanning installer packages in the app folder, selecting packages, and installing them in order.

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
