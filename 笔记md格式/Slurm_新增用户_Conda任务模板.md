# Slurm 多用户新增与 Conda 任务提交模板

> 本文档只整理本次对话中已经确定可用的配置与模板，不包含最开始上传文件中的内容。  
> 当前服务器 Slurm 使用方式：
>
> - 小任务 / 调试：`debug_shared` 队列，申请 `mps:25`    （1-99）
> - 正式单卡训练：`train_exclusive` 队列，申请 `gpu:rtx_pro_6000:1`
> - 双卡训练：`bigtrain` 队列，申请 `gpu:rtx_pro_6000:2`
> - 历史任务 / 资源统计：已启用 `sacct / slurmdbd / MariaDB`

---

## 1. 当前服务器 Slurm 使用规则

### 1.1 小任务 / 调试任务

适合：

- 代码调试
- 小 batch 测试
- 数据加载测试
- 短时间推理
- 检查环境是否可用

申请方式：

```bash
#SBATCH --partition=debug_shared
#SBATCH --gres=mps:25
```

### 1.2 正式单卡训练

适合：

- 正式模型训练
- 论文实验
- 消融实验
- YOLO / UNet / DINOv3 / Mask2Former 等单卡任务

申请方式：

```bash
#SBATCH --partition=train_exclusive
#SBATCH --gres=gpu:rtx_pro_6000:1
```

### 1.3 双卡训练

适合：

- PyTorch DDP 多卡训练
- 大模型训练
- 需要两张 GPU 同时参与的任务

申请方式：

```bash
#SBATCH --partition=bigtrain
#SBATCH --gres=gpu:rtx_pro_6000:2
```

---

## 2. 新增普通用户流程

下面以新增用户 `mcd` 为例。以后新增其他用户时，把 `mcd` 替换成对应用户名即可。

### 2.1 创建 Linux 用户

用 root 或有 sudo 权限的管理员账号执行：

```bash
sudo adduser mcd
```

按提示设置密码，其他信息可以直接回车。

检查用户是否创建成功：

```bash
id mcd
groups mcd
```

普通用户不应该有 sudo 权限。如果看到 `sudo` 组，执行：

```bash
sudo deluser mcd sudo
```

再次确认：

```bash
groups mcd
```

---

## 3. 创建用户专属目录

### 3.1 创建项目目录、日志目录、checkpoint 目录

```bash
sudo mkdir -p /data/users/mcd/project
sudo mkdir -p /data/logs/mcd
sudo mkdir -p /data/checkpoints/mcd
```

### 3.2 修改目录归属

```bash
sudo chown -R mcd:mcd /data/users/mcd
sudo chown -R mcd:mcd /data/logs/mcd
sudo chown -R mcd:mcd /data/checkpoints/mcd
```

### 3.3 设置权限，防止组员相互修改

```bash
sudo chmod 700 /data/users/mcd
sudo chmod 700 /data/logs/mcd
sudo chmod 700 /data/checkpoints/mcd
```

这样设置后：

```text
mcd 可以读写自己的项目、日志和 checkpoint 目录
其他普通用户不能进入 mcd 的目录
root 管理员仍然可以管理
```

---

## 4. 公共目录设置（已经设置过不用重复）

### 4.1 公共数据集目录只读

```bash
sudo mkdir -p /data/datasets
sudo chown -R root:root /data/datasets
sudo chmod -R 755 /data/datasets
```

含义：

```text
普通用户可以读取 /data/datasets
普通用户不能删除或修改公共数据集
```

### 4.2 临时共享目录

```bash
sudo mkdir -p /data/shared
sudo chmod 1777 /data/shared
```

`1777` 类似 `/tmp`，所有用户都可以写入，但普通用户不能随便删除别人的文件。

---

## 5. 新用户 Slurm 测试

切换到新用户：

```bash
su - mcd
```

进入项目目录：

```bash
cd /data/users/mcd/project
```

创建测试脚本：

```bash
cat > debug.sh <<'EOF'
#!/bin/bash
#SBATCH --job-name=debug_test
#SBATCH --partition=debug_shared
#SBATCH --gres=mps:25
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

echo "========== Slurm Info =========="
echo "Job ID: $SLURM_JOB_ID"
echo "Job Name: $SLURM_JOB_NAME"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "================================"

nvidia-smi

cd /data/users/$USER/project

echo "debug job test success"
EOF
```

添加执行权限：

```bash
chmod +x debug.sh
```

提交测试任务：

```bash
sbatch debug.sh
```

查看当前用户任务：

```bash
squeue -u mcd
```

如果任务很快结束，`squeue` 里看不到是正常的。

查看日志：

```bash
ls -lh /data/logs/mcd
```

假设任务号是 `12`，查看输出：

```bash
cat /data/logs/mcd/debug_test-12.out
cat /data/logs/mcd/debug_test-12.err
```

