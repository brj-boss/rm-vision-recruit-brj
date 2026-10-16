# q1_env　开发环境与工程规范

## 本目录应包含

| 文件 / 目录 | 说明 |
|---|---|
| `README.md` | 本文件：环境说明与验证步骤 |
| `screenshots/` | 全部截图 |

### screenshots 建议清单

| 文件名 | 内容 |
|---|---|
| `01_python_version.png` | `python -V` 与 `pip -V`（在**自己终端**里跑，确认是 3.12 而非其它 Python） |
| `02_lib_versions.png` | `python -c "import numpy, cv2, matplotlib, yaml; ..."` 能打印出四个库的版本号 |
| `03_pip_freeze.png` | `pip freeze` 输出（与根目录 `requirements.txt` 对应） |
| `04_repo_tree.png` | 仓库目录树 |
| `05_git_log.png` | `git log --oneline`，体现考核期间的持续提交 |
| `06_ubuntu/` | 发挥部分：WSL2 / 虚拟机 / 双系统 Ubuntu 22.04 的 `ls -la`、`top`、`cat /proc/cpuinfo \| head` 截图 |

## 环境方案

- 解释器：**Python 3.12**
- 虚拟环境：仓库内 `.venv`（未入库）
- 依赖：见仓库根目录 `requirements.txt`
- 脚本：本目录不放业务代码，只放环境验证脚本（如有）

## 复现步骤

```bash
uv venv --python 3.12 --seed .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -c "import numpy, cv2, matplotlib, yaml; print(numpy.__version__, cv2.__version__, matplotlib.__version__, yaml.__version__)"
```

## 发挥部分：Ubuntu 22.04

待填：安装方式（WSL2 / 虚拟机 / 双系统）、版本号、执行的三条命令及输出截图位置。
