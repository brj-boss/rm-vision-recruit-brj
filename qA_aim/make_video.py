# -*- coding: utf-8 -*-
"""A 题可视化：生成 4 段识别结果视频 + 俯视轨迹图

读 detections_*.csv，逐帧画装甲板四边形与关键点顺序，合成 mp4。
文件名用 ASCII，避免 Windows GBK 乱码。
"""
import csv
from pathlib import Path

import cv2
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "armor"
FIG = HERE / "figures"

# 视频名 → ASCII 输出名（远距离平移 / 中距离陀螺 / 近距离陀螺 / 装甲板_蓝）
NAME_MAP = {
    "远距离平移": "far_trans",
    "中距离陀螺": "mid_spin",
    "近距离陀螺": "near_spin",
    "装甲板_蓝": "blue",
}


def load_csv(name):
    """返回 {frame: [ [kp8, pose4], ... ]}"""
    per = {}
    with open(HERE / f"detections_{name}.csv", encoding="utf-8") as f:
        rd = csv.reader(f)
        header = next(rd)
        has_pose = "x" in header
        for r in rd:
            fr = int(r[0])
            kp = np.array(list(map(float, r[1:9]))).reshape(4, 2).astype(np.float32)
            pose = list(map(float, r[9:13])) if has_pose and r[9] else None
            per.setdefault(fr, []).append((kp, pose))
    return per


def draw_frame(bgr, dets):
    for kp, pose in dets:
        kp_i = kp.astype(np.int32)
        # 四边形
        cv2.polylines(bgr, [kp_i], True, (0, 255, 0), 2)
        # 关键点 + 顺序
        for i in range(4):
            cv2.circle(bgr, tuple(kp_i[i]), 5, (0, 0, 255), -1)
            cv2.putText(bgr, str(i + 1), tuple(kp_i[i] + [8, -8]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if pose is not None:
            x, y, z, yaw = pose
            cv2.putText(bgr, f"x={x:.2f} y={y:.2f} z={z:.2f}",
                        tuple(kp_i[0] + [0, -14]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
    return bgr


def make_video(name):
    per = load_csv(name)
    cap = cv2.VideoCapture(str(DATA / f"{name}.mp4"))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    out = str(FIG / f"detect_{NAME_MAP[name]}.mp4")
    # 高清、慢速码率；150fps 太吃体积，抽到 30fps 输出
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (w, h))
    idx = 0
    written = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if idx in per:
            bgr = draw_frame(bgr, per[idx])
        vw.write(bgr)
        written += 1
        idx += 1
    cap.release()
    vw.release()
    print(f"{name}: 视频 {written} 帧 → {Path(out).name}")


def plot_topview():
    """远距离平移：俯视 x-z 轨迹 + 三轴位置时间曲线"""
    per = load_csv("远距离平移")
    # 每帧取第一条
    t, x, y, z = [], [], [], []
    for fr in sorted(per):
        _, pose = per[fr][0]
        if pose is None:
            continue
        t.append(fr / 150.0)
        x.append(pose[0]); y.append(pose[1]); z.append(pose[2])
    t, x, y, z = map(np.array, (t, x, y, z))

    fig = plt.figure(figsize=(11, 5))
    # 左：俯视 x-z
    ax1 = fig.add_subplot(121)
    ax1.plot(z, x, "-", lw=1, color="tab:red")
    ax1.scatter(z[0], x[0], c="green", s=40, zorder=3, label="起点")
    ax1.scatter(z[-1], x[-1], c="blue", s=40, zorder=3, label="终点")
    ax1.set_xlabel("z (m)")
    ax1.set_ylabel("x (m)")
    ax1.set_title("俯视轨迹（x–z 平面）")
    ax1.invert_xaxis()          # 相机系 z 指向前，俯视时远处在上
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8)
    ax1.set_aspect("equal")
    # 右：三轴随时间
    ax2 = fig.add_subplot(122)
    for arr, lab in [(x, "x"), (y, "y"), (z, "z")]:
        ax2.plot(t, arr, lw=1, label=lab)
    ax2.set_xlabel("t (s)")
    ax2.set_ylabel("位置 (m)")
    ax2.set_title("装甲板位置随时间变化")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "far_trans_traj.png", dpi=150)
    print("俯视轨迹图已存 figures/far_trans_traj.png")


def main():
    for name in NAME_MAP:
        make_video(name)
    plot_topview()


if __name__ == "__main__":
    main()
