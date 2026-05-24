# Slurm 三队列简单训练模板（用户看）

本文档给出当前服务器三个 Slurm 队列的简单训练脚本模板，并附常用资源和任务查看命令。

## 当前服务器配置

服务器当前 Slurm 分区：

```text
debug_shared*      最长 2 天，共享调试队列，默认队列
train_exclusive    最长 7 天，正式单卡训练队列
bigtrain           最长 7 天，双卡或大任务队列
```

说明：分区名后面的 `*` 表示默认队列。不写 `#SBATCH --partition=...` 时会默认进入 `debug_shared`。

当前节点 GPU / MPS 资源：

```text
gpu:rtx_pro_6000:2
mps:rtx_pro_6000:200
```

资源使用建议：

- `debug_shared`：用 MPS 份额，例如 `--gres=mps:40`，适合调试和小任务。
- `train_exclusive`：用整张 GPU，例如 `--gres=gpu:rtx_pro_6000:1`，适合正式单卡训练。
- `bigtrain`：用两张 GPU，例如 `--gres=gpu:rtx_pro_6000:2`，适合双卡训练。

注意：`debug_shared` 不建议写 `--gres=gpu:rtx_pro_6000:1`。虽然 Slurm 能解析，但这会申请整张卡，不符合共享调试队列的目的。

## 环境激活写法

下面模板里环境激活给了两种方式，保留你实际使用的一种，删除或注释另一种。

### 方式 1：已有虚拟环境或项目自带环境

适合 venv、conda-pack、项目目录里已经打包好的环境。

```bash
# 需要改：把用户名、环境路径换成自己的
source /data/users/你的用户名/envs/你的环境/bin/activate
```

也可能是：

```bash
# 需要改：项目自带环境时常见这种路径
source /data/users/你的用户名/project/env/你的环境/bin/activate
```

你的当前示例类似：

```bash
# 需要改：这是示例路径，按自己的项目环境修改
source /data/users/mcd/project/env/dinounet/bin/activate
```

### 方式 2：系统级 Conda 环境

适合在系统 Conda / Miniconda 下创建的环境。

```bash
# 需要改：如果 conda 不在 /opt/miniconda3，先用 conda info --base 查真实路径
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate 你的环境名
```

如果不知道 Conda 安装路径：

```bash
conda info --base
```

然后替换成：

```bash
# 需要改：把 /实际conda路径 换成 conda info --base 输出的路径
source /实际conda路径/etc/profile.d/conda.sh
conda activate 你的环境名
```

## 模板 1：debug_shared 共享调试队列

适合短时间调试、小数据跑通、检查环境。这个队列用 MPS 份额，不独占整卡。

```bash
#!/bin/bash
#SBATCH --job-name=debug_test
#SBATCH --partition=debug_shared
#SBATCH --gres=mps:40              # 需要改：共享队列用 MPS 份额；常用 20/40/60，不要写 gpu:1
#SBATCH --cpus-per-task=4          # 需要改：按数据加载线程数调整
#SBATCH --mem=32G                  # 需要改：按任务内存需求调整
#SBATCH --time=02:00:00            # 需要改：debug_shared 最长 2-00:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# 方式 1：已有虚拟环境或项目自带环境，二选一
source /data/users/你的用户名/envs/你的环境/bin/activate  # 需要改

# 方式 2：系统级 Conda 环境，二选一
# source /opt/miniconda3/etc/profile.d/conda.sh          # 需要改
# conda activate 你的环境名                              # 需要改

cd /data/users/你的用户名/project/你的项目               # 需要改

python -u train.py                                      # 需要改
```

## 模板 2：train_exclusive 正式单卡训练

适合日常正式单卡训练。这个队列申请整张 GPU。

```bash
#!/bin/bash
#SBATCH --job-name=train_job
#SBATCH --partition=train_exclusive
#SBATCH --gres=gpu:rtx_pro_6000:1  # 正式单卡训练申请 1 张整卡
#SBATCH --cpus-per-task=8          # 需要改：按 DataLoader workers 和预处理压力调整
#SBATCH --mem=96G                  # 需要改：按任务内存需求调整
#SBATCH --time=72:00:00            # 需要改：train_exclusive 最长 7-00:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# 方式 1：已有虚拟环境或项目自带环境，二选一
source /data/users/你的用户名/envs/你的环境/bin/activate  # 需要改

# 方式 2：系统级 Conda 环境，二选一
# source /opt/miniconda3/etc/profile.d/conda.sh          # 需要改
# conda activate 你的环境名                              # 需要改

cd /data/users/你的用户名/project/你的项目               # 需要改

python -u train.py                                      # 需要改
```

## 模板 3：bigtrain 双卡或大任务

适合双卡训练、较长时间任务、较大内存任务。

```bash
#!/bin/bash
#SBATCH --job-name=big_train
#SBATCH --partition=bigtrain
#SBATCH --gres=gpu:rtx_pro_6000:2  # 双卡训练申请 2 张整卡
#SBATCH --cpus-per-task=16         # 需要改：双卡任务通常需要更多 CPU
#SBATCH --mem=180G                 # 需要改：按任务内存需求调整
#SBATCH --time=120:00:00           # 需要改：bigtrain 最长 7-00:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# 方式 1：已有虚拟环境或项目自带环境，二选一
source /data/users/你的用户名/envs/你的环境/bin/activate  # 需要改

# 方式 2：系统级 Conda 环境，二选一
# source /opt/miniconda3/etc/profile.d/conda.sh          # 需要改
# conda activate 你的环境名                              # 需要改

cd /data/users/你的用户名/project/你的项目               # 需要改

# 需要改：你的训练代码必须支持 torchrun / DDP，否则不要直接用双卡模板
torchrun --nproc_per_node=2 train.py
```

