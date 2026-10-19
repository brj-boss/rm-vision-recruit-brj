# -*- coding: utf-8 -*-
"""平移目标卡尔曼滤波 + 0.25s 预测

输入：detections_远距离平移.csv（solvePnP 得到的相机系坐标）
模型：匀速运动（CV）卡尔曼滤波，状态 [x,y,z,vx,vy,vz]
输出：
  pred_远距离平移.csv          t, x, y, z（对 t+0.25s 的预测）
  figures/pred_compare.png     观测/滤波/预测 对比曲线
  figures/pred_error.png       预测值 vs 0.25s 后观测值 的误差统计
自检①：0.25s 前的预测值应与当时实际观测一致 → 误差表即为证明
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
FPS = 150.0
DT = 1.0 / FPS
LEAD = 0.25                    # 预测提前量 s


def load_detections(path):
    """读 CSV，每帧取一个检测（同帧多条时取第一条，检测端已保证唯一）"""
    per_frame = {}
    with open(path, encoding="utf-8") as f:
        rd = csv.reader(f)
        header = next(rd)
        for r in rd:
            fr = int(r[0])
            kp = list(map(float, r[1:9]))
            pose = [float(v) if v else np.nan for v in r[9:12]]   # x,y,z（不含 yaw）
            if fr not in per_frame and not np.isnan(pose[0]):
                per_frame[fr] = pose            # 只要有位姿的才算
    return per_frame


def make_kalman(dt=DT, q_pos=1e-3, q_vel=0.5, r_meas=1e-2):
    kf = cv2.KalmanFilter(6, 3)
    # 状态 [x,y,z,vx,vy,vz]
    F = np.eye(6, dtype=np.float32)
    F[0, 3] = F[1, 4] = F[2, 5] = dt
    kf.transitionMatrix = F
    kf.measurementMatrix = np.zeros((3, 6), np.float32)
    kf.measurementMatrix[0, 0] = kf.measurementMatrix[1, 1] = kf.measurementMatrix[2, 2] = 1
    q = np.eye(6, dtype=np.float32)
    q[:3, :3] *= q_pos
    q[3:, 3:] *= q_vel
    kf.processNoiseCov = q
    kf.measurementNoiseCov = np.eye(3, dtype=np.float32) * r_meas
    return kf


def predict_ahead(kf, t_ahead):
    """从当前状态外推 t_ahead 秒（不改变滤波器状态）"""
    F = np.eye(6, dtype=np.float32)
    F[0, 3] = F[1, 4] = F[2, 5] = t_ahead
    return (F @ kf.statePost.reshape(-1, 1)).ravel()[:3]


def main():
    per_frame = load_detections(HERE / "detections_远距离平移.csv")
    frames = sorted(per_frame)
    print(f"有位姿的帧: {len(frames)} / {frames[-1]+1}")

    kf = make_kalman()
    obs, filt, preds = [], [], []       # 每帧记录
    err_rows = []                       # (t, 预测, 0.25s后观测, 误差)
    pred_by_time = {}                   # t_pred -> 预测位置（供自检）

    # 用第一帧初始化
    z0 = np.array(per_frame[frames[0]], np.float32)
    kf.statePost = np.concatenate([z0, np.zeros(3)]).reshape(6, 1).astype(np.float32)
    kf.errorCovPost = np.eye(6, dtype=np.float32)

    GATE = 0.30                    # 观测门控（m）：偏离预测过远视为 PnP 离群
    prev = frames[0]
    n_gate = 0
    for fr in frames[1:]:
        # 时间推进（可能跳帧）
        while prev + 1 < fr:
            kf.predict()
            prev += 1
        kf.predict()
        prev = fr
        z = np.array(per_frame[fr], np.float32).reshape(3, 1)
        # 马氏门控：观测偏离预测太远则丢弃（防 PnP 离群污染滤波器）
        innov = z - kf.measurementMatrix @ kf.statePre
        if np.linalg.norm(innov) > GATE:
            n_gate += 1
            kf.statePost = kf.statePre.copy()      # 仅时间更新
            kf.errorCovPost = kf.errorCovPre.copy()
        else:
            kf.correct(z)
        t = fr / FPS
        obs.append([t, *per_frame[fr]])
        filt.append([t, *kf.statePost.ravel().tolist()])
        p = predict_ahead(kf, LEAD)
        preds.append([t, *p])
        pred_by_time[round(t + LEAD, 6)] = p

    obs = np.array(obs)
    filt = np.array(filt)
    preds = np.array(preds)

    # 自检①：预测(t) vs 观测(t+0.25)。150fps 下 0.25s=37.5 帧，观测时刻
    # 不与预测时刻重合，用相邻两帧观测线性插值对齐
    obs_t = obs[:, 0]
    d_list = []
    for t, *p in preds:
        t1 = t + LEAD
        if t1 < obs_t[0] or t1 > obs_t[-1]:
            continue
        o = np.array([np.interp(t1, obs_t, obs[:, 1 + i]) for i in range(3)])
        d_list.append([t1, *p, *o])
    err = np.array(d_list)

    # 写 CSV
    out = HERE / "pred_远距离平移.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "x", "y", "z"])
        for t, p in zip([r[0] for r in preds], [r[1:] for r in preds]):
            w.writerow([f"{t:.6f}", *(f"{v:.6f}" for v in p)])
    print("已写", out.name, f"（门控剔除 {n_gate} 帧离群观测）")

    # 统计：err 列 = [t, 预测x/y/z, 观测x/y/z]
    print("\n自检① 预测(t) vs 插值观测(t+0.25) 误差（{} 个配对）".format(len(err)))
    d = err[:, 4:7] - err[:, 1:4]
    for i, ax in enumerate("xyz"):
        e = d[:, i]
        print(f"  {ax}: mean={e.mean()*1000:+7.1f}mm  std={e.std():7.4f}m  "
              f"|max|={np.abs(e).max():7.4f}m")
    dist_err = np.linalg.norm(d, axis=1)
    print(f"  3D 距离误差: mean={dist_err.mean()*1000:.1f}mm  "
          f"median={np.median(dist_err)*1000:.1f}mm  p95={np.percentile(dist_err,95)*1000:.1f}mm")

    # 图 1：位置曲线
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for i, ax in enumerate("xyz"):
        axes[i].plot(obs[:, 0], obs[:, 1 + i], ".", ms=2, alpha=0.4, label="观测")
        axes[i].plot(filt[:, 0], filt[:, 1 + i], "-", lw=1, label="滤波")
        axes[i].plot(preds[:, 0], preds[:, 1 + i], "-", lw=1, label=f"预测 t+{LEAD}s")
        axes[i].set_ylabel(f"{ax} (m)")
        axes[i].legend(loc="upper right", fontsize=8)
        axes[i].grid(alpha=0.3)
    axes[-1].set_xlabel("t (s)")
    fig.suptitle("远距离平移：观测 / 滤波 / 预测")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "pred_compare.png", dpi=150)

    # 图 2：预测误差
    fig2, ax2 = plt.subplots(figsize=(10, 4))
    ax2.plot(err[:, 0], dist_err * 1000, ".", ms=2)
    ax2.set_xlabel("t (s)")
    ax2.set_ylabel("3D 误差 (mm)")
    ax2.set_title(f"预测值 vs {LEAD}s 后观测值（中位数 {np.median(dist_err)*1000:.1f} mm）")
    ax2.grid(alpha=0.3)
    fig2.tight_layout()
    fig2.savefig(HERE / "figures" / "pred_error.png", dpi=150)

    # 图 3：Q、R 参数对比（发挥部分）
    obs_t, obs_xyz = obs[:, 0], obs[:, 1:4]

    def run(qp, qv, r):
        kf = make_kalman(q_pos=qp, q_vel=qv, r_meas=r)
        kf.statePost = np.concatenate(
            [np.array(per_frame[frames[0]], np.float32), np.zeros(3)]).reshape(6, 1).astype(np.float32)
        kf.errorCovPost = np.eye(6, dtype=np.float32)
        prev, out = frames[0], []
        for fr in frames[1:]:
            while prev + 1 < fr:
                kf.predict(); prev += 1
            kf.predict(); prev = fr
            z = np.array(per_frame[fr], np.float32).reshape(3, 1)
            innov = z - kf.measurementMatrix @ kf.statePre
            if np.linalg.norm(innov) > GATE:
                kf.statePost = kf.statePre.copy()
                kf.errorCovPost = kf.errorCovPre.copy()
            else:
                kf.correct(z)
            out.append([fr / FPS, *predict_ahead(kf, LEAD)])
        return np.array(out)

    settings = [
        ("Q小(1e-4,1e-2) 平滑但滞后", 1e-4, 1e-2, 1e-2),
        ("Q大(1e-3,0.5) 跟随快（采用）", 1e-3, 0.5, 1e-2),
        ("R大(1.0) 过度平滑", 1e-3, 0.5, 1.0),
    ]
    fig3, ax3 = plt.subplots(figsize=(10, 4.5))
    for name, qp, qv, r in settings:
        pr = run(qp, qv, r)
        ts, d = [], []
        for t, *p in pr:
            t1 = t + LEAD
            if t1 < obs_t[0] or t1 > obs_t[-1]:
                continue
            o = np.array([np.interp(t1, obs_t, obs_xyz[:, i]) for i in range(3)])
            ts.append(t)
            d.append(np.linalg.norm(o - np.array(p)) * 1000)
        ax3.plot(ts, d, ".", ms=2, label=name)
    ax3.set_xlabel("t (s)")
    ax3.set_ylabel(f"预测误差 |Δ| (mm), t+{LEAD}s")
    ax3.set_title("Q、R 参数对预测误差的影响")
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.3)
    fig3.tight_layout()
    fig3.savefig(HERE / "figures" / "qr_compare.png", dpi=150)
    print("图已存 figures/pred_compare.png, figures/pred_error.png, figures/qr_compare.png")


if __name__ == "__main__":
    main()
