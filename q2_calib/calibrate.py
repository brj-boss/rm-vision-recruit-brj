"""
题二 · 相机标定脚本

用法：
    .venv\\Scripts\\python.exe q2_calib/calibrate.py
    .venv\\Scripts\\python.exe q2_calib/calibrate.py --dir q2_calib/calib_images
    .venv\\Scripts\\python.exe q2_calib/calibrate.py --square 17.9    # 实测方格边长(mm)

流程：
    findChessboardCorners 提角点 → cornerSubPix 亚像素精化 → calibrateCamera 求解
    → 用求得的参数把三维点反投影回图像，与实测角点求残差（这就是重投影误差）

输出：
    results/camera_calib.npz    给后续脚本读（undistort / measure）
    results/camera_calib.json   给人看
    q2_figs/corners_detected.png  角点检测结果拼图
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

BOARD_INNER = (9, 6)
# 本项目走屏幕方案，方格边长由显示器 PPI 决定，实测 25.0 mm。
# 若改用 A4 打印版，此处应为 18.0（且必须确认打印未被缩放）。
DEFAULT_SQUARE_MM = 25.0
HERE = Path(__file__).parent


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(HERE / "calib_images"), help="标定图目录")
    ap.add_argument("--cols", type=int, default=BOARD_INNER[0], help="内角点列数")
    ap.add_argument("--rows", type=int, default=BOARD_INNER[1], help="内角点行数")
    ap.add_argument("--square", type=float, default=DEFAULT_SQUARE_MM,
                    help="实测方格边长(mm)。本项目屏幕实测 25.0；A4 打印版为 18.0")
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--figs", default=str(HERE / "q2_figs"))
    return ap.parse_args()


def imread_upright(path: Path):
    """读图并按 EXIF 转正。

    手机竖拍的照片像素是横的，方向信息只在 EXIF 里，cv2.imread 不读 EXIF。
    虽然角点照样能检出（标定结果不受影响），但拼图和报告里的图会全躺倒。
    优先用 PIL 按 EXIF 转正，失败时退回 cv2。
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return cv2.imread(str(path))

    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            arr = np.array(im)
        return arr[:, :, ::-1].copy()
    except Exception:
        return cv2.imread(str(path))


def collect(img_dir: Path, pattern, square_mm):
    """遍历图片，返回 objpoints / imgpoints / 每张图的覆盖率 / 跳过的文件。"""
    # 世界坐标：棋盘平铺在 z=0 平面上，一格一个单位。
    # 这里用 mm 为单位，后续 solvePnP 解出的 tvec 就直接是 mm。
    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * square_mm

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4)
    files = sorted([p for p in img_dir.iterdir()
                    if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}])

    objpoints, imgpoints, records, failed = [], [], [], []
    for f in files:
        img = imread_upright(f)
        if img is None:
            failed.append((f.name, "读取失败"))
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(
            gray, pattern,
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
        )
        if not found:
            # 行列对调说明这张图是竖着拍的（手机常见）。强制旋转会让角点顺序
            # 与其他图不一致，进而污染 objp，所以这里只报错不擅自处理。
            rev = (pattern[1], pattern[0])
            ok_rev, _ = cv2.findChessboardCorners(
                gray, rev,
                cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
            )
            if ok_rev:
                failed.append((f.name, f"方向旋转 90°（内角点呈 {rev[0]}x{rev[1]}）"))
            else:
                failed.append((f.name, "未检出角点"))
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        objpoints.append(objp)
        imgpoints.append(corners)
        x, y, w, h = cv2.boundingRect(corners.astype(np.int32))
        cover = 100.0 * (w * h) / (img.shape[0] * img.shape[1])
        records.append({"file": f.name, "size": img.shape[:2][::-1],
                        "cover": cover, "corners": corners, "image": img})

    return objpoints, imgpoints, records, failed


