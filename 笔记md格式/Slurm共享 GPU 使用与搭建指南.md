# 单机双 RTX PRO 6000 + Slurm 组内共享 GPU 使用与搭建指南

## 1. 目标说明

本指南适用于以下场景：

- 1 台 GPU 服务器
- 2 张 RTX PRO 6000 显卡
- 4 人左右组内共享使用
- 主要用于深度学习模型训练、调试、推理和实验

目标是实现：

- 小任务可以共享一张 GPU，提高显存利用率
- 大模型正式训练独占一张 GPU，保证训练稳定性
- 双卡训练需要单独申请，避免长期占满资源
- 所有任务通过 Slurm 提交，方便排队、查看状态和管理

---

## 2. 推荐资源使用模式

### 2.1 GPU 分工建议

建议将两张 GPU 按用途进行区分：

| GPU | Slurm 资源 | 用途 | 使用方式 |
|---|---|---|---|
| GPU0 | `mps:100` + `gpu:debug:1` | debug 共享卡 | 小实验、调试、推理，多人按 MPS 百分比共享 |
| GPU1 | `gpu:train:1` | train 独占卡 | 正式训练、大模型训练，单任务独占 |
| GPU0 + GPU1 | `gpu:debug:1,gpu:train:1` | bigtrain 双卡任务 | DDP 多卡训练、大模型正式实验 |

这里推荐的核心思路是：

- 小实验走 `debug` 队列，申请 `mps` 份额，共享 GPU0 的算力。
- 正式单卡训练走 `train` 队列，申请 GPU1，独占使用。
- 双卡训练走 `bigtrain` 队列，同时申请 GPU0 和 GPU1。
- 当 GPU0 正在被 `mps` 任务共享时，双卡任务会等待；当双卡任务占用 GPU0 时，新的 debug 共享任务会等待。

### 2.2 Slurm 队列设计

建议设置 3 个队列：

| 队列 | 用途 | 推荐申请方式 | 时间限制 | 适合任务 |
|---|---|---|---|---|
| debug | 调试、小任务、推理 | `--gres=mps:25` | 2 小时 | debug.py、小 batch 测试、推理 |
| train | 正式训练 | `--gres=gpu:train:1` | 72 小时 | train.py、论文实验、消融实验 |
| bigtrain | 双卡训练 | `--gres=gpu:debug:1,gpu:train:1` | 72 小时 | DDP、多卡训练、大模型训练 |

### 2.3 GPU 共享方案选择

小实验共享 GPU 有两种做法：

| 方案 | 优点 | 缺点 | 推荐程度 |
|---|---|---|---|
| 软共享 | 配置简单，只靠规则和 PyTorch 限显存 | Slurm 不会真正按 GPU 份额排队，容易互相抢显存 | 只适合临时过渡 |
| MPS 共享 | Slurm 可以按 `mps` 份额调度，多人共享一张卡更可控 | 需要配置 NVIDIA MPS，部分任务需要测试兼容性 | 推荐 |

本指南后面采用 **MPS 共享 GPU0 + GPU1 独占 + 双卡队列** 的方案。

注意：MPS 控制的是 GPU 计算资源份额，不等于显存硬隔离。显存仍然建议在 PyTorch 里主动限制。

---

## 3. 系统推荐

### 3.1 推荐 Linux 系统

建议安装：

```bash
Ubuntu Server 22.04 LTS
```

如果硬件比较新，也可以安装：

```bash
Ubuntu Server 24.04 LTS
```

不建议安装：

- Windows
- Ubuntu Desktop
- 普通桌面版 Linux

原因：

- Ubuntu Server 更适合 SSH 远程访问
- 更适合 Slurm
- 更适合多人账号管理
- 更适合长期深度学习训练
- 更适合 Docker、Conda、CUDA、PyTorch 环境

---

## 4. 安装前需要查看的参数

配置 Slurm 前，需要先查看服务器的几个关键参数。