如果 `.out` 里能看到：

```text
CUDA_VISIBLE_DEVICES=0
nvidia-smi 显卡信息
debug job test success
```

说明新用户已经可以正常通过 Slurm 使用 GPU。

---

## 6. 注意：SBATCH 参数必须放在最前面

正确写法：

```bash
#!/bin/bash
#SBATCH --job-name=debug_test
#SBATCH --partition=debug_shared
#SBATCH --gres=mps:25
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail
```

不要这样写：

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=debug_test
#SBATCH --output=/data/logs/%u/%x-%j.out
```

因为某些 Slurm 版本中，`#SBATCH` 必须紧跟在 `#!/bin/bash` 后面。如果在 `#SBATCH` 前面写了普通命令，后面的 `#SBATCH --output` 可能不会被识别，日志就会默认写到当前目录的 `slurm-任务ID.out`。

---

## 7. 小任务 / 调试任务模板（已有虚拟环境或自己创建 Conda）

文件名建议：`debug_env.sh`

适合快速检查代码、环境、CUDA、数据路径是否正常。小任务走 `debug_shared`，使用 `mps:25`，不要在这个队列里跑正式大训练。

模板支持两种环境方式：

```text
方式 A：已有虚拟环境目录，使用 ENV_MODE="venv" + ENV_DIR="..."
方式 B：自己创建的 Conda 环境，使用 ENV_MODE="conda" + ENV_NAME="..."
```

复制模板后，优先只改顶部 `ENV_MODE`、`ENV_DIR`、`ENV_NAME`、`PROJECT_DIR`、`RUN_CMD`。

```bash
#!/bin/bash
#SBATCH --job-name=debug_test
#SBATCH --partition=debug_shared
#SBATCH --gres=mps:25
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# ====== 按项目修改这里 ======
# 必改：环境方式。已有虚拟环境目录用 venv；自己创建的 Conda 环境用 conda。
ENV_MODE="venv"

# ENV_MODE=venv 时必改：改成已有环境目录，目录下必须有 bin/activate。
ENV_DIR="/data/users/$USER/project/env/dinounet"

# ENV_MODE=conda 时必改：改成 conda env list 里能看到的环境名。
ENV_NAME="seg"

# 必改：改成自己的项目目录。
PROJECT_DIR="/data/users/$USER/project/your_project"

# 必改：改成调试时要执行的命令。
RUN_CMD="python -u debug.py"
# ============================

mkdir -p "/data/logs/$USER"

activate_env() {
    if [ "$ENV_MODE" = "venv" ]; then
        if [ ! -f "$ENV_DIR/bin/activate" ]; then
            echo "ERROR: venv activate not found: $ENV_DIR/bin/activate" >&2
            exit 1
        fi
        set +u
        source "$ENV_DIR/bin/activate"
        set -u
    elif [ "$ENV_MODE" = "conda" ]; then
        if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
            set +u
            source "$HOME/miniconda3/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME"
            set -u
        elif [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
            set +u
            source "/opt/miniconda3/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME"
            set -u
        else
            echo "ERROR: cannot find conda.sh" >&2
            exit 1
        fi
    else
        echo "ERROR: ENV_MODE must be venv or conda" >&2
        exit 1
    fi
}

echo "========== Slurm Info =========="
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Job Name: ${SLURM_JOB_NAME:-}"
echo "User: ${USER:-}"
echo "Node: ${SLURMD_NODENAME:-}"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "================================"

nvidia-smi || true

activate_env

cd "$PROJECT_DIR"

echo "========== Env Info =========="
which python
python -V
python -m pip -V || true
echo "ENV_MODE=$ENV_MODE"
echo "VIRTUAL_ENV=${VIRTUAL_ENV:-not_set}"
echo "CONDA_PREFIX=${CONDA_PREFIX:-not_set}"
echo "Conda env: ${CONDA_DEFAULT_ENV:-not_activated}"
echo "Project dir: $PROJECT_DIR"
echo "Run command: $RUN_CMD"
echo "================================"

echo "========== CUDA / PyTorch Check =========="
python - <<'PY'
try:
    import torch
    print("torch:", torch.__version__)
    print("torch cuda:", torch.version.cuda)
    print("cuda available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("device:", torch.cuda.get_device_name(0))
        print("capability:", torch.cuda.get_device_capability(0))
        print("arch list:", torch.cuda.get_arch_list())
except Exception as e:
    print("torch check skipped or failed:", repr(e))
PY
echo "=========================================="

eval "$RUN_CMD"
```

提交：

```bash
mkdir -p /data/logs/$USER
sbatch debug_env.sh
```

如果是 PyTorch 小任务，建议在 `debug.py` 最前面加入显存限制，避免调试任务占满整张卡：

