# -*- coding: utf-8 -*-
"""装甲板识别（灯条检测 + 配对 + PnP）

核心思路：
  暗场环境下灯条是画面中唯一的高亮竖直亮条。
  1. 亮度阈值分割 → findContours 提取亮斑
  2. 按几何特征过滤出「灯条」（细长竖条、面积、长宽比）
  3. 灯条两两配对成装甲板（高度差小、夹角小、连线近水平、长度比合理）
  4. 有内参的视频用 solvePnP 解位姿；装甲板_蓝.mp4 无内参，位姿留空
"""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "armor"
FIG = HERE / "figures"

# 装甲板 3D 尺寸（mm），原点在装甲板几何中心
#   灯条长 55，两灯条中心距 135 → 灯条中心横坐标 ±67.5
LIGHT_LEN = 55.0
LIGHT_DIST = 135.0
HALF_D = LIGHT_DIST / 2
# 关键点顺序：左灯条上端 → 左灯条下端 → 右灯条下端 → 右灯条上端
OBJ_PTS = np.array([
    [-HALF_D,  LIGHT_LEN / 2, 0],
    [-HALF_D, -LIGHT_LEN / 2, 0],
    [ HALF_D, -LIGHT_LEN / 2, 0],
    [ HALF_D,  LIGHT_LEN / 2, 0],
], np.float32) / 1000.0  # m

VIDEOS = ["远距离平移", "中距离陀螺", "近距离陀螺", "装甲板_蓝"]


def load_camera():
    info = json.loads((DATA / "camera_info.json").read_text(encoding="utf-8"))
    K = np.array(info["camera_matrix"], np.float32)
    dist = np.array(info["distortion_coefficients"], np.float32)
    return K, dist


