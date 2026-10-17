"""
题二 · 标定图采集脚本（带姿态引导 + 实时角点检测）

用法：
    .venv\\Scripts\\python.exe q2_calib/capture_calib.py
    .venv\\Scripts\\python.exe q2_calib/capture_calib.py --index 1     # 换另一个摄像头
    .venv\\Scripts\\python.exe q2_calib/capture_calib.py --size 1920x1080

为什么要有这个脚本：
    标定成败的 90% 取决于图片质量，而"这张图能不能用"在相机取景框里是看不出来的。
    本脚本实时跑 findChessboardCorners：
        - 检出角点 → 绿框 + 底部变绿，此时按空格才允许保存
        - 没检出   → 底部变灰，按空格无效（避免收进废图）
    同时按预设顺序提示该拍什么姿态，拍够 20 张后自动结束。

按键：
    空格  保存当前帧（仅在检出角点时有效）
    d     删除最后一张（拍错了重来）
    r     重置整组（清空本次采集记录，不删文件）
    q/ESC 退出

注意：保存的是**原始帧**，不带角点绘制和提示文字，直接可用于 calibrateCamera。
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- 配置

BOARD_INNER = (9, 6)          # 内角点数（列, 行）—— 必须与打印的棋盘格一致
SQUARE_MM = 18.0              # 标称方格边长（实际值要靠尺子量，填进报告）
CALIB_DIR = Path(__file__).parent / "calib_images"
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"

# 姿态计划：(组名, 提示文字, 文件名标记)
# 20 张，覆盖 5 类姿态。缺了哪一类，标定结果都会系统性变差：
#   正对     → 提供尺度与主点信息
#   左右/上下倾斜 → 解出 fx、fy 与径向畸变 k1 k2
#   光轴旋转  → 解开 fx 与 fy 的耦合（不转的话两者容易一起漂）
#   画面四角  → 切向畸变 p1 p2 与高阶 k3 只能靠画面边缘的角点来定
PLAN = [
    ("正对", "正对棋盘格，距离约 0.35 m", "front_035cm"),
    ("正对", "正对棋盘格，距离约 0.50 m", "front_050cm"),
    ("正对", "正对棋盘格，距离约 0.70 m", "front_070cm"),
    ("正对", "正对棋盘格，距离约 1.00 m", "front_100cm"),
    ("左右倾斜", "向左倾斜约 30 度（棋盘左侧离镜头更远）", "tilt_L30"),
    ("左右倾斜", "向左倾斜约 45 度", "tilt_L45"),
    ("左右倾斜", "向右倾斜约 30 度（棋盘右侧离镜头更远）", "tilt_R30"),
    ("左右倾斜", "向右倾斜约 45 度", "tilt_R45"),
    ("上下倾斜", "向上倾斜约 30 度（棋盘上沿离镜头更远）", "tilt_U30"),
    ("上下倾斜", "向上倾斜约 45 度", "tilt_U45"),
    ("上下倾斜", "向下倾斜约 30 度（棋盘下沿离镜头更远）", "tilt_D30"),
    ("上下倾斜", "向下倾斜约 45 度", "tilt_D45"),
    ("光轴旋转", "把棋盘在画面内旋转约 15 度", "roll_15"),
    ("光轴旋转", "把棋盘在画面内旋转约 30 度", "roll_30"),
    ("光轴旋转", "把棋盘在画面内旋转约 45 度", "roll_45"),
    ("光轴旋转", "把棋盘在画面内旋转约 60 度", "roll_60"),
    ("画面四角", "把棋盘移到画面【左上角】，占画面约 1/4", "corner_LT"),
    ("画面四角", "把棋盘移到画面【右上角】，占画面约 1/4", "corner_RT"),
    ("画面四角", "把棋盘移到画面【左下角】，占画面约 1/4", "corner_LB"),
    ("画面四角", "把棋盘移到画面【右下角】，占画面约 1/4", "corner_RB"),
]


# ---------------------------------------------------------------- 中文绘制
# cv2.putText 不支持中文，这里用 PIL 预渲染成图片再混合。
# 预渲染 + 缓存，避免每帧重新排版（1280x720 下每帧多花 10ms 会明显掉帧）。

_font_cache = {}
_panel_cache = {}


def _font(size):
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
    return _font_cache[size]


def make_panel(text, width, height, font_size=24, color=(255, 255, 255)):
    """把一行文字渲染成 height×width 的 BGR 图，黑底白字，用于半透明叠加。"""
    key = (text, width, height, font_size, color)
    if key in _panel_cache:
        return _panel_cache[key]

    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = max(0, (width - tw) // 2)
    y = max(0, (height - th) // 2 - bbox[1])
    draw.text((x, y), text, font=font, fill=color)

    arr = np.array(img)[:, :, ::-1].copy()  # RGB → BGR
    _panel_cache[key] = arr
    return arr


def overlay(frame, panel, x, y, alpha=0.62):
    """把 panel 以 alpha 混合方式贴到 frame 的 (x, y)。"""
    fh, fw = frame.shape[:2]
    ph, pw = panel.shape[:2]
    x = max(0, min(x, fw - pw))
    y = max(0, min(y, fh - ph))
    if pw <= 0 or ph <= 0:
        return frame
    roi = frame[y:y + ph, x:x + pw]
    cv2.addWeighted(panel, alpha, roi, 1 - alpha, 0, roi)
    return frame


# ---------------------------------------------------------------- 采集逻辑

def open_camera(index, width, height):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)   # DSHOW 在 Windows 上打开更快、更稳
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"[错误] 打不开摄像头 index={index}")
        print("  1) 检查是否有其他程序占用（微信/QQ/浏览器会议页面）")
        print("  2) 试试 --index 1 或 --index 2")
        print("  3) Windows 设置 → 隐私 → 相机 → 允许桌面应用访问相机")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # 高分辨率下提高帧率

    for _ in range(10):        # 前几帧往往是黑的，先丢掉
        cap.read()
    return cap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0, help="摄像头编号，默认 0")
    ap.add_argument("--size", default="1280x720", help="分辨率，如 1920x1080")
    args = ap.parse_args()

    width, height = (int(v) for v in args.size.lower().split("x"))
    CALIB_DIR.mkdir(parents=True, exist_ok=True)

    # 清掉上一次的同名文件，避免 20 张混进 30 张
    stale = sorted(CALIB_DIR.glob("*.jpg"))
    if stale:
        print(f"[提示] {CALIB_DIR.name}/ 里已有 {len(stale)} 张图，新图会按序号覆盖同名文件。")

    cap = open_camera(args.index, width, height)
    print(f"[已连接] {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
    print(f"[目标] {len(PLAN)} 张，保存到 {CALIB_DIR}")
    print("[按键] 空格保存 / d 删最后一张 / q 退出\n")

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    win = "Calibration Capture  (SPACE=save  D=undo  Q=quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, width, height)

    saved = []          # [(文件名, 覆盖率%)]
    idx = 0
    last_tip = None

    while idx < len(PLAN):
        ok, frame = cap.read()
        if not ok:
            print("[错误] 读不到画面，摄像头可能被拔出。")
            break

        raw = frame.copy()                       # 存盘用原始帧
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        found, corners = cv2.findChessboardCorners(
            gray, BOARD_INNER,
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FAST_CHECK,
        )

        cover = 0.0
        if found:
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            cv2.drawChessboardCorners(frame, BOARD_INNER, corners, found)
            x, y, w, h = cv2.boundingRect(corners.astype(np.int32))
            cover = 100.0 * (w * h) / (frame.shape[0] * frame.shape[1])

        group, tip, tag = PLAN[idx]

        # 顶部：当前任务
        overlay(frame, make_panel(f"[{idx + 1}/{len(PLAN)}]  {group}", width, 44, 24),
                0, 0, 0.68)
        overlay(frame, make_panel(tip, width, 40, 21), 0, 44, 0.62)

        # 底部：状态条
        if found:
            if cover < 8:
                status = f"角点已检出，但棋盘太小（占画面 {cover:.0f}%），请靠近一些"
                s_color = (140, 220, 255)
            else:
                status = f"角点已检出（占画面 {cover:.0f}%）  按空格保存"
                s_color = (120, 255, 120)
        else:
            status = "未检出棋盘格：调整距离、角度或光照，让棋盘完整进入画面"
            s_color = (190, 190, 190)
        overlay(frame, make_panel(status, width, 42, 21, s_color), 0, height - 42, 0.68)

        # 右侧：进度
        overlay(frame, make_panel(f"{len(saved)}/{len(PLAN)}", 150, 36, 20),
                width - 155, 0, 0.55)

        cv2.imshow(win, frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), 27):
            print("[退出] 已保存的图片仍保留在磁盘上。")
            break

        elif key == ord(" ") and found and cover >= 8:
            name = f"{len(saved) + 1:02d}_{tag}.jpg"
            path = CALIB_DIR / name
            cv2.imwrite(str(path), raw, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved.append((name, cover))
            print(f"  [{len(saved):02d}/{len(PLAN)}] {name}   覆盖率 {cover:.0f}%")
            idx += 1
            if idx < len(PLAN):
                last_tip = PLAN[idx][1]

        elif key == ord(" ") and found and cover < 8:
            print("  [跳过] 棋盘占画面太小，标定精度会变差，请靠近后重拍。")

        elif key == ord("d") and saved:
            name, _ = saved.pop()
            (CALIB_DIR / name).unlink(missing_ok=True)
            idx = max(0, idx - 1)
            print(f"  [撤销] 已删除 {name}，回到第 {idx + 1} 张")

    cap.release()
    cv2.destroyAllWindows()

    # ---------------------------------------------------------------- 收尾
    print("\n" + "=" * 56)
    print(f"采集结束：计划 {len(PLAN)} 张，实际保存 {len(saved)} 张")
    if saved:
        print(f"目录：{CALIB_DIR}")
        avg = sum(c for _, c in saved) / len(saved)
        print(f"棋盘平均覆盖率：{avg:.1f}%  （20%~60% 是理想区间）")
        if avg < 12:
            print("[提醒] 覆盖率偏低，建议整体靠近一些重拍，角点像素坐标更准。")
        if len(saved) < len(PLAN):
            missing = [PLAN[i][0] for i in range(len(saved), len(PLAN))]
            print(f"[提醒] 还缺：{', '.join(sorted(set(missing)))} 类姿态")
        print("\n下一步：python q2_calib/calibrate.py")
    print("=" * 56)


if __name__ == "__main__":
    main()
