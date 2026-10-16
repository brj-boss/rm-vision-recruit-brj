# MountainForge 战队视觉组 2027 赛季招新考核 — 设计报告

## 0. 基本信息

| 项目 | 内容 |
|---|---|
| 姓名 | 待填 |
| 学校 / 专业 | 待填 |
| 考核时间 | 2026.10.16 – 2026.10.19 |
| 仓库地址 | 待填（建好 GitHub 仓库后补上） |
| 所选方向题 | **A 题　装甲板识别与运动预测** |
| 运行环境 | Python 3.12（`.venv`）+ NumPy / OpenCV / Matplotlib / PyYAML，详见 `requirements.txt` |

### 如何运行本仓库代码

```bash
# 1. 建环境（需要 uv 或 python 3.10+）
uv venv --python 3.12 --seed .venv
.venv\Scripts\activate

# 2. 装依赖
pip install -r requirements.txt

# 3. 放置原始素材
#    考核包中的 data/ 目录请放到本仓库根目录下（该目录已加入 .gitignore，未入库）

# 4. 运行（示例，按实际文件名调整）
python q2_calib/calibrate.py
python qA_aim/detect.py
```

> 说明：原始素材 `data/`（实拍视频、点云等）体积较大，且由考核包统一提供，故未纳入版本库。
> 代码中一律使用相对路径 `data/...`，把 `data/` 放回仓库根目录即可直接运行。

---

## 1. 完成情况一览

| 题目 | 基本要求 | 发挥部分 | 备注 |
|---|---|---|---|
| 题一　开发环境与工程规范 | 待填 | 待填 | |
| 题二　相机标定与单目测距 | 待填 | 待填 | |
| A 题　装甲板识别与运动预测 | 待填 | 待填 | |
| 附加题一　PyTorch + ONNX 分类网络 | — | 待填 | |
| 附加题二　ARM/x86、NPU/GPU 比较 | — | 待填 | |
| 附加题三　自瞄命中率论述 | — | 待填 | |
| 附加题四　开源项目评述 | — | 待填 | |

---

## 2. 题一　开发环境与工程规范

### 2.1 环境搭建

| 组件 | 版本 |
|---|---|
| Python | 待填 |
| numpy | 待填 |
| opencv-python | 待填 |
| matplotlib | 待填 |
| PyYAML | 待填 |
| Git | 待填 |
| 操作系统 | 待填 |

安装命令：

```bash
待填
```

验证方式（截图见 `q1_env/screenshots/`）：

```bash
python -c "import numpy, cv2, matplotlib, yaml; print('OK')"
```

### 2.2 仓库结构

```
rm-vision-recruit-brj/
├── README.md            本设计报告
├── ai_log.md            AI 使用记录
├── requirements.txt     依赖清单
├── q1_env/              题一：环境与工程规范
├── q2_calib/            题二：相机标定与单目测距
├── qA_aim/              A 题：装甲板识别与运动预测
└── extra/               附加题
```

### 2.3 发挥部分：Linux 环境与基本命令

待填（WSL2 / 虚拟机 / 双系统 三选一，附截图）

---

## 3. 题二　相机标定与单目测距

### 3.1 方案

待填：棋盘格制作方式、方格实测边长、采集方式、标定流程。

### 3.2 标定结果

- 图像尺寸：待填
- 内参矩阵 K：待填
- 畸变系数：待填
- 重投影误差：待填 px

### 3.3 去畸变前后对比

![去畸变对比](q2_calib/q2_figs/undistort_compare.png)

### 3.4 单目测距（PnP）

| 序号 | 实测距离 (m) | 计算距离 (m) | 误差 (m) | 相对误差 |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

### 3.5 发挥部分

- **角度影响**：待填（正对 / 斜 30° / 斜 60° 的误差对比）
- **误差曲线**：待填（图见 `q2_calib/q2_figs/`）
- **误差来源分析（≥3 项）**：待填
- **对比实验**：
  - ① 仅用 5 张标定图 → 待填
  - ② 全部正对拍摄 → 待填
  - ③ 方格边长输错（25 mm 输成 20 mm）→ 待填

### 3.6 问题回答

- [ ] ① 内参矩阵中各参数的物理含义是什么？fx 与 fy 为何接近？
- [ ] ② 重投影误差衡量的是什么？

---

## 4. A 题　装甲板识别与运动预测

### 4.1 整体流程

待填（可用流程图）：
```
相机图像 → 颜色/亮度阈值分割 → 灯条拟合 → 灯条配对 → 装甲板四边形
        → PnP 解算 (x, y, z, yaw) → 卡尔曼滤波 → 预测 t + 0.25 s 位置
```

### 4.2 装甲板识别

