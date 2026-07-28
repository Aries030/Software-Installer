# Software Installer

Software Installer is a portable Windows desktop tool for enterprise-style package deployment. It scans the application folder and its subfolders for installer packages, lets you select what to deploy, then launches each installer in sequence.

The interface is designed for an IT operations workflow: dark surfaces, blue action emphasis, package counters, deployment details, command preview, and an activity log.

## Download

Use the latest package from GitHub Releases:

[Download Releases](https://github.com/Aries030/Software-Installer/releases)

The normal usage flow is:

1. Download `Software-Installer-<version>.zip`.
2. Extract the zip to the folder that contains your installer packages, or copy installer packages into the extracted folder.
3. Open `Start-SoftwareInstaller.bat`.
4. Select packages and click `Deploy selected`.

No installation is required.

## Supported Installer Files

The scanner searches the tool folder and its subfolders for:

```text
.exe .msi .msu .msp .bat .cmd
```

The app ignores development and release folders such as `.git`, `.github`, `dist`, virtual environments, `node_modules`, and the application launcher files.

## Deployment Behavior

Software Installer starts each selected package and waits for that process to exit before continuing. If an installer needs manual interaction, the queue pauses naturally until the user finishes that installer.

Default silent arguments:

- `.msi`: `msiexec /i <file> /qn /norestart`
- `.msp`: `msiexec /p <file> /qn /norestart`
- `.msu`: `wusa <file> /quiet /norestart`
- `.exe`: `<file> /S`
- `.bat` / `.cmd`: `cmd /c <file>`

Different `.exe` installers use different silent flags. For example, Inno Setup installers often use:

```text
/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
```

Select a package and edit `INSTALL ARGUMENTS` when a vendor requires different silent parameters.

## Build A Portable Zip

Run:

```powershell
.\Build-Release.ps1 -Version 1.1.0
```

The zip is written to:

```text
dist\Software-Installer-1.1.0.zip
```

## GitHub Release Process

Push a version tag to trigger the Release workflow:

```powershell
git tag v1.1.0
git push origin v1.1.0
```

GitHub Actions will build the portable zip and publish it to the repository Releases page.
