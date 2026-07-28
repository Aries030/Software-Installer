"""Software Installer v2.0 — 现代化 GUI (customtkinter)

按照 UI 设计规范 v2.0 实现:
  - 三栏 + 命令栏布局(左栏统计/类型筛选 · 中栏卡片列表 · 右栏详情)
  - 卡片式列表项(5 种状态:未选/已选/安装中/已完成/失败)
  - 空状态引导
  - 键盘快捷键(Ctrl+A/R/F, Enter, Esc, Space, 双击)
  - Toast 提示 + 确认对话框
  - 进度条 + 日志 + 状态栏
"""
from __future__ import annotations

import os
import queue
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


# ==================== 常量 ====================

APP_NAME = "Software Installer"
APP_VERSION = "2.1.0"
APP_TAGLINE = "批量静默部署 · 一键搞定"

# 颜色(浅色主题)
C_BG_APP = "#F1F5F9"
C_BG_SURFACE = "#FFFFFF"
C_BG_RAISED = "#F8FAFC"
C_BG_SELECTED = "#E6F1FB"
C_BG_COMPLETED = "#F0FDF4"
C_BORDER = "#E2E8F0"
C_BORDER_SOFT = "#E2E8F0"
C_TEXT_PRIMARY = "#1E293B"
C_TEXT_TITLE = "#0F172A"
C_TEXT_SECONDARY = "#475569"
C_TEXT_MUTED = "#94A3B8"
C_ACCENT = "#378ADD"
C_ACCENT_HOVER = "#185FA5"
C_ACCENT_ACTIVE = "#0C447C"
C_SUCCESS = "#1D9E75"
C_WARNING = "#EF9F27"
C_ERROR = "#E24B4A"
C_PURPLE = "#7F77DD"
C_PINK = "#D4537E"

# 类型徽标配色
EXT_COLORS: Dict[str, str] = {
    ".exe": C_ACCENT,
    ".msi": C_PURPLE,
    ".msp": C_PURPLE,
    ".msu": C_PINK,
    ".bat": C_WARNING,
    ".cmd": C_WARNING,
}

SPINNER_CHARS = "◐◓◑◒"

# 卡片状态
S_UNSELECTED = "unselected"
S_SELECTED = "selected"
S_INSTALLING = "installing"
S_COMPLETED = "completed"
S_FAILED = "failed"


