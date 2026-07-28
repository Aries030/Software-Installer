"""Software Installer 的核心逻辑。

负责:
  - 扫描目录查找安装包
  - 构造静默安装命令
  - 按顺序执行安装并通过回调报告进度
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional


INSTALLER_EXTENSIONS = {".exe", ".msi", ".msu", ".msp", ".bat", ".cmd"}
IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "installer_manager",
    "assets",
    "dist",
    "build",
}


@dataclass(frozen=True)
class InstallerPackage:
    path: Path
    root: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()

    @property
    def relative_folder(self) -> str:
        try:
            parent = self.path.parent.relative_to(self.root)
        except ValueError:
            parent = self.path.parent
        return "." if str(parent) == "." else str(parent)

    @property
    def size_mb(self) -> float:
        try:
            return self.path.stat().st_size / 1024 / 1024
        except OSError:
            return 0.0


@dataclass
class InstallResult:
    """单次安装的执行结果。"""
    success: bool
    return_code: int
    message: str = ""


@dataclass
class InstallProgress:
    """批量安装过程中的进度事件。"""
    index: int                  # 1-based 当前序号
    total: int                  # 总数
    package: InstallerPackage
    stage: str = "start"        # start | finish | skipped | failed
    result: Optional[InstallResult] = None
    aborted: bool = False       # 因失败导致中断

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.index / self.total * 100.0


# 进度回调签名: (progress: InstallProgress) -> None
ProgressCallback = Callable[[InstallProgress], None]


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_installers(root: Path, extensions: Iterable[str] = INSTALLER_EXTENSIONS) -> List[InstallerPackage]:
    normalized_extensions = {ext.lower() for ext in extensions}
    packages: List[InstallerPackage] = []

    # frozen 模式下,排除工具自身的可执行文件(避免扫描到 SoftwareInstaller.exe)
    self_exe_name = None
    if getattr(sys, "frozen", False):
        self_exe_name = Path(sys.executable).name.lower()

    for current_root, dir_names, file_names in os.walk(root):
        # 跳过忽略目录,且跳过以 . 开头的隐藏目录
        dir_names[:] = [
            name
            for name in dir_names
            if name not in IGNORED_DIR_NAMES and not name.startswith(".")
        ]

        for file_name in file_names:
            path = Path(current_root) / file_name
            if path.suffix.lower() not in normalized_extensions:
                continue
            # 避免把自身启动脚本当作安装包
            if path.name.lower() in {"start-softwareinstaller.bat", "启动安装包管理器.bat"}:
                continue
            # frozen 模式下排除自身 exe
            if self_exe_name and path.name.lower() == self_exe_name:
                continue
            packages.append(InstallerPackage(path=path, root=root))

    return sorted(packages, key=lambda item: (item.relative_folder.lower(), item.name.lower()))


def default_arguments(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    if suffix == ".msi":
        return ["/i", str(path), "/qn", "/norestart"]
    if suffix == ".msp":
        return ["/p", str(path), "/qn", "/norestart"]
    if suffix == ".msu":
        return [str(path), "/quiet", "/norestart"]
    if suffix == ".exe":
        return [str(path), "/S"]
    return [str(path)]


def build_command(path: Path, custom_args: Optional[str] = None) -> List[str]:
    suffix = path.suffix.lower()
    if custom_args and custom_args.strip():
        args = split_windows_arguments(custom_args)
        if suffix in {".msi", ".msp"} and args and args[0].lower() == "msiexec":
            return args
        if suffix == ".msi":
            return ["msiexec", "/i", str(path), *args]
        if suffix == ".msp":
            return ["msiexec", "/p", str(path), *args]
        if suffix == ".msu":
            return ["wusa", str(path), *args]
        if suffix in {".bat", ".cmd"}:
            return ["cmd", "/c", str(path), *args]
        return [str(path), *args]

    args = default_arguments(path)
    if suffix in {".msi", ".msp"}:
        return ["msiexec", *args]
    if suffix == ".msu":
        return ["wusa", *args]
    if suffix in {".bat", ".cmd"}:
        return ["cmd", "/c", *args]
    return args


def command_preview(path: Path, custom_args: Optional[str] = None) -> str:
    command = build_command(path, custom_args)
    return " ".join(quote_argument(part) for part in command)


def split_windows_arguments(raw_args: str) -> List[str]:
    return shlex.split(raw_args, posix=True)


def quote_argument(argument: str) -> str:
    if not argument:
        return '""'
    if any(char.isspace() for char in argument) or '"' in argument:
        return '"' + argument.replace('"', '\\"') + '"'
    return argument


def explain_return_code(code: int, extension: str) -> str:
    """对常见 Windows 安装返回码给出友好解释。"""
    ext = extension.lower()
    if code == 0:
        return "成功"
    # MSI 通用错误码
    if ext in {".msi", ".msp"}:
        msi_codes = {
            1602: "用户取消安装",
            1603: "安装过程中发生严重错误(可能被其他安装阻塞)",
            1618: "另一个安装正在进行",
            1620: "写入磁盘失败",
            1638: "已有另一个版本的此产品安装",
            3010: "需要重启系统才能完成",
        }
        if code in msi_codes:
            return msi_codes[code]
    if ext == ".msu":
        if code == 2359304:  # 0x240006 - CBS_E_ALREADY_INSTALLED
            return "此更新已安装"
    if 3010 <= code <= 3013:
        return "需要重启系统才能完成"
    return "失败"


def install_package(
    path: Path,
    custom_args: Optional[str] = None,
    timeout: Optional[float] = None,
) -> InstallResult:
    """执行单个安装包,返回 InstallResult。"""
    command = build_command(path, custom_args)
    try:
        completed = subprocess.run(
            command,
            cwd=str(path.parent),
            shell=False,
            check=False,
            timeout=timeout,
        )
        code = int(completed.returncode)
        success = code == 0
        message = explain_return_code(code, path.suffix)
        return InstallResult(success=success, return_code=code, message=message)
    except subprocess.TimeoutExpired:
        return InstallResult(success=False, return_code=-1, message="安装超时")
    except FileNotFoundError as exc:
        return InstallResult(success=False, return_code=-2, message=f"未找到命令: {exc}")
    except PermissionError:
        return InstallResult(success=False, return_code=-3, message="权限不足,请尝试以管理员身份运行")
    except Exception as exc:  # noqa: BLE001
        return InstallResult(success=False, return_code=-99, message=f"异常: {exc}")


def install_packages_sequential(
    packages: List[InstallerPackage],
    custom_args: dict,
    on_progress: ProgressCallback,
    stop_on_error: bool = True,
) -> InstallResult:
    """按顺序执行批量安装,通过 on_progress 回调报告进度。"""
    total = len(packages)
    for index, package in enumerate(packages, start=1):
        args = custom_args.get(package.path, "")
        on_progress(InstallProgress(
            index=index, total=total, package=package, stage="start",
        ))
        result = install_package(package.path, args)
        if result.success:
            on_progress(InstallProgress(
                index=index, total=total, package=package,
                stage="finish", result=result,
            ))
        else:
            aborted = stop_on_error
            on_progress(InstallProgress(
                index=index, total=total, package=package,
                stage="failed", result=result, aborted=aborted,
            ))
            if aborted:
                return result
    return InstallResult(success=True, return_code=0, message="全部完成")