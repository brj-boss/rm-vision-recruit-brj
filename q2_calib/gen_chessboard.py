# -*- coding: utf-8 -*-
"""生成 A4 精确尺寸的棋盘格标定板。

题二要求「自制棋盘格」。本脚本按**毫米**尺寸绘制，保证打印后格子边长准确，
可直接作为 cv2.calibrateCamera / solvePnP 的标定物，无需手工测量。

关键参数
--------
COLS, ROWS : 内角点数（不是方格数）。9x6 表示内部有 9 列 6 行可检测角点，
             整个棋盘因此是 10x7 个方格。
SQUARE_MM  : 单个方格边长，打印后即标定时的 square_size（换算成米为 0.018）。
DPI        : 输出分辨率。300 是常见家用/商用打印机的合适值。

用法
----
    python gen_chessboard.py

输出
----
    board/chessboard_9x6_18mm_a4.png
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ============ 可调参数 ============
COLS = 9
ROWS = 6
SQUARE_MM = 18.0
DPI = 300

# ============ A4 纸张 ============
PAPER_W_MM = 210.0
PAPER_H_MM = 297.0
PX_PER_MM = DPI / 25.4

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"

OUT_DIR = Path(__file__).resolve().parent / "board"
OUT_FILE = OUT_DIR / f"chessboard_{COLS}x{ROWS}_{int(SQUARE_MM)}mm_a4.png"


def mm(v: float) -> int:
    """毫米转像素。"""
    return round(v * PX_PER_MM)


def text_center(draw, cx, y_mm, s, font, fill="black"):
    """按水平中心绘制文字，y 以毫米给出。"""
    left, top, right, bottom = draw.textbbox((0, 0), s, font=font)
    draw.text((cx - (right - left) / 2 - left, mm(y_mm)), s, font=font, fill=fill)


def main() -> None:
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
    for r in range(n_rows):
        for c in range(n_cols):
            if (r + c) % 2 == 0:
                x, y = x0 + c * sq, y0 + r * sq
                d.rectangle([x, y, x + sq - 1, y + sq - 1], fill="black")

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
    img.save(OUT_FILE, dpi=(DPI, DPI))

    print(f"已生成: {OUT_FILE}")
    print(f"  图片像素      : {W} x {H}")
    print(f"  棋盘占用      : {board_w / PX_PER_MM:.1f} x {board_h / PX_PER_MM:.1f} mm")
    print(f"  单格边长      : {sq} px = {sq / PX_PER_MM:.2f} mm")
    print(f"  左右留白      : {x0 / PX_PER_MM:.1f} mm")
    print(f"  棋盘下沿      : {board_bottom_mm:.1f} mm（A4 高 297 mm）")
    print(f"  内角点        : {COLS} x {ROWS}")
    print(f"  square_size   : {SQUARE_MM:.1f} mm = {SQUARE_MM / 1000:.4f} m")


if __name__ == "__main__":
    main()
