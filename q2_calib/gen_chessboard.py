# -*- coding: utf-8 -*-
"""生成棋盘格标定板：A4 打印版 与 全屏显示版。

题二要求「制作棋盘格标定板（打印后贴于硬质平板，**或在另一显示屏上全屏显示**）」。

两种载体差别很大，所以本脚本出两套图：

A4 打印版
    按**毫米**绘制，300 DPI 输出。打印后只要没被缩放，方格边长就是标称的
    18.00 mm，直接用 --square 18 即可。

全屏显示版
    按**像素**绘制，尺寸与显示器原生分辨率一致。方格的物理尺寸取决于屏幕
    PPI，无法预先确定，**必须用直尺量**：量 10 格总长再除以 10，把实测值
    传给 calibrate.py 的 --square。这是原文「并实际测量方格边长」的由来。

关键参数
--------
COLS, ROWS : 内角点数（不是方格数）。9x6 表示内部有 9 列 6 行可检测角点，
             整个棋盘因此是 10x7 个方格。
SQUARE_MM  : A4 版的单格边长，打印后即标定时的 square_size。
DPI        : A4 版输出分辨率。300 是常见打印机合适值。

用法
----
    python gen_chessboard.py                      # A4 打印版
    python gen_chessboard.py --screen             # 全屏版（自动读取屏幕分辨率）
    python gen_chessboard.py --screen --size 1920x1200
    python gen_chessboard.py --all                # 两版都出

输出
----
    board/chessboard_9x6_18mm_a4.png
    board/chessboard_9x6_screen_<W>x<H>.png
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ============ 可调参数 ============
COLS = 9
ROWS = 6
SQUARE_MM = 18.0
DPI = 300

# 全屏版四周留白（像素）。留白给白格一个外围，避免边缘黑格紧贴屏幕边缘
# 导致 findChessboardCorners 无法确定图案范围。
SCREEN_MARGIN = 40

# ============ A4 纸张 ============
PAPER_W_MM = 210.0
PAPER_H_MM = 297.0
PX_PER_MM = DPI / 25.4

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"

OUT_DIR = Path(__file__).resolve().parent / "board"


def mm(v: float) -> int:
    """毫米转像素（仅 A4 版使用）。"""
    return round(v * PX_PER_MM)


def text_center(draw, cx, y_mm, s, font, fill="black"):
    """按水平中心绘制文字，y 以毫米给出。"""
    left, top, right, bottom = draw.textbbox((0, 0), s, font=font)
    draw.text((cx - (right - left) / 2 - left, mm(y_mm)), s, font=font, fill=fill)


def draw_board(d, x0, y0, sq, n_cols, n_rows):
    """在 (x0, y0) 处画一个 n_cols x n_rows 的棋盘，左上角为黑格。"""
    for r in range(n_rows):
        for c in range(n_cols):
            if (r + c) % 2 == 0:
                x, y = x0 + c * sq, y0 + r * sq
                d.rectangle([x, y, x + sq - 1, y + sq - 1], fill="black")


# ---------------------------------------------------------------- A4 打印版
def gen_a4() -> Path:
    W, H = mm(PAPER_W_MM), mm(PAPER_H_MM)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    cx = W // 2

    sq = mm(SQUARE_MM)
    n_cols, n_rows = COLS + 1, ROWS + 1
    board_w, board_h = n_cols * sq, n_rows * sq

    if board_w > W - mm(24):
        raise ValueError(
            f"棋盘宽 {board_w / PX_PER_MM:.1f}mm 超出 A4 安全打印区，请减小 SQUARE_MM"
        )

    f_title = ImageFont.truetype(FONT_PATH, 50)
    f_body = ImageFont.truetype(FONT_PATH, 36)
    f_small = ImageFont.truetype(FONT_PATH, 30)

    # ---- 顶部标题 ----
    text_center(d, cx, 18, "棋盘格标定板", f_title)
    text_center(
        d, cx, 34,
        f"内角点 {COLS} × {ROWS}　方格边长 {SQUARE_MM:.0f} mm　A4 · {DPI} DPI",
        f_body,
    )

    # ---- 棋盘格：左上角为黑格 ----
    x0 = (W - board_w) // 2
    y0 = mm(52)
    draw_board(d, x0, y0, sq, n_cols, n_rows)

    board_bottom_mm = 52 + board_h / PX_PER_MM

    # ---- 100mm 校准尺 ----
    ruler_len = mm(100.0)
    ruler_x0 = (W - ruler_len) // 2
    ruler_y = mm(board_bottom_mm + 16)
    d.line([ruler_x0, ruler_y, ruler_x0 + ruler_len, ruler_y], fill="black", width=6)
    for i in range(11):
        tx = ruler_x0 + mm(i * 10.0)
        long_tick = i % 5 == 0
        half = mm(5.0) if long_tick else mm(2.5)
        d.line([tx, ruler_y - half, tx, ruler_y + half], fill="black", width=6 if long_tick else 3)
    text_center(d, cx, board_bottom_mm + 22, "注意：此标尺实际长度应为 100 mm，打印后用直尺核对", f_small)

    # ---- 底部说明 ----
    text_center(
        d, cx, board_bottom_mm + 38,
        f"检测参数　pattern_size = ({COLS}, {ROWS})　square_size = {SQUARE_MM:.0f} mm",
        f_body,
    )
    text_center(
        d, cx, board_bottom_mm + 52,
        "打印时缩放须选「实际大小 / 100%」，切勿选「适应页面」",
        f_small,
    )
    text_center(
        d, cx, board_bottom_mm + 62,
        "标尺不足 100 mm 说明被缩放，需重新打印，否则测距结果会整体偏大",
        f_small,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"chessboard_{COLS}x{ROWS}_{int(SQUARE_MM)}mm_a4.png"
    img.save(out, dpi=(DPI, DPI))

    print(f"[A4 打印版] {out}")
    print(f"  图片像素      : {W} x {H}")
    print(f"  棋盘占用      : {board_w / PX_PER_MM:.1f} x {board_h / PX_PER_MM:.1f} mm")
    print(f"  单格边长      : {sq} px = {sq / PX_PER_MM:.2f} mm")
    print(f"  左右留白      : {x0 / PX_PER_MM:.1f} mm")
    print(f"  棋盘下沿      : {board_bottom_mm:.1f} mm（A4 高 297 mm）")
    print(f"  内角点        : {COLS} x {ROWS}")
    print(f"  square_size   : {SQUARE_MM:.1f} mm")
    return out


# ---------------------------------------------------------------- 全屏显示版
def gen_screen(W: int, H: int) -> Path:
    """按屏幕原生分辨率生成满屏棋盘格。

    用整数像素画格子，保证每格严格等大、是正方形（非整数会累积舍入误差，
    20 格下来能差出几个像素，等于人为引入一个非均匀缩放）。
    """
    n_cols, n_rows = COLS + 1, ROWS + 1
    sq = min((W - 2 * SCREEN_MARGIN) // n_cols, (H - 2 * SCREEN_MARGIN) // n_rows)
    board_w, board_h = n_cols * sq, n_rows * sq

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    x0 = (W - board_w) // 2
    y0 = (H - board_h) // 2
    draw_board(d, x0, y0, sq, n_cols, n_rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"chessboard_{COLS}x{ROWS}_screen_{W}x{H}.png"
    img.save(out)

    print(f"[全屏显示版] {out}")
    print(f"  画布像素      : {W} x {H}  （须与显示器原生分辨率一致）")
    print(f"  单格边长      : {sq} px")
    print(f"  棋盘占用      : {board_w} x {board_h} px")
    print(f"  四周留白      : 左右 {(W - board_w) // 2} px，上下 {(H - board_h) // 2} px")
    print(f"  内角点        : {COLS} x {ROWS}")
    print()
    print("  屏幕上必须有直尺实测，不能填标称值。")
    print("  量第 1 行前 10 格的总长（含 10 个格子），除以 10 得到单格边长：")
    print(f"    例：10 格共 305 mm  ->  --square 30.5")
    return out


# ---------------------------------------------------------------- 入口
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", action="store_true", help="生成全屏显示版")
    ap.add_argument("--a4", action="store_true", help="生成 A4 打印版")
    ap.add_argument("--all", action="store_true", help="两版都生成")
    ap.add_argument("--size", default=None,
                    help="屏幕分辨率，如 1920x1200。缺省自动读取当前主显示器")
    return ap.parse_args()


def detect_screen():
    """读取主显示器原生像素分辨率。"""
    import ctypes
    u = ctypes.windll.user32
    u.SetProcessDPIAware()
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def main() -> None:
    args = parse_args()
    do_a4 = args.a4 or args.all or not (args.screen or args.all)
    do_screen = args.screen or args.all

    if do_a4:
        gen_a4()
        print()

    if do_screen:
        if args.size:
            w, h = (int(v) for v in args.size.lower().split("x"))
        else:
            w, h = detect_screen()
        gen_screen(w, h)


if __name__ == "__main__":
    main()