```python
import torch
torch.cuda.set_per_process_memory_fraction(0.25, device=0)
```

---

## 8. 正式单卡训练模板（已有虚拟环境或自己创建 Conda）

文件名建议：`train_single_env.sh`

正式单卡训练走 `train_exclusive`，申请 1 张 `rtx_pro_6000`。这个模板按你当前真实训练脚本风格整理：保留 PyTorch/CUDA 检查、checkpoint、TensorBoard 和完整日志输出。

模板支持两种环境方式：

```text
方式 A：已有虚拟环境目录，使用 ENV_MODE="venv" + ENV_DIR="..."
方式 B：自己创建的 Conda 环境，使用 ENV_MODE="conda" + ENV_NAME="..."
```

```bash
#!/bin/bash
#SBATCH --job-name=dino-router_train1
#SBATCH --partition=train_exclusive
#SBATCH --gres=gpu:rtx_pro_6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=72:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# ====== 按项目修改这里 ======
# 必改：环境方式。已有虚拟环境目录用 venv；自己创建的 Conda 环境用 conda。
ENV_MODE="venv"

# ENV_MODE=venv 时必改：改成已有环境目录，目录下必须有 bin/activate。
ENV_DIR="/data/users/$USER/project/env/dinounet"

# ENV_MODE=conda 时必改：改成 conda env list 里能看到的环境名。
ENV_NAME="seg"

# 必改：改成自己的项目目录。
PROJECT_DIR="/data/users/$USER/project/dino_router"

# 必改：改成训练入口脚本。
TRAIN_SCRIPT="$PROJECT_DIR/train_query_moe_v2_advanced.py"

# 按需改：下面 python 命令里的训练参数，例如 epoch、image_size、seed、tensorboard 等。
# ============================

mkdir -p "/data/logs/$USER" "/data/checkpoints/$USER"

export CKPT_DIR="/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID"
export TB_DIR="$CKPT_DIR/tensorboard"
mkdir -p "$CKPT_DIR" "$TB_DIR"

activate_env() {
    if [ "$ENV_MODE" = "venv" ]; then
        if [ ! -f "$ENV_DIR/bin/activate" ]; then
            echo "ERROR: venv activate not found: $ENV_DIR/bin/activate" >&2
            exit 1
        fi
        set +u
        source "$ENV_DIR/bin/activate"
        set -u
    elif [ "$ENV_MODE" = "conda" ]; then
        if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
            set +u
            source "$HOME/miniconda3/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME"
            set -u
        elif [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
            set +u
            source "/opt/miniconda3/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME"
            set -u
        else
            echo "ERROR: cannot find conda.sh" >&2
            exit 1
        fi
    else
        echo "ERROR: ENV_MODE must be venv or conda" >&2
        exit 1
    fi
}

echo "========== Slurm Info =========="
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Job Name: ${SLURM_JOB_NAME:-}"
echo "User: ${USER:-}"
echo "Node: ${SLURMD_NODENAME:-}"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "Checkpoint dir: $CKPT_DIR"
echo "TensorBoard dir: $TB_DIR"
echo "================================"

nvidia-smi || true

activate_env

cd "$PROJECT_DIR"

echo "========== Env Info =========="
which python
python -V
python -m pip -V || true
echo "ENV_MODE=$ENV_MODE"
echo "VIRTUAL_ENV=${VIRTUAL_ENV:-not_set}"
echo "CONDA_PREFIX=${CONDA_PREFIX:-not_set}"
echo "Conda env: ${CONDA_DEFAULT_ENV:-not_activated}"
echo "Workdir: $(pwd)"
echo "Train script: $TRAIN_SCRIPT"
echo "================================"

echo "========== CUDA / PyTorch Check =========="
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("torch cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
    print("arch list:", torch.cuda.get_arch_list())
PY
echo "=========================================="

echo "========== Start Training =========="
python -u "$TRAIN_SCRIPT" \
  --mode three_stage \
  --image_size 256 \
  --strong_aug \
  --stage1_epochs 40 \
  --stage2_epochs 85 \
  --stage3_epochs 75 \
  --boundary_loss \
  --tensorboard \
  --no-lora_full_freeze \
  --tensorboard_log_dir "$TB_DIR" \
  --tensorboard_run_name "${SLURM_JOB_NAME}-${SLURM_JOB_ID}" \
  --seed 3407 \
  --patience 15
```

提交：

```bash
mkdir -p /data/logs/$USER /data/checkpoints/$USER
sbatch train_single_env.sh
```

查看日志：

```bash
tail -f /data/logs/$USER/dino-router_train1-任务ID.out
```

查看 TensorBoard 文件：

```bash
ls -lh /data/checkpoints/$USER/dino-router_train1/任务ID/tensorboard
```

---

