"""生成 Software Installer 的 LOGO 图标文件 (PNG + ICO)。

用 Pillow 复刻 SVG 设计:
  - 圆角方形深蓝渐变背景
  - 中央向下箭头 (青蓝渐变,代表安装/部署)
  - 底部托盘横条 (青色,代表安装到位)
  - 柔和阴影
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """生成垂直线性渐变的 RGBA 图像(用作背景裁剪源)。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    return img


def _diagonal_gradient(size: int, c1: tuple, c2: tuple, c3: tuple) -> Image.Image:
    """生成对角线渐变(三点:左上 -> 中 -> 右下)。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        for x in range(size):
            # 对角进度 0..1
            t = (x + y) / max(2 * (size - 1), 1)
            if t < 0.55:
                k = t / 0.55
                r = int(c1[0] + (c2[0] - c1[0]) * k)
                g = int(c1[1] + (c2[1] - c1[1]) * k)
                b = int(c1[2] + (c2[2] - c1[2]) * k)
            else:
                k = (t - 0.55) / 0.45
                r = int(c2[0] + (c3[0] - c2[0]) * k)
                g = int(c2[1] + (c3[1] - c2[1]) * k)
                b = int(c2[2] + (c3[2] - c2[2]) * k)
            px[x, y] = (r, g, b, 255)
    return img


def _rounded_mask(size: int, radius: int) -> Image.Image:
    """圆角方形蒙版。"""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _arrow_shaft_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """箭头杆垂直渐变。"""
    return _vertical_gradient(size, top, bottom)


def render_logo(size: int = 256) -> Image.Image:
    """渲染指定尺寸的 LOGO。"""
    s = size
    # 边距比例:SVG 中背景 8..248,即边距 8/256
    pad = max(1, int(s * 8 / 256))
    radius = int(s * 56 / 256)

    # 1) 圆角背景(对角深蓝渐变)
    bg_full = _diagonal_gradient(s, (10, 37, 64), (13, 71, 161), (1, 87, 155))
    mask = _rounded_mask(s, radius)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(bg_full, (0, 0), mask)

    # 2) 顶部高光(半透明白)
    highlight = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.rounded_rectangle((pad, pad, s - pad, pad + int(s * 120 / 256)),
                         radius=radius, fill=(255, 255, 255, 15))
    img = Image.alpha_composite(img, highlight)

    # 阴影层:先画到阴影画布再合成
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)

    # 箭头几何(按 SVG 256 坐标缩放)
    def sc(v: float) -> int:
        return int(v * s / 256)

    shaft_x0, shaft_y0 = sc(108), sc(56)
    shaft_x1, shaft_y1 = sc(148), sc(148)
    shaft_r = max(2, sc(14))

    # 箭头头:三角,顶点 (128,196),左上 (70,138),右上 (186,138)
    head_top_y = sc(132)
    head_pts = [
        (sc(128), sc(196)),
        (sc(70), sc(138)),
        (sc(186), sc(138)),
    ]

    # 托盘
    tray_x0, tray_y0 = sc(56), sc(206)
    tray_x1, tray_y1 = sc(200), sc(226)
    tray_r = max(2, sc(10))

    # 绘制阴影(向下偏移3)
    offset = max(1, sc(3))
    sd.rounded_rectangle((shaft_x0, shaft_y0 + offset, shaft_x1, shaft_y1 + offset),
                         radius=shaft_r, fill=(0, 0, 0, 90))
    sd.polygon([(p[0], p[1] + offset) for p in head_pts], fill=(0, 0, 0, 90))
    sd.rounded_rectangle((tray_x0, tray_y0 + offset, tray_x1, tray_y1 + offset),
                         radius=tray_r, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, sc(2))))
    img = Image.alpha_composite(img, shadow)

    # 3) 箭头本体(青蓝渐变)
    arrow_color_top = (79, 195, 247, 255)
    arrow_color_bottom = (0, 176, 255, 255)
    # 用一个渐变图裁剪成箭头形状
    grad = _arrow_shaft_gradient(s, arrow_color_top, arrow_color_bottom)

    arrow_mask = Image.new("L", (s, s), 0)
    am = ImageDraw.Draw(arrow_mask)
    am.rounded_rectangle((shaft_x0, shaft_y0, shaft_x1, shaft_y1),
                         radius=shaft_r, fill=255)
    am.polygon(head_pts, fill=255)
    arrow_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    arrow_layer.paste(grad, (0, 0), arrow_mask)
    img = Image.alpha_composite(img, arrow_layer)

    # 4) 托盘(青色水平渐变)
    tray_grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    tg = ImageDraw.Draw(tray_grad)
    # 近似水平渐变:用多段矩形
    tray_c1 = (128, 222, 234, 255)
    tray_c2 = (38, 198, 218, 255)
    segs = 32
    for i in range(segs):
        t = i / (segs - 1)
        r = int(tray_c1[0] + (tray_c2[0] - tray_c1[0]) * t)
        g = int(tray_c1[1] + (tray_c2[1] - tray_c1[1]) * t)
        b = int(tray_c1[2] + (tray_c2[2] - tray_c1[2]) * t)
        x0 = tray_x0 + int((tray_x1 - tray_x0) * i / segs)
        x1 = tray_x0 + int((tray_x1 - tray_x0) * (i + 1) / segs) + 1
        tg.rectangle((x0, tray_y0, x1, tray_y1), fill=(r, g, b, 255))
    # 把渐变裁成圆角
    tray_mask = Image.new("L", (s, s), 0)
    tm = ImageDraw.Draw(tray_mask)
    tm.rounded_rectangle((tray_x0, tray_y0, tray_x1, tray_y1), radius=tray_r, fill=255)
    tray_final = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    tray_final.paste(tray_grad, (0, 0), tray_mask)
    img = Image.alpha_composite(img, tray_final)

    return img


def main() -> None:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    assets = here  # 脚本本身就在 assets 目录内
    os.makedirs(assets, exist_ok=True)

    big = render_logo(512)
    big.save(os.path.join(assets, "logo.png"))

    # ICO 需要多尺寸
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_images = [render_logo(n) for n in ico_sizes]
    ico_images[0].save(
        os.path.join(assets, "logo.ico"),
        format="ICO",
        sizes=[(n, n) for n in ico_sizes],
        append_images=ico_images[1:],
    )

    # 额外保存一个 256 的预览
    render_logo(256).save(os.path.join(assets, "logo_256.png"))

    print("LOGO 生成完成:")
    print(f"  - {assets}/logo.png (512x512)")
    print(f"  - {assets}/logo_256.png (256x256)")
    print(f"  - {assets}/logo.ico (多尺寸: {ico_sizes})")


if __name__ == "__main__":
    main()