### 4.1 查看主机名

```bash
hostname
```

假设输出：

```bash
gpu-node01
```

后面 Slurm 配置中就使用：

```bash
SlurmctldHost=gpu-node01
NodeName=gpu-node01
```

如果需要修改主机名：

```bash
sudo hostnamectl set-hostname gpu-node01
```

修改后建议重启：

```bash
sudo reboot
```

### 4.2 查看 CPU 数量

查看 CPU 详细信息：

```bash
lscpu
```

查看逻辑 CPU 数量：

```bash
nproc
```

例如输出：

```bash
64
```

那么 Slurm 配置中可以写：

```bash
CPUs=64
```

### 4.3 查看内存大小

```bash
free -m
```

例如输出中看到总内存约为：

```bash
515000 MB
```

Slurm 配置中建议写得略小一些：

```bash
RealMemory=500000
```

常见参考：

| 实际内存 | 建议填写 |
|---:|---:|
| 256GB | RealMemory=250000 |
| 512GB | RealMemory=500000 |
| 1TB | RealMemory=1000000 |

### 4.4 查看 GPU 数量

```bash
nvidia-smi -L
```

正常应该看到类似：

```bash
GPU 0: NVIDIA RTX PRO 6000
GPU 1: NVIDIA RTX PRO 6000
```

### 4.5 查看 GPU 设备文件

```bash
ls -l /dev/nvidia*
```

正常应该包含：

```bash
/dev/nvidia0
/dev/nvidia1
/dev/nvidiactl
/dev/nvidia-uvm
```

其中：

```bash
/dev/nvidia0 对应 GPU0
/dev/nvidia1 对应 GPU1
```

### 4.6 查看 GPU UUID、PCIe ID 和显存

```bash
nvidia-smi --query-gpu=index,name,uuid,pci.bus_id,memory.total --format=csv
```

示例输出：

```bash
index, name, uuid, pci.bus_id, memory.total [MiB]
0, NVIDIA RTX PRO 6000, GPU-xxxx, 00000000:41:00.0, 98304 MiB
1, NVIDIA RTX PRO 6000, GPU-yyyy, 00000000:61:00.0, 98304 MiB
```

如果 RTX PRO 6000 是 96GB 版本，显存大约为：

```bash
98304 MiB
```

---

## 5. 基础系统准备

### 5.1 更新系统

```bash
sudo apt update
sudo apt upgrade -y
```

### 5.2 安装常用工具

```bash
sudo apt install -y vim htop tmux git curl wget build-essential net-tools openssh-server
```

### 5.3 检查 SSH 服务

```bash
sudo systemctl status ssh
```

如果没有启动：

```bash
sudo systemctl enable ssh
sudo systemctl start ssh
```

### 5.4 检查 NVIDIA 驱动

安装 NVIDIA 驱动后，执行：

```bash
nvidia-smi
```

如果能看到两张 RTX PRO 6000，说明驱动正常。

---

## 6. 创建组内用户

### 6.1 每个人创建一个独立账号

例如 4 个成员：

```bash
sudo adduser user1
sudo adduser user2
sudo adduser user3
sudo adduser user4
```

不建议多人共用一个账号。

原因：

- 不好判断谁在使用 GPU
- 容易覆盖代码和模型
- 容易把 Conda 环境弄乱
- 不好限制资源
- 不好追踪任务日志

---

## 7. 规划数据目录

### 7.1 创建统一数据目录

```bash
sudo mkdir -p /data/{datasets,projects,users,checkpoints,logs,shared}
```

目录结构：

```bash
/data
  /datasets        # 公共数据集，只读
  /projects        # 共享项目
  /users           # 每个人个人目录
  /checkpoints     # 模型权重
  /logs            # Slurm 日志
  /shared          # 临时共享文件
```

### 7.2 创建每个人的个人目录