## 9. 双卡训练模板（已有虚拟环境或自己创建 Conda）

文件名建议：`train_2gpu_env.sh`

双卡任务走 `bigtrain`，使用 `torchrun --nproc_per_node=2`。如果你的项目还没有 DDP 支持，不要直接用这个模板。

```bash
#!/bin/bash
#SBATCH --job-name=two_gpu_train
#SBATCH --partition=bigtrain
#SBATCH --gres=gpu:rtx_pro_6000:2
#SBATCH --cpus-per-task=16
#SBATCH --mem=192G
#SBATCH --time=72:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# ====== 按项目修改这里 ======
# 必改：环境方式。已有虚拟环境目录用 venv；自己创建的 Conda 环境用 conda。
ENV_MODE="venv"

# ENV_MODE=venv 时必改：改成已有环境目录，目录下必须有 bin/activate。
ENV_DIR="/data/users/$USER/project/env/dinounet"

# ENV_MODE=conda 时必改：改成 conda env list 里能看到的环境名。
ENV_NAME="seg"

# 必改：改成自己的项目目录。
PROJECT_DIR="/data/users/$USER/project/your_project"

# 必改：改成支持 DDP / torchrun 的训练入口脚本。
TRAIN_SCRIPT="$PROJECT_DIR/train_ddp.py"

# 按需改：最后一行 torchrun 后面的训练参数。
# ============================

mkdir -p "/data/logs/$USER" "/data/checkpoints/$USER"

export RUN_ROOT="/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID"
mkdir -p "$RUN_ROOT"

activate_env() {
    if [ "$ENV_MODE" = "venv" ]; then
        if [ ! -f "$ENV_DIR/bin/activate" ]; then
            echo "ERROR: venv activate not found: $ENV_DIR/bin/activate" >&2
            exit 1
        fi
        set +u
        source "$ENV_DIR/bin/activate"
        set -u
    elif [ "$ENV_MODE" = "conda" ]; then
        if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
            set +u
            source "$HOME/miniconda3/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME"
            set -u
        elif [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
            set +u
            source "/opt/miniconda3/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME"
            set -u
        else
            echo "ERROR: cannot find conda.sh" >&2
            exit 1
        fi
    else
        echo "ERROR: ENV_MODE must be venv or conda" >&2
        exit 1
    fi
}

echo "========== Slurm Info =========="
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Job Name: ${SLURM_JOB_NAME:-}"
echo "User: ${USER:-}"
echo "Node: ${SLURMD_NODENAME:-}"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "Run root: $RUN_ROOT"
echo "================================"

nvidia-smi || true

activate_env

cd "$PROJECT_DIR"

echo "========== Env Info =========="
which python
python -V
python -m pip -V || true
echo "ENV_MODE=$ENV_MODE"
echo "VIRTUAL_ENV=${VIRTUAL_ENV:-not_set}"
echo "CONDA_PREFIX=${CONDA_PREFIX:-not_set}"
echo "Conda env: ${CONDA_DEFAULT_ENV:-not_activated}"
echo "Workdir: $(pwd)"
echo "Train script: $TRAIN_SCRIPT"
echo "================================"

echo "========== CUDA / PyTorch Check =========="
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("torch cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("visible devices:", torch.cuda.device_count())
    for i in range(torch.cuda.device_count()):
        print(i, torch.cuda.get_device_name(i), torch.cuda.get_device_capability(i))
PY
echo "=========================================="

torchrun --standalone --nnodes=1 --nproc_per_node=2 "$TRAIN_SCRIPT" --output-dir "$RUN_ROOT"
```

提交：

```bash
mkdir -p /data/logs/$USER /data/checkpoints/$USER
sbatch train_2gpu_env.sh
```

---
## 10. Conda / venv 和项目 package 的常见情况

### 10.1 用户自己的 Conda

如果每个用户自己安装 Miniconda，默认路径通常是：

```bash
~/miniconda3
```

