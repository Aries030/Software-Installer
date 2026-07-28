# Software Installer

> **批量静默部署 · 一键搞定**
> 面向 IT 运维 / 软件分发场景的便携式 Windows 安装包管理器

Software Installer 会扫描指定目录(含子目录)下的安装包,让你勾选并按顺序静默部署。
现代化的暗色界面、实时命令预览、进度条与详细日志,把繁琐的批量装机变成 1-2-3 三步。

![Software Installer 主界面](assets/logo_256.png)

---

## 特性一览

- **完全免安装**:单个 ZIP 包下载,解压即用,无需 Python 环境,无注册表残留
- **现代化 UI**:暗色主题、圆角扁平、清晰分区,基于 [customtkinter](https://github.com/TomSchimansky/CustomTkinter)
- **智能扫描**:自动发现 `.exe / .msi / .msu / .msp / .bat / .cmd`,支持任意层级子目录
- **批量部署**:一键按顺序静默安装,可中途取消
- **实时预览**:每个包的静默参数均可编辑,命令预览即时刷新
- **进度可见**:进度条 + 详细日志(时间戳 + 序号 + 返回码说明)
- **典型返回码友好提示**:1602/1603/1618/3010 等常见错误码附带中文解释
- **小巧体积**:单个 exe 仅约 18 MB,zip 发布包约 17 MB
- **中文友好**:全中文 UI,双启动脚本(中英两套)

## 使用流程(3 步搞定)

```
┌──────────────────────────────────────────────────────┐
│  1. 下载 Software-Installer-<version>.zip           │
│  2. 解压到任意目录(推荐直接放到安装包所在目录)       │
│  3. 双击 启动安装包管理器.bat(或 Start-Software.bat)│
└──────────────────────────────────────────────────────┘
```

第一次打开后,程序会扫描本目录(含子目录)中的所有安装包,你只需要:

1. 在左侧列表里 **勾选** 要安装的软件(支持双击行、点勾选框、按住回车快速勾选)
2. 在右侧详情区按需 **修改安装参数**(留空使用默认静默参数)
3. 点击底部的 **▶ 开始安装** 按钮,即可按顺序静默部署

> 💡 想要扫描其他目录?直接点击工具栏的"选择目录",或者把要部署的安装包复制/移动到本目录后点"重新扫描"。

## 支持的安装包类型

| 类型  | 默认静默参数                                   |
| ----- | ---------------------------------------------- |
| `.msi` | `msiexec /i <file> /qn /norestart`           |
| `.msp` | `msiexec /p <file> /qn /norestart`           |
| `.msu` | `wusa <file> /quiet /norestart`              |
| `.exe` | `<file> /S`(NSIS / Inno Setup 通用)          |
| `.bat` | `cmd /c <file>`                              |
| `.cmd` | `cmd /c <file>`                              |

> 不同厂商的 `.exe` 静默参数可能不同,例如 Inno Setup 通常用:
> ```
> /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
> ```
> 选中对应包后,在右侧"安装参数"里覆盖即可。

## 典型返回码说明

| 返回码 | 含义                                       |
| ------ | ------------------------------------------ |
| 0      | 成功                                       |
| 1602   | 用户取消安装                               |
| 1603   | 安装过程中发生严重错误(可能被其他安装阻塞) |
| 1618   | 另一个安装正在进行                         |
| 1638   | 已有另一个版本的此产品安装                 |
| 3010   | 需要重启系统才能完成                       |
| 2359304 | 此更新已安装(仅 .msu)                    |

## 项目结构

```
Software-Installer/
├── SoftwareInstaller.exe          # 主程序(PyInstaller 打包,内置 Python+Tk+CustomTk+PIL+LOGO)
├── Start-SoftwareInstaller.bat    # 英文启动脚本
├── 启动安装包管理器.bat             # 中文启动脚本
├── README.md                      # 本文档
├── assets/
│   ├── logo.svg                   # 矢量 LOGO 源文件
│   ├── logo.png                   # 512x512 PNG
│   ├── logo_256.png               # 256x256 PNG(README/UI 预览)
│   ├── logo.ico                   # 多尺寸图标(嵌入 exe,用于任务栏/标题栏)
│   └── make_logo.py               # LOGO 生成脚本
├── installer_manager/
│   ├── __init__.py
│   ├── core.py                    # 核心逻辑(扫描、命令构建、安装执行)
│   └── gui.py                     # customtkinter GUI
├── run_installer_app.py           # Python 入口
├── Build-Release.ps1              # 发布构建脚本(PowerShell)
└── .github/workflows/
    ├── ci.yml                     # CI(PowerShell + Python 语法校验)
    └── release.yml                # Release 工作流
```

## 构建发布包

需要本地环境:
- Python 3.10+
- `pip install customtkinter pillow pyinstaller`

```powershell
# 默认:全量打包(Python → exe → zip)
.\Build-Release.ps1 -Version 1.2.0

# 跳过 exe 重建,只重新打 zip
.\Build-Release.ps1 -Version 1.2.0 -SkipExeBuild
```

产物:`dist\Software-Installer-1.2.0.zip`

## GitHub Release 发布流程

```powershell
git tag v1.2.0
git push origin v1.2.0
```

GitHub Actions 会自动构建并发布到 Releases 页面。

## 开发模式

```powershell
# 安装依赖
pip install customtkinter pillow

# 直接运行(需要 Python 环境)
python run_installer_app.py

# 或在 PowerShell 里
python -m installer_manager.gui
```

## 设计 LOGO

`assets/logo.svg` 是矢量源文件,如需调整:
1. 编辑 `assets/logo.svg`
2. 运行 `python assets/make_logo.py` 重新生成 PNG/ICO

## 系统要求

- Windows 10 / 11(64 位)
- 不需要任何运行时(Python、.NET 已嵌入到 exe 中)
- 建议以普通用户身份运行;遇到 `1603` 等权限错误时,以管理员身份重新启动

## License

MIT