```bash
sudo mkdir -p /data/users/user1
sudo mkdir -p /data/users/user2
sudo mkdir -p /data/users/user3
sudo mkdir -p /data/users/user4
```

设置归属：

```bash
sudo chown -R user1:user1 /data/users/user1
sudo chown -R user2:user2 /data/users/user2
sudo chown -R user3:user3 /data/users/user3
sudo chown -R user4:user4 /data/users/user4
```

### 7.3 设置公共数据集权限

公共数据集目录建议只读：

```bash
sudo chmod -R 755 /data/datasets
```

### 7.4 设置日志目录

简单方式：

```bash
sudo chmod -R 777 /data/logs
```

这种方式配置快，但不建议长期使用，因为任何用户都可以改别人的日志。

更规范方式：

```bash
sudo mkdir -p /data/logs/user1 /data/logs/user2 /data/logs/user3 /data/logs/user4

sudo chown -R user1:user1 /data/logs/user1
sudo chown -R user2:user2 /data/logs/user2
sudo chown -R user3:user3 /data/logs/user3
sudo chown -R user4:user4 /data/logs/user4
```

---

## 8. 安装 Slurm

### 8.1 安装 munge 和 Slurm

```bash
sudo apt update
sudo apt install -y munge slurm-wlm
```

### 8.2 启动 munge

```bash
sudo systemctl enable munge
sudo systemctl start munge
sudo systemctl status munge
```

如果看到：

```bash
active (running)
```

说明正常。

---

## 9. 配置 Slurm

### 9.1 创建或编辑 slurm.conf

打开配置文件：

```bash
sudo vim /etc/slurm/slurm.conf
```

写入以下内容。

注意：下面的 `gpu-node01`、`CPUs=64`、`RealMemory=500000` 需要根据你自己的机器修改。

```conf
ClusterName=labgpu
SlurmctldHost=gpu-node01

MpiDefault=none
ProctrackType=proctrack/cgroup
ReturnToService=2

SlurmctldPidFile=/var/run/slurmctld.pid
SlurmdPidFile=/var/run/slurmd.pid
SlurmdSpoolDir=/var/spool/slurmd
StateSaveLocation=/var/spool/slurmctld

SwitchType=switch/none
TaskPlugin=task/cgroup,task/affinity

SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory

GresTypes=gpu,mps

# GPU0: debug 共享卡，同时定义为 gpu:debug:1 和 mps:100
# GPU1: train 独占卡，定义为 gpu:train:1
NodeName=gpu-node01 CPUs=64 RealMemory=500000 Gres=gpu:debug:1,gpu:train:1,mps:100 State=UNKNOWN

# 默认进 debug，避免用户忘记写 partition 时直接进入正式训练队列。
PartitionName=debug Nodes=gpu-node01 Default=YES MaxTime=02:00:00 State=UP OverSubscribe=YES
PartitionName=train Nodes=gpu-node01 Default=NO MaxTime=72:00:00 State=UP OverSubscribe=NO
PartitionName=bigtrain Nodes=gpu-node01 Default=NO MaxTime=72:00:00 State=UP OverSubscribe=NO
```

### 9.2 slurm.conf 参数说明

| 参数 | 含义 | 如何查看 |
|---|---|---|
| ClusterName | Slurm 集群名字，单机也需要 | 自己定义即可 |
| SlurmctldHost | Slurm 控制节点主机名 | `hostname` |
| NodeName | 计算节点主机名 | `hostname` |
| CPUs | 逻辑 CPU 数量 | `nproc` |
| RealMemory | 可分配内存，单位 MB | `free -m` |
| GresTypes | 通用资源类型，这里同时管理 GPU 和 MPS | 写 `gpu,mps` |
| Gres | 节点 GPU/MPS 资源 | 根据 GPU 规划填写 |
| PartitionName | 队列名称 | 自己定义 |
| MaxTime | 队列最大运行时间 | 自己根据规则设置 |
| OverSubscribe | 是否允许超额共享 CPU | debug 可 YES，train 建议 NO |
| TaskPlugin | 是否启用 cgroup 约束 | 推荐 `task/cgroup,task/affinity` |
| ProctrackType | 进程追踪方式 | 推荐 `proctrack/cgroup` |