任务脚本里使用：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
```

### 10.2 系统级 Conda

如果 Conda 统一安装在：

```bash
/opt/miniconda3
```

任务脚本里使用：

```bash
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate seg
```

上面的模板已经同时兼容这两个路径，会优先使用用户自己的 `~/miniconda3`，找不到时再使用 `/opt/miniconda3`。

### 10.3 已有环境目录 bin/activate

如果环境已经放在项目目录里，例如：

```bash
/data/users/mcd/project/env/dinounet
```

并且里面有：

```bash
/data/users/mcd/project/env/dinounet/bin/activate
```

任务脚本里可以直接激活：

```bash
set +u
source /data/users/$USER/project/env/dinounet/bin/activate
set -u
```

这里临时 `set +u` 是为了避免某些 `activate` 脚本内部引用未定义变量，导致 `set -u` 下任务直接退出。激活完成后再恢复 `set -u`。

检查当前环境：

```bash
which python
python -V
python -m pip -V
echo "VIRTUAL_ENV=${VIRTUAL_ENV:-not_set}"
echo "CONDA_PREFIX=${CONDA_PREFIX:-not_set}"
```

### 10.4 项目源码直接运行

适合普通脚本项目：

```bash
cd /data/users/$USER/project/your_project
python train.py
```

### 10.5 项目作为本地 package 安装

如果项目里有 `pyproject.toml`、`setup.py` 或 `setup.cfg`，建议先在登录节点或交互终端里安装一次：

```bash
cd /data/users/$USER/project/your_project
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
python -m pip install -U pip
python -m pip install -e .
```

`-e .` 是 editable 安装，适合自己改代码、反复调试。安装后任务脚本可以直接运行：

```bash
python -m your_package.train --output-dir "$RUN_ROOT"
```

### 10.6 项目打成 wheel 包安装

适合把稳定版本发给别人跑，或者希望训练时使用固定版本：

```bash
cd /data/users/$USER/project/your_project
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
python -m pip install -U build
python -m build
ls -lh dist/
```

安装 wheel：

```bash
python -m pip install --force-reinstall dist/your_package-版本号-py3-none-any.whl
```

任务脚本里通常不建议每次都重新安装 wheel。更稳的做法是提交任务前安装好，然后脚本里只负责激活环境和运行模型。

### 10.7 离线 wheelhouse 安装依赖

如果服务器不能直接访问 pip 源，可以在能联网的机器上准备 wheelhouse：

```bash
mkdir -p wheelhouse
python -m pip download -r requirements.txt -d wheelhouse
```

上传到服务器后安装：

```bash
cd /data/users/$USER/project/your_project
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
python -m pip install --no-index --find-links wheelhouse -r requirements.txt
python -m pip install --no-index --find-links wheelhouse -e .
```

如果有自己打好的 wheel，也可以放进 `wheelhouse` 后安装：

```bash
python -m pip install --no-index --find-links wheelhouse your_package
```

### 10.8 conda-pack 打包好的环境

如果环境已经在另一台机器上做好，可以用 `conda-pack` 打包迁移。原机器执行：

```bash
conda activate seg
conda install -c conda-forge conda-pack
conda pack -n seg -o seg.tar.gz
```

上传到服务器后解压：

```bash
mkdir -p /data/users/$USER/envs/seg
cd /data/users/$USER/envs/seg
tar -xzf /data/users/$USER/packages/seg.tar.gz
./bin/conda-unpack
```

使用 conda-pack 环境时，任务脚本里不需要 `conda activate`，可以直接指定 Python：

```bash
PYTHON=/data/users/$USER/envs/seg/bin/python
$PYTHON train.py --output-dir "$RUN_ROOT"
```

---

## 11. 如果 conda activate 失败

Slurm 是非交互环境，不建议只写：

```bash
conda activate seg
```

更稳的写法是：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
```

检查用户是否有自己的 Conda：

```bash
ls ~/miniconda3/etc/profile.d/conda.sh
```

检查系统级 Conda：

```bash
ls /opt/miniconda3/etc/profile.d/conda.sh
```

检查环境是否存在：

```bash
conda env list
```

如果任务脚本里找不到包，先在登录终端里确认：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
which python
python -V
python -m pip list | grep 包名
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

---
## 12. 正常训练流程

### 12.1 登录服务器

```bash
ssh mcd@服务器IP
```

或者通过 VS Code Remote-SSH 登录。

### 12.2 进入自己的项目目录

```bash
cd /data/users/$USER/project
```

### 12.3 准备代码和数据

建议项目代码放在：

```bash
/data/users/$USER/project
```

公共数据集读取路径一般放在：

```bash
/data/datasets
```

不要把代码或训练输出写到别人的目录。

### 12.4 选择合适的模板

小任务调试：

```bash
sbatch debug_conda.sh
```

正式单卡训练：

```bash
sbatch train_single_conda.sh
```

双卡训练：

```bash
sbatch train_2gpu_conda.sh
```

### 12.5 查看任务

```bash
squeue -u $USER
```

### 12.6 查看日志

```bash
ls -lh /data/logs/$USER
tail -f /data/logs/$USER/任务名-任务ID.out
```

### 12.7 查看 checkpoint

```bash
ls -lh /data/checkpoints/$USER
```

---

## 13. 查看算力和 GPU 状态

### 13.1 查看 GPU 实时状态

```bash
nvidia-smi
```

实时刷新：

```bash
watch -n 1 nvidia-smi
```

### 13.2 查看 GPU 设备

```bash
nvidia-smi -L
```

### 13.3 查看某个进程属于谁

先用 `nvidia-smi` 找到 PID，然后：

```bash
ps -fp 进程ID
```

