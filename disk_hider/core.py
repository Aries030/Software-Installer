import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set


RULE_PATH = Path("/etc/udev/rules.d/99-kylin-disk-hider.rules")
RULE_HEADER = "# Managed by Kylin Disk Hider. Edit from the app when possible."
UUID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True)
class Partition:
    name: str
    path: str
    size: str
    fstype: str
    uuid: str
    label: str
    mountpoint: str
    hidden: bool = False

    @property
    def display_name(self) -> str:
        parts = [self.path or self.name, self.size]
        if self.label:
            parts.append(self.label)
        if self.fstype:
            parts.append(self.fstype)
        return "  |  ".join(part for part in parts if part)


def sys_platform() -> str:
    return platform.system().lower()


def is_linux() -> bool:
    return sys_platform() == "linux"


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def is_probably_kylin() -> bool:
    if not is_linux():
        return False

    release_files = ["/etc/os-release", "/etc/kylin-release"]
    text = ""
    for release_file in release_files:
        try:
            text += Path(release_file).read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            pass

    if "kylin" in text or "\u9e92\u9e9f" in text:
        return True

    try:
        result = subprocess.run(
            ["lsb_release", "-a"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return "kylin" in (result.stdout + result.stderr).lower()


def get_hidden_uuids() -> Set[str]:
    try:
        content = RULE_PATH.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()

    hidden: Set[str] = set()
    for line in content.splitlines():
        match = re.search(r'ENV\{ID_FS_UUID\}=="([^"]+)".*ENV\{UDISKS_IGNORE\}="1"', line)
        if match:
            hidden.add(match.group(1))
    return hidden


def get_all_partitions() -> List[Partition]:
    if not is_linux():
        return get_mock_partitions()

    result = subprocess.run(
        ["lsblk", "-J", "-o", "NAME,PATH,FSTYPE,SIZE,UUID,LABEL,MOUNTPOINT,TYPE"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    data = json.loads(result.stdout)
    hidden_uuids = get_hidden_uuids()
    partitions: List[Partition] = []

    def visit(items: Iterable[dict]) -> None:
        for item in items:
            if item.get("type") == "part" and item.get("uuid"):
                uuid = str(item.get("uuid") or "")
                partitions.append(
                    Partition(
                        name=str(item.get("name") or ""),
                        path=str(item.get("path") or ""),
                        size=str(item.get("size") or ""),
                        fstype=str(item.get("fstype") or ""),
                        uuid=uuid,
                        label=str(item.get("label") or ""),
                        mountpoint=str(item.get("mountpoint") or ""),
                        hidden=uuid in hidden_uuids,
                    )
                )
            visit(item.get("children") or [])

    visit(data.get("blockdevices") or [])
    return partitions


def get_mock_partitions() -> List[Partition]:
    return [
        Partition(
            name="sda1",
            path="/dev/sda1",
            size="256M",
            fstype="vfat",
            uuid="MOCK-EFI-1234",
            label="EFI",
            mountpoint="/boot/efi",
            hidden=False,
        ),
        Partition(
            name="sda2",
            path="/dev/sda2",
            size="120G",
            fstype="ext4",
            uuid="MOCK-DATA-5678",
            label="Data",
            mountpoint="",
            hidden=True,
        ),
    ]


def apply_hidden_uuids(uuids: Iterable[str]) -> None:
    normalized = sorted(set(uuids))
    for uuid in normalized:
        if not UUID_RE.match(uuid):
            raise ValueError(f"Invalid partition UUID: {uuid}")

    content = build_rule_content(normalized)
    write_rules_as_admin(content)
    reload_udev_rules()


def build_rule_content(uuids: Iterable[str]) -> str:
    lines = [RULE_HEADER]
    for uuid in uuids:
        escaped = uuid.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(
            f'ENV{{ID_FS_UUID}}=="{escaped}", '
            f'ENV{{UDISKS_IGNORE}}="1", '
            f'ENV{{UDISKS_PRESENTATION_HIDE}}="1"'
        )
    return "\n".join(lines) + "\n"


def write_rules_as_admin(content: str) -> None:
    if is_root():
        RULE_PATH.write_text(content, encoding="utf-8")
        return

    subprocess.run(
        ["pkexec", "tee", str(RULE_PATH)],
        input=content,
        text=True,
        stdout=subprocess.DEVNULL,
        check=True,
        timeout=60,
    )


def reload_udev_rules() -> None:
    commands = [
        ["udevadm", "control", "--reload-rules"],
        ["udevadm", "trigger"],
    ]
    for command in commands:
        if is_root():
            subprocess.run(command, check=True, timeout=30)
        else:
            subprocess.run(["pkexec", *command], check=True, timeout=60)


def unmount_partitions(partitions: Sequence[Partition], hidden_uuids: Set[str]) -> List[str]:
    skipped_or_failed: List[str] = []
    critical_mounts = {"/", "/home", "/boot", "/boot/efi"}

    for partition in partitions:
        if partition.uuid not in hidden_uuids or not partition.mountpoint:
            continue
        if partition.mountpoint in critical_mounts:
            skipped_or_failed.append(f"{partition.path}: skipped critical mount {partition.mountpoint}")
            continue

        try:
            subprocess.run(["udisksctl", "unmount", "-b", partition.path], check=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            skipped_or_failed.append(f"{partition.path}: {exc}")

    return skipped_or_failed