### 9.3 配置 gres.conf

打开：

```bash
sudo vim /etc/slurm/gres.conf
```

写入：

```conf
AutoDetect=nvml

# GPU0：既可以作为整卡给 bigtrain 使用，也可以作为 MPS 共享卡给 debug 使用。
Name=gpu Type=debug File=/dev/nvidia0
Name=mps Count=100 File=/dev/nvidia0

# GPU1：正式训练独占卡。
Name=gpu Type=train File=/dev/nvidia1
```

含义：

```bash
/dev/nvidia0 作为 debug 共享卡，debug 任务通过 mps 份额使用
/dev/nvidia1 作为 train 独占卡，正式训练通过 gpu:train:1 使用
```

`mps:100` 可以理解为把 GPU0 的计算资源划成 100 份。常见申请方式：

| 申请方式 | 约等于 GPU0 计算份额 | 适合任务 |
|---|---:|---|
| `--gres=mps:10` | 10% | 很小的测试、短推理 |
| `--gres=mps:20` | 20% | 一般 debug |
| `--gres=mps:25` | 25% | 推荐默认值 |
| `--gres=mps:50` | 50% | 较大的小实验 |

注意：

- `mps` 和整张 `gpu` 不能在同一张卡上同时分配。
- 当 GPU0 有 debug 的 MPS 任务运行时，bigtrain 双卡任务会等待。
- 当 bigtrain 占用 GPU0 时，新的 debug MPS 任务会等待。
- MPS 主要限制计算份额，不提供严格显存隔离。

### 9.4 确认 GPU 设备路径

```bash
ls -l /dev/nvidia0 /dev/nvidia1
```

如果存在，说明路径正确。

### 9.5 配置 cgroup 资源隔离

如果希望 Slurm 真正限制用户只能访问被分配的 GPU 设备，需要启用 cgroup。

打开：

```bash
sudo vim /etc/slurm/cgroup.conf
```

写入：

```conf
CgroupPlugin=autodetect
ConstrainCores=yes
ConstrainDevices=yes
ConstrainRAMSpace=yes
ConstrainSwapSpace=no
```

重点是：

```conf
ConstrainDevices=yes
```

它会配合 `gres.conf` 中的 `File=/dev/nvidia0`、`File=/dev/nvidia1`，限制任务只能看到自己申请到的 GPU 设备。

如果不启用 cgroup，用户有可能绕过 Slurm，直接访问没有申请的 GPU。

### 9.6 配置校验命令

修改 Slurm 配置后，先不要急着重启，建议先检查配置。

检查 `slurm.conf` 语法：

```bash
sudo slurmctld -t
```

查看 Slurm 自动识别到的节点信息：

```bash
sudo slurmd -C
```

检查 GRES/GPU 配置：

```bash
sudo slurmd -G
```

如果 `slurmd -G` 报 GPU 名称、文件路径或 AutoDetect 不匹配，需要先修正 `/etc/slurm/gres.conf`。

### 9.7 关于 debug 共享 GPU 的重要说明

不要把：

```conf
OverSubscribe=YES
```

理解成 GPU 可以自动共享。

`OverSubscribe=YES` 主要影响 CPU 资源调度，不会自动把一张 GPU 分给多个任务。GPU 共享需要使用 `mps`、`shard`、MIG，或者只靠组内规则做软共享。

本指南推荐使用：

```bash
--gres=mps:25
```

作为 debug 小任务的默认申请方式。

---

## 10. 创建 Slurm 运行目录

```bash
sudo mkdir -p /var/spool/slurmctld
sudo mkdir -p /var/spool/slurmd
```

检查是否存在 slurm 用户：

```bash
id slurm
```