例如：

```bash
ps -fp 12345
```

### 13.4 查看 CPU 和内存

```bash
htop
```

或者：

```bash
top
free -h
lscpu
```

### 13.5 查看磁盘空间

```bash
df -h
du -sh /data/users/*
du -sh /data/checkpoints/*
```

---

## 14. 查看 Slurm 队列和任务

### 14.1 查看所有队列

```bash
sinfo
```

### 14.2 查看所有任务

```bash
squeue
```

### 14.3 查看自己的任务

```bash
squeue -u $USER
```

### 14.4 查看某个用户的任务

```bash
squeue -u mcd
```

### 14.5 查看任务详情

```bash
scontrol show job 任务ID
```

例如：

```bash
scontrol show job 12
```

### 14.6 取消任务

```bash
scancel 任务ID
```

例如：

```bash
scancel 12
```

### 14.7 查看节点状态

```bash
scontrol show node user
```

重点看：

```text
State=IDLE / ALLOCATED / MIXED / DRAIN
Gres=gpu:rtx_pro_6000:2,mps:rtx_pro_6000:200
CPUTot=128
RealMemory=250000
```

---

## 15. 查看历史任务和资源记录（sacct）

当前服务器已经启用 Slurm accounting：

```text
sacct / slurmdbd / MariaDB 已可用
AccountingStorageType=accounting_storage/slurmdbd
JobAcctGatherType=jobacct_gather/linux
```

`squeue` 只能看正在排队或正在运行的任务；任务结束后要用 `sacct` 查历史记录。

### 15.1 查看今天的历史任务

```bash
sacct -S today
```

更推荐使用固定字段：

```bash
sacct -X -S today -o JobID,JobName,User,Partition,State,Elapsed,AllocCPUS,ReqMem
```

### 15.2 查看自己的历史任务

```bash
sacct -u $USER -S today -o JobID,JobName,Partition,State,Elapsed,AllocCPUS,ReqMem
```

查看最近 7 天：

```bash
sacct -u $USER -S now-7days -o JobID,JobName,Partition,State,Elapsed,AllocCPUS,ReqMem
```

### 15.3 查看某个任务详情

```bash
sacct -j 任务ID -o JobID,JobName,User,Partition,State,ExitCode,Elapsed,AllocCPUS,ReqMem,MaxRSS,Start,End
```

例如：

```bash
sacct -j 24 -o JobID,JobName,User,Partition,State,ExitCode,Elapsed,AllocCPUS,ReqMem,MaxRSS,Start,End
```

字段含义：

| 字段              | 含义                                       |
| --------------- | ---------------------------------------- |
| `State`         | 任务状态，例如 `COMPLETED`、`FAILED`、`CANCELLED` |
| `ExitCode`      | 程序退出码，`0:0` 通常表示正常结束                     |
| `Elapsed`       | 实际运行时间                                   |
| `AllocCPUS`     | Slurm 分配的 CPU 数                          |
| `ReqMem`        | 提交任务时申请的内存                               |
| `MaxRSS`        | 任务记录到的最大内存使用量，部分任务可能为空                   |
| `Start` / `End` | 任务开始和结束时间                                |

### 15.4 查看某个用户的任务历史

管理员查看某个用户：

```bash
sacct -u mcd -S today -o JobID,JobName,User,Partition,State,Elapsed,AllocCPUS,ReqMem
```

查看所有用户今天的记录：

```bash
sacct -a -X -S today -o JobID,JobName,User,Partition,State,Elapsed,AllocCPUS,ReqMem
```

### 15.5 只看失败任务

```bash
sacct -a -X -S today --state=FAILED,CANCELLED,TIMEOUT,OUT_OF_MEMORY -o JobID,JobName,User,Partition,State,ExitCode,Elapsed
```

如果任务失败，先看 `sacct` 的 `State` 和 `ExitCode`，再看对应 `.err` 日志：

```bash
cat /data/logs/用户名/任务名-任务ID.err
```

### 15.6 sacct 和 squeue 的区别

| 命令                       | 用途                                      |
| ------------------------ | --------------------------------------- |
| `squeue`                 | 查看正在排队、正在运行的任务                          |
| `sacct`                  | 查看已经记录到 accounting 的历史任务，包括已完成、失败、取消的任务 |
| `scontrol show job 任务ID` | 查看当前仍在 Slurm 控制器状态里的任务详情                |

---

## 16. 常见任务状态含义

| 状态   | 含义                |
| ---- | ----------------- |
| `R`  | Running，正在运行      |
| `PD` | Pending，正在等待资源    |
| `CG` | Completing，任务正在结束 |
| `CD` | Completed，任务已完成   |
| `F`  | Failed，任务失败       |
| `CA` | Cancelled，任务被取消   |

如果任务一直 `PD`，查看原因：

