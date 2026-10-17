"""
内部自检脚本（不属于交付物，用于验证 calibrate.py 的正确性）

思路：
    已知真值 (K_true, dist_true) → 用它们渲染出带透视与畸变的棋盘格图像
    → 交给 calibrate 的同一套角点检测与求解流程 → 看能不能把真值反解出来。

    能反解，说明后续用真实照片标定时结果可信；反解不出，说明参数或流程有 bug。
    这样可以在拿到实物照片之前就把代码错误排掉。

运行：
    .venv\\Scripts\\python.exe q2_calib/_selftest.py
"""

import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np

import calibrate as calib

W, H = 1280, 720
PATTERN = (9, 6)
SQUARE = 18.0

# 真值：模拟一个广角笔记本摄像头
K_TRUE = np.array([[905.0, 0.0, 643.5],
                   [0.0, 902.0, 361.2],
                   [0.0, 0.0, 1.0]])
DIST_TRUE = np.array([-0.1520, 0.0830, 0.00075, -0.00052, -0.0120])

# 姿态表：(rx, ry, rz, 距离mm, 水平偏移mm, 垂直偏移mm)，角度为度
# 覆盖 5 类：正对 / 左右倾 / 上下倾 / 绕光轴转 / 偏置到画面边缘
POSES = [
    (0, 0, 0, 420, 0, 0),
    (0, 0, 0, 520, 0, 0),
    (0, 0, 0, 650, 0, 0),
    (18, 12, 0, 500, 0, 0),
    (-20, 16, 0, 520, 0, 0),
    (24, 20, 0, 620, 0, 0),
    (-26, -15, 0, 480, 0, 0),
    (35, 0, 0, 540, 0, 0),
    (-35, 0, 0, 540, 0, 0),
    (0, 35, 0, 540, 0, 0),
    (0, -35, 0, 540, 0, 0),
    (28, -22, 0, 580, 0, 0),
    (-30, 24, 0, 580, 0, 0),
    (20, 15, 35, 520, 0, 0),
    (-22, -18, -40, 520, 0, 0),
    (15, -12, 50, 560, 0, 0),
    (-16, 14, -50, 560, 0, 0),
    (12, 10, 0, 760, -170, 90),
    (-14, -8, 0, 760, 170, -90),
    (10, 6, 25, 700, 150, 80),
]

SS = 3  # 超采样倍数，让方格边缘平滑，便于亚像素角点检测

BOARD_CENTER = np.array([SQUARE * (PATTERN[0] + 1) / 2,
                         SQUARE * (PATTERN[1] + 1) / 2, 0.0])


def make_pose(rx, ry, rz, dist, tx=0.0, ty=0.0):
    """给定旋转角与期望的棋盘中心位置，反解出 tvec。

    棋盘世界坐标原点在左上角，直接设 tvec 会让棋盘整体偏出画面。
    这里先把棋盘中心转到目标位置，再反推平移量。
    """
    rvec = np.radians(np.array([rx, ry, rz], np.float64)).reshape(3, 1)
    R, _ = cv2.Rodrigues(rvec)
    tvec = (np.array([tx, ty, dist], np.float64) - R @ BOARD_CENTER).reshape(3, 1)
    return rvec, tvec


def render(rvec, tvec):
    """按真值参数渲染一张棋盘格图像。"""
    K2 = K_TRUE.copy()
    K2[0, 0] *= SS; K2[1, 1] *= SS
    K2[0, 2] *= SS; K2[1, 2] *= SS

    # 9x6 内角点 → 10x7 个方格 → 11x8 个顶点
    nx, ny = PATTERN[0] + 2, PATTERN[1] + 2
    verts = np.zeros((ny * nx, 3), np.float64)
    for r in range(ny):
        for c in range(nx):
            verts[r * nx + c] = (c * SQUARE, r * SQUARE, 0.0)

    proj, _ = cv2.projectPoints(verts, rvec, tvec, K2, DIST_TRUE)
    proj = proj.reshape(ny, nx, 2)

    canvas = np.full((H * SS, W * SS), 255, np.uint8)
    for r in range(ny - 1):
        for c in range(nx - 1):
            if (r + c) % 2 == 1:
                quad = np.round(proj[r:r + 2, c:c + 2].reshape(-1, 2)).astype(np.int32)
                quad = np.array([quad[0], quad[1], quad[3], quad[2]], np.int32)
                cv2.fillConvexPoly(canvas, quad, 0, cv2.LINE_AA)

    img = cv2.resize(canvas, (W, H), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calib_selftest_"))
    print(f"[自检] 合成 {len(POSES)} 张图 -> {tmp}")

    for i, pose in enumerate(POSES, 1):
        rvec, tvec = make_pose(*pose)
        img = render(rvec, tvec)
        cv2.imwrite(str(tmp / f"{i:02d}_synth.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 96])

    objpoints, imgpoints, records, failed = calib.collect(tmp, PATTERN, SQUARE)
    print(f"[自检] 检出 {len(records)}/{len(POSES)} 张，失败 {len(failed)} 张")
    for name, why in failed:
        print(f"   [- ] {name}: {why}")

    if len(records) < 6:
        print("[自检失败] 检出数量不足，渲染或检测环节有问题。")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    w = records[0]["size"][0]
    h = records[0]["size"][1]
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, (w, h), None, None
    )

    fx_err = abs(K[0, 0] - K_TRUE[0, 0]) / K_TRUE[0, 0] * 100
    fy_err = abs(K[1, 1] - K_TRUE[1, 1]) / K_TRUE[1, 1] * 100
    cx_err = abs(K[0, 2] - K_TRUE[0, 2])
    cy_err = abs(K[1, 2] - K_TRUE[1, 2])

    print("\n" + "=" * 60)
    print("自检结果：反解值 vs 真值")
    print("=" * 60)
    print(f"{'参数':<8}{'真值':>12}{'反解':>12}{'偏差':>12}")
    print(f"{'fx':<8}{K_TRUE[0, 0]:>12.3f}{K[0, 0]:>12.3f}{fx_err:>11.3f}%")
    print(f"{'fy':<8}{K_TRUE[1, 1]:>12.3f}{K[1, 1]:>12.3f}{fy_err:>11.3f}%")
    print(f"{'cx':<8}{K_TRUE[0, 2]:>12.3f}{K[0, 2]:>12.3f}{cx_err:>11.3f}px")
    print(f"{'cy':<8}{K_TRUE[1, 2]:>12.3f}{K[1, 2]:>12.3f}{cy_err:>11.3f}px")
    print(f"\n{'畸变':<8}{'真值':>12}{'反解':>12}")
    for i, n in enumerate(["k1", "k2", "p1", "p2", "k3"]):
        print(f"{n:<8}{DIST_TRUE[i]:>12.6f}{dist.ravel()[i]:>12.6f}")
    print(f"\n重投影误差 RMS = {rms:.4f} px")
    print(f"有效图 {len(records)} 张")

    ok = fx_err < 1.0 and fy_err < 1.0 and cx_err < 8 and cy_err < 8 and rms < 0.5
    print("\n" + ("[通过] 流程与求解正确，可以用于真实照片。" if ok
                  else "[未通过] 偏差偏大，检查渲染或角点提供顺序。"))

    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