如果不存在，创建：

```bash
sudo useradd -r -s /usr/sbin/nologin slurm
```

设置目录权限：

```bash
sudo chown -R slurm:slurm /var/spool/slurmctld
sudo chown -R slurm:slurm /var/spool/slurmd
```

---

## 11. 启动 Slurm 服务

```bash
sudo systemctl enable slurmctld
sudo systemctl enable slurmd

sudo systemctl restart slurmctld
sudo systemctl restart slurmd
```

查看服务状态：

```bash
systemctl status slurmctld
systemctl status slurmd
```

如果都显示：

```bash
active (running)
```

说明 Slurm 服务正常。

---

## 12. 查看 Slurm 状态

### 12.1 查看队列状态

```bash
sinfo
```

正常应该看到类似：

```bash
PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
debug*       up   2:00:00      1   idle  gpu-node01
train        up 3-00:00:00     1   idle  gpu-node01
bigtrain     up 3-00:00:00     1   idle  gpu-node01
```

### 12.2 查看节点详细状态

```bash
scontrol show node gpu-node01
```

重点看：

```bash
State=IDLE
Gres=gpu:debug:1,gpu:train:1,mps:100
CPUTot=64
RealMemory=500000
```

### 12.3 查看任务队列

```bash
squeue
```

### 12.4 查看某个用户的任务

```bash
squeue -u user1
```

或者当前用户查看自己的任务：

```bash
squeue -u $USER
```

### 12.5 查看 GPU 实时状态

```bash
nvidia-smi
```

建议实时刷新：

```bash
watch -n 1 nvidia-smi
```

---

## 13. 测试 Slurm 是否可用

### 13.1 测试 debug 共享 GPU

debug 队列建议申请 MPS 份额：

```bash
srun --partition=debug --gres=mps:25 nvidia-smi
```

也可以检查环境变量：

```bash
srun --partition=debug --gres=mps:25 bash -lc 'echo CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES; echo CUDA_MPS_ACTIVE_THREAD_PERCENTAGE=$CUDA_MPS_ACTIVE_THREAD_PERCENTAGE; nvidia-smi'
```

正常情况下，debug 任务只应看到 GPU0。

### 13.2 测试 train 独占 GPU

```bash
srun --partition=train --gres=gpu:train:1 nvidia-smi
```

正常情况下，train 任务只应看到 GPU1。

### 13.3 测试双卡

```bash
srun --partition=bigtrain --gres=gpu:debug:1,gpu:train:1 nvidia-smi
```

正常情况下，bigtrain 任务应看到两张 GPU。

---

## 14. 用户使用说明

### 14.1 小任务使用 debug 队列

适合任务：

- 代码调试
- 小 batch 测试
- 数据加载测试
- 推理测试
- 小模型短时间训练

创建脚本：

```bash
vim debug.sh
```

写入：

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=debug_test
#SBATCH --partition=debug
#SBATCH --gres=mps:25
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/data/logs/%u/%j.out
#SBATCH --error=/data/logs/%u/%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "CUDA_MPS_ACTIVE_THREAD_PERCENTAGE=${CUDA_MPS_ACTIVE_THREAD_PERCENTAGE:-}"
nvidia-smi

source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg

cd /data/users/$USER/project

python debug.py
```

提交任务：

```bash
sbatch debug.sh
```

### 14.2 debug.py 中限制显存

MPS 主要限制计算份额，不是显存硬隔离。debug 任务仍然建议在 `debug.py` 最前面主动限制 PyTorch 显存：

```python
import torch

