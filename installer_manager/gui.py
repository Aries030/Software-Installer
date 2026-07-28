"""Software Installer - 现代化 GUI (customtkinter)

设计目标:
  - 暗色主题 + 圆角扁平 + 现代感
  - 标题栏展示 LOGO
  - 自定义列表行(勾选 + 文件名 + 类型徽标 + 大小 + 路径)
  - 实时命令预览
  - 进度条 + 详细日志
  - 易用性:快捷键、筛选、自动保存参数、状态反馈
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Dict, List, Optional

import customtkinter as ctk
from PIL import Image

from installer_manager.core import (
    InstallerPackage,
    InstallProgress,
    InstallResult,
    app_directory,
    command_preview,
    find_installers,
    install_package,
)


APP_NAME = "Software Installer"
APP_VERSION = "1.2.0"
APP_TAGLINE = "批量静默部署 · 一键搞定"

# 主题色:与 LOGO 同源的品牌蓝
COLOR_ACCENT = "#0078D4"
COLOR_ACCENT_HOVER = "#1F8AE8"
COLOR_SUCCESS = "#2DD4BF"
COLOR_WARNING = "#F59E0B"
COLOR_ERROR = "#F87171"

# 类型徽标配色
EXT_COLORS = {
    ".exe": ("#1F8AE8", "#0F4F8F"),  # 蓝
    ".msi": ("#8B5CF6", "#4C2E91"),  # 紫
    ".msp": ("#8B5CF6", "#4C2E91"),
    ".msu": ("#EC4899", "#8E2A6A"),  # 粉
    ".bat": ("#F59E0B", "#7A4F08"),  # 橙
    ".cmd": ("#F59E0B", "#7A4F08"),
}


def _resource_path(rel: str) -> Path:
    """获取资源文件绝对路径,兼容 PyInstaller 打包 (sys._MEIPASS)。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent / rel


class PackageRow(ctk.CTkFrame):
    """安装包列表中的一行。"""

    def __init__(
        self,
        master,
        package: InstallerPackage,
        selected: bool,
        on_toggle,
        on_select,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=8, height=42)
        self.package = package
        self.on_toggle = on_toggle
        self.on_select = on_select
        self._selected = selected

        self.grid_columnconfigure(2, weight=1)
        self.grid_propagate(False)

        # 勾选框
        self.check_var = tk.BooleanVar(value=selected)
        self.checkbox = ctk.CTkCheckBox(
            self, text="", variable=self.check_var, width=24,
            checkbox_width=20, checkbox_height=20, corner_radius=5,
            command=self._on_check,
        )
        self.checkbox.grid(row=0, column=0, padx=(12, 8), pady=10, sticky="w")

        # 类型徽标
        ext = package.extension
        fg, _ = EXT_COLORS.get(ext, ("#64748B", "#334155"))
        self.type_badge = ctk.CTkLabel(
            self, text=ext.lstrip(".").upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=fg, text_color="#FFFFFF",
            corner_radius=6, width=54, height=22,
        )
        self.type_badge.grid(row=0, column=1, padx=(0, 10), pady=10)

        # 文件名
        self.name_label = ctk.CTkLabel(
            self, text=package.name, anchor="w",
            font=ctk.CTkFont(size=13),
        )
        self.name_label.grid(row=0, column=2, padx=(0, 10), pady=10, sticky="ew")

        # 大小
        size_text = f"{package.size_mb:.1f} MB"
        self.size_label = ctk.CTkLabel(
            self, text=size_text, anchor="e",
            font=ctk.CTkFont(size=12), text_color="#94A3B8", width=80,
        )
        self.size_label.grid(row=0, column=3, padx=(0, 12), pady=10)

        # 文件夹路径
        folder = package.relative_folder
        folder_display = "." if folder == "." else folder
        self.folder_label = ctk.CTkLabel(
            self, text=folder_display, anchor="w",
            font=ctk.CTkFont(size=11), text_color="#64748B",
        )
        self.folder_label.grid(row=0, column=4, padx=(0, 12), pady=10, sticky="w")

        # 整行点击切换勾选
        for widget in (self, self.type_badge, self.name_label, self.size_label, self.folder_label):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Double-Button-1>", self._on_click)
        self.checkbox.bind("<Button-1>", lambda _e: self._on_select_only(), add="+")

    def _on_click(self, _event=None) -> None:
        self.on_toggle(self.package)

    def _on_check(self) -> None:
        self.on_toggle(self.package)

    def _on_select_only(self) -> None:
        self.on_select(self.package)

    def set_selected(self, selected: bool, highlight: bool = False) -> None:
        self._selected = selected
        if self.check_var.get() != selected:
            self.check_var.set(selected)
        # 高亮当前选中行
        if highlight:
            self.configure(fg_color=("#1F2A3D", "#243044"))
        else:
            self.configure(fg_color="transparent")