- 预处理：待填
- 灯条筛选判据：待填（面积、长宽比、角度、填充率……）
- 灯条配对判据：待填（长度比、中心距、倾角差……）
- 关键点顺序：左灯条上端 → 左灯条下端 → 右灯条下端 → 右灯条上端

识别结果视频：

| 视频 | 文件 | 备注 |
|---|---|---|
| 远距离平移 | `qA_aim/figures/det_远距离平移.mp4` | |
| 中距离陀螺 | `qA_aim/figures/det_中距离陀螺.mp4` | |
| 近距离陀螺 | `qA_aim/figures/det_近距离陀螺.mp4` | 发挥部分 |
| 装甲板_蓝 | `qA_aim/figures/det_装甲板_蓝.mp4` | 发挥部分，仅识别 |

### 4.3 位姿解算

- 使用的相机参数：`data/armor/camera_info.json`（8 mm 镜头，1440×1080）
- 装甲板参数：灯条长 55 mm，两灯条中心距 135 mm
- 坐标系：相机坐标系，x 右、y 下、z 前，单位 m
- 解算结果：`qA_aim/detections_远距离平移.csv` 等

位置随时间曲线与俯视轨迹：

![位置曲线](qA_aim/figures/position_curve.png)
![俯视轨迹](qA_aim/figures/trajectory_xz.png)

### 4.4 运动预测（卡尔曼滤波）

- 状态量选取：待填
- 状态转移 / 观测矩阵：待填
- Q、R 初值：待填

结果文件：`qA_aim/pred_远距离平移.csv`（格式 `t,x,y,z`，对 t + 0.25 s 的预测）

观测值 / 滤波值 / 预测值对比：

![预测对比](qA_aim/figures/predict_compare.png)

预测值与 0.25 s 后实际观测值的对比与误差统计：

| 轴 | RMSE (m) | MAE (m) | 最大误差 (m) |
|---|---|---|---|
| x | | | |
| y | | | |
| z | | | |

### 4.5 阈值调节工具

待填（截图 + 说明，如 `qA_aim/tune_threshold.py`）

### 4.6 发挥部分

- **复杂场景识别**：待填
- **小陀螺目标估计**：待填
  - 车体中心估计方法：待填
  - 旋转角速度：待填 rad/s
  - 结果文件：`qA_aim/pred_中距离陀螺.csv`、`pred_近距离陀螺.csv`（格式 `t,cx,cy,cz,omega`）
  - 图见 `qA_aim/figures/`
- **Q、R 参数分析**：待填

### 4.7 问题回答

- [ ] ① 识别流程中各步骤的设计依据是什么？
- [ ] ② 画面中有哪些物体可能被误识别为装甲板？你是如何排除的？
- [ ] ③ 相邻两块装甲板的灯条可能被错误配对，你是如何处理的？
- [ ] ④ 解算 PnP 时使用与不使用畸变系数，结果相差多少？在画面中心与边缘是否相同？
- [ ] ⑤ 关键点顺序错误会产生什么后果？
- [ ] ⑥ 你的观测数据中存在哪些噪声或异常？分别如何处理？
- [ ] ⑦ 普通卡尔曼滤波器为何不适用于小陀螺目标？测试台的旋转角速度约为多少？

---

## 5. 附加题

### 附加题一　装甲板数字分类网络（PyTorch → ONNX）

待填：网络结构、数据集、训练曲线、ONNX 导出、PyTorch 与 ONNX Runtime 的 CPU 推理速度对比。

| 框架 | 平均单张耗时 (ms) | 备注 |
|---|---|---|
| PyTorch | | |
| ONNX Runtime | | |

### 附加题二　ARM 与 x86 / NPU 与 GPU

待填

### 附加题三　影响自瞄命中率的最主要因素

待填

### 附加题四　开源项目评述

待填（项目名 / 链接 / 功能 / 技术方案 / 评价）

---

## 6. 问题记录

> 记录考核过程中实际遇到的问题及解决方法（真实、具体）。

| # | 遇到的问题 | 现象 / 报错 | 排查过程 | 解决方法 |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |

---

## 7. 学习总结

> 用本人语言总结考核期间所学内容（不要写成知识点罗列，写"我原本以为……实际发现……"这类真实认知变化）。

待填

---

## 参考资料

- 廖雪峰 Git 教程：https://liaoxuefeng.com/books/git/introduction/index.html
- OpenCV-Python 官方教程：https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html
- OpenCV 相机标定：https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
- OpenCV solvePnP：https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html
- How a Kalman filter works, in pictures：https://www.bzarg.com/p/how-a-kalman-filter-works-in-pictures/
- rm_vision（开源自瞄系统）：https://github.com/chenjunnn/rm_vision