注意：如果你的代码没有写 DDP / torchrun 支持，`bigtrain` 申请双卡也不一定会自动用上两张卡。普通单进程脚本通常只会用一张卡。

## Checkpoint 和 TensorBoard 路径建议

推荐把日志、TensorBoard、checkpoint 都写到按用户和任务隔离的目录，避免多人互相覆盖。

```bash
export CKPT_DIR=/data/checkpoints/${USER}/${SLURM_JOB_NAME}/${SLURM_JOB_ID}
export OUTPUT_DIR="$CKPT_DIR/outputs"
export TB_DIR="$OUTPUT_DIR/tensorboard"
mkdir -p "$CKPT_DIR" "$OUTPUT_DIR" "$TB_DIR"

python -u train.py \
  --checkpoint_dir "$CKPT_DIR" \
  --tensorboard_log_dir "$TB_DIR"
```

如果你的代码里写死了：

```python
CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
```

建议改成支持命令行参数或环境变量，例如：

```python
# 需要改：优先读取环境变量，没有再用项目默认目录
CHECKPOINT_DIR = Path(os.environ.get("CKPT_DIR", PROJECT_ROOT / "checkpoints"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "outputs"))
```

这样 Slurm 脚本里设置的 `CKPT_DIR`、`OUTPUT_DIR` 和 `TB_DIR` 才会生效。

## 提交和查看任务

提交任务：

```bash
sbatch 你的脚本.sh
```

查看当前排队和运行任务：

```bash
squeue
```

查看自己的任务：

```bash
squeue -u $USER
```

查看更清楚的排队原因和申请资源：

```bash
squeue -o "%.18i %.14P %.24j %.8u %.2t %.10M %.20b %R"
```

说明：

- `ST=R`：正在运行。
- `ST=PD`：正在排队。
- `NODELIST(REASON)`：运行节点或排队原因。
- `TRES_PER_NODE`：申请的 GPU/MPS 等资源。

查看指定任务详情：

```bash
scontrol show job 任务ID
```

查看历史记录：

```bash
sacct -j 任务ID
```

查看更详细的历史记录：

```bash
sacct -j 任务ID -o JobID,JobName,User,Partition,State,ExitCode,Elapsed,AllocTRES%80
```

取消任务：

```bash
scancel 任务ID
```

查看日志：

```bash
tail -f /data/logs/用户名/任务名-任务ID.out
tail -f /data/logs/用户名/任务名-任务ID.err
```

## 查看服务器资源

查看 Slurm 分区和节点：

```bash
sinfo
```

说明：

- `idle`：空闲。
- `mix` 或 `mixed`：部分资源被占用，还能继续调度剩余资源。
- `alloc`：资源已分配。
- `down` 或 `drain`：节点不可用或被管理员排空。

查看节点详细资源：

```bash
scontrol show node user
```

重点看：

```text
Gres
CfgTRES
AllocTRES
State
```

含义：

- `Gres`：节点配置的 GPU/MPS 资源。
- `CfgTRES`：节点总资源。
- `AllocTRES`：已经被 Slurm 分配的资源。
- `State`：节点当前状态。

查看 GPU 状态：

```bash
nvidia-smi
```

只看 GPU 利用率和显存：

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv
```

查看 GPU 上的进程：

```bash
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv
```

查看 CPU、内存和负载：

```bash
uptime
free -h
top
```

说明：

- `uptime` 里的 load average 是系统负载。
- `free -h` 看内存是否充足。
- `top` 看 CPU 和进程占用。

查看磁盘：

```bash
df -h
```

查看目录占用：

```bash
du -sh /data/*
du -sh /data/users/*
du -sh /data/checkpoints/*
```

## 查看 Slurm 服务状态

查看核心服务：

```bash
systemctl status slurmctld
systemctl status slurmd
systemctl status slurmdbd
systemctl status munge
```

查看 Slurm 日志：

```bash
journalctl -u slurmctld -f
journalctl -u slurmd -f
journalctl -u slurmdbd -f
```

查看最近错误：

```bash
journalctl -u slurmctld -u slurmd -u slurmdbd --since "1 hour ago" --no-pager | egrep -i 'error|fatal|fail|drain|invalid|down'
```

## 使用建议

- 调试先用 `debug_shared`，确认环境和数据路径没问题后再跑正式训练。
- `debug_shared` 用 `--gres=mps:40` 这类 MPS 份额，适合多人共享。
- 单卡正式训练用 `train_exclusive`，写 `--gres=gpu:rtx_pro_6000:1`。
- 双卡训练或大任务用 `bigtrain`，写 `--gres=gpu:rtx_pro_6000:2`。
- 不要绕过 Slurm 直接在登录 shell 里跑长时间 GPU 训练。
- 如果任务一直排队，用 `squeue` 看原因，常见是 GPU 不够、内存不够、时间超过分区限制或分区资源被占用。


