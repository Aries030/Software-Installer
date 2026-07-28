import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


INSTALLER_EXTENSIONS = {".exe", ".msi", ".msu", ".msp", ".bat", ".cmd"}
IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "installer_manager",
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


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_installers(root: Path, extensions: Iterable[str] = INSTALLER_EXTENSIONS) -> List[InstallerPackage]:
    normalized_extensions = {ext.lower() for ext in extensions}
    packages: List[InstallerPackage] = []

    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = [
            name
            for name in dir_names
            if name not in IGNORED_DIR_NAMES and not name.startswith(".")
        ]

        for file_name in file_names:
            path = Path(current_root) / file_name
            if path.suffix.lower() in normalized_extensions:
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
        lower_name = path.name.lower()
        if "setup" in lower_name or "install" in lower_name:
            return [str(path), "/S"]
        return [str(path), "/S"]
    return [str(path)]


def command_preview(path: Path, custom_args: Optional[str] = None) -> str:
    command = build_command(path, custom_args)
    return " ".join(quote_argument(part) for part in command)


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


def split_windows_arguments(raw_args: str) -> List[str]:
    import shlex

    return shlex.split(raw_args, posix=True)


def quote_argument(argument: str) -> str:
    if not argument:
        return '""'
    if any(char.isspace() for char in argument) or '"' in argument:
        return '"' + argument.replace('"', '\\"') + '"'
    return argument


def install_package(path: Path, custom_args: Optional[str] = None) -> int:
    command = build_command(path, custom_args)
    completed = subprocess.run(command, cwd=str(path.parent), shell=False, check=False)
    return int(completed.returncode)