def find_lights(gray, v_min, area_min, ratio_min):
    """亮度阈值分割 + 灯条几何过滤，返回 [ (top(x,y), bottom(x,y), box), ... ]"""
    _, bw = cv2.threshold(gray, v_min, 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lights = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < area_min:
            continue
        rect = cv2.minAreaRect(c)          # ((cx,cy),(w,h),angle)
        (cx, cy), (w, h), ang = rect
        # minAreaRect 角度约定：ang ∈ [-90, 0)。ang 接近 -90 时长边沿 y（竖直），
        # 接近 0 时长边沿 x（水平）。灯条要求长边竖直。
        # 归一化：把 (w,h) 统一转成「w=短边, h=长边」
        if abs(ang) <= 45:              # 长边沿 x
            continue                     # 水平亮条不是灯条（窗帘漏光等）
        long_side, short_side = max(w, h), min(w, h)
        if long_side / short_side < ratio_min:      # 灯条细长
            continue
        box = cv2.boxPoints(rect)
        # 端点 = y 最大的两顶点均值 与 y 最小的两顶点均值
        vs = sorted(box.tolist(), key=lambda p: p[1])
        top = ((vs[0][0] + vs[1][0]) / 2, vs[0][1])
        bot = ((vs[2][0] + vs[3][0]) / 2, vs[3][1])
        lights.append((top, bot, box, area, ang))
    return lights


def match_lights(lights, max_ang=35, max_len_ratio=0.7, ratio_lo=1.5, ratio_hi=4.5):
    """灯条两两配对成装甲板。返回 [(左灯条, 右灯条), ...]

    真实装甲板中心距/灯条长 = 135/55 ≈ 2.45，透视下允许 [1.5, 4.5]。
    """
    pairs = []
    n = len(lights)
    for i in range(n):
        for j in range(i + 1, n):
            L, R = lights[i], lights[j]
            if L[0][0] > R[0][0]:
                L, R = R, L
            hL = L[1][1] - L[0][1]          # 灯条像素长（top.y < bot.y）
            hR = R[1][1] - R[0][1]
            if hL <= 1 or hR <= 1:
                continue
            if min(hL, hR) / max(hL, hR) < max_len_ratio:   # 长度差过大
                continue
            # 倾角一致性：同一块装甲板两灯条倾角接近（跨板配对倾角差大）
            if abs(L[4] - R[4]) > 12:
                continue
            # 顶端高度一致：跨板配对的两灯条顶端错位可达 ~0.7 倍灯条高，
            # 真配对通常 < 0.3；倾斜装甲板会抬高该项，取 0.5 折中
            if abs(L[0][1] - R[0][1]) > 0.5 * (hL + hR) / 2:
                continue
            # 连线角度：与水平线的夹角
            dx = R[0][0] - L[0][0]
            dy = (R[0][1] + R[1][1]) / 2 - (L[0][1] + L[1][1]) / 2
            if abs(dx) < 1:
                continue
            ang = abs(np.degrees(np.arctan2(dy, dx)))
            if ang > max_ang:               # 同一块装甲板两灯条连线近似水平
                continue
            dist = np.hypot(dx, dy)
            r = dist / max(hL, hR)
            if not (ratio_lo < r < ratio_hi):  # 中心距/灯条长 须接近真值 2.45
                continue
            pairs.append((L, R))
    return pairs


def armor_keypoints(L, R):
    """(左灯条, 右灯条) → 4 关键点（图像坐标，float）"""
    return np.array([L[0], L[1], R[1], R[0]], np.float32)


def solve_pose(kp, K, dist):
    ok, rvec, tvec = cv2.solvePnP(OBJ_PTS, kp.reshape(-1, 1, 2).astype(np.float32),
                                  K, dist, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        return None
    yaw = np.degrees(np.arctan2(tvec[0, 0], tvec[2, 0]))
    return tvec.ravel(), float(yaw)


def detect_frame(bgr, K, dist, params, want_pose):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lights = find_lights(gray, params["v_min"], params["area_min"], params["ratio_min"])
    out = []
    for L, R in match_lights(lights):
        kp = armor_keypoints(L, R)
        rec = {"kp": kp}
        if want_pose:
            pose = solve_pose(kp, K, dist)
            rec["pose"] = pose
        out.append(rec)
    return out, lights


def draw(img, dets, lights, yaw=None):
    for top, bot, box, area, ang in lights:
        cv2.polylines(img, [box.astype(np.int32)], True, (0, 255, 255), 1)
    for d in dets:
        kp = d["kp"].astype(np.int32)
        for i in range(4):
            cv2.circle(img, tuple(kp[i]), 4, (0, 0, 255), -1)
        cv2.polylines(img, [kp.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
        # 标关键点顺序
        for i, ch in enumerate(["1", "2", "3", "4"]):
            cv2.putText(img, ch, tuple(kp[i] + [6, -6]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        if "pose" in d and d["pose"]:
            (x, y, z), yw = d["pose"]
            cv2.putText(img, f"x={x:.2f} y={y:.2f} z={z:.2f} yaw={yw:.1f}",
                        tuple(d["kp"][0].astype(int) + [0, -12]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, choices=VIDEOS)
    ap.add_argument("--v-min", type=int, default=170)
    ap.add_argument("--area-min", type=int, default=6)
    ap.add_argument("--ratio-min", type=float, default=3.0)
    ap.add_argument("--max-frames", type=int, default=0, help="0=全部")
    ap.add_argument("--vis-every", type=int, default=0, help="每 N 帧存一帧可视化图")
    args = ap.parse_args()

    K, dist = load_camera()
    want_pose = args.video != "装甲板_蓝"
    params = dict(v_min=args.v_min, area_min=args.area_min, ratio_min=args.ratio_min)

    cap = cv2.VideoCapture(str(DATA / f"{args.video}.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS)
    out_csv = HERE / f"detections_{args.video}.csv"
    f = open(out_csv, "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    if want_pose:
        w.writerow(["frame", "lt_x", "lt_y", "lb_x", "lb_y",
                    "rb_x", "rb_y", "rt_x", "rt_y", "x", "y", "z", "yaw"])
    else:
        w.writerow(["frame", "lt_x", "lt_y", "lb_x", "lb_y",
                    "rb_x", "rb_y", "rt_x", "rt_y"])

    n_det = 0
    idx = 0
    while True:
        ok, bgr = cap.read()
        if not ok or (args.max_frames and idx >= args.max_frames):
            break
        dets, lights = detect_frame(bgr, K, dist, params, want_pose)
        for d in dets:
            kp = d["kp"]
            row = [idx] + kp.reshape(-1).astype(float).tolist()
            if want_pose:
                if d.get("pose"):
                    (x, y, z), yaw = d["pose"]
                    row += [x, y, z, yaw]
                else:
                    row += ["", "", "", ""]      # PnP 失败留空
            w.writerow(row)
            n_det += 1
        if args.vis_every and idx % args.vis_every == 0:
            vis = draw(bgr.copy(), dets, lights)
            cv2.imwrite(str(FIG / f"vis_{args.video}_{idx:05d}.jpg"), vis)
        idx += 1
    cap.release()
    f.close()
    print(f"{args.video}: {idx} 帧, {n_det} 条检测结果 → {out_csv.name}")


if __name__ == "__main__":
    main()
