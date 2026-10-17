# -*- coding: utf-8 -*-
"""题二 · 去畸变对比与畸变模型体检

本脚本回答两个问题：

  1. 去畸变到底改了图像哪里？
     → 三栏对比图 + 四角放大对比

  2. 标定出来的畸变系数可信吗？
     → 两个客观指标，不靠肉眼：
        (a) 直线度：棋盘格边缘在物理世界是直线，图像上却会弯。
            把「角点偏离拟合直线的最大距离」作为指标，去畸变后应显著下降。
        (b) 径向单调性：畸变模型 r_d = r(1+k1r²+k2r⁴+k3r⁶) 必须在整个画面
            内单调递增。若 d(r_d)/dr 在某半径处变负，说明该处映射折叠 ——
            这是高阶系数过拟合的典型症状，去畸变图边缘会出现撕裂/重影。

用法：
    .venv\\Scripts\\python.exe q2_calib/undistort.py
    .venv\\Scripts\\python.exe q2_calib/undistort.py --img q2_calib/calib_images/xxx.jpg

输出：
    q2_figs/undistort_compare.png   三栏：原图 / 去畸变(裁边) / 去畸变(全视场)
    q2_figs/undistort_zoom.png      左上与右下 2.5 倍放大对比
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
FIGS = HERE / "q2_figs"
RES = HERE / "results"
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"


# ------------------------------------------------------------------ 读图
def imread_upright(path: Path) -> np.ndarray:
    """按 EXIF 转正读图。cv2.imread 不读 EXIF，手机竖拍会躺倒。"""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


# ------------------------------------------------------------------ 指标
def max_line_offset(pts: np.ndarray) -> float:
    """一组共线点偏离其最小二乘直线的最大距离（px）。"""
    p = pts.astype(np.float32).reshape(-1, 2)
    vx, vy, x0, y0 = cv2.fitLine(p, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    d = np.abs((p[:, 0] - x0) * vy - (p[:, 1] - y0) * vx)
    return float(d.max())


def straightness(pts: np.ndarray, pattern=(9, 6)) -> float:
    """棋盘所有行、所有列的直线度误差取最大值。"""
    cols, rows = pattern
    grid = pts.reshape(rows, cols, 2)
    devs = [max_line_offset(grid[r]) for r in range(rows)]
    devs += [max_line_offset(grid[:, c]) for c in range(cols)]
    return max(devs)


def radial_check(K, dist, image_size):
    """检查径向畸变映射在画面内是否单调，返回临界半径。

    r_d/r = 1 + k1 r² + k2 r⁴ + k3 r⁶
    导数  = 1 + 3k1 r² + 5k2 r⁴ + 7k3 r⁶
    若导数在 r < r_corner 处过零，映射折叠，去畸变会出伪影。
    """
    k1, k2, _, _, k3 = dist.ravel()[:5]
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    w, h = image_size
    # 归一化图像坐标: x=(u-cx)/fx, y=(v-cy)/fy，r=hypot(x,y)
    # 注意分母是单方向焦距，不是对角线 —— 用对角线会把 r 算小一半。
    r_corner = max(
        np.hypot((u - cx) / fx, (v - cy) / fy)
        for u, v in [(0, 0), (w, 0), (0, h), (w, h)]
    )
    rs = np.linspace(0, r_corner * 1.2, 4000)
    deriv = 1 + 3 * k1 * rs**2 + 5 * k2 * rs**4 + 7 * k3 * rs**6
    bad = np.where(deriv <= 0)[0]
    r_fold = float(rs[bad[0]]) if bad.size else None
    return r_corner, r_fold


# ------------------------------------------------------------------ 绘图
def caption(bgr: np.ndarray, text: str, band: int = 44, size: int = 25) -> Image.Image:
    """给一张图加顶部白底黑字标题条。"""
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    w, h = pil.size
    out = Image.new("RGB", (w, h + band), (255, 255, 255))
    out.paste(pil, (0, band))
    d = ImageDraw.Draw(out)
    f = ImageFont.truetype(FONT_PATH, size)
    bb = d.textbbox((0, 0), text, font=f)
    d.text(((w - (bb[2] - bb[0])) // 2, (band - (bb[3] - bb[1])) // 2 - 3),
           text, font=f, fill=(30, 30, 30))
    return out


def resize_h(img: np.ndarray, h: int) -> np.ndarray:
    r = h / img.shape[0]
    return cv2.resize(img, (int(img.shape[1] * r), h), interpolation=cv2.INTER_AREA)


def paste_row(imgs, gap=10, bg=(255, 255, 255)) -> Image.Image:
    h = max(i.size[1] for i in imgs)
    w = sum(i.size[0] for i in imgs) + gap * (len(imgs) - 1)
    out = Image.new("RGB", (w, h), bg)
    x = 0
    for i in imgs:
        out.paste(i, (x, 0))
        x += i.size[0] + gap
    return out


# ------------------------------------------------------------------ 主流程
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default=str(RES / "camera_calib.npz"))
    ap.add_argument("--img", default=None, help="要处理的图，缺省自动挑棋盘覆盖率最大的")
    ap.add_argument("--dir", default=str(HERE / "calib_images"))
    args = ap.parse_args()

    z = np.load(args.npz)
    K, dist = z["K"], z["dist"]
    rms = float(z["rms"])
    W, H = (int(v) for v in z["image_size"])
    pattern = tuple(int(v) for v in z["pattern"])

    print("=" * 62)
    print("当前标定")
    print("=" * 62)
    print(f"  图像尺寸 {W} x {H}　方格 {float(z['square_mm'])} mm　RMS {rms:.4f} px")
    print(f"  fx={K[0,0]:.2f}  fy={K[1,1]:.2f}  cx={K[0,2]:.2f}  cy={K[1,2]:.2f}")

    # ---- 挑图：优先用 --img，否则找角点外接框占比最大的 ----
    if args.img:
        img_path = Path(args.img)
    else:
        best, best_area = None, -1
        for p in sorted(Path(args.dir).glob("*")):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue
            g = cv2.cvtColor(imread_upright(p), cv2.COLOR_BGR2GRAY)
            ok, pts = cv2.findChessboardCorners(
                g, pattern,
                cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
            if not ok:
                continue
            area = cv2.contourArea(cv2.convexHull(pts)) / (g.shape[0] * g.shape[1])
            if area > best_area:
                best, best_area = p, area
        if best is None:
            raise SystemExit("没有可用标定图，先跑 check_images.py")
        img_path = best
        print(f"\n[选图] {img_path.name}（棋盘占画面 {best_area*100:.1f}%）")

    img = imread_upright(img_path)
    if (img.shape[1], img.shape[0]) != (W, H):
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)

    # ---- 去畸变两种策略 ----
    K0, roi0 = cv2.getOptimalNewCameraMatrix(K, dist, (W, H), 0)
    und0 = cv2.undistort(img, K, dist, None, K0)
    K1, _ = cv2.getOptimalNewCameraMatrix(K, dist, (W, H), 1)
    und1 = cv2.undistort(img, K, dist, None, K1)

    print("\n[去畸变视场代价]")
    print(f"  alpha=0（裁掉黑边）: fx {K[0,0]:.1f} → {K0[0,0]:.1f}"
          f"　有效视场保留 {100*K[0,0]/K0[0,0]:.1f}%")
    print(f"  alpha=1（保留全视场）: fx {K[0,0]:.1f} → {K1[0,0]:.1f}"
          f"　边缘会有黑角")

    # ---- 指标 a：直线度 ----
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, pts = cv2.findChessboardCorners(
        g, pattern, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if ok:
        pts = cv2.cornerSubPix(
            g, pts.astype(np.float32), (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)).reshape(-1, 2)
        pts_u = cv2.undistortPoints(pts.reshape(-1, 1, 2), K, dist, P=K).reshape(-1, 2)
        d_raw = straightness(pts, pattern)
        d_und = straightness(pts_u, pattern)
        print("\n[直线度检验] 棋盘格边缘本应是直线")
        print(f"  原图   角点偏离直线最大 {d_raw:.3f} px")
        print(f"  去畸变 角点偏离直线最大 {d_und:.3f} px"
              f"　（降幅 {100*(1-d_und/max(d_raw,1e-9)):.1f}%）")

    # ---- 指标 b：径向单调性 ----
    r_corner, r_fold = radial_check(K, dist, (W, H))
    print("\n[畸变模型单调性检查]")
    print(f"  画面角落归一化半径 r_corner = {r_corner:.4f}")
    if r_fold is None:
        print("  映射在画面内单调 ✅ 畸变模型自洽")
    else:
        flag = "❌ 画面内已折叠" if r_fold < r_corner else "⚠️ 画面外才折叠"
        print(f"  映射在 r = {r_fold:.4f} 处开始折叠　{flag}")
        if r_fold < r_corner:
            print("  → 高阶系数（k2/k3）在边缘过拟合，去畸变图四角可能出现撕裂或重影。")

    # ---- 输出图 ----
    FIGS.mkdir(parents=True, exist_ok=True)
    TH = 420
    row = paste_row([
        caption(resize_h(img, TH), "原图（有畸变）"),
        caption(resize_h(und0, TH), "去畸变 alpha=0（裁边）"),
        caption(resize_h(und1, TH), "去畸变 alpha=1（全视场）"),
    ])
    out1 = FIGS / "undistort_compare.png"
    row.save(out1)
    print(f"\n[已保存] {out1}")

    # 角落放大：左上与右下，原图对比去畸变
    zoom = paste_row([
        caption(resize_h(img[0:int(H*.32), 0:int(W*.32)], 360), "原图 左上角"),
        caption(resize_h(und0[0:int(H*.32), 0:int(W*.32)], 360), "去畸变 左上角"),
        caption(resize_h(img[int(H*.68):, int(W*.68):], 360), "原图 右下角"),
        caption(resize_h(und0[int(H*.68):, int(W*.68):], 360), "去畸变 右下角"),
    ])
    out2 = FIGS / "undistort_zoom.png"
    zoom.save(out2)
    print(f"[已保存] {out2}")
    print("\n提示：若 alpha=0 图四角有明显撕裂/拉伸，说明畸变系数边缘不可信，需补拍角落覆盖图。")


if __name__ == "__main__":
    main()
