import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from installer_manager.core import (
    InstallerPackage,
    app_directory,
    command_preview,
    find_installers,
    install_package,
)


class InstallerManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("安装包筛选与批量安装")
        self.geometry("1040x680")
        self.minsize(860, 560)

        self.root_dir = app_directory()
        self.packages: List[InstallerPackage] = []
        self.filtered: List[InstallerPackage] = []
        self.selected_paths: set[Path] = set()
        self.custom_args: Dict[Path, str] = {}
        self.worker: Optional[threading.Thread] = None
        self.events: queue.Queue[tuple] = queue.Queue()

        self._build_ui()
        self.scan()
        self.after(120, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=(12, 10, 12, 6))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="扫描目录").grid(row=0, column=0, sticky="w")
        self.dir_var = tk.StringVar(value=str(self.root_dir))
        ttk.Entry(top, textvariable=self.dir_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="选择目录", command=self.choose_directory).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(top, text="重新扫描", command=self.scan).grid(row=0, column=3)

        filters = ttk.Frame(self, padding=(12, 0, 12, 8))
        filters.grid(row=1, column=0, sticky="ew")
        filters.columnconfigure(1, weight=1)

        ttk.Label(filters, text="筛选").grid(row=0, column=0, sticky="w")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.apply_filter())
        ttk.Entry(filters, textvariable=self.filter_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(filters, text="全选", command=self.select_all).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(filters, text="全不选", command=self.clear_selection).grid(row=0, column=3)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))

        list_frame = ttk.Frame(body)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        body.add(list_frame, weight=3)

        columns = ("selected", "name", "type", "size", "folder")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("selected", text="安装")
        self.tree.heading("name", text="文件名")
        self.tree.heading("type", text="类型")
        self.tree.heading("size", text="大小")
        self.tree.heading("folder", text="所在文件夹")
        self.tree.column("selected", width=64, anchor="center", stretch=False)
        self.tree.column("name", width=300)
        self.tree.column("type", width=70, anchor="center", stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("folder", width=260)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self.toggle_current)
        self.tree.bind("<space>", self.toggle_current)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.refresh_details())

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        detail_frame = ttk.Frame(body, padding=(12, 0, 0, 0))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(5, weight=1)
        body.add(detail_frame, weight=2)

        ttk.Label(detail_frame, text="安装参数").grid(row=0, column=0, sticky="w")
        self.args_var = tk.StringVar()
        self.args_entry = ttk.Entry(detail_frame, textvariable=self.args_var)
        self.args_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.args_entry.bind("<FocusOut>", lambda _event: self.save_args())
        self.args_entry.bind("<Return>", lambda _event: self.save_args())

        ttk.Label(detail_frame, text="命令预览").grid(row=2, column=0, sticky="w")
        self.preview_text = tk.Text(detail_frame, height=4, wrap="word")
        self.preview_text.grid(row=3, column=0, sticky="ew", pady=(4, 8))
        self.preview_text.configure(state="disabled")

        actions = ttk.Frame(detail_frame)
        actions.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        actions.columnconfigure(0, weight=1)
        self.install_button = ttk.Button(actions, text="确定安装已勾选", command=self.start_install)
        self.install_button.grid(row=0, column=0, sticky="ew")

        ttk.Label(detail_frame, text="日志").grid(row=5, column=0, sticky="sw")
        self.log_text = tk.Text(detail_frame, height=12, wrap="word")
        self.log_text.grid(row=6, column=0, sticky="nsew", pady=(4, 0))

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(12, 0, 12, 10)).grid(row=3, column=0, sticky="ew")

    def choose_directory(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(self.root_dir))
        if not chosen:
            return
        self.root_dir = Path(chosen)
        self.dir_var.set(str(self.root_dir))
        self.scan()

    def scan(self) -> None:
        self.save_args()
        self.packages = find_installers(self.root_dir)
        existing_paths = {package.path for package in self.packages}
        self.selected_paths &= existing_paths
        self.custom_args = {
            path: args for path, args in self.custom_args.items() if path in existing_paths
        }
        self.apply_filter()
        self.log(f"已扫描到 {len(self.packages)} 个安装包。")

    def apply_filter(self) -> None:
        keyword = self.filter_var.get().strip().lower()
        if keyword:
            self.filtered = [
                package
                for package in self.packages
                if keyword in package.name.lower()
                or keyword in package.relative_folder.lower()
                or keyword in package.extension.lower()
            ]
        else:
            self.filtered = list(self.packages)
        self.render_tree()

    def render_tree(self) -> None:
        current_selection = self.current_package_path()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for package in self.filtered:
            self.tree.insert(
                "",
                "end",
                iid=str(package.path),
                values=(
                    "是" if package.path in self.selected_paths else "",
                    package.name,
                    package.extension,
                    f"{package.size_mb:.1f} MB",
                    package.relative_folder,
                ),
            )
        if current_selection and self.tree.exists(str(current_selection)):
            self.tree.selection_set(str(current_selection))
        self.status_var.set(f"显示 {len(self.filtered)} 个，已勾选 {len(self.selected_paths)} 个")
        self.refresh_details()

    def current_package_path(self) -> Optional[Path]:
        selected = self.tree.selection()
        if not selected:
            return None
        return Path(selected[0])

    def current_package(self) -> Optional[InstallerPackage]:
        path = self.current_package_path()
        if not path:
            return None
        for package in self.packages:
            if package.path == path:
                return package
        return None

    def toggle_current(self, _event=None) -> None:
        package = self.current_package()
        if not package:
            return
        if package.path in self.selected_paths:
            self.selected_paths.remove(package.path)
        else:
            self.selected_paths.add(package.path)
        self.render_tree()

    def select_all(self) -> None:
        self.selected_paths.update(package.path for package in self.filtered)
        self.render_tree()

    def clear_selection(self) -> None:
        self.selected_paths.difference_update(package.path for package in self.filtered)
        self.render_tree()

    def refresh_details(self) -> None:
        package = self.current_package()
        if not package:
            self.args_var.set("")
            self.set_preview("")
            return
        args = self.custom_args.get(package.path, "")
        if self.args_var.get() != args:
            self.args_var.set(args)
        self.set_preview(command_preview(package.path, args))

    def save_args(self) -> None:
        package = self.current_package()
        if not package:
            return
        args = self.args_var.get().strip()
        if args:
            self.custom_args[package.path] = args
        else:
            self.custom_args.pop(package.path, None)
        self.set_preview(command_preview(package.path, args))

    def set_preview(self, text: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def start_install(self) -> None:
        self.save_args()
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("正在安装", "当前安装任务还没有结束。")
            return
        packages = [package for package in self.packages if package.path in self.selected_paths]
        if not packages:
            messagebox.showwarning("未选择", "请先勾选要安装的安装包。")
            return
        names = "\n".join(package.name for package in packages[:12])
        if len(packages) > 12:
            names += f"\n... 以及另外 {len(packages) - 12} 个"
        if not messagebox.askyesno("确认安装", f"将按顺序安装 {len(packages)} 个安装包：\n\n{names}"):
            return
        self.install_button.configure(state="disabled")
        self.worker = threading.Thread(target=self._install_worker, args=(packages,), daemon=True)
        self.worker.start()

    def _install_worker(self, packages: List[InstallerPackage]) -> None:
        for index, package in enumerate(packages, start=1):
            args = self.custom_args.get(package.path, "")
            self.events.put(("log", f"[{index}/{len(packages)}] 开始安装：{package.path}"))
            self.events.put(("log", "命令：" + command_preview(package.path, args)))
            try:
                code = install_package(package.path, args)
            except Exception as exc:
                self.events.put(("log", f"安装启动失败：{exc}"))
                self.events.put(("done", False))
                return
            if code != 0:
                self.events.put(("log", f"返回码 {code}，已停止后续安装。"))
                self.events.put(("done", False))
                return
            self.events.put(("log", "完成。"))
        self.events.put(("done", True))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "log":
                    self.log(event[1])
                elif event[0] == "done":
                    self.install_button.configure(state="normal")
                    self.log("全部安装完成。" if event[1] else "安装流程已停止。")
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    def log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)


def main() -> int:
    app = InstallerManagerApp()
    app.mainloop()
    return 0

