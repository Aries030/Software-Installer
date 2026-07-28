from typing import List, Set

from disk_hider.core import (
    Partition,
    apply_hidden_uuids,
    get_all_partitions,
    is_linux,
    unmount_partitions,
)


def main() -> int:
    print("Kylin Disk Hider")
    print("=================")
    print()

    try:
        partitions = get_all_partitions()
    except Exception as exc:
        print(f"Failed to read partitions: {exc}")
        pause()
        return 1

    if not partitions:
        print("No partitions with UUID were found.")
        pause()
        return 0

    selected = {partition.uuid for partition in partitions if partition.hidden}

    while True:
        print_partition_table(partitions, selected)
        print()
        print("Type numbers to ADD to the hidden list, for example: 1 3 4")
        print("Type 'u 2 3' to unhide numbers, 'a' to hide all, 'n' to hide none, 'q' to quit.")
        answer = input("Selection: ").strip().lower()

        if answer == "q":
            return 0
        if answer == "a":
            selected = {partition.uuid for partition in partitions}
            break
        if answer == "n":
            selected = set()
            break
        if answer.startswith("u "):
            try:
                selected -= parse_selection(answer[2:], partitions)
            except ValueError as exc:
                print()
                print(exc)
                print()
                continue
            break

        try:
            selected |= parse_selection(answer, partitions)
        except ValueError as exc:
            print()
            print(exc)
            print()
            continue
        break

    print()
    print_partition_table(partitions, selected)
    print()
    if not is_linux():
        print("Mock mode: this is not Linux, so no system rule will be written.")
        pause()
        return 0

    confirm = input("Apply this hidden partition list? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Canceled.")
        pause()
        return 0

    try:
        apply_hidden_uuids(selected)
    except Exception as exc:
        print(f"Failed to apply rules: {exc}")
        pause()
        return 1

    unmount_warnings = unmount_partitions(partitions, selected)

    print("Done. The udev rule has been updated.")
    if unmount_warnings:
        print("Some mounted partitions could not be unmounted automatically:")
        for warning in unmount_warnings:
            print(f"- {warning}")
    print("If the file manager does not update immediately, re-login or unplug/replug the disk.")
    pause()
    return 0


def print_partition_table(partitions: List[Partition], selected: Set[str]) -> None:
    print("Current partitions:")
    print()
    print(f"{'No.':<4} {'Hide':<5} {'Device':<14} {'Size':<9} {'FS':<8} {'Label':<16} UUID")
    print("-" * 90)
    for index, partition in enumerate(partitions, start=1):
        marker = "yes" if partition.uuid in selected else "no"
        label = shorten(partition.label or "-", 15)
        fstype = partition.fstype or "-"
        device = partition.path or partition.name
        print(
            f"{index:<4} {marker:<5} {device:<14} {partition.size:<9} "
            f"{fstype:<8} {label:<16} {partition.uuid}"
        )


def parse_selection(answer: str, partitions: List[Partition]) -> Set[str]:
    if not answer:
        raise ValueError("Please enter at least one number, or choose 'n' to hide none.")

    selected: Set[str] = set()
    for raw in answer.replace(",", " ").split():
        if not raw.isdigit():
            raise ValueError(f"Invalid selection: {raw}")
        index = int(raw)
        if index < 1 or index > len(partitions):
            raise ValueError(f"Selection out of range: {index}")
        selected.add(partitions[index - 1].uuid)
    return selected


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def pause() -> None:
    try:
        input("Press Enter to close...")
    except EOFError:
        pass
