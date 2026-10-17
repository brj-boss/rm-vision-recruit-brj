# -*- coding: utf-8 -*-
"""手机照片入库前处理：EXIF 转正 → 缩放 → 角点可检性批量检查。

为什么需要这个脚本
------------------
用笔记摄像头时，capture_calib.py 会**实时**检查角点，检不出就不让存。
手机拍没有这层保护：拍完才知道哪张废。而且手机照片还有两个额外麻烦：

1. **EXIF 方向**。竖着拍的照片，像素本身是横的，靠 EXIF 里一个 Orientation
   标记告诉看图软件转过来。cv2.imread **完全不读 EXIF**，所以竖拍的图在
   Python 里是躺倒的，角点照样能检出，但画出来的拼图全歪，报告也不好看。
2. **分辨率过大**。4000x3000 的照片每张 3~5 MB，20 张就上百 MB，仓库受不了。
   标定本身用不到这个分辨率，长边缩到 1600 完全够（角点亚像素精度不受影响）。

所以本脚本做三件事：转正、缩小、检查。输出的副本直接喂给 calibrate.py。

用法
----
    # 1) 把手机照片放进 q2_calib/phone_raw/（原始文件，不入库）
    # 2) 跑检查，同时在 calib_images/ 生成转正缩小后的副本
    python check_images.py

    python check_images.py --src 别的目录 --out-dir 别的输出 --max-side 2000
    python check_images.py --max-side 0      # 不缩放

输出
----
    calib_images/            转正+缩放后的图，calibrate.py 直接读这里
    q2_figs/corner_check.png 角点检查拼图，一眼看出哪张废了
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
BOARD_INNER = (9, 6)
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE / "phone_raw"),
                    help="手机原图目录（只读，不会被改动）")
    ap.add_argument("--out-dir", default=str(HERE / "calib_images"),
                    help="转正缩小后的副本输出目录")
    ap.add_argument("--max-side", type=int, default=1600,
                    help="长边上限，0 表示不缩放")
    ap.add_argument("--cols", type=int, default=BOARD_INNER[0])
    ap.add_argument("--rows", type=int, default=BOARD_INNER[1])
    ap.add_argument("--figs", default=str(HERE / "q2_figs"))
    return ap.parse_args()


def load_upright(path: Path) -> np.ndarray:
    """读图并按 EXIF 转正，返回 BGR。PIL 缺失时退回 cv2。"""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return cv2.imread(str(path))

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        arr = np.array(im)
    return arr[:, :, ::-1].copy()


def resize_max_side(img: np.ndarray, max_side: int) -> np.ndarray:
    if max_side <= 0:
        return img
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return img
    s = max_side / m
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def detect(gray: np.ndarray, pattern):
    """返回 (是否检出, 角点, 实际匹配到的 pattern)。

    手机上把棋盘转 90° 拍很常见，内角点行列会对调，所以两个方向都试。
    """
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    for pat in (pattern, (pattern[1], pattern[0])):
        ok, corners = cv2.findChessboardCorners(gray, pat, flags)
        if ok:
            return True, corners, pat
    return False, None, None


def make_montage(items, cols=5, tile=(320, 240)):
    """把每张图缩成小图拼在一起，OK 画绿角点，FAIL 打红标。"""
    tw, th = tile
    rows = (len(items) + cols - 1) // cols
    canvas = np.full((rows * (th + 26), cols * tw, 3), 245, np.uint8)

    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x, y = c * tw, r * (th + 26)
        thumb = cv2.resize(it["img"], (tw, th), interpolation=cv2.INTER_AREA)

        if it["ok"]:
            sx, sy = tw / it["img"].shape[1], th / it["img"].shape[0]
            pts = (it["corners"].reshape(-1, 2) * [sx, sy]).astype(np.float32)
            thumb = thumb.copy()
            cv2.drawChessboardCorners(thumb, it["pattern"], pts.reshape(-1, 1, 2), True)
            color = (0, 150, 0)
        else:
            color = (0, 0, 220)
            # 角落画个叉，缩略图上也能一眼认出来
            cv2.line(thumb, (10, 10), (60, 60), (0, 0, 220), 4)
            cv2.line(thumb, (60, 10), (10, 60), (0, 0, 220), 4)

        canvas[y:y + th, x:x + tw] = thumb
        label = f"{i + 1:02d} {'OK' if it['ok'] else 'FAIL'} {it['name'][:22]}"
        cv2.putText(canvas, label, (x + 4, y + th + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return canvas


def main() -> None:
    args = parse_args()
    src = Path(args.src)
    out_dir = Path(args.out_dir)
    figs = Path(args.figs)

    if not src.exists():
        print(f"源目录不存在: {src}")
        print(f"请把手机照片放到 {src} 下再跑。")
        return

    files = sorted(p for p in src.iterdir() if p.suffix.lower() in EXTS)
    if not files:
        print(f"{src} 里没有图片（支持 {' '.join(sorted(EXTS))}）")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    pattern = (args.cols, args.rows)
    items = []

    print(f"源目录 : {src}")
    print(f"输出   : {out_dir}   (长边上限 {args.max_side or '不缩放'})")
    print(f"棋盘   : 内角点 {args.cols} x {args.rows}")
    print()
    print(f"{'#':>3}  {'文件':<26} {'尺寸':>11}  {'清晰度':>8}  {'亮度':>5}  结果")
    print("-" * 78)

    for i, f in enumerate(files, 1):
        img = load_upright(f)
        if img is None:
            print(f"{i:>3}  {f.name[:26]:<26} {'读取失败':>11}")
            items.append({"name": f.name, "img": np.zeros((240, 320, 3), np.uint8),
                          "ok": False, "corners": None, "pattern": None})
            continue

        h, w = img.shape[:2]
        img = resize_max_side(img, args.max_side)
        h2, w2 = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        ok, corners, pat = detect(gray, pattern)

        # 竖拍时棋盘在画面里是"高大于宽"的。OpenCV 5 对 (9,6) 和 (6,9) 都会
        # 返回 True，光看返回值判断不出方向，但角点顺序会不一致 —— 而 objp 是
        # 按 (cols, rows) 铺的，顺序一乱标定就被污染。所以按几何形状判定：
        # 棋盘是 10x7 方格（长宽比 1.43），外接框高宽比明显大于 1 就是转过了。
        rot_note = ""
        if ok:
            pts = corners.reshape(-1, 2)
            bw = pts[:, 0].max() - pts[:, 0].min()
            bh = pts[:, 1].max() - pts[:, 1].min()
            if bw > 0 and bh / bw > 1.25:
                img_rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                gray_rot = cv2.cvtColor(img_rot, cv2.COLOR_BGR2GRAY)
                ok2, c2, pat2 = detect(gray_rot, pattern)
                if ok2:
                    img, gray, ok, corners, pat = img_rot, gray_rot, ok2, c2, pat2
                    h2, w2 = img.shape[:2]
                    rot_note = "  已转正 90°"
                else:
                    ok = False
                    rot_note = "  方向异常"

        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
        bright = gray.mean()

        note = ""
        if not ok:
            if sharp < 60:
                note = "偏糊"
            elif bright < 40:
                note = "偏暗"
            elif bright > 235:
                note = "过曝"

        tag = "OK" if ok else "FAIL"
        print(f"{i:>3}  {f.name[:26]:<26} {w2:>5}x{h2:<5}  {sharp:>8.1f}  {bright:>5.0f}  "
              f"{tag}{('  ' + note) if note else ''}{rot_note}")

        # 写副本给 calibrate.py 用
        cv2.imwrite(str(out_dir / (f.stem + ".jpg")), img,
                    [cv2.IMWRITE_JPEG_QUALITY, 95])

        items.append({"name": f.name, "img": img, "ok": ok,
                      "corners": corners, "pattern": pat})

    n_ok = sum(1 for it in items if it["ok"])
    n_all = len(items)

    print("-" * 78)
    print(f"检出 {n_ok}/{n_all} 张")
    if n_ok < n_all:
        bad = [it["name"] for it in items if not it["ok"]]
        print(f"未检出 {len(bad)} 张：")
        for b in bad:
            print(f"  - {b}")
        print()
        print("未检出的常见原因（按概率排序）：")
        print("  1. 棋盘没拍全 / 贴边被裁   -> 重拍，四周留白")
        print("  2. 屏幕摩尔纹               -> 换个角度、稍拉远、提高屏幕亮度")
        print("  3. 屏幕反光（灯管/窗户）    -> 关顶灯，换站位")
        print("  4. 运动模糊                 -> 稳住手，开专业模式提高快门")
        print("  5. 照片被压缩过             -> 用原图，别用缩略图")

    if n_ok < 8:
        print()
        print(f"只有 {n_ok} 张可用，标定至少要 15 张（原文要求 15~25），请补拍。")

    montage = make_montage(items)
    out_png = figs / "corner_check.png"
    cv2.imwrite(str(out_png), montage)
    print()
    print(f"检查拼图: {out_png}")
    print(f"可直接标定的图: {out_dir}")


if __name__ == "__main__":
    main()