```bash
squeue
scontrol show job 任务ID
```

常见原因：

| 原因 | 含义 |
|---|---|
| `Resources` | GPU、CPU 或内存资源暂时不够 |
| `Priority` | 优先级不够，正在排队 |
| `PartitionTimeLimit` | 申请时间超过队列限制 |
| `ReqNodeNotAvail` | 节点不可用 |

---

## 17. 日志查看命令

### 17.1 查看日志目录

```bash
ls -lh /data/logs/$USER
```

### 17.2 实时查看训练日志

```bash
tail -f /data/logs/$USER/任务名-任务ID.out
```

例如：

```bash
tail -f /data/logs/mcd/single_train-20.out
```

### 17.3 查看错误日志

```bash
cat /data/logs/$USER/任务名-任务ID.err
```

如果 `.err` 是空的，通常说明没有标准错误输出。

---

## 18. 管理员常用命令

### 18.1 查看 Slurm 服务

```bash
systemctl status slurmctld --no-pager
systemctl status slurmd --no-pager
systemctl status slurmdbd --no-pager
systemctl status mariadb --no-pager
systemctl status munge --no-pager
```

### 18.2 重启 Slurm 服务

```bash
sudo systemctl restart mariadb
sudo systemctl restart slurmdbd
sudo systemctl restart slurmctld
sudo systemctl restart slurmd
```

一般不要随便重启 `munge`。如果确实需要重启 `munge`，建议按下面顺序：

```bash
sudo systemctl restart munge
sudo systemctl restart slurmdbd
sudo systemctl restart slurmctld
sudo systemctl restart slurmd
```

### 18.3 查看 Slurm 日志

```bash
sudo journalctl -u slurmctld -n 100 --no-pager
sudo journalctl -u slurmd -n 100 --no-pager
sudo journalctl -u slurmdbd -n 100 --no-pager
sudo tail -n 100 /var/log/slurm/slurmdbd.log
```

### 18.4 查看 accounting 是否正常

```bash
sacctmgr -n show cluster format=Cluster,ControlHost,ControlPort,RPC
sacct -X -S today -o JobID,JobName,User,Partition,State,Elapsed,AllocCPUS,ReqMem
```

当前配置文件位置：

```text
/etc/slurm/slurm.conf
/etc/slurm/slurmdbd.conf
/etc/mysql/mariadb.conf.d/99-slurm-accounting.cnf
```

如果 `sacct` 提示 accounting disabled，重点检查：

```bash
scontrol show config | grep -E 'AccountingStorage|JobAcctGather'
systemctl status slurmdbd --no-pager
systemctl status mariadb --no-pager
```

### 18.5 恢复异常节点

如果节点状态是 `DOWN` 或 `DRAIN`，可以先查看原因：

```bash
scontrol show node user
```

尝试恢复：

```bash
sudo scontrol update NodeName=user State=RESUME
```

### 18.6 查看是否有人绕过 Slurm 占用 GPU

```bash
nvidia-smi
```

找到 PID 后：

```bash
ps -fp 进程ID
```

再看该用户有没有 Slurm 任务：

```bash
squeue -u 用户名
```

如果 `nvidia-smi` 里有 GPU 进程，但 `squeue -u 用户名` 没有任务，通常说明该用户可能绕过 Slurm 直接运行了训练。

---

## 19. 给组员的最简使用规则

可以直接发给组员：

```text
1. 每个人只能使用自己的 Linux 账号。
2. 项目代码放在 /data/users/自己的用户名/project。
3. 公共数据集从 /data/datasets 读取，不要修改公共数据集。
4. 小任务、调试、推理走 debug_shared，使用 --gres=mps:25。
5. 正式单卡训练走 train_exclusive，使用 --gres=gpu:rtx_pro_6000:1。
6. 双卡训练走 bigtrain，使用 --gres=gpu:rtx_pro_6000:2。
7. 长任务必须使用 sbatch 提交，不要直接在终端运行 python train.py。
8. 日志保存在 /data/logs/自己的用户名。
9. 模型权重保存在 /data/checkpoints/自己的用户名。
10. 不要修改别人的 /data/users/用户名 目录。
11. 任务结束后用 `sacct` 查看历史任务和运行状态。
```

---

## 20. 新增用户快速命令模板

以后新增用户时，可以直接使用下面这一段。把 `NEWUSER` 改成真实用户名即可。