def main():
    args = parse_args()
    img_dir = Path(args.dir)
    pattern = (args.cols, args.rows)

    if not img_dir.exists():
        print(f"[错误] 目录不存在：{img_dir}")
        print("  先跑 q2_calib/capture_calib.py 采集标定图。")
        return

    print(f"[读取] {img_dir}")
    print(f"[棋盘] 内角点 {pattern[0]}x{pattern[1]}，方格 {args.square} mm\n")

    objpoints, imgpoints, records, failed = collect(img_dir, pattern, args.square)

    if failed:
        print(f"[跳过 {len(failed)} 张]")
        for name, why in failed:
            print(f"   {name:24s} {why}")
        print()

    if len(objpoints) < 6:
        print(f"[错误] 仅 {len(objpoints)} 张可用于标定，至少需要 6 张，建议 15 张以上。")
        print("  重拍时注意：棋盘要完整入镜、光照均匀、避免反光和运动模糊。")
        return

    h, w = records[0]["size"][1], records[0]["size"][0]
    print(f"[开始标定] 有效图 {len(objpoints)} 张，分辨率 {w}x{h}")

    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, (w, h), None, None
    )

    # 逐张重投影误差：把世界坐标点用解出的内外参投回图像，与检出的亚像素角点比距离
    per_image = []
    for i, rec in enumerate(records):
        proj, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], K, dist)
        err = float(np.linalg.norm(imgpoints[i].reshape(-1, 2) - proj.reshape(-1, 2), axis=1).mean())
        per_image.append((rec["file"], err, rec["cover"]))

    print("\n  每张图的重投影误差：")
    for name, err, cover in per_image:
        flag = "  <-- 偏大，建议重拍" if err > 1.0 else ""
        print(f"    {name:24s} 覆盖率 {cover:5.1f}%   误差 {err:6.3f} px{flag}")

    dist_v = dist.ravel()
    print("\n" + "=" * 60)
    print("标定结果")
    print("=" * 60)
    print(f"图像尺寸        {w} x {h}")
    print(f"内参矩阵 K")
    print(f"  [[{K[0, 0]:10.3f}   0           {K[0, 2]:10.3f}]")
    print(f"   [  0           {K[1, 1]:10.3f}   {K[1, 2]:10.3f}]")
    print(f"   [  0             0             1        ]]")
    print(f"  fx = {K[0, 0]:.3f}   fy = {K[1, 1]:.3f}   cx = {K[0, 2]:.3f}   cy = {K[1, 2]:.3f}")
    print(f"  主点偏离画面中心 dx = {K[0, 2] - w / 2:+.2f} px, "
          f"dy = {K[1, 2] - h / 2:+.2f} px")
    print(f"  fx / fy = {K[0, 0] / K[1, 1]:.5f}   （实际像素是正方形，理想值 1.0）")
    print(f"\n畸变系数 (k1, k2, p1, p2, k3)")
    print(f"  {np.array2string(dist_v, precision=6, separator=', ')}")
    print(f"\n重投影误差 RMS = {rms:.4f} px")
    print(f"  判定：", end="")
    if rms < 0.5:
        print("很好（< 0.5 px）")
    elif rms < 1.0:
        print("可接受（0.5 ~ 1.0 px）")
    else:
        print("偏大（> 1.0 px），检查是否有模糊/反光/角点检出错误的图")

    # ---------------------------------------------------------------- 落盘
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    np.savez(out_dir / "camera_calib.npz", K=K, dist=dist, rms=rms,
             image_size=np.array([w, h]), square_mm=args.square,
             pattern=np.array(pattern))
    payload = {
        "image_size": [w, h],
        "pattern_inner": list(pattern),
        "square_mm": args.square,
        "rms_reprojection_px": round(float(rms), 6),
        "camera_matrix": [[round(float(v), 5) for v in row] for row in K],
        "dist_coeffs": [round(float(v), 6) for v in dist_v],
        "focal": {"fx": round(float(K[0, 0]), 4), "fy": round(float(K[1, 1]), 4)},
        "principal_point": {"cx": round(float(K[0, 2]), 4), "cy": round(float(K[1, 2]), 4)},
        "per_image_error_px": {n: round(e, 4) for n, e, _ in per_image},
        "num_images_used": len(records),
        "num_images_failed": len(failed),
    }
    (out_dir / "camera_calib.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[已保存] {out_dir / 'camera_calib.npz'}")
    print(f"[已保存] {out_dir / 'camera_calib.json'}")

    # ---------------------------------------------------------------- 角点可视化
    fig_dir = Path(args.figs)
    fig_dir.mkdir(parents=True, exist_ok=True)

    cols, rows = 5, (len(records) + 4) // 5
    tw, th = w // 3, h // 3
    canvas = np.full((rows * th, cols * tw, 3), 245, np.uint8)
    for i, rec in enumerate(records):
        tile = cv2.resize(rec["image"], (tw, th))
        sx, sy = tw / rec["image"].shape[1], th / rec["image"].shape[0]
        # drawChessboardCorners 要求 corners 为 float32 的 (N,1,2)
        pts = (rec["corners"] * np.array([sx, sy], np.float32)).astype(np.float32)
        cv2.drawChessboardCorners(tile, pattern, pts, True)
        cv2.putText(tile, f"{i + 1:02d} {per_image[i][1]:.2f}px",
                    (6, th - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        r, c = divmod(i, cols)
        canvas[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = tile

    cv2.putText(canvas, f"corner detection  |  {len(records)} images  |  RMS = {rms:.3f} px",
                (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2, cv2.LINE_AA)
    vis = fig_dir / "corners_detected.png"
    cv2.imwrite(str(vis), canvas)
    print(f"[已保存] {vis}")
    print("\n下一步：python q2_calib/undistort.py")


if __name__ == "__main__":
    main()
