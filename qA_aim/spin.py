# -*- coding: utf-8 -*-
"""小陀螺车体中心与角速度估计（发挥部分）

原理：
  小陀螺车绕竖直轴高速旋转，装甲板固定在车上，随车体绕「车体中心」做圆周运动。
  相机观测到的是装甲板位置在水平面 (x, z) 上绕一个圆心转圈。

  1. 同帧多条检测 → 最近邻关联，跟踪同一块装甲板
  2. yaw 角 unwrap 后差分 → 角速度 omega（rad/s）
  3. 车体中心 = 装甲板 (x,z) 轨迹在滑动窗口内拟合的圆心
     （车体本身缓慢平移，用短窗口拟合局部圆心）

自检②：小陀螺车体中心在空间中应近似不动（缓慢漂移）。
输出：pred_<视频名>.csv  =  t, cx, cy, cz, omega
"""
import csv
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).parent
FIG = HERE / "figures"
FPS = 150.0


def load(name):
    """读 detections，返回按帧组织、含 yaw 的记录列表 [(frame, x,y,z, yaw)]，逐帧取多条"""
    rows = []
    with open(HERE / f"detections_{name}.csv", encoding="utf-8") as f:
        rd = csv.reader(f)
        header = next(rd)
        for r in rd:
            fr = int(r[0])
            if not r[9]:
                continue
            x, y, z, yaw = map(float, r[9:13])
            rows.append((fr, x, y, z, yaw))
    return rows


def track_single(rows):
    """最近邻关联，跟踪一条装甲板轨迹（优先跟踪出现最连续的那条）"""
    from collections import defaultdict
    by_frame = defaultdict(list)
    for fr, x, y, z, yaw in rows:
        by_frame[fr].append((x, y, z, yaw))

    frames = sorted(by_frame)
    # 选第一条记录里，后续持续出现的目标：贪心取每帧距上一帧最近者
    traj = []
    prev = None
    for fr in frames:
        cands = by_frame[fr]
        if prev is None:
            # 起始：取 z 最小的（主装甲板通常在最近处？改用第一条）
            best = cands[0]
        else:
            # 最近邻：距离上一帧位置的 2D 距离（含 yaw 差）
            def cost(c):
                d = (c[0] - prev[0]) ** 2 + (c[2] - prev[2]) ** 2
                dy = abs(c[3] - prev[3])
                dy = min(dy, 2 * np.pi - dy)
                return d + (dy * 0.1) ** 2
            best = min(cands, key=cost)
        traj.append((fr, *best))
        prev = best
    return traj


def fit_center(x, z):
    """最小二乘拟合圆心：|p - c|^2 最小，2D 圆拟合"""
    A = np.c_[2 * x, 2 * z, np.ones_like(x)]
    b = x * x + z * z
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    return sol[0], sol[1]          # cx, cz


def estimate(name, win=45):
    rows = load(name)
    traj = track_single(rows)
    fr = np.array([t[0] for t in traj])
    x = np.array([t[1] for t in traj])
    y = np.array([t[2] for t in traj])
    z = np.array([t[3] for t in traj])
    yaw = np.array([t[4] for t in traj])

    # 角速度：unwrap yaw 后按时间梯度
    yaw_u = np.unwrap(yaw)
    t = fr / FPS
    # 用中值滤波平滑角速度（对跳帧鲁棒）
    omega_raw = np.gradient(yaw_u, t)
    omega = _median_filter(omega_raw, 11)

    # 车体中心：滑动窗口拟合圆心；残差过大的窗口（跟踪跳变/几何退化）丢弃
    n = len(x)
    cx = np.full(n, np.nan)
    cy = np.full(n, np.nan)
    cz = np.full(n, np.nan)
    half = win // 2
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        if hi - lo < 6:
            continue
        ex, ez = fit_center(x[lo:hi], z[lo:hi])
        r = np.hypot(x[lo:hi] - ex, z[lo:hi] - ez)
        if r.std() > 0.08 or r.mean() > 1.0:      # 圆拟合残差检查
            continue
        cx[i], cz[i] = ex, ez
        cy[i] = np.median(y[lo:hi])
    # 空洞用邻域中值填补
    for arr in (cx, cy, cz):
        good = ~np.isnan(arr)
        if good.any():
            arr[~good] = np.interp(t[~good], t[good], arr[good])

    # 写 CSV
    out = HERE / f"pred_{name}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "cx", "cy", "cz", "omega"])
        for i in range(n):
            if np.isnan(cx[i]):
                continue
            w.writerow([f"{t[i]:.6f}", f"{cx[i]:.6f}", f"{cy[i]:.6f}",
                        f"{cz[i]:.6f}", f"{omega[i]:.6f}"])
    print(f"{name}: 跟踪 {n} 点 → {out.name}")

    # 图：装甲板观测 vs 车体中心、角速度曲线
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for i, axname in enumerate("xyz"):
        obs = [x, y, z][i]
        cen = [cx, cy, cz][i]
        axes[i].plot(t, obs, ".", ms=2, alpha=0.4, label="装甲板观测")
        axes[i].plot(t, cen, "-", lw=1, label="车体中心估计")
        axes[i].set_ylabel(f"{axname} (m)")
        axes[i].legend(fontsize=8)
        axes[i].grid(alpha=0.3)
    axes[-1].set_xlabel("t (s)")
    fig.suptitle(f"{name}：装甲板观测 vs 车体中心")
    fig.tight_layout()
    fig.savefig(FIG / f"spin_center_{_ascii(name)}.png", dpi=150)

    fig2, ax2 = plt.subplots(figsize=(10, 3))
    ax2.plot(t, omega, lw=1)
    ax2.axhline(np.median(omega), color="r", ls="--", lw=1,
                label=f"中位数 {np.median(omega):.2f} rad/s")
    ax2.set_xlabel("t (s)")
    ax2.set_ylabel("omega (rad/s)")
    ax2.set_title(f"{name}：角速度估计（≈ {np.median(omega)*57.3:.0f} 度/s）")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)
    fig2.tight_layout()
    fig2.savefig(FIG / f"spin_omega_{_ascii(name)}.png", dpi=150)
    print(f"图已存 figures/spin_center_{_ascii(name)}.png, spin_omega_{_ascii(name)}.png")


def _median_filter(a, k):
    out = np.full_like(a, np.nan)
    half = k // 2
    for i in range(len(a)):
        lo, hi = max(0, i - half), min(len(a), i + half + 1)
        out[i] = np.median(a[lo:hi])
    return out


def _ascii(name):
    return {"中距离陀螺": "mid", "近距离陀螺": "near"}[name]


def main():
    for name in ["中距离陀螺", "近距离陀螺"]:
        estimate(name)


if __name__ == "__main__":
    main()
