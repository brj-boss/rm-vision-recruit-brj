# -*- coding: utf-8 -*-
"""题二 · 单目测距（solvePnP + 已知尺寸纸）

原理：目标纸尺寸已知（实测 230 × 285 mm），检测出它在照片里的四个角，
用标定得到的 (K, dist) 解 PnP，得到纸坐标系相对相机的平移 tvec。
把 A4 的四个角点以**纸中心**为原点建模，‖tvec‖ 就是相机光心到纸中心的距离。

与标定的尺度约定：measure 图会缩放到长边 1600，与 calib_images 一致，
因此 camera_calib.npz 里的内参可直接使用。

用法：
    .venv\\Scripts\\python.exe q2_calib/measure.py
    .venv\\Scripts\\python.exe q2_calib/measure.py --truth 0.52,1.02,1.53,2.01,2.98
    .venv\\Scripts\\python.exe q2_calib/measure.py --selftest

输出：
    终端对比表（解算距离 / 卷尺真值 / 误差）
    q2_figs/measure_check.png  每张图的角点标注与解算距离拼图
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
MEASURE_DIR = HERE / "measure_images"
FIGS = HERE / "q2_figs"
RES = HERE / "results"
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"

TARGET_LONG_EDGE = 1600          # 与标定图一致的尺度
# 目标纸实测尺寸（mm）。你的纸不是标准 A4，务必量准后改这里。
# 只要长宽比能区分横竖放即可（这里 285/230=1.239）。
PAPER_W, PAPER_H = 230.0, 285.0
ASPECT = PAPER_H / PAPER_W       # 1.239


def imread_upright(path: Path) -> np.ndarray:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def resize_long_edge(bgr: np.ndarray, long_edge: int) -> np.ndarray:
    h, w = bgr.shape[:2]
    s = long_edge / max(h, w)
    if abs(s - 1.0) < 1e-3:
        return bgr
    return cv2.resize(bgr, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """按 左上/右上/右下/左下 排序。"""
    p = pts.reshape(-1, 2).astype(np.float32)
    s = p.sum(1)
    d = p[:, 0] - p[:, 1]
    return np.array([p[np.argmin(s)], p[np.argmin(d)],
                     p[np.argmax(s)], p[np.argmax(d)]], np.float32)


def detect_a4(bgr: np.ndarray):
    """检测画面里的白纸，返回 4 角（已排序）或 None。

    过滤条件：四边形 + 面积 > 2% 画面 + 长宽比接近 1.239（容忍拍摄透视带来的偏差）。
    """
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE,
                          np.ones((9, 9), np.uint8))          # 补小洞
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_img = bgr.shape[0] * bgr.shape[1]
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:8]:
        if cv2.contourArea(c) < 0.02 * area_img:
            break
        ap = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(ap) != 4:
            continue
        pts = order_corners(ap)
        top = np.linalg.norm(pts[1] - pts[0])
        left = np.linalg.norm(pts[3] - pts[0])
        long_e, short_e = max(top, left), min(top, left)
        if short_e < 1e-6 or not (1.12 < long_e / short_e < 1.40):
            continue
        return pts
    return None


def solve_distance(pts: np.ndarray, K, dist) -> tuple[float, np.ndarray]:
    """四角 → PnP → 相机到纸中心的距离(mm)。"""
    top = np.linalg.norm(pts[1] - pts[0])
    left = np.linalg.norm(pts[3] - pts[0])
    if top > left:                                   # 横放：宽 285，高 230
        w, h = PAPER_H, PAPER_W
    else:                                            # 竖放：宽 230，高 285
        w, h = PAPER_W, PAPER_H
    objp = np.array([(-w/2, -h/2, 0), (w/2, -h/2, 0),
                     (w/2, h/2, 0), (-w/2, h/2, 0)], np.float32)
    ok, rvec, tvec = cv2.solvePnP(objp, pts.reshape(-1, 1, 2).astype(np.float32),
                                  K, dist, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        raise RuntimeError("solvePnP 失败")
    return float(np.linalg.norm(tvec)), tvec


def caption(bgr, text, band=40, size=24):
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


def selftest() -> None:
    """渲染一张已知距离的虚拟 A4，验证整条链路的解算精度。"""
    rng = np.random.default_rng(0)
    K = np.array([[620.0, 0, 400], [0, 618.0, 300], [0, 0, 1.0]])
    dist = np.array([-0.18, 0.12, 0.001, -0.002, 0.0])
    print("[自检] 合成 5 个距离（含 ±15° 姿态扰动），检验解算误差\n")
    print(f"{'真值mm':>9} {'解算mm':>9} {'误差mm':>8} {'误差%':>7}")
    worst = 0.0
    for d_true in (500.0, 1000.0, 1500.0, 2000.0, 3000.0):
        rvec = rng.normal(0, 0.12, 3)                     # ±7° 左右的姿态扰动
        tvec = np.array([rng.normal(0, 20), rng.normal(0, 20), d_true])
        objp = np.array([(-PAPER_W/2, -PAPER_H/2, 0), (PAPER_W/2, -PAPER_H/2, 0),
                         (PAPER_W/2, PAPER_H/2, 0), (-PAPER_W/2, PAPER_H/2, 0)], np.float32)
        imgp, _ = cv2.projectPoints(objp, rvec, tvec, K, dist)
        d_est, _ = solve_distance(order_corners(imgp.reshape(-1, 2)), K, dist)
        err = d_est - d_true
        worst = max(worst, abs(err) / d_true)
        print(f"{d_true:9.0f} {d_est:9.1f} {err:+8.1f} {100*err/d_true:+7.2f}")
    print(f"\n最大相对误差 {100*worst:.2f}% —— "
          + ("链路正确 ✓" if worst < 0.02 else "⚠ 超出 2%，检查 solve_distance"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default=str(RES / "camera_calib.npz"))
    ap.add_argument("--dir", default=str(MEASURE_DIR))
    ap.add_argument("--truth", default=None,
                    help="逗号分隔的卷尺真值(m)，按文件名排序与图一一对应，"
                         "如 --truth 0.52,1.02,1.53,2.01,2.98")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    z = np.load(args.npz)
    K, dist = z["K"], z["dist"]
    paths = sorted(p for p in Path(args.dir).iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    if not paths:
        print(f"[空] {args.dir} 里没有照片。")
        print("  先拍 5 组 A4 测距图（0.5/1.0/1.5/2.0/3.0 m，卷尺入镜），"
              "传进 q2_calib/measure_images/ 再跑。")
        return
    truths = None
    if args.truth:
        tv = [float(v) for v in args.truth.split(",")]
        if len(tv) != len(paths):
            print(f"[警告] 给了 {len(tv)} 个真值但有 {len(paths)} 张图，忽略真值")
        else:
            truths = tv

    print(f"{'文件':<34} {'解算m':>8}", end="")
    print(f" {'真值m':>7} {'误差mm':>8} {'误差%':>7}" if truths else "")
    print("-" * 78)
    tiles, records = [], []
    for i, p in enumerate(paths):
        bgr = resize_long_edge(imread_upright(p), TARGET_LONG_EDGE)
        pts = detect_a4(bgr)
        if pts is None:
            print(f"{p.name:<34} {'未检出 A4':>8}")
            tiles.append(caption(cv2.resize(bgr, (533, 400)), f"{p.name[:16]} 未检出"))
            continue
        d_mm, tvec = solve_distance(pts, K, dist)
        line = f"{p.name:<34} {d_mm/1000:8.3f}"
        if truths:
            err = d_mm - truths[i] * 1000
            line += f" {truths[i]:7.3f} {err:+8.1f} {100*err/(truths[i]*1000):+7.2f}"
        print(line)
        records.append((p.name, d_mm / 1000))
        vis = bgr.copy()
        cv2.polylines(vis, [pts.astype(np.int32)], True, (0, 200, 0), 4)
        for pt in pts:
            cv2.circle(vis, tuple(pt.astype(int)), 7, (0, 0, 255), -1)
        cv2.putText(vis, f"{d_mm/1000:.3f} m", (30, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 255), 5)
        tiles.append(caption(cv2.resize(vis, (533, 400)), p.name[:24]))

    FIGS.mkdir(parents=True, exist_ok=True)
    if tiles:
        cols = 3
        rows = [tiles[i:i+cols] for i in range(0, len(tiles), cols)]
        W = max(sum(t.size[0] for t in r) + 10 * (len(r) - 1) for r in rows)
        H = sum(max(t.size[1] for t in r) for r in rows) + 10 * (len(rows) - 1)
        canvas = Image.new("RGB", (W, H), (255, 255, 255))
        y = 0
        for r in rows:
            x = 0
            for t in r:
                canvas.paste(t, (x, y))
                x += t.size[0] + 10
            y += max(t.size[1] for t in r) + 10
        out = FIGS / "measure_check.png"
        canvas.save(out)
        print(f"\n[已保存] {out}")
    if not truths:
        print("\n提示：用卷尺量出每张的真实距离后，按上面文件顺序加 --truth 重跑，"
              "才能得到误差表。")


if __name__ == "__main__":
    main()
