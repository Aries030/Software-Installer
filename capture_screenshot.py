"""启动 GUI 并精准截图主窗口。

使用 Win32 API 定位 Software Installer 窗口并截取它本身,
避免其他窗口遮挡。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time


def find_window_by_title(partial_title: str):
    """查找包含指定文本的可见顶层窗口。"""
    user32 = ctypes.windll.user32
    result = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        if partial_title.lower() in buff.value.lower():
            result.append((hwnd, buff.value))
        return True

    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    return result


def capture_window(hwnd: int, out_path: str) -> tuple:
    """使用 PrintWindow 截取指定窗口。"""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # 获取窗口尺寸
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError(f"窗口尺寸无效: {w}x{h}")

    # 创建设备上下文
    hdc_window = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
    gdi32.SelectObject(hdc_mem, hbitmap)

    # 使用 PrintWindow 抓取(PW_RENDERFULLCONTENT = 2,支持现代应用)
    PW_RENDERFULLCONTENT = 0x00000002
    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

    # 提取位图到 buffer
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD),
            ("biWidth", wt.LONG),
            ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD),
            ("biBitCount", wt.WORD),
            ("biCompression", wt.DWORD),
            ("biSizeImage", wt.DWORD),
            ("biXPelsPerMeter", wt.LONG),
            ("biYPelsPerMeter", wt.LONG),
            ("biClrUsed", wt.DWORD),
            ("biClrImportant", wt.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    buf_len = w * h * 4
    buf = (ctypes.c_ubyte * buf_len)()
    gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)

    # 用 Pillow 转换为图像(BGRX -> RGBA)
    from PIL import Image
    img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
    img = img.convert("RGB")
    img.save(out_path)
    return (w, h)


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    exe = os.path.join(project_root, "SoftwareInstaller.exe")
    out_path = os.path.join(project_root, "assets", "screenshot_gui.png")
    full_path = os.path.join(project_root, "assets", "screenshot_gui_full.png")
    if not os.path.exists(exe):
        print(f"[错误] 未找到 {exe}")
        sys.exit(1)

    print(f"[启动] {exe}")
    proc = subprocess.Popen([exe])

    # 等 GUI 完全渲染(寻找窗口)
    hwnd_found = None
    for attempt in range(20):
        time.sleep(0.5)
        wins = find_window_by_title("Software Installer")
        if wins:
            hwnd_found = wins[0][0]
            title = wins[0][1]
            print(f"[找到窗口] hwnd={hwnd_found} title={title!r}")
            # 多等一会儿,等组件完全渲染
            time.sleep(2)
            break

    try:
        if hwnd_found:
            w, h = capture_window(hwnd_found, out_path)
            print(f"[OK] 窗口截图: {out_path} ({w}x{h})")
        else:
            print("[WARN] 未找到 GUI 窗口,改用全屏截图")
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(full_path)
            print(f"[OK] 全屏截图: {full_path} ({img.size[0]}x{img.size[1]})")
    except Exception as exc:
        print(f"[错误] 截图失败: {exc}")
        import traceback; traceback.print_exc()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[OK] GUI 已关闭")


if __name__ == "__main__":
    main()