torch.cuda.set_per_process_memory_fraction(0.25, device=0)
```

显存比例建议：

| PyTorch 显存比例 | 约占 96GB 显存 | 推荐 MPS 份额 | 适合任务 |
|---:|---:|---:|---|
| 0.10 | 约 10GB | `mps:10` | 很小的测试、短推理 |
| 0.20 | 约 19GB | `mps:20` | 代码调试 |
| 0.25 | 约 24GB | `mps:25` | 推荐默认值 |
| 0.30 | 约 29GB | `mps:30` | 小模型训练 |
| 0.40 | 约 38GB | `mps:50` | 较大小任务 |

建议规则：

- debug 任务默认使用 `--gres=mps:25`
- debug 任务建议 PyTorch 显存比例不超过 0.25–0.30
- 需要超过 0.40 显存比例的任务，通常应该走 train 队列
- 非 PyTorch 程序不受 `set_per_process_memory_fraction()` 限制，需要用户自觉遵守规则

### 14.3 正式训练使用 train 队列

适合任务：

- 正式训练
- 论文实验
- 消融实验
- DINOv3 微调
- Mask2Former
- UNet / UPerNet
- 多解码器模型

创建脚本：

```bash
vim train.sh
```

写入：

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=formal_train
#SBATCH --partition=train
#SBATCH --gres=gpu:train:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=72:00:00
#SBATCH --output=/data/logs/%u/%j.out
#SBATCH --error=/data/logs/%u/%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
nvidia-smi

source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg

cd /data/users/$USER/project

python train.py
```

提交：

```bash
sbatch train.sh
```

### 14.4 双卡训练使用 bigtrain 队列

适合任务：

- DDP 多卡训练
- 双卡大模型训练
- 需要两张 RTX PRO 6000 的正式实验

创建脚本：

```bash
vim bigtrain.sh
```

写入：

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=big_train
#SBATCH --partition=bigtrain
#SBATCH --gres=gpu:debug:1,gpu:train:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=192G
#SBATCH --time=72:00:00
#SBATCH --output=/data/logs/%u/%j.out
#SBATCH --error=/data/logs/%u/%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
nvidia-smi

source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg

cd /data/users/$USER/project