class InstallerManagerApp(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.root_dir: Path = app_directory()
        self.packages: List[InstallerPackage] = []
        self.filtered: List[InstallerPackage] = []
        self.selected_paths: set[Path] = set()
        self.custom_args: Dict[Path, str] = {}
        self.worker: Optional[threading.Thread] = None
        self.stop_event: threading.Event = threading.Event()
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self._rows: Dict[Path, PackageRow] = {}
        self._current_package: Optional[InstallerPackage] = None

        self._set_window_icon()
        self._build_ui()
        self.scan()
        self.after(100, self._poll_events)

    # ---------- 资源 / 主题 ----------

    def _set_window_icon(self) -> None:
        try:
            ico = _resource_path("assets/logo.ico")
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

    def _logo_image(self, size: int = 32) -> Optional[ctk.CTkImage]:
        try:
            png = _resource_path("assets/logo.png")
            if not png.exists():
                png = _resource_path("assets/logo_256.png")
            if not png.exists():
                return None
            img = Image.open(png).convert("RGBA")
            return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        except Exception:
            return None

    # ---------- 布局 ----------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 标题栏
        self._build_header(row=0)

        # 工具栏(目录 + 扫描)
        self._build_toolbar(row=1)

        # 筛选条
        self._build_filterbar(row=2)

        # 主体(列表 + 详情)
        self._build_body(row=3)

        # 底部进度 + 操作
        self._build_bottom(row=4)

        # 状态栏
        self._build_statusbar(row=5)

    def _build_header(self, row: int) -> None:
        header = ctk.CTkFrame(self, fg_color=("#0F172A", "#0B1220"), corner_radius=0, height=64)
        header.grid(row=row, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        logo = self._logo_image(36)
        if logo:
            self._logo_ref = logo
            logo_label = ctk.CTkLabel(header, image=logo, text="")
            logo_label.grid(row=0, column=0, padx=(20, 12), pady=14, sticky="w")

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=1, sticky="w", pady=10)
        title = ctk.CTkLabel(
            title_frame, text=APP_NAME,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=("#F1F5F9", "#E2E8F0"),
        )
        title.grid(row=0, column=0, sticky="w")
        subtitle = ctk.CTkLabel(
            title_frame, text=APP_TAGLINE,
            font=ctk.CTkFont(size=12), text_color="#94A3B8",
        )
        subtitle.grid(row=1, column=0, sticky="w")

        version = ctk.CTkLabel(
            header, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=12), text_color="#64748B",
        )
        version.grid(row=0, column=2, padx=20, sticky="e")

    def _build_toolbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 6))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="📂  扫描目录", font=ctk.CTkFont(size=13))\
            .grid(row=0, column=0, sticky="w")

        self.dir_var = tk.StringVar(value=str(self.root_dir))
        dir_entry = ctk.CTkEntry(
            bar, textvariable=self.dir_var,
            placeholder_text="请选择包含安装包的目录",
            height=36, font=ctk.CTkFont(size=13),
        )
        dir_entry.grid(row=0, column=1, padx=(10, 10), sticky="ew")

        ctk.CTkButton(
            bar, text="选择目录", width=100, height=36, command=self.choose_directory,
            fg_color=("#334155", "#1E293B"), hover_color=("#475569", "#334155"),
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(
            bar, text="🔄 重新扫描", width=110, height=36, command=self.scan,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=3)

    def _build_filterbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="🔍 筛选", font=ctk.CTkFont(size=13))\
            .grid(row=0, column=0, sticky="w")

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.apply_filter())
        ctk.CTkEntry(
            bar, textvariable=self.filter_var, height=34,
            placeholder_text="按文件名 / 类型 / 所在文件夹筛选…",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=1, padx=(10, 10), sticky="ew")

        ctk.CTkButton(
            bar, text="全选", width=72, height=34, command=self.select_all,
            fg_color=("#334155", "#1E293B"), hover_color=("#475569", "#334155"),
        ).grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            bar, text="全不选", width=80, height=34, command=self.clear_selection,
            fg_color=("#334155", "#1E293B"), hover_color=("#475569", "#334155"),
        ).grid(row=0, column=3, padx=(0, 6))

        self.count_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=12), text_color="#94A3B8",
        )
        self.count_label.grid(row=0, column=4, padx=(12, 0), sticky="e")

    def _build_body(self, row: int) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=row, column=0, sticky="nsew", padx=16, pady=(0, 8))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(1, weight=1)

        # 列表区
        list_card = ctk.CTkFrame(body, fg_color=("#1E293B", "#111827"), corner_radius=12)
        list_card.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            list_card, text="安装包列表", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")

        # 表头
        header = ctk.CTkFrame(list_card, fg_color=("#0F172A", "#0B1220"), corner_radius=8, height=32)
        header.grid(row=0, column=0, padx=12, pady=(40, 6), sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(header, text="", width=24).grid(row=0, column=0, padx=(12, 8))
        ctk.CTkLabel(header, text="类型", width=54, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8")\
            .grid(row=0, column=1, padx=(0, 10))
        ctk.CTkLabel(header, text="文件名", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8")\
            .grid(row=0, column=2, padx=(0, 10), sticky="ew")
        ctk.CTkLabel(header, text="大小", width=80, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8")\
            .grid(row=0, column=3, padx=(0, 12))
        ctk.CTkLabel(header, text="位置", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8")\
            .grid(row=0, column=4, padx=(0, 12), sticky="w")

        # 滚动列表
        self.list_scroll = ctk.CTkScrollableFrame(
            list_card, fg_color=("#1E293B", "#111827"), corner_radius=0,
        )
        self.list_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self.list_scroll.grid_columnconfigure(0, weight=1)

        # 详情区
        detail = ctk.CTkFrame(body, fg_color=("#1E293B", "#111827"), corner_radius=12)
        detail.grid(row=0, column=1, rowspan=2, sticky="nsew")
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(3, weight=1)
        detail.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            detail, text="安装包详情", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(12, 8), sticky="ew")

        self.detail_name = ctk.CTkLabel(
            detail, text="未选择安装包", anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#F1F5F9", "#E2E8F0"),
        )
        self.detail_name.grid(row=1, column=0, padx=16, pady=(0, 2), sticky="ew")

        self.detail_path = ctk.CTkLabel(
            detail, text="", anchor="w",
            font=ctk.CTkFont(size=11), text_color="#64748B", wraplength=380, justify="left",
        )
        self.detail_path.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="ew")

        # 安装参数
        ctk.CTkLabel(detail, text="安装参数(留空使用默认)",
                     anchor="w", font=ctk.CTkFont(size=12), text_color="#94A3B8")\
            .grid(row=3, column=0, padx=16, pady=(0, 4), sticky="new")

        self.args_var = tk.StringVar()
        self.args_entry = ctk.CTkEntry(
            detail, textvariable=self.args_var, height=34,
            placeholder_text="/VERYSILENT /SUPPRESSMSGBOXES /NORESTART",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.args_entry.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="ew")
        self.args_entry.bind("<FocusOut>", lambda _e: self.save_args())
        self.args_entry.bind("<Return>", lambda _e: self.save_args())

        # 命令预览
        ctk.CTkLabel(detail, text="命令预览",
                     anchor="w", font=ctk.CTkFont(size=12), text_color="#94A3B8")\
            .grid(row=5, column=0, padx=16, pady=(0, 4), sticky="new")

        self.preview_box = ctk.CTkTextbox(
            detail, height=80, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=("#0F172A", "#0B1220"), text_color="#CBD5E1",
        )
        self.preview_box.grid(row=6, column=0, padx=16, pady=(0, 16), sticky="nsew")
        self.preview_box.configure(state="disabled")

    def _build_bottom(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color=("#1E293B", "#111827"), corner_radius=12)
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 6))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="🚀 部署进度", font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=0, column=0, padx=(16, 12), pady=14, sticky="w")

        self.progress = ctk.CTkProgressBar(bar, height=10, corner_radius=6,
                                           progress_color=COLOR_ACCENT)
        self.progress.grid(row=0, column=1, padx=(0, 12), pady=14, sticky="ew")
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(
            bar, text="0 / 0", width=80,
            font=ctk.CTkFont(size=12), text_color="#94A3B8",
        )
        self.progress_label.grid(row=0, column=2, padx=(0, 12))

        self.install_button = ctk.CTkButton(
            bar, text="▶ 开始安装", width=140, height=38,
            command=self.start_install,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.install_button.grid(row=0, column=3, padx=(0, 16), pady=10)

        self.stop_button = ctk.CTkButton(
            bar, text="⏹ 停止", width=80, height=38,
            command=self.request_stop,
            fg_color=("#475569", "#334155"), hover_color=("#64748B", "#475569"),
            state="disabled", font=ctk.CTkFont(size=13),
        )
        self.stop_button.grid(row=0, column=4, padx=(0, 16), pady=10)

        # 日志区
        log_card = ctk.CTkFrame(self, fg_color=("#1E293B", "#111827"), corner_radius=12)
        log_card.grid(row=row + 1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_header, text="📋 部署日志",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            log_header, text="清空", width=60, height=26, command=self.clear_log,
            fg_color=("#334155", "#1E293B"), hover_color=("#475569", "#334155"),
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=1, sticky="e")

        self.log_box = ctk.CTkTextbox(
            log_card,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=("#0F172A", "#0B1220"), text_color="#CBD5E1",
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        # 调整主网格,把日志也加入 stretch
        self.grid_rowconfigure(row + 1, weight=1)

    def _build_statusbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color=("#0F172A", "#0B1220"), corner_radius=0, height=28)
        bar.grid(row=row, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="就绪")
        ctk.CTkLabel(bar, textvariable=self.status_var,
                     font=ctk.CTkFont(size=11), text_color="#94A3B8")\
            .grid(row=0, column=0, padx=16, pady=6, sticky="w")

        self.tip_var = tk.StringVar(value="提示: 双击行或点击勾选框选择要安装的包")
        ctk.CTkLabel(bar, textvariable=self.tip_var,
                     font=ctk.CTkFont(size=11), text_color="#64748B")\
            .grid(row=0, column=1, padx=16, pady=6, sticky="e")

    # ---------- 行为 ----------

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
        self.log(f"✓ 已扫描到 {len(self.packages)} 个安装包")
        if not self.packages:
            self.status_var.set("未发现安装包")
        else:
            self.status_var.set("就绪")

    def apply_filter(self) -> None:
        keyword = self.filter_var.get().strip().lower()
        if keyword:
            self.filtered = [
                package for package in self.packages
                if keyword in package.name.lower()
                or keyword in package.relative_folder.lower()
                or keyword in package.extension.lower()
            ]
        else:
            self.filtered = list(self.packages)
        self.render_list()

    def render_list(self) -> None:
        # 清空旧行
        for widget in self.list_scroll.winfo_children():
            widget.destroy()
        self._rows.clear()

        for index, package in enumerate(self.filtered):
            row = PackageRow(
                self.list_scroll, package,
                selected=package.path in self.selected_paths,
                on_toggle=self._on_toggle,
                on_select=self._on_select,
            )
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
            self._rows[package.path] = row
            if package is self._current_package:
                row.set_selected(package.path in self.selected_paths, highlight=True)

        total = len(self.packages)
        shown = len(self.filtered)
        selected = len(self.selected_paths)
        if shown == total:
            self.count_label.configure(text=f"共 {total} 个  · 已选 {selected}")
        else:
            self.count_label.configure(text=f"显示 {shown} / 共 {total}  · 已选 {selected}")

        self.status_var.set(f"显示 {shown} 个,已选 {selected} 个")

    def _on_toggle(self, package: InstallerPackage) -> None:
        if package.path in self.selected_paths:
            self.selected_paths.remove(package.path)
        else:
            self.selected_paths.add(package.path)
        # 只更新这一行,避免全列表重绘
        row = self._rows.get(package.path)
        if row:
            row.set_selected(package.path in self.selected_paths, highlight=True)
        self._update_count_label()
        self._current_package = package
        self.refresh_details()

    def _on_select(self, package: InstallerPackage) -> None:
        prev = self._current_package
        self._current_package = package
        if prev and prev in self._rows:
            self._rows[prev].set_selected(
                prev.path in self.selected_paths, highlight=False,
            )
        if package in self._rows:
            self._rows[package].set_selected(
                package.path in self.selected_paths, highlight=True,
            )
        self.refresh_details()

    def _update_count_label(self) -> None:
        total = len(self.packages)
        shown = len(self.filtered)
        selected = len(self.selected_paths)
        if shown == total:
            self.count_label.configure(text=f"共 {total} 个  · 已选 {selected}")
        else:
            self.count_label.configure(text=f"显示 {shown} / 共 {total}  · 已选 {selected}")
        self.status_var.set(f"显示 {shown} 个,已选 {selected} 个")

    def select_all(self) -> None:
        self.selected_paths.update(package.path for package in self.filtered)
        self._refresh_row_checkboxes()
        self._update_count_label()

    def clear_selection(self) -> None:
        self.selected_paths.difference_update(package.path for package in self.filtered)
        self._refresh_row_checkboxes()
        self._update_count_label()

    def _refresh_row_checkboxes(self) -> None:
        for path, row in self._rows.items():
            row.set_selected(path in self.selected_paths,
                             highlight=self._current_package is not None and path == self._current_package.path)

    def refresh_details(self) -> None:
        package = self._current_package
        if not package:
            self.detail_name.configure(text="未选择安装包")
            self.detail_path.configure(text="从左侧列表中选择一个安装包查看详情")
            self.args_var.set("")
            self._set_preview("")
            return
        self.detail_name.configure(text=package.name)
        self.detail_path.configure(text=f"📁 {package.path}")
        args = self.custom_args.get(package.path, "")
        if self.args_var.get() != args:
            self.args_var.set(args)
        self._set_preview(command_preview(package.path, args))

    def save_args(self) -> None:
        package = self._current_package
        if not package:
            return
        args = self.args_var.get().strip()
        if args:
            self.custom_args[package.path] = args
        else:
            self.custom_args.pop(package.path, None)
        self._set_preview(command_preview(package.path, args))

    def _set_preview(self, text: str) -> None:
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", tk.END)
        self.preview_box.insert("1.0", text)
        self.preview_box.configure(state="disabled")

    # ---------- 安装流程 ----------

    def start_install(self) -> None:
        self.save_args()
        if self.worker and self.worker.is_alive():
            self._toast("当前安装任务还没结束")
            return
        packages = [p for p in self.packages if p.path in self.selected_paths]
        if not packages:
            self._toast("请先勾选要安装的安装包")
            return

        confirm = self._confirm_dialog(packages)
        if not confirm:
            return

        self.stop_event.clear()
        self.install_button.configure(state="disabled", text="安装中…")
        self.stop_button.configure(state="normal")
        self.progress.set(0)
        self.progress_label.configure(text=f"0 / {len(packages)}")
        self.status_var.set("正在安装…")

        self.worker = threading.Thread(
            target=self._install_worker,
            args=(packages,),
            daemon=True,
        )
        self.worker.start()

    def _install_worker(self, packages: List[InstallerPackage]) -> None:
        total = len(packages)
        completed = 0
        had_error = False
        for index, package in enumerate(packages, start=1):
            if self.stop_event.is_set():
                self.events.put(("log", "⚠ 已停止,跳过剩余安装包"))
                break
            args = self.custom_args.get(package.path, "")
            self.events.put(("progress", InstallProgress(
                index=index, total=total, package=package, stage="start",
            )))
            result = install_package(package.path, args)
            completed += 1
            if result.success:
                self.events.put(("progress", InstallProgress(
                    index=index, total=total, package=package,
                    stage="finish", result=result,
                )))
            else:
                had_error = True
                self.events.put(("progress", InstallProgress(
                    index=index, total=total, package=package,
                    stage="failed", result=result, aborted=self.stop_event.is_set(),
                )))
                # 出错时跳过剩余,避免连锁失败
                if not self.stop_event.is_set():
                    self.events.put(("log", "⚠ 检测到失败,跳过剩余安装包"))
                    break
        if completed == total and not had_error:
            self.events.put(("finished", InstallResult(
                success=True, return_code=0, message="全部完成",
            )))
        else:
            self.events.put(("finished", InstallResult(
                success=False, return_code=-1,
                message="已停止" if self.stop_event.is_set() else "存在失败项",
            )))

    def request_stop(self) -> None:
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.log("⚠ 已请求停止")

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._on_progress(event[1])
                elif kind == "finished":
                    self._on_finished(event[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _on_progress(self, progress: InstallProgress) -> None:
        ratio = (progress.index - 1 + (1 if progress.stage == "finish" else 0)) / max(progress.total, 1)
        self.progress.set(max(0.0, min(1.0, ratio)))
        self.progress_label.configure(
            text=f"{progress.index if progress.stage == 'finish' else progress.index - 1} / {progress.total}"
        )
        ts = datetime.now().strftime("%H:%M:%S")
        if progress.stage == "start":
            self.log(f"[{ts}] [{progress.index}/{progress.total}] ▶ 开始安装: {progress.package.name}")
            self.log(f"        命令: {command_preview(progress.package.path, self.custom_args.get(progress.package.path, ''))}")
        elif progress.stage == "finish":
            self.log(f"[{ts}] [{progress.index}/{progress.total}] ✓ 完成 ({progress.result.message})")
        elif progress.stage == "failed":
            self.log(f"[{ts}] [{progress.index}/{progress.total}] ✗ 失败: {progress.result.message} (返回码 {progress.result.return_code})")

    def _on_finished(self, result) -> None:
        self.progress.set(1.0)
        self.install_button.configure(state="normal", text="▶ 开始安装")
        self.stop_button.configure(state="disabled")
        if result.success:
            self.status_var.set("全部安装完成")
            self.log("✅ 全部安装完成")
            self._toast("全部安装完成", level="success")
        else:
            self.status_var.set(f"安装流程结束: {result.message}")
            self.log(f"⚠ 安装流程结束: {result.message}")
            self._toast(f"安装结束: {result.message}", level="warning")

    # ---------- 日志 ----------

    def log(self, message: str) -> None:
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)

    def clear_log(self) -> None:
        self.log_box.delete("1.0", tk.END)

    # ---------- 简易弹窗 ----------

    def _toast(self, message: str, level: str = "info") -> None:
        """右下角短暂提示。"""
        colors = {
            "info": COLOR_ACCENT,
            "success": COLOR_SUCCESS,
            "warning": COLOR_WARNING,
            "error": COLOR_ERROR,
        }
        color = colors.get(level, COLOR_ACCENT)
        toast = ctk.CTkLabel(
            self, text=message, corner_radius=8,
            fg_color=color, text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            padx=18, pady=10,
        )
        toast.place(relx=0.5, y=80, anchor="n")
        self.after(2200, toast.destroy)

    def _confirm_dialog(self, packages: List[InstallerPackage]) -> bool:
        """自定义确认对话框。"""
        dlg = ctk.CTkToplevel(self)
        dlg.title("确认开始安装")
        dlg.geometry("460x420")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        ctk.CTkLabel(
            dlg, text="即将开始批量安装",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(20, 4), padx=20, anchor="w")

        ctk.CTkLabel(
            dlg, text=f"将按顺序静默安装 {len(packages)} 个安装包,无法撤销。",
            font=ctk.CTkFont(size=12), text_color="#94A3B8",
        ).pack(pady=(0, 12), padx=20, anchor="w")

        list_frame = ctk.CTkScrollableFrame(dlg, height=220, corner_radius=8,
                                            fg_color=("#1E293B", "#111827"))
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        for i, pkg in enumerate(packages, start=1):
            ctk.CTkLabel(
                list_frame,
                text=f"{i:>2}.  {pkg.name}",
                anchor="w", font=ctk.CTkFont(family="Consolas", size=12),
            ).pack(fill="x", padx=8, pady=2)

        result = {"ok": False}

        def yes() -> None:
            result["ok"] = True
            dlg.destroy()

        def no() -> None:
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 18))
        btns.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btns, text="取消", width=100, height=36, command=no,
            fg_color=("#334155", "#1E293B"), hover_color=("#475569", "#334155"),
        ).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(
            btns, text="开始安装", width=140, height=36, command=yes,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=2, padx=(8, 0))

        dlg.protocol("WM_DELETE_WINDOW", no)
        self.wait_window(dlg)
        return result["ok"]


def main() -> int:
    app = InstallerManagerApp()
    app.mainloop()
    return 0