```bash
NEWUSER=user2

sudo adduser $NEWUSER

sudo mkdir -p /data/users/$NEWUSER/project
sudo mkdir -p /data/logs/$NEWUSER
sudo mkdir -p /data/checkpoints/$NEWUSER

sudo chown -R $NEWUSER:$NEWUSER /data/users/$NEWUSER
sudo chown -R $NEWUSER:$NEWUSER /data/logs/$NEWUSER
sudo chown -R $NEWUSER:$NEWUSER /data/checkpoints/$NEWUSER

sudo chmod 700 /data/users/$NEWUSER
sudo chmod 700 /data/logs/$NEWUSER
sudo chmod 700 /data/checkpoints/$NEWUSER

groups $NEWUSER
ls -ld /data/users/$NEWUSER /data/logs/$NEWUSER /data/checkpoints/$NEWUSER
```

如果发现用户在 sudo 组：

```bash
sudo deluser $NEWUSER sudo
```

---

## 21. 从创建环境到提交模型的通用流程

下面是一套新项目从零开始跑模型的通用流程。假设用户名是 `mcd`，项目名是 `your_project`，Conda 环境名是 `seg`。

### 21.1 登录服务器并准备目录

```bash
ssh mcd@服务器IP

mkdir -p /data/users/$USER/project
mkdir -p /data/logs/$USER
mkdir -p /data/checkpoints/$USER
mkdir -p /data/users/$USER/packages
```

### 21.2 上传或拉取项目

如果用 Git：

```bash
cd /data/users/$USER/project
git clone 项目地址 your_project
cd your_project
```

如果是压缩包上传：

```bash
cd /data/users/$USER/project
tar -xzf your_project.tar.gz
cd your_project
```

### 21.3 创建 Conda 环境

如果项目有 `environment.yml`：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda env create -f environment.yml
conda activate seg
```

如果项目只有 `requirements.txt`：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda create -n seg python=3.10 -y
conda activate seg
python -m pip install -U pip
python -m pip install -r requirements.txt
```

如果需要 PyTorch，按项目要求安装对应 CUDA 版本。安装后先测试：

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

### 21.4 安装自己的项目 package

如果项目可以作为 package 安装，优先使用 editable 模式：

```bash
cd /data/users/$USER/project/your_project
python -m pip install -e .
```

如果已经打成 wheel：

```bash
python -m pip install --force-reinstall /data/users/$USER/packages/your_package-版本号-py3-none-any.whl
```

如果是离线依赖包：

```bash
python -m pip install --no-index --find-links /data/users/$USER/packages/wheelhouse -r requirements.txt
python -m pip install --no-index --find-links /data/users/$USER/packages/wheelhouse -e .
```

### 21.5 先用 debug 队列试跑

先创建或复制 `debug_conda.sh`，确认里面这两个变量正确：

```bash
ENV_NAME="seg"
PROJECT_DIR="/data/users/$USER/project/your_project"
```

提交小任务：

```bash
sbatch debug_conda.sh
squeue -u $USER
```

任务结束后查看：

```bash
sacct -u $USER -S today -o JobID,JobName,Partition,State,ExitCode,Elapsed
ls -lh /data/logs/$USER
cat /data/logs/$USER/debug_test-任务ID.out
cat /data/logs/$USER/debug_test-任务ID.err
```

### 21.6 正式提交训练

单卡训练：

```bash
sbatch train_single_conda.sh
```

双卡训练：

```bash
sbatch train_2gpu_conda.sh
```

查看运行中任务：

```bash
squeue -u $USER
```

查看训练日志：

```bash
tail -f /data/logs/$USER/任务名-任务ID.out
```

查看历史记录：

```bash
sacct -j 任务ID -o JobID,JobName,User,Partition,State,ExitCode,Elapsed,AllocCPUS,ReqMem,MaxRSS,Start,End
```

查看输出模型：

```bash
ls -lh /data/checkpoints/$USER/任务名/任务ID
```

### 21.7 常见检查顺序

如果任务失败，按这个顺序查：

```bash
sacct -j 任务ID -o JobID,JobName,State,ExitCode,Elapsed,ReqMem,MaxRSS
cat /data/logs/$USER/任务名-任务ID.err
tail -n 100 /data/logs/$USER/任务名-任务ID.out
scontrol show job 任务ID
```

如果是环境问题，进入项目目录手动检查：

```bash
cd /data/users/$USER/project/your_project
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
which python
python -V
python -m pip list
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

---

## 22. 推荐的目录结构

```text
/data
├── datasets              # 公共数据集，只读
├── shared                # 临时共享目录
├── users
│   ├── mcd
│   │   ├── project       # mcd 的代码目录
│   │   ├── envs          # conda-pack 解压后的环境，可选
│   │   └── packages      # wheel、wheelhouse、环境包等，可选
│   ├── user2
│   │   ├── project
│   │   ├── envs
│   │   └── packages
│   └── user3
│       ├── project
│       ├── envs
│       └── packages
├── logs
│   ├── mcd               # mcd 的 Slurm 日志
│   ├── user2
│   └── user3
└── checkpoints
    ├── mcd               # mcd 的模型输出
    ├── user2
    └── user3
```