torchrun --nproc_per_node=2 train_ddp.py
```

提交：

```bash
sbatch bigtrain.sh
```

---

## 15. 用户常用命令

### 15.1 提交任务

```bash
sbatch train.sh
```

### 15.2 查看所有任务

```bash
squeue
```

### 15.3 查看自己的任务

```bash
squeue -u $USER
```

### 15.4 取消任务

```bash
scancel 任务ID
```

例如：

```bash
scancel 12345
```

### 15.5 查看任务详情

```bash
scontrol show job 任务ID
```

### 15.6 查看节点状态

```bash
sinfo
```

### 15.7 查看 GPU 状态

```bash
nvidia-smi
```

实时查看：

```bash
watch -n 1 nvidia-smi
```

### 15.8 查看任务日志

如果脚本中写了：

```bash
#SBATCH --output=/data/logs/%u/%j.out
#SBATCH --error=/data/logs/%u/%j.err
```

则日志在：

```bash
/data/logs/用户名/任务ID.out
/data/logs/用户名/任务ID.err
```

例如：

```bash
/data/logs/user1/12345.out
/data/logs/user1/12345.err
```

实时查看日志：

```bash
tail -f /data/logs/$USER/任务ID.out
```

---

## 16. 管理员常用命令

### 16.1 查看 Slurm 控制服务

```bash
systemctl status slurmctld
```

### 16.2 查看 Slurm 计算服务

```bash
systemctl status slurmd
```

### 16.3 重启 Slurm

```bash
sudo systemctl restart slurmctld
sudo systemctl restart slurmd
```

### 16.4 查看 Slurm 日志

```bash
sudo journalctl -u slurmctld -n 100
sudo journalctl -u slurmd -n 100
```

查看更多：

```bash
sudo journalctl -u slurmd -n 300
```

### 16.5 查看节点详细状态

```bash
scontrol show node gpu-node01
```

### 16.6 恢复异常节点

如果节点进入 `drain` 或 `down` 状态，可以尝试：

```bash
sudo scontrol update NodeName=gpu-node01 State=RESUME
```

### 16.7 查看谁在占用 GPU

先看 GPU 进程：

```bash
nvidia-smi
```

找到 PID 后：

```bash
ps -fp 进程ID
```

例如：

```bash
ps -fp 12345
```

### 16.8 杀掉异常进程

谨慎使用。

```bash
sudo kill -9 进程ID
```

例如：

```bash
sudo kill -9 12345
```

建议先确认是谁的任务，不要随便杀。

---

## 17. 常见问题排查

### 17.1 sinfo 显示节点 down

查看原因：

```bash
scontrol show node gpu-node01
```

查看服务日志：

```bash
sudo journalctl -u slurmd -n 200
```

尝试恢复：

```bash
sudo scontrol update NodeName=gpu-node01 State=RESUME
```

### 17.2 任务一直 Pending

查看队列：

```bash
squeue
```

查看任务详情：

```bash
scontrol show job 任务ID
```

常见原因：

| 原因 | 含义 |
|---|---|
| Resources | 资源不够，正在等待 GPU、CPU 或内存 |
| ReqNodeNotAvail | 节点不可用 |
| PartitionTimeLimit | 申请时间超过队列限制 |
| Priority | 优先级不够，正在排队 |

### 17.3 slurmd 启动失败

查看日志：

```bash
sudo journalctl -u slurmd -n 200
```

常见原因：

- 主机名和 slurm.conf 不一致
- RealMemory 写得太大
- gres.conf 里 GPU 路径写错
- munge 没启动
- Slurm 配置语法错误

### 17.4 检查主机名是否一致

```bash
hostname
```

确保和 `/etc/slurm/slurm.conf` 中一致：

```conf
SlurmctldHost=gpu-node01
NodeName=gpu-node01
```

### 17.5 检查内存参数是否写太大

查看实际内存：

```bash
free -m
```

如果实际内存是 515000 MB，建议写：

```conf
RealMemory=500000
```

不要写超过实际内存。

### 17.6 检查 GPU 配置

```bash
cat /etc/slurm/gres.conf
```

应该类似：

```conf
Name=gpu Type=debug File=/dev/nvidia0
Name=gpu Type=train File=/dev/nvidia1
```

检查设备是否存在：

```bash
ls -l /dev/nvidia0 /dev/nvidia1
```

### 17.7 检查 munge

```bash
systemctl status munge
```

如果异常：

```bash
sudo systemctl restart munge
```

然后重启 Slurm：

```bash
sudo systemctl restart slurmctld
sudo systemctl restart slurmd
```

---

## 18. 组内使用规则建议

建议直接发给组员：

1. 每个人必须使用自己的 Linux 账号。
2. 不允许多人共用同一个账号。
3. 小任务、调试、推理走 debug 队列，并使用 `--gres=mps:25` 或更小份额。
4. 正式训练走 train 队列，并使用 `--gres=gpu:train:1`。
5. 双卡训练走 bigtrain 队列，并使用 `--gres=gpu:debug:1,gpu:train:1`，提交前提前说明。
6. debug 队列最长 2 小时。
7. train 队列最长 72 小时。
8. debug 任务必须限制 PyTorch 显存比例。
9. debug 任务建议显存不超过 24GB–30GB。
10. 显存超过 40GB 的任务禁止走 debug，应该走 train。
11. 正式论文实验必须走 train 独占队列。
12. 所有长任务必须通过 sbatch 提交。
13. 不允许直接在登录 shell 里长期运行 python train.py。
14. 公共数据集目录 `/data/datasets` 只读。
15. 个人实验放在 `/data/users/用户名`。
16. 每个任务必须保存日志。
17. checkpoint 和中间结果定期清理。
18. 任务异常时及时取消，不要长期占用 GPU。

---

## 19. 推荐使用流程

### 19.1 用户调试代码

```bash
cd /data/users/$USER/project
vim debug.sh
sbatch debug.sh
squeue -u $USER
```

查看 GPU：

```bash
nvidia-smi
```

查看日志：

```bash
tail -f /data/logs/$USER/任务ID.out
```

### 19.2 用户正式训练

```bash
cd /data/users/$USER/project
vim train.sh
sbatch train.sh
squeue -u $USER
```

查看任务详情：

```bash
scontrol show job 任务ID
```

### 19.3 用户取消任务

```bash
scancel 任务ID
```

### 19.4 管理员查看整体状态

```bash
sinfo
squeue
nvidia-smi
```

---

## 20. 最终推荐方案总结

建议你的双 RTX PRO 6000 服务器这样部署：

- 系统：Ubuntu Server 22.04 LTS
- 调度：Slurm
- 用户：每人独立 Linux 账号
- 数据：统一放在 `/data`
- GPU0：debug 共享卡，通过 `mps:100` 切分为共享份额
- GPU1：train 独占卡，通过 `gpu:train:1` 独占使用
- 双卡：bigtrain 队列，通过 `gpu:debug:1,gpu:train:1` 同时申请两张卡
- 隔离：启用 `task/cgroup` 和 `ConstrainDevices=yes`
- 环境：Conda 为主，Docker 可后续增加
- 日志：统一保存到 `/data/logs`

最终使用规则：

- 小任务共享，提高显存利用率
- 大任务独占，保证训练稳定性
- 双卡任务提前申请
- 所有任务通过 Slurm 提交
- 所有任务保留日志

一句话总结：

> 单机双 RTX PRO 6000 搭 Slurm 完全可行。推荐用 `debug=mps 共享 GPU0`、`train=独占 GPU1`、`bigtrain=双卡独占` 的结构管理资源，再配合 cgroup、限时、限显存、日志和组内规则，就能满足小实验共享、大实验独占、超大实验双卡的使用目标。
---

## 21. MPS 共享方案的落地注意事项

### 21.1 为什么推荐 MPS

你的目标是：

- 小实验大家可以共享一张卡的算力
- 大一点的模型独占一张卡
- 再大的模型可以双卡一起跑

这正好对应：

| 使用场景 | 推荐队列 | 推荐资源 |
|---|---|---|
| 小实验、调试、推理 | debug | `--gres=mps:10` 到 `--gres=mps:30` |
| 中大型单卡训练 | train | `--gres=gpu:train:1` |
| 双卡训练 | bigtrain | `--gres=gpu:debug:1,gpu:train:1` |

MPS 的优点是 Slurm 可以把 GPU0 的计算资源按份额调度，不再只是靠大家口头约定。

### 21.2 MPS 不是显存硬隔离

需要明确：

- MPS 可以限制计算资源份额。
- MPS 不等于显存硬隔离。
- PyTorch 显存仍然需要用 `torch.cuda.set_per_process_memory_fraction()` 主动限制。
- 如果某个 debug 任务显存用太多，仍然可能影响同卡其他 debug 任务。

所以 debug 队列必须同时使用：

```bash
#SBATCH --gres=mps:25
```

和：

```python
torch.cuda.set_per_process_memory_fraction(0.25, device=0)
```

### 21.3 MPS 需要额外测试

不同 CUDA、NVIDIA 驱动、PyTorch 版本对 MPS 的表现可能不同。正式给组员使用前，建议测试：

```bash
sbatch debug.sh
sbatch debug.sh
sbatch debug.sh
```

然后观察：

```bash
squeue
nvidia-smi
```

确认多个 debug 任务能同时落到 GPU0，并且 train 任务仍然只使用 GPU1。

如果 MPS 在某些模型上不稳定，可以临时退回软共享方案：

- debug 队列不申请 `gpu`，只在脚本中设置 `CUDA_VISIBLE_DEVICES=0`
- 通过组内规则限制显存
- 缺点是 Slurm 不会真正按 GPU 份额排队

软共享只建议作为过渡方案，长期还是推荐 MPS。