def _resource_path(rel: str) -> Path:
    """获取资源文件绝对路径,兼容 PyInstaller 打包 (sys._MEIPASS)。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent / rel


import sys  # noqa: E402


# ==================== 卡片组件 ====================

class PackageCard(ctk.CTkFrame):
    """安装包列表中的一张卡片,支持 5 种状态。"""

    def __init__(self, master, package: InstallerPackage, on_toggle, on_select):
        super().__init__(master, fg_color=C_BG_SURFACE, corner_radius=12,
                         border_width=1, border_color=C_BORDER, height=60)
        self.package = package
        self.on_toggle = on_toggle
        self.on_select = on_select
        self._state = S_UNSELECTED
        self._spinner_after: Optional[str] = None

        self.grid_propagate(False)
        self.grid_columnconfigure(2, weight=1)

        # 勾选框 / 状态图标
        self.check_label = ctk.CTkLabel(self, text="", width=28, anchor="center",
                                        font=ctk.CTkFont(size=14))
        self.check_label.grid(row=0, column=0, padx=(12, 8), pady=12)
        self.check_label.bind("<Button-1>", lambda e: self._on_click())

        # 类型徽标
        ext = package.extension
        badge_color = EXT_COLORS.get(ext, C_TEXT_MUTED)
        self.badge = ctk.CTkLabel(
            self, text=ext.lstrip(".").upper(),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=badge_color, text_color="#FFFFFF",
            corner_radius=6, width=44, height=26,
        )
        self.badge.grid(row=0, column=1, padx=(0, 10), pady=12)

        # 文件名 + 子标题
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.grid(row=0, column=2, padx=(0, 10), pady=8, sticky="ew")
        name_frame.grid_columnconfigure(0, weight=1)

        self.name_label = ctk.CTkLabel(
            name_frame, text=package.name, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.name_label.grid(row=0, column=0, sticky="ew")

        size_text = f"{package.size_mb:.1f} MB" if package.size_mb >= 0.1 else f"{int(package.size_mb * 1024)} KB"
        folder = package.relative_folder
        folder_display = "" if folder == "." else f" · {folder}"
        self.sub_label = ctk.CTkLabel(
            name_frame, text=f"{size_text}{folder_display}", anchor="w",
            font=ctk.CTkFont(size=12), text_color=C_TEXT_MUTED,
        )
        self.sub_label.grid(row=1, column=0, sticky="ew")

        # 状态标签(右侧)
        self.status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), width=80, anchor="e",
        )
        self.status_label.grid(row=0, column=3, padx=(0, 14), pady=12)

        # 整行点击
        for w in (self, self.badge, self.name_label, self.sub_label, self.status_label):
            w.bind("<Button-1>", lambda e: self._on_click())
            w.bind("<Double-Button-1>", lambda e: self._on_click())

        self.set_state(S_UNSELECTED)

    def _on_click(self):
        self.on_select(self.package)
        self.on_toggle(self.package)

    def set_state(self, state: str, result_msg: str = ""):
        self._state = state
        # 取消旋转
        if self._spinner_after and state != S_INSTALLING:
            self.after_cancel(self._spinner_after)
            self._spinner_after = None

        if state == S_UNSELECTED:
            self.configure(fg_color=C_BG_SURFACE, border_color=C_BORDER)
            self.check_label.configure(text="", fg_color="transparent")
            self.name_label.configure(text_color=C_TEXT_PRIMARY)
            self.status_label.configure(text="", text_color=C_TEXT_MUTED)
        elif state == S_SELECTED:
            self.configure(fg_color=C_BG_SELECTED, border_color=C_ACCENT)
            self._style_check_filled(C_ACCENT, "✓")
            self.name_label.configure(text_color=C_TEXT_TITLE)
            self.status_label.configure(text="已选择", text_color=C_ACCENT_HOVER)
        elif state == S_INSTALLING:
            self.configure(fg_color=C_BG_SELECTED, border_color=C_ACCENT)
            self._start_spinner()
            self.name_label.configure(text_color=C_ACCENT_HOVER)
            self.status_label.configure(text="安装中…", text_color=C_ACCENT_HOVER)
        elif state == S_COMPLETED:
            self.configure(fg_color=C_BG_COMPLETED, border_color=C_SUCCESS)
            self._style_check_filled(C_SUCCESS, "✓")
            self.name_label.configure(text_color=C_SUCCESS)
            msg = result_msg or "已完成"
            self.status_label.configure(text=msg, text_color=C_SUCCESS)
        elif state == S_FAILED:
            self.configure(fg_color=C_BG_SURFACE, border_color=C_ERROR)
            self._style_check_filled(C_ERROR, "✕")
            self.name_label.configure(text_color=C_ERROR)
            msg = result_msg or "失败"
            self.status_label.configure(text=msg, text_color=C_ERROR)

    def _style_check_filled(self, color: str, symbol: str = "✓"):
        """用一个小色块+符号模拟填充的勾选框。"""
        self.check_label.configure(text=symbol, text_color="#FFFFFF",
                                   fg_color=color)

    def _start_spinner(self):
        self.check_label.configure(text=SPINNER_CHARS[0], text_color=C_ACCENT,
                                   fg_color="transparent")
        self._spin(0)

    def _spin(self, idx: int):
        self.check_label.configure(text=SPINNER_CHARS[idx % 4])
        self._spinner_after = self.after(150, lambda: self._spin(idx + 1))


# ==================== 空状态组件 ====================

class EmptyState(ctk.CTkFrame):
    """列表为空时的引导状态。"""

    def __init__(self, master, on_rescan):
        super().__init__(master, fg_color="transparent", corner_radius=12)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color=C_BG_SURFACE, corner_radius=12,
                             border_width=0.5, border_color=C_BORDER)
        inner.grid(row=0, column=0, padx=20, pady=20)
        inner.grid_columnconfigure(0, weight=1)

        # 图标(用文字代替 SVG)
        icon = ctk.CTkLabel(
            inner, text="📦", font=ctk.CTkFont(size=32)),
        icon[0].grid(row=0, column=0, padx=40, pady=(32, 8))

        ctk.CTkLabel(
            inner, text="未发现安装包",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_TEXT_SECONDARY,
        ).grid(row=1, column=0, padx=40, pady=(0, 4))

        ctk.CTkLabel(
            inner, text="把 .exe / .msi / .bat 文件放到本目录,\n然后点击「重新扫描」",
            font=ctk.CTkFont(size=14), text_color=C_TEXT_MUTED,
            justify="center",
        ).grid(row=2, column=0, padx=40, pady=(0, 16))

        ctk.CTkButton(
            inner, text="重新扫描", width=120, height=32,
            command=on_rescan,
            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=3, column=0, padx=40, pady=(0, 32))


# ==================== 主应用 ====================

class InstallerManagerApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(fg_color=C_BG_APP)

        self.root_dir: Path = app_directory()
        self.packages: List[InstallerPackage] = []
        self.filtered: List[InstallerPackage] = []
        self.selected_paths: set[Path] = set()
        self.custom_args: Dict[Path, str] = {}
        self.card_states: Dict[Path, str] = {}
        self.worker: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self._cards: Dict[Path, PackageCard] = {}
        self._current_package: Optional[InstallerPackage] = None
        self._type_filter: Optional[str] = None  # None = 全部
        self._is_installing = False

        self._set_window_icon()
        self._build_ui()
        self._bind_shortcuts()
        self.scan()
        self.after(100, self._poll_events)

    # ---------- 资源 ----------

    def _set_window_icon(self):
        try:
            ico = _resource_path("assets/logo.ico")
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

    def _logo_image(self, size: int = 28):
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

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)  # 主体三栏 flex

        self._build_header(0)       # 标题栏 56px
        self._build_command_bar(1)  # 命令栏 48px
        self._build_filter_bar(2)   # 筛选栏 44px
        self._build_body(3)         # 三栏主体
        self._build_progress_bar(4) # 进度栏 56px
        self._build_log_area(5)     # 日志区
        self._build_status_bar(6)   # 状态栏 24px

    def _build_header(self, row):
        header = ctk.CTkFrame(self, fg_color=C_BG_APP, corner_radius=0, height=56)
        header.grid(row=row, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        logo = self._logo_image(28)
        if logo:
            self._logo_ref = logo
            ctk.CTkLabel(header, image=logo, text="").grid(
                row=0, column=0, padx=(16, 10), pady=14, sticky="w")

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=1, sticky="w", pady=10)
        ctk.CTkLabel(
            title_frame, text=APP_NAME,
            font=ctk.CTkFont(size=18, weight="bold"), text_color=C_TEXT_TITLE,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_frame, text=APP_TAGLINE,
            font=ctk.CTkFont(size=13), text_color=C_TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w")

        ctk.CTkLabel(
            header, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=13), text_color=C_TEXT_MUTED,
        ).grid(row=0, column=2, padx=16, sticky="e")

    def _build_command_bar(self, row):
        bar = ctk.CTkFrame(self, fg_color=C_BG_SURFACE, corner_radius=0)
        bar.grid(row=row, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="扫描目录", font=ctk.CTkFont(size=14),
                     text_color=C_TEXT_SECONDARY).grid(
            row=0, column=0, padx=(16, 8), pady=12, sticky="w")

        self.dir_var = tk.StringVar(value=str(self.root_dir))
        dir_entry = ctk.CTkEntry(
            bar, textvariable=self.dir_var, height=32,
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=C_BG_APP, border_color=C_BORDER,
        )
        dir_entry.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        dir_entry.configure(state="readonly")

        ctk.CTkButton(
            bar, text="选择目录", width=90, height=32,
            command=self.choose_directory,
            fg_color=C_BG_RAISED, hover_color=C_BORDER,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            bar, text="重新扫描", width=100, height=32,
            command=self.scan,
            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=3, padx=(0, 16))

    def _build_filter_bar(self, row):
        bar = ctk.CTkFrame(self, fg_color=C_BG_APP, corner_radius=0)
        bar.grid(row=row, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.apply_filter())
        ctk.CTkEntry(
            bar, textvariable=self.filter_var, height=30,
            placeholder_text="按名称 / 类型筛选…",
            font=ctk.CTkFont(size=14),
            fg_color=C_BG_SURFACE, border_color=C_BORDER,
        ).grid(row=0, column=1, padx=(8, 8), sticky="ew", pady=8)

        ctk.CTkButton(
            bar, text="全选", width=60, height=30, command=self.select_all,
            fg_color=C_BG_RAISED, hover_color=C_BORDER,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=2, padx=(0, 4))

        ctk.CTkButton(
            bar, text="全不选", width=68, height=30, command=self.clear_selection,
            fg_color=C_BG_RAISED, hover_color=C_BORDER,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=3, padx=(0, 8))

        self.count_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=13), text_color=C_TEXT_MUTED,
        )
        self.count_label.grid(row=0, column=4, padx=(0, 16), sticky="e")

    def _build_body(self, row):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=row, column=0, sticky="nsew", padx=0, pady=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # 左栏 140px
        self._build_left_panel(body, 0)
        # 中栏 flex
        self._build_center_panel(body, 1)
        # 右栏 200px
        self._build_right_panel(body, 2)

    def _build_left_panel(self, body, col):
        panel = ctk.CTkFrame(body, fg_color=C_BG_APP, width=140, corner_radius=0)
        panel.grid(row=0, column=col, sticky="ns")
        panel.grid_propagate(False)
        panel.grid_columnconfigure(0, weight=1)

        # 统计区
        ctk.CTkLabel(
            panel, text="统计", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")

        self.stat_total_label = ctk.CTkLabel(
            panel, text="0", font=ctk.CTkFont(size=28, weight="bold"),
            text_color=C_ACCENT, anchor="w",
        )
        self.stat_total_label.grid(row=1, column=0, padx=12, sticky="w")
        ctk.CTkLabel(
            panel, text="总安装包", font=ctk.CTkFont(size=12), text_color=C_TEXT_MUTED,
        ).grid(row=2, column=0, padx=12, sticky="w")

        # 已选 / 已装
        sub_frame = ctk.CTkFrame(panel, fg_color="transparent")
        sub_frame.grid(row=3, column=0, padx=8, pady=(8, 0), sticky="ew")
        sub_frame.grid_columnconfigure(0, weight=1)
        sub_frame.grid_columnconfigure(1, weight=1)

        sel_card = ctk.CTkFrame(sub_frame, fg_color=C_BG_RAISED, corner_radius=8)
        sel_card.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        self.stat_selected_label = ctk.CTkLabel(
            sel_card, text="0", font=ctk.CTkFont(size=18, weight="bold"),
            text_color=C_SUCCESS,
        )
        self.stat_selected_label.grid(row=0, column=0, padx=8, pady=(6, 0))
        ctk.CTkLabel(
            sel_card, text="已选", font=ctk.CTkFont(size=11), text_color=C_TEXT_MUTED,
        ).grid(row=1, column=0, padx=8, pady=(0, 6))

        done_card = ctk.CTkFrame(sub_frame, fg_color=C_BG_RAISED, corner_radius=8)
        done_card.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        self.stat_done_label = ctk.CTkLabel(
            done_card, text="0", font=ctk.CTkFont(size=18, weight="bold"),
            text_color=C_TEXT_SECONDARY,
        )
        self.stat_done_label.grid(row=0, column=0, padx=8, pady=(6, 0))
        ctk.CTkLabel(
            done_card, text="已装", font=ctk.CTkFont(size=11), text_color=C_TEXT_MUTED,
        ).grid(row=1, column=0, padx=8, pady=(0, 6))

        # 类型筛选
        ctk.CTkLabel(
            panel, text="类型", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_SECONDARY,
        ).grid(row=4, column=0, padx=12, pady=(16, 6), sticky="w")

        self.type_filter_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self.type_filter_frame.grid(row=5, column=0, padx=8, sticky="ew")
        self.type_filter_frame.grid_columnconfigure(0, weight=1)

    def _build_center_panel(self, body, col):
        panel = ctk.CTkFrame(body, fg_color=C_BG_APP, corner_radius=0)
        panel.grid(row=0, column=col, sticky="nsew", padx=(0, 0))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        # 滚动列表
        self.list_scroll = ctk.CTkScrollableFrame(
            panel, fg_color=C_BG_APP, corner_radius=0,
        )
        self.list_scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.list_scroll.grid_columnconfigure(0, weight=1)

        # 空状态(默认隐藏)
        self.empty_state = EmptyState(self.list_scroll, self.scan)

    def _build_right_panel(self, body, col):
        panel = ctk.CTkFrame(body, fg_color=C_BG_APP, width=200, corner_radius=0)
        panel.grid(row=0, column=col, sticky="ns")
        panel.grid_propagate(False)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel, text="详情", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")

        self.detail_name = ctk.CTkLabel(
            panel, text="未选择安装包", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT_TITLE,
            wraplength=176,
        )
        self.detail_name.grid(row=1, column=0, padx=12, sticky="w")

        self.detail_path = ctk.CTkLabel(
            panel, text="", anchor="w",
            font=ctk.CTkFont(family="Consolas", size=11), text_color=C_TEXT_MUTED,
            wraplength=176, justify="left",
        )
        self.detail_path.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="w")

        ctk.CTkLabel(
            panel, text="安装参数", anchor="w",
            font=ctk.CTkFont(size=12), text_color=C_TEXT_SECONDARY,
        ).grid(row=3, column=0, padx=12, pady=(0, 4), sticky="w")

        self.args_var = tk.StringVar()
        self.args_entry = ctk.CTkEntry(
            panel, textvariable=self.args_var, height=28,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=C_BG_SURFACE, border_color=C_BORDER,
        )
        self.args_entry.grid(row=4, column=0, padx=12, sticky="ew")
        self.args_entry.bind("<FocusOut>", lambda e: self.save_args())
        self.args_entry.bind("<Return>", lambda e: self.save_args())

        ctk.CTkLabel(
            panel, text="命令预览", anchor="w",
            font=ctk.CTkFont(size=12), text_color=C_TEXT_SECONDARY,
        ).grid(row=5, column=0, padx=12, pady=(12, 4), sticky="w")

        self.preview_box = ctk.CTkTextbox(
            panel, height=80,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=C_BG_SURFACE, text_color=C_TEXT_PRIMARY,
            border_width=0.5, border_color=C_BORDER, corner_radius=6,
        )
        self.preview_box.grid(row=6, column=0, padx=12, sticky="ew", pady=(0, 12))
        self.preview_box.configure(state="disabled")

    def _build_progress_bar(self, row):
        bar = ctk.CTkFrame(self, fg_color=C_BG_APP, corner_radius=0)
        bar.grid(row=row, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="部署进度", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=(16, 8), pady=12, sticky="w")

        self.progress = ctk.CTkProgressBar(
            bar, height=6, corner_radius=3, progress_color=C_ACCENT,
        )
        self.progress.grid(row=0, column=1, padx=(0, 8), pady=12, sticky="ew")
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(
            bar, text="0 / 0", width=50,
            font=ctk.CTkFont(size=13), text_color=C_TEXT_MUTED,
        )
        self.progress_label.grid(row=0, column=2, padx=(0, 8))

        self.install_button = ctk.CTkButton(
            bar, text="开始安装", width=110, height=32,
            command=self.start_install,
            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.install_button.grid(row=0, column=3, padx=(0, 6), pady=8)

        self.stop_button = ctk.CTkButton(
            bar, text="停止", width=60, height=32,
            command=self.request_stop,
            fg_color=C_BG_RAISED, hover_color=C_BORDER,
            state="disabled", font=ctk.CTkFont(size=13),
        )
        self.stop_button.grid(row=0, column=4, padx=(0, 16), pady=8)

    def _build_log_area(self, row):
        self.grid_rowconfigure(row, weight=0)
        log_frame = ctk.CTkFrame(self, fg_color=C_BG_APP, corner_radius=0)
        log_frame.grid(row=row, column=0, sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(log_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(4, 2))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="部署日志", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header, text="清空", width=50, height=22, command=self.clear_log,
            fg_color=C_BG_RAISED, hover_color=C_BORDER,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, sticky="e")

        self.log_box = ctk.CTkTextbox(
            log_frame, height=100,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=C_BG_APP, text_color=C_TEXT_SECONDARY,
        )
        self.log_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

    def _build_status_bar(self, row):
        bar = ctk.CTkFrame(self, fg_color=C_BG_SURFACE, corner_radius=0)
        bar.grid(row=row, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="就绪")
        ctk.CTkLabel(
            bar, textvariable=self.status_var,
            font=ctk.CTkFont(size=12), text_color=C_TEXT_MUTED,
        ).grid(row=0, column=0, padx=12, pady=4, sticky="w")

        ctk.CTkLabel(
            bar, text="双击选择 · Space 切换 · Enter 安装 · Ctrl+A 全选 · Ctrl+R 扫描",
            font=ctk.CTkFont(size=11), text_color=C_TEXT_MUTED,
        ).grid(row=0, column=1, padx=12, pady=4, sticky="e")

    # ---------- 键盘快捷键 ----------

    def _bind_shortcuts(self):
        self.bind("<Control-a>", lambda e: self.select_all())
        self.bind("<Control-A>", lambda e: self.select_all())
        self.bind("<Control-r>", lambda e: self.scan())
        self.bind("<Control-R>", lambda e: self.scan())
        self.bind("<Control-f>", lambda e: self.filter_var.set("") or self._focus_filter())
        self.bind("<Control-F>", lambda e: self.filter_var.set("") or self._focus_filter())
        self.bind("<Return>", lambda e: self.start_install())
        self.bind("<Escape>", lambda e: self._on_escape())

    def _focus_filter(self):
        try:
            self.filter_entry.focus_set()
        except Exception:
            pass

    def _on_escape(self):
        # 如果有筛选,清除筛选;否则不做
        if self.filter_var.get():
            self.filter_var.set("")

    # ---------- 行为 ----------

    def choose_directory(self):
        chosen = filedialog.askdirectory(initialdir=str(self.root_dir))
        if not chosen:
            return
        self.root_dir = Path(chosen)
        self.dir_var.set(str(self.root_dir))
        self.scan()

    def scan(self):
        self.save_args()
        self.packages = find_installers(self.root_dir)
        existing = {p.path for p in self.packages}
        self.selected_paths &= existing
        self.custom_args = {k: v for k, v in self.custom_args.items() if k in existing}
        # 重置安装状态
        self.card_states = {p: S_UNSELECTED for p in self.packages}
        self._type_filter = None
        self.apply_filter()
        self._update_left_panel()
        self.log(f"已扫描到 {len(self.packages)} 个安装包")
        self.status_var.set("就绪")

    def apply_filter(self):
        keyword = self.filter_var.get().strip().lower()
        self.filtered = []
        for p in self.packages:
            # 类型筛选
            if self._type_filter and p.extension != self._type_filter:
                continue
            # 关键字筛选
            if keyword:
                if (keyword not in p.name.lower()
                        and keyword not in p.relative_folder.lower()
                        and keyword not in p.extension.lower()):
                    continue
            self.filtered.append(p)
        self.render_list()

    def render_list(self):
        # 清空旧卡片
        for w in self.list_scroll.winfo_children():
            w.destroy()
        self._cards.clear()

        if not self.filtered:
            # 显示空状态
            self.empty_state = EmptyState(self.list_scroll, self.scan)
            self.empty_state.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        else:
            for i, pkg in enumerate(self.filtered):
                state = self.card_states.get(pkg.path, S_UNSELECTED)
                if pkg.path in self.selected_paths and state == S_UNSELECTED:
                    state = S_SELECTED
                card = PackageCard(
                    self.list_scroll, pkg,
                    on_toggle=self._on_toggle,
                    on_select=self._on_select,
                )
                card.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
                card.set_state(state)
                self._cards[pkg.path] = card

        self._update_count_label()

    def _on_toggle(self, pkg: InstallerPackage):
        if self._is_installing:
            return
        if pkg.path in self.selected_paths:
            self.selected_paths.remove(pkg.path)
            self.card_states[pkg.path] = S_UNSELECTED
        else:
            self.selected_paths.add(pkg.path)
            self.card_states[pkg.path] = S_SELECTED
        # 更新卡片
        card = self._cards.get(pkg.path)
        if card:
            card.set_state(self.card_states[pkg.path])
        self._update_count_label()
        self._update_left_panel()

    def _on_select(self, pkg: InstallerPackage):
        self._current_package = pkg
        self.refresh_details()

    def _update_count_label(self):
        total = len(self.packages)
        shown = len(self.filtered)
        selected = len(self.selected_paths)
        if shown == total:
            self.count_label.configure(text=f"共 {total} · 已选 {selected}")
        else:
            self.count_label.configure(text=f"显示 {shown} / 共 {total} · 已选 {selected}")

    def _update_left_panel(self):
        """更新左栏统计和类型筛选。"""
        self.stat_total_label.configure(text=str(len(self.packages)))
        self.stat_selected_label.configure(text=str(len(self.selected_paths)))
        done = sum(1 for s in self.card_states.values() if s == S_COMPLETED)
        self.stat_done_label.configure(text=str(done))

        # 类型筛选标签
        for w in self.type_filter_frame.winfo_children():
            w.destroy()
        ext_counts: Dict[str, int] = {}
        for p in self.packages:
            ext_counts[p.extension] = ext_counts.get(p.extension, 0) + 1
        for i, (ext, count) in enumerate(sorted(ext_counts.items())):
            color = EXT_COLORS.get(ext, C_TEXT_MUTED)
            is_active = self._type_filter == ext
            bg = C_BG_RAISED if is_active else "transparent"
            border = color if is_active else C_BORDER
            label = ctk.CTkFrame(
                self.type_filter_frame, fg_color=bg, corner_radius=6,
                border_width=0.5, border_color=border, height=24,
            )
            label.grid(row=i, column=0, padx=4, pady=1, sticky="ew")
            label.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                label, text="", width=8, height=8, corner_radius=2, fg_color=color,
            ).grid(row=0, column=0, padx=(6, 4), pady=6)
            ext_text = ext.lstrip(".").upper()
            ctk.CTkLabel(
                label, text=ext_text, font=ctk.CTkFont(size=12),
                text_color=C_TEXT_PRIMARY if is_active else C_TEXT_SECONDARY,
            ).grid(row=0, column=1, padx=(0, 4), sticky="w")
            ctk.CTkLabel(
                label, text=str(count), font=ctk.CTkFont(size=12),
                text_color=C_TEXT_MUTED,
            ).grid(row=0, column=2, padx=(0, 6))
            # 点击切换类型筛选
            label.bind("<Button-1>", lambda e, x=ext: self._toggle_type_filter(x))
            for child in label.winfo_children():
                child.bind("<Button-1>", lambda e, x=ext: self._toggle_type_filter(x))

    def _toggle_type_filter(self, ext: str):
        if self._is_installing:
            return
        if self._type_filter == ext:
            self._type_filter = None
        else:
            self._type_filter = ext
        self.apply_filter()
        self._update_left_panel()

    def select_all(self):
        if self._is_installing:
            return
        for p in self.filtered:
            self.selected_paths.add(p.path)
            self.card_states[p.path] = S_SELECTED
        self._refresh_card_states()
        self._update_count_label()
        self._update_left_panel()

    def clear_selection(self):
        if self._is_installing:
            return
        for p in self.filtered:
            self.selected_paths.discard(p.path)
            if self.card_states.get(p.path) == S_SELECTED:
                self.card_states[p.path] = S_UNSELECTED
        self._refresh_card_states()
        self._update_count_label()
        self._update_left_panel()

    def _refresh_card_states(self):
        for path, card in self._cards.items():
            state = self.card_states.get(path, S_UNSELECTED)
            if path in self.selected_paths and state == S_UNSELECTED:
                state = S_SELECTED
            card.set_state(state)

    def refresh_details(self):
        pkg = self._current_package
        if not pkg:
            self.detail_name.configure(text="未选择安装包")
            self.detail_path.configure(text="")
            self.args_var.set("")
            self._set_preview("")
            return
        self.detail_name.configure(text=pkg.name)
        self.detail_path.configure(text=str(pkg.path))
        args = self.custom_args.get(pkg.path, "")
        if self.args_var.get() != args:
            self.args_var.set(args)
        self._set_preview(command_preview(pkg.path, args))

    def save_args(self):
        pkg = self._current_package
        if not pkg:
            return
        args = self.args_var.get().strip()
        if args:
            self.custom_args[pkg.path] = args
        else:
            self.custom_args.pop(pkg.path, None)
        self._set_preview(command_preview(pkg.path, args))

    def _set_preview(self, text: str):
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", tk.END)
        self.preview_box.insert("1.0", text)
        self.preview_box.configure(state="disabled")

    # ---------- 安装流程 ----------

    def start_install(self):
        if self._is_installing:
            return
        self.save_args()
        packages = [p for p in self.packages if p.path in self.selected_paths]
        if not packages:
            self._toast("请先勾选要安装的安装包", "warning")
            return
        if not self._confirm_dialog(packages):
            return

        self._is_installing = True
        self.stop_event.clear()
        self.install_button.configure(state="disabled", text="安装中…")
        self.stop_button.configure(state="normal")
        self.progress.set(0)
        self.progress_label.configure(text=f"0 / {len(packages)}")
        self.status_var.set("正在安装…")
        self.progress.configure(progress_color=C_ACCENT)

        self.worker = threading.Thread(
            target=self._install_worker, args=(packages,), daemon=True)
        self.worker.start()

    def _install_worker(self, packages: List[InstallerPackage]):
        total = len(packages)
        completed = 0
        had_error = False
        for index, pkg in enumerate(packages, start=1):
            if self.stop_event.is_set():
                self.events.put(("log", "已停止,跳过剩余安装包"))
                break
            args = self.custom_args.get(pkg.path, "")
            self.events.put(("progress", index, total, pkg, "start"))
            result = install_package(pkg.path, args)
            completed += 1
            if result.success:
                self.card_states[pkg.path] = S_COMPLETED
                self.events.put(("progress", index, total, pkg, "finish", result))
            else:
                had_error = True
                self.card_states[pkg.path] = S_FAILED
                self.events.put(("progress", index, total, pkg, "failed", result))
                if not self.stop_event.is_set():
                    self.events.put(("log", f"检测到失败,跳过剩余安装包"))
                    break
        if completed == total and not had_error:
            self.events.put(("finished", True, "全部完成"))
        else:
            msg = "已停止" if self.stop_event.is_set() else "存在失败项"
            self.events.put(("finished", False, msg))

    def request_stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.log("已请求停止")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._on_progress_event(event)
                elif kind == "log":
                    self.log(event[1])
                elif kind == "finished":
                    self._on_finished(event[1], event[2])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _on_progress_event(self, event):
        _, index, total, pkg, stage = event[:5]
        result = event[5] if len(event) > 5 else None

        ratio = (index - 1 + (1 if stage in ("finish", "failed") else 0)) / max(total, 1)
        self.progress.set(max(0.0, min(1.0, ratio)))
        done_count = index - 1 + (1 if stage in ("finish", "failed") else 0)
        self.progress_label.configure(text=f"{done_count} / {total}")

        ts = datetime.now().strftime("%H:%M:%S")
        if stage == "start":
            self.log(f"[{ts}] [{index}/{total}] 开始: {pkg.name}")
            self.log(f"  命令: {command_preview(pkg.path, self.custom_args.get(pkg.path, ''))}")
            # 更新卡片状态为安装中
            card = self._cards.get(pkg.path)
            if card:
                card.set_state(S_INSTALLING)
        elif stage == "finish":
            self.log(f"[{ts}] [{index}/{total}] 完成 · {result.message}")
            card = self._cards.get(pkg.path)
            if card:
                card.set_state(S_COMPLETED, result.message)
        elif stage == "failed":
            self.log(f"[{ts}] [{index}/{total}] 失败 · {result.message} (返回码 {result.return_code})")
            card = self._cards.get(pkg.path)
            if card:
                card.set_state(S_FAILED, f"失败 · {result.return_code}")

        self._update_left_panel()

    def _on_finished(self, success: bool, message: str):
        self._is_installing = False
        self.progress.set(1.0 if success else self.progress.get())
        self.progress.configure(progress_color=C_SUCCESS if success else C_ERROR)
        self.install_button.configure(state="normal", text="开始安装")
        self.stop_button.configure(state="disabled")
        if success:
            self.status_var.set("全部安装完成")
            self.log("全部安装完成")
            self._toast("全部安装完成", "success")
        else:
            self.status_var.set(f"安装结束: {message}")
            self.log(f"安装结束: {message}")
            self._toast(f"安装结束: {message}", "warning")
        self._update_left_panel()

    # ---------- 日志 ----------

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{ts}] {message}\n")
        self.log_box.see(tk.END)

    def clear_log(self):
        self.log_box.delete("1.0", tk.END)

    # ---------- Toast ----------

    def _toast(self, message: str, level: str = "info"):
        colors = {
            "info": C_ACCENT, "success": C_SUCCESS,
            "warning": C_WARNING, "error": C_ERROR,
        }
        toast = ctk.CTkLabel(
            self, text=message, corner_radius=8,
            fg_color=colors.get(level, C_ACCENT), text_color="#FFFFFF",
            font=ctk.CTkFont(size=14, weight="bold"),
            padx=16, pady=8,
        )
        toast.place(relx=0.5, y=70, anchor="n")
        self.after(2000, toast.destroy)

    # ---------- 确认对话框 ----------

    def _confirm_dialog(self, packages: List[InstallerPackage]) -> bool:
        dlg = ctk.CTkToplevel(self)
        dlg.title("确认开始安装")
        dlg.geometry("420x380")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(fg_color=C_BG_APP)

        ctk.CTkLabel(
            dlg, text="即将开始批量安装",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C_TEXT_TITLE,
        ).pack(pady=(20, 4), padx=20, anchor="w")

        ctk.CTkLabel(
            dlg, text=f"将按顺序静默安装 {len(packages)} 个安装包,无法撤销。",
            font=ctk.CTkFont(size=13), text_color=C_TEXT_SECONDARY,
        ).pack(pady=(0, 12), padx=20, anchor="w")

        list_frame = ctk.CTkScrollableFrame(
            dlg, height=200, corner_radius=8, fg_color=C_BG_SURFACE)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        for i, pkg in enumerate(packages, start=1):
            ctk.CTkLabel(
                list_frame, text=f"{i:>2}.  {pkg.name}", anchor="w",
                font=ctk.CTkFont(family="Consolas", size=13),
                text_color=C_TEXT_PRIMARY,
            ).pack(fill="x", padx=8, pady=2)

        result = {"ok": False}

        def yes():
            result["ok"] = True
            dlg.destroy()

        def no():
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 16))
        btns.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btns, text="取消", width=90, height=32, command=no,
            fg_color=C_BG_RAISED, hover_color=C_BORDER,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(
            btns, text="开始安装", width=120, height=32, command=yes,
            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=2, padx=(8, 0))

        dlg.protocol("WM_DELETE_WINDOW", no)
        dlg.bind("<Escape>", lambda e: no())
        self.wait_window(dlg)
        return result["ok"]


def main() -> int:
    app = InstallerManagerApp()
    app.mainloop()
    return 0
