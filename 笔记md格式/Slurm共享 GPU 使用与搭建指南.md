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

### 2.1 推荐总体设计

更推荐把两张 GPU 都设计成“可共享，也可独占”的资源池，而不是固定 GPU0 只能 debug、GPU1 只能 train。

目标效果：

| 场景 | GPU0 | GPU1 | 调度效果 |
|---|---|---|---|
| 大家都在调试 | A、B 小任务共享 | C、D 小任务共享 | 两张卡都能被小任务利用 |
| 有人正式训练 | A 正式训练独占 | B、C、D 小任务共享 | 正式训练占一张空闲卡，另一张继续服务小任务 |
| 有人双卡训练 | 大任务独占 | 大任务独占 | 其他任务排队 |

这比固定 GPU0/GPU1 分工更灵活，资源利用率更高。

### 2.2 Slurm 队列设计

建议设置 3 个队列：

| 队列 | 用途 | 推荐申请方式 | 时间限制 | 适合任务 |
|---|---|---|---|---|
| debug_shared | 调试、小任务、推理 | `--gres=shard:25` | 2 小时 | debug.py、小 batch 测试、推理 |
| train_exclusive | 正式训练 | `--gres=gpu:rtx_pro_6000:1` | 72 小时 | train.py、论文实验、消融实验 |
| bigtrain | 双卡训练 | `--gres=gpu:rtx_pro_6000:2` | 72 小时 | DDP、多卡训练、大模型训练 |

### 2.3 资源设计逻辑

两张 RTX PRO 6000 同时定义为：

- `gpu:rtx_pro_6000:2`：两张完整 GPU，可被正式训练独占申请。
- `shard:200`：两张 GPU 各 100 份 shard，可被小任务共享申请。

`shard` 可以理解为 Slurm 调度层面的 GPU 共享份额：

```text
GPU0 = shard:100
GPU1 = shard:100
总计 = shard:200
```

小任务申请：

```bash
--gres=shard:25
```

正式训练申请：

```bash
--gres=gpu:rtx_pro_6000:1
```

双卡训练申请：

```bash
--gres=gpu:rtx_pro_6000:2
```

### 2.4 重要限制

`shard` 适合做共享调度，但不是显存硬隔离，也不是严格的算力硬隔离。

所以 debug_shared 队列仍然需要配合：

- 短时间限制
- 小 shard 份额
- PyTorch 显存比例限制
- 组内使用规则

如果要更强的硬隔离，需要硬件支持 MIG；RTX PRO 6000 是否支持 MIG 要以具体型号和 NVIDIA 官方说明为准。
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

GresTypes=gpu,shard

# 两张 RTX PRO 6000 都可以被整卡独占，也可以被 shard 共享。
# rtx_pro_6000 需要能匹配 slurmd -C 里检测到的 GPU 名称子串。
NodeName=gpu-node01 CPUs=64 RealMemory=500000 Gres=gpu:rtx_pro_6000:2,shard:200 State=UNKNOWN

# 默认进入 debug_shared，避免用户忘记写 partition 时直接进入正式训练队列。
PartitionName=debug_shared Nodes=gpu-node01 Default=YES MaxTime=02:00:00 State=UP OverSubscribe=YES
PartitionName=train_exclusive Nodes=gpu-node01 Default=NO MaxTime=72:00:00 State=UP OverSubscribe=NO
PartitionName=bigtrain Nodes=gpu-node01 Default=NO MaxTime=72:00:00 State=UP OverSubscribe=NO
```

### 9.2 slurm.conf 参数说明

| 参数            | 含义                      | 如何查看                           |
| ------------- | ----------------------- | ------------------------------ |
| ClusterName   | Slurm 集群名字，单机也需要        | 自己定义即可                         |
| SlurmctldHost | Slurm 控制节点主机名           | `hostname`                     |
| NodeName      | 计算节点主机名                 | `hostname`                     |
| CPUs          | 逻辑 CPU 数量               | `nproc`                        |
| RealMemory    | 可分配内存，单位 MB             | `free -m`                      |
| GresTypes     | 通用资源类型，这里同时管理 GPU 和 shard | 写 `gpu,shard`                    |
| Gres          | 节点 GPU/shard 资源           | 根据 GPU 规划填写                    |
| PartitionName | 队列名称                    | 自己定义                           |
| MaxTime       | 队列最大运行时间                | 自己根据规则设置                       |
| OverSubscribe | 是否允许超额共享 CPU | debug_shared 可 YES，train_exclusive 建议 NO |
| TaskPlugin    | 是否启用 cgroup 约束          | 推荐 `task/cgroup,task/affinity` |
| ProctrackType | 进程追踪方式                  | 推荐 `proctrack/cgroup`          |

### 9.3 配置 gres.conf

打开：

```bash
sudo vim /etc/slurm/gres.conf
```

写入：

```conf
AutoDetect=nvml

# 两张卡都作为完整 GPU 资源，供 train_exclusive 或 bigtrain 独占申请。
Name=gpu Type=rtx_pro_6000 File=/dev/nvidia0
Name=gpu Type=rtx_pro_6000 File=/dev/nvidia1

# 两张卡也都切成 shard 共享份额，供 debug_shared 小任务申请。
Name=shard Count=100 File=/dev/nvidia0
Name=shard Count=100 File=/dev/nvidia1
```

含义：

```bash
/dev/nvidia0 可以整卡独占，也可以按 shard 共享
/dev/nvidia1 可以整卡独占，也可以按 shard 共享
```

`shard:200` 可以理解为两张 GPU 一共 200 份共享调度份额。常见申请方式：

| 申请方式 | 大致含义 | 适合任务 |
|---|---:|---|
| `--gres=shard:10` | 很小份额 | 很小的测试、短推理 |
| `--gres=shard:20` | 小份额 | 一般 debug |
| `--gres=shard:25` | 推荐默认值 | 小 batch 测试 |
| `--gres=shard:50` | 较大份额 | 较大的小实验 |

注意：

- 同一张 GPU 不能同时分配为整卡 `gpu` 和共享 `shard`。
- 如果 GPU0 上已有 shard 小任务，正式训练会优先选择另一张空闲 GPU。
- 如果两张 GPU 都有 shard 小任务，正式训练会等待资源释放。
- 如果 bigtrain 申请两张完整 GPU，所有 shard 小任务都需要等待。
- shard 提供的是 Slurm 调度份额，不提供严格显存隔离。
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
--gres=shard:25
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
debug_shared*       up   2:00:00      1   idle  gpu-node01
train_exclusive     up 3-00:00:00     1   idle  gpu-node01
bigtrain     up 3-00:00:00     1   idle  gpu-node01
```

### 12.2 查看节点详细状态

```bash
scontrol show node gpu-node01
```

重点看：

```bash
State=IDLE
Gres=gpu:rtx_pro_6000:2,shard:200
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

### 13.1 测试 debug_shared 共享 GPU

debug_shared 队列建议申请 shard 份额：

```bash
srun --partition=debug_shared --gres=shard:25 nvidia-smi
```

也可以检查环境变量：

```bash
srun --partition=debug_shared --gres=shard:25 bash -lc 'echo CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES; nvidia-smi'
```

正常情况下，debug_shared 任务会被 Slurm 分配到某一张有空闲 shard 的 GPU。

### 13.2 测试 train_exclusive 独占 GPU

```bash
srun --partition=train_exclusive --gres=gpu:rtx_pro_6000:1 nvidia-smi
```

正常情况下，train_exclusive 任务只会看到一张被独占分配的 GPU。

### 13.3 测试 bigtrain 双卡

```bash
srun --partition=bigtrain --gres=gpu:rtx_pro_6000:2 nvidia-smi
```

正常情况下，bigtrain 任务应看到两张 GPU。

---
## 14. 用户使用说明

### 14.1 小任务使用 debug_shared 队列

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
#SBATCH --partition=debug_shared
#SBATCH --gres=shard:25
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/data/logs/%u/%j.out
#SBATCH --error=/data/logs/%u/%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo ""
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

shard 主要提供调度份额，不是显存硬隔离。debug_shared 任务仍然建议在 `debug.py` 最前面主动限制 PyTorch 显存：

```python
import torch

torch.cuda.set_per_process_memory_fraction(0.25, device=0)
```

显存比例建议：

| PyTorch 显存比例 | 约占 96GB 显存 | 推荐 shard 份额 | 适合任务 |
|---:|---:|---:|---|
| 0.10 | 约 10GB | `shard:10` | 很小的测试、短推理 |
| 0.20 | 约 19GB | `shard:20` | 代码调试 |
| 0.25 | 约 24GB | `shard:25` | 推荐默认值 |
| 0.30 | 约 29GB | `shard:30` | 小模型训练 |
| 0.40 | 约 38GB | `shard:50` | 较大小任务 |

建议规则：

- debug_shared 任务默认使用 `--gres=shard:25`
- debug_shared 任务建议 PyTorch 显存比例不超过 0.25–0.30
- 需要超过 0.40 显存比例的任务，通常应该走 train_exclusive 队列
- 非 PyTorch 程序不受 `set_per_process_memory_fraction()` 限制，需要用户自觉遵守规则

### 14.3 正式训练使用 train_exclusive 队列

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
#SBATCH --partition=train_exclusive
#SBATCH --gres=gpu:rtx_pro_6000:1
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
#SBATCH --gres=gpu:rtx_pro_6000:2
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
3. 小任务、调试、推理走 debug_shared 队列，并使用 `--gres=shard:25` 或更小份额。
4. 正式训练走 train_exclusive 队列，并使用 `--gres=gpu:rtx_pro_6000:1`。
5. 双卡训练走 bigtrain 队列，并使用 `--gres=gpu:rtx_pro_6000:2`，提交前提前说明。
6. debug_shared 队列最长 2 小时。
7. train_exclusive 队列最长 72 小时。
8. debug_shared 任务必须限制 PyTorch 显存比例。
9. debug_shared 任务建议显存不超过 24GB–30GB。
10. 显存超过 40GB 的任务禁止走 debug，应该走 train。
11. 正式论文实验必须走 train_exclusive 独占队列。
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
- 两张 GPU：都可通过 `shard:200` 作为 debug_shared 共享资源池
- 正式训练：通过 `gpu:rtx_pro_6000:1` 独占任意一张空闲 GPU
- 双卡：bigtrain 队列通过 `gpu:rtx_pro_6000:2` 同时申请两张卡
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

> 单机双 RTX PRO 6000 搭 Slurm 完全可行。推荐用 `debug_shared=两卡 shard 共享`、`train_exclusive=任意单卡独占`、`bigtrain=双卡独占` 的结构管理资源，再配合 cgroup、限时、限显存、日志和组内规则，就能满足小实验共享、大实验独占、超大实验双卡的使用目标。

---

## 21. 共享 GPU 方案的落地注意事项

### 21.1 为什么推荐 shard

你的目标是：

- 小实验大家可以共享两张卡的算力。
- 大一点的模型独占任意一张空闲 GPU。
- 再大的模型可以双卡一起跑。

这正好对应：

| 使用场景 | 推荐队列 | 推荐资源 |
|---|---|---|
| 小实验、调试、推理 | debug_shared | `--gres=shard:10` 到 `--gres=shard:30` |
| 中大型单卡训练 | train_exclusive | `--gres=gpu:rtx_pro_6000:1` |
| 双卡训练 | bigtrain | `--gres=gpu:rtx_pro_6000:2` |

shard 的优点是 Slurm 可以把两张 GPU 都作为共享资源池调度，不再固定某一张卡只能 debug 或只能 train。

### 21.2 shard 不是显存硬隔离

需要明确：

- shard 可以做 Slurm 调度层面的共享份额。
- shard 不等于显存硬隔离。
- shard 不严格限制实际算力百分比。
- PyTorch 显存仍然需要用 `torch.cuda.set_per_process_memory_fraction()` 主动限制。
- 如果某个 debug_shared 任务显存用太多，仍然可能影响同卡其他小任务。

所以 debug_shared 队列建议同时使用：

```bash
#SBATCH --gres=shard:25
```

和：

```python
torch.cuda.set_per_process_memory_fraction(0.25, device=0)
```

### 21.3 为什么不默认用 MPS

NVIDIA MPS 可以限制一定的计算份额，但在多用户场景下有额外限制：不同用户的 MPS server 并不是真正完全并行共享，可能出现排队或序列化访问。

所以本指南默认采用 Slurm `shard`：

- 更符合多用户共享调度。
- 能让两张 GPU 都作为小任务资源池。
- 能和整卡 `gpu` 独占资源互斥。

如果后续确认你的驱动、CUDA、PyTorch 和使用方式都适合 MPS，也可以把 `shard` 方案替换为 MPS 方案，但需要单独测试。

### 21.4 需要额外测试

正式给组员使用前，建议测试：

```bash
sbatch debug.sh
sbatch debug.sh
sbatch debug.sh
sbatch debug.sh
```

然后观察：

```bash
squeue
nvidia-smi
```

理想情况：

- 多个 debug_shared 小任务可以分布到 GPU0 和 GPU1。
- train_exclusive 可以独占一张当前没有 shard 任务的 GPU。
- bigtrain 会等待两张 GPU 都空闲后再运行。
## 22. 多用户日志、项目和训练是否会冲突

### 22.1 正常情况下不会冲突

只要按下面规则使用，多用户之间一般不会互相覆盖：

- 每个人使用自己的 Linux 账号。
- 每个人的代码放在自己的目录，例如 `/data/users/user1/project`。
- 每个人的日志放在自己的目录，例如 `/data/logs/user1`。
- 每个人的 Conda 环境放在自己的 home 目录，或者使用明确命名的共享环境。
- 所有训练任务通过 `sbatch` 或 `srun` 提交，不直接在登录 shell 里长期运行。

推荐目录结构：

```bash
/data/users/user1/project
/data/users/user2/project
/data/users/user3/project
/data/users/user4/project

/data/logs/user1
/data/logs/user2
/data/logs/user3
/data/logs/user4
```

这样每个人的代码、输出、日志、checkpoint 都分开，最不容易互相影响。

### 22.2 日志冲突如何避免

不要让所有人的任务都写到同一个固定文件，例如：

```bash
# 不推荐
#SBATCH --output=/data/logs/train.out
#SBATCH --error=/data/logs/train.err
```

这样多个任务同时运行时，日志可能混在一起，也可能互相覆盖。

推荐写法：

```bash
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err
```

含义：

| 占位符 | 含义 |
|---|---|
| `%u` | 用户名 |
| `%x` | 作业名 |
| `%j` | Slurm 任务 ID |

例如用户 `user1` 提交了作业 `debug_test`，任务 ID 是 `12345`，日志会变成：

```bash
/data/logs/user1/debug_test-12345.out
/data/logs/user1/debug_test-12345.err
```

这种写法可以避免不同用户、不同任务之间日志冲突。

### 22.3 checkpoint 和输出文件冲突如何避免

训练脚本里不要把 checkpoint 固定写到公共路径，例如：

```bash
# 不推荐
/data/checkpoints/latest.pth
```

推荐按用户、项目、任务 ID 分目录：

```bash
/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID
```

在 sbatch 脚本里可以这样写：

```bash
export CKPT_DIR=/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID
mkdir -p "$CKPT_DIR"

python train.py --output-dir "$CKPT_DIR"
```

这样每次训练都有独立输出目录，不会覆盖别人或自己上一次的实验结果。

### 22.4 Conda 环境是否会冲突

如果每个人都在自己的账号下安装 Conda 环境，通常不会冲突：

```bash
~/miniconda3/envs/seg
```

但如果多人共用一个共享环境，例如：

```bash
/opt/conda/envs/seg
```

则不建议普通用户随意执行：

```bash
pip install -U xxx
conda install xxx
```

否则可能把别人正在用的环境改坏。

推荐做法：

- 基础共享环境由管理员维护。
- 个人实验环境放在自己的 home 目录。
- 重要实验记录 `environment.yml` 或 `requirements.txt`。

导出环境：

```bash
conda env export > environment.yml
pip freeze > requirements.txt
```

### 22.5 GPU 训练是否会冲突

按本指南配置后：

- `debug_shared` 队列共享两张 GPU 的 shard 份额。
- `train_exclusive` 队列独占任意一张空闲 GPU。
- `bigtrain` 队列同时申请两张完整 GPU。

Slurm 会根据资源申请排队，避免同一张独占 GPU 被多个正式训练任务同时占用。

但是 debug_shared 队列需要注意：

- shard 提供的是调度份额，不是显存硬隔离。
- 多个 debug_shared 任务如果都占很多显存，仍然可能互相影响。
- 所以 debug_shared 任务必须主动限制 PyTorch 显存比例。

推荐 debug_shared 脚本默认：

```bash
#SBATCH --gres=shard:25
```

并在 Python 里限制：

```python
torch.cuda.set_per_process_memory_fraction(0.25, device=0)
```

### 22.6 最推荐的多用户 sbatch 模板

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=debug_test
#SBATCH --partition=debug_shared
#SBATCH --gres=shard:25
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "Job Name: $SLURM_JOB_NAME"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo ""
nvidia-smi

export CKPT_DIR=/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID
mkdir -p "$CKPT_DIR"

source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg

cd /data/users/$USER/project

python debug.py --output-dir "$CKPT_DIR"
```

---

## 23. VS Code 通过 SSH 连接服务器并运行代码

### 23.1 本地电脑安装插件

在本地 Windows 电脑的 VS Code 中安装插件：

```text
Remote - SSH
```

安装后，VS Code 左侧会出现远程连接入口，也可以按：

```text
Ctrl + Shift + P
```

搜索：

```text
Remote-SSH: Connect to Host
```

### 23.2 配置 SSH 连接

假设服务器 IP 是：

```text
10.126.11.150
```

用户名是：

```text
user1
```

在本地 Windows PowerShell 中可以先测试：

```powershell
ssh user1@10.126.11.150
```

如果可以登录，再配置 VS Code SSH。

打开本地 SSH 配置文件：

```powershell
notepad C:\Users\DELL\.ssh\config
```

添加：

```sshconfig
Host lab-gpu
  HostName 10.126.11.150
  User user1
  Port 22
```

如果使用密钥登录，可以加：

```sshconfig
Host lab-gpu
  HostName 10.126.11.150
  User user1
  Port 22
  IdentityFile C:\Users\DELL\.ssh\你的私钥文件
```

然后在 VS Code 中执行：

```text
Remote-SSH: Connect to Host
```

选择：

```text
lab-gpu
```

### 23.3 在 VS Code 中打开个人项目目录

连接成功后，在远程 VS Code 中打开目录：

```bash
/data/users/user1/project
```

建议每个人只在自己的目录里开发：

```bash
/data/users/$USER/project
```

不要直接在别人的目录或公共数据集目录里改文件。

### 23.4 在 VS Code 终端中准备环境

打开 VS Code 远程终端：

```text
Terminal -> New Terminal
```

进入项目：

```bash
cd /data/users/$USER/project
```

加载 Conda：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg
```

检查 Python：

```bash
which python
python -V
```

检查 GPU：

```bash
nvidia-smi
```

注意：`nvidia-smi` 可以用来查看 GPU 状态，但不要在 VS Code 终端里直接长期运行训练。

### 23.5 在 VS Code 里调试小代码

很短的小测试可以在 VS Code 终端里运行，例如：

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

但正式训练不要直接运行：

```bash
python train.py
```

原因：

- 直接运行不会进入 Slurm 队列。
- 不会按 `debug_shared/train_exclusive/bigtrain` 规则申请资源。
- 日志不会自动保存到 `/data/logs`。
- 管理员不容易判断任务归属。
- 可能绕过 cgroup 资源限制。

### 23.6 正确方式：在 VS Code 中写代码，用 Slurm 运行

推荐流程是：

1. 用 VS Code Remote-SSH 编辑代码。
2. 在 VS Code 终端里写好 `debug.sh`、`train.sh` 或 `bigtrain.sh`。
3. 用 `sbatch` 提交任务。
4. 用 `squeue` 查看队列。
5. 用 `tail -f` 查看日志。

例如提交 debug_shared 任务：

```bash
sbatch debug.sh
```

查看自己的任务：

```bash
squeue -u $USER
```

查看日志：

```bash
tail -f /data/logs/$USER/debug_test-任务ID.out
```

取消任务：

```bash
scancel 任务ID
```

### 23.7 VS Code 中运行正式训练示例

在项目目录中创建：

```bash
vim train.sh
```

内容：

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=my_train
#SBATCH --partition=train_exclusive
#SBATCH --gres=gpu:rtx_pro_6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=72:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
nvidia-smi

export CKPT_DIR=/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID
mkdir -p "$CKPT_DIR"

source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg

cd /data/users/$USER/project

python train.py --output-dir "$CKPT_DIR"
```

提交：

```bash
sbatch train.sh
```

### 23.8 VS Code 断开后任务会不会停止

如果任务是用：

```bash
sbatch train.sh
```

提交的，那么 VS Code 断开、电脑关机、SSH 断开，任务一般仍会继续运行。

如果你是在 VS Code 终端里直接运行：

```bash
python train.py
```

那么 SSH 断开后任务可能会停止，也不受 Slurm 正常管理。

所以长任务必须用：

```bash
sbatch
```

### 23.9 VS Code 使用建议

- VS Code 负责写代码和看文件。
- Slurm 负责运行训练。
- 小测试可以短时间直接运行。
- 长训练必须 `sbatch`。
- 每个人只打开自己的 `/data/users/$USER/project`。
- 不要在公共数据集目录里直接修改文件。
- 不要用 VS Code 同时打开别人的项目目录并改文件。
---

## 24. 管理员权限与安全边界设置

### 24.1 核心原则

多人共享 GPU 服务器时，管理员需要把权限边界提前设清楚。

目标是：

- 普通用户不能修改 Slurm、MUNGE、NVIDIA 驱动等集群配置。
- 普通用户不能修改别人的代码、数据、日志、checkpoint。
- 普通用户不能随意修改共享 Conda 环境。
- 普通用户不能绕过 Slurm 长期占用 GPU。
- 公共数据集可以读，但默认不允许普通用户写。

建议把用户分成两类：

| 角色   | 权限                            |
| ---- | ----------------------------- |
| 管理员  | 可以 sudo，可以改系统配置、Slurm 配置、共享环境 |
| 普通用户 | 只能管理自己的代码、环境、日志和实验输出          |

### 24.2 不要给普通用户 sudo 权限

创建普通用户时，不要把他们加入 `sudo` 组。

检查用户是否有 sudo 权限：

```bash
groups user1
```

如果看到：

```bash
sudo
```

说明这个用户有 sudo 权限。

移除普通用户 sudo 权限：

```bash
sudo deluser user1 sudo
```

建议只有管理员账号保留 sudo，例如：

```bash
admin
```

普通用户使用：

```bash
user1
user2
user3
user4
```

### 24.3 个人目录权限

每个人的实验目录应该只允许自己写。

例如：

```bash
sudo mkdir -p /data/users/user1
sudo chown -R user1:user1 /data/users/user1
sudo chmod 700 /data/users/user1
```

含义：

```text
user1 可以读写自己的目录
其他普通用户不能进入这个目录
管理员 root 可以管理
```

如果组内希望互相查看代码，但不允许修改，可以用：

```bash
sudo chmod 750 /data/users/user1
```

更严格的推荐：

```bash
chmod 700
```

更方便协作的推荐：

```bash
chmod 750
```

不要使用：

```bash
chmod 777 /data/users/user1
```

否则任何人都可以改这个用户的代码和输出。

### 24.4 公共数据集目录只读

公共数据集建议放在：

```bash
/data/datasets
```

设置为普通用户只读：

```bash
sudo mkdir -p /data/datasets
sudo chown -R root:root /data/datasets
sudo chmod -R 755 /data/datasets
```

含义：

```text
管理员可以写入和更新数据集
普通用户可以读取数据集
普通用户不能删除或修改数据集
```

如果有专门的数据管理员组，可以创建：

```bash
sudo groupadd data-admin
sudo usermod -aG data-admin admin
sudo chown -R root:data-admin /data/datasets
sudo chmod -R 775 /data/datasets
```

但普通训练用户不要加入 `data-admin`。

### 24.5 共享项目目录权限

如果需要共享项目目录：

```bash
/data/projects
```

可以创建项目组：

```bash
sudo groupadd project-rw
sudo usermod -aG project-rw user1
sudo usermod -aG project-rw user2
```

设置目录权限：

```bash
sudo mkdir -p /data/projects
sudo chown -R root:project-rw /data/projects
sudo chmod -R 2775 /data/projects
```

这里的 `2` 是 setgid 位：

```bash
2775
```

作用是让新建文件自动继承 `project-rw` 组，方便协作。

如果不需要共享写权限，建议普通用户只在自己的 `/data/users/$USER` 下工作。

### 24.6 日志目录权限

不要长期使用：

```bash
chmod -R 777 /data/logs
```

推荐为每个用户建立独立日志目录：

```bash
sudo mkdir -p /data/logs/user1 /data/logs/user2 /data/logs/user3 /data/logs/user4

sudo chown user1:user1 /data/logs/user1
sudo chown user2:user2 /data/logs/user2
sudo chown user3:user3 /data/logs/user3
sudo chown user4:user4 /data/logs/user4

sudo chmod 700 /data/logs/user1
sudo chmod 700 /data/logs/user2
sudo chmod 700 /data/logs/user3
sudo chmod 700 /data/logs/user4
```

如果希望组员之间可以互相查看日志，但不能修改，可以用：

```bash
sudo chmod 755 /data/logs/user1
```

但更安全的是：

```bash
chmod 700
```

### 24.7 checkpoint 目录权限

checkpoint 容易很大，也容易被误删，建议按用户分目录：

```bash
sudo mkdir -p /data/checkpoints/user1 /data/checkpoints/user2
sudo chown user1:user1 /data/checkpoints/user1
sudo chown user2:user2 /data/checkpoints/user2
sudo chmod 700 /data/checkpoints/user1
sudo chmod 700 /data/checkpoints/user2
```

用户脚本中使用：

```bash
export CKPT_DIR=/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID
mkdir -p "$CKPT_DIR"
```

这样不同用户、不同任务不会互相覆盖 checkpoint。

### 24.8 共享 Conda 环境权限

如果管理员维护共享环境，例如：

```bash
/opt/conda/envs/seg
```

建议设置为普通用户只读：

```bash
sudo chown -R root:root /opt/conda
sudo chmod -R a+rX /opt/conda
sudo chmod -R go-w /opt/conda
```

普通用户不要直接修改共享环境。

普通用户需要安装自己的包时，建议创建个人环境：

```bash
conda create -n myseg python=3.10
conda activate myseg
pip install 包名
```

也可以安装到个人 home 下：

```bash
~/miniconda3/envs/myseg
```

规则建议：

- 共享环境只由管理员维护。
- 个人实验依赖放在个人 Conda 环境。
- 重要实验保存 `environment.yml` 或 `requirements.txt`。

### 24.9 Slurm 和 MUNGE 配置权限

Slurm 配置文件应只允许 root 修改：

```bash
sudo chown root:root /etc/slurm/slurm.conf
sudo chown root:root /etc/slurm/gres.conf
sudo chown root:root /etc/slurm/cgroup.conf

sudo chmod 644 /etc/slurm/slurm.conf
sudo chmod 644 /etc/slurm/gres.conf
sudo chmod 644 /etc/slurm/cgroup.conf
```

MUNGE key 必须严格保护：

```bash
sudo chown munge:munge /etc/munge/munge.key
sudo chmod 400 /etc/munge/munge.key
```

如果 MUNGE key 权限太宽，Slurm 认证可能失败。

Slurm spool 目录：

```bash
sudo chown -R slurm:slurm /var/spool/slurmctld
sudo chown -R slurm:slurm /var/spool/slurmd
sudo chmod 755 /var/spool/slurmctld
sudo chmod 755 /var/spool/slurmd
```

普通用户不应该修改这些目录。

### 24.10 防止普通用户绕过 Slurm 直接占 GPU

技术上，只要用户能 SSH 到服务器并能访问 `/dev/nvidia*`，就可能直接运行：

```bash
python train.py
```

这会绕过 Slurm。

推荐同时使用管理规则和技术限制：

1. 明确规定长任务必须通过 `sbatch`。
2. 启用 cgroup：

```conf
TaskPlugin=task/cgroup,task/affinity
ProctrackType=proctrack/cgroup
ConstrainDevices=yes
```

3. 管理员定期检查 GPU 进程：

```bash
nvidia-smi
ps -fp 进程ID
```

4. 对违规长期占用 GPU 的进程，先通知用户，再由管理员处理。

更强硬的做法是限制普通用户访问 GPU 设备文件，但这需要更复杂的 cgroup 或设备权限策略。对 4 人左右组内服务器，通常先用 Slurm + 规则 + 日志追踪就够用。

### 24.11 用户磁盘配额

如果担心某个用户写满硬盘，可以启用 Linux quota。

简单管理方式是定期查看：

```bash
du -sh /data/users/*
du -sh /data/checkpoints/*
```

如果需要硬限制，可以后续配置：

```bash
quota
```

或者把 `/data` 放在支持项目配额的文件系统上。

组内规则建议：

- checkpoint 定期清理。
- 临时文件不要长期放 `/data/shared`。
- 每个用户超过约定容量时需要清理。

### 24.12 管理员检查清单

管理员配置完成后，建议检查：

```bash
groups user1
ls -ld /data/users/user1
ls -ld /data/datasets
ls -ld /data/logs/user1
ls -ld /data/checkpoints/user1
ls -l /etc/slurm/slurm.conf /etc/slurm/gres.conf /etc/slurm/cgroup.conf
ls -l /etc/munge/munge.key
```

重点确认：

- 普通用户不在 `sudo` 组。
- `/data/users/user1` 不是 777。
- `/data/datasets` 普通用户不能写。
- `/data/logs/user1` 归 user1 所有。
- `/data/checkpoints/user1` 归 user1 所有。
- `/etc/slurm/*.conf` 只有 root 可改。
- `/etc/munge/munge.key` 权限是 400。
---

## 25. 后续新增用户流程

### 25.1 新增用户时要做哪些事

后续组里新增成员时，管理员需要完成：

1. 创建 Linux 用户。
2. 设置初始密码或 SSH key。
3. 创建个人项目目录。
4. 创建个人日志目录。
5. 创建个人 checkpoint 目录。
6. 确认没有 sudo 权限。
7. 测试 SSH 登录。
8. 测试 Slurm debug_shared 队列。
9. 告诉用户 VS Code Remote-SSH 连接方式和使用规则。

下面以新增用户：

```text
user5
```

为例。

### 25.2 创建 Linux 用户

```bash
sudo adduser user5
```

按照提示设置密码。

不要把普通用户加入 `sudo` 组。

检查用户组：

```bash
groups user5
```

如果看到 `sudo`，移除：

```bash
sudo deluser user5 sudo
```

### 25.3 创建个人目录

创建个人项目目录：

```bash
sudo mkdir -p /data/users/user5/project
sudo chown -R user5:user5 /data/users/user5
sudo chmod 700 /data/users/user5
```

如果希望组内可以只读查看该用户目录，可以改成：

```bash
sudo chmod 750 /data/users/user5
```

更安全的默认值是：

```bash
700
```

### 25.4 创建日志目录

```bash
sudo mkdir -p /data/logs/user5
sudo chown user5:user5 /data/logs/user5
sudo chmod 700 /data/logs/user5
```

用户的 sbatch 脚本中建议写：

```bash
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err
```

这样 `user5` 的日志会进入：

```bash
/data/logs/user5/
```

### 25.5 创建 checkpoint 目录

```bash
sudo mkdir -p /data/checkpoints/user5
sudo chown user5:user5 /data/checkpoints/user5
sudo chmod 700 /data/checkpoints/user5
```

用户脚本中建议写：

```bash
export CKPT_DIR=/data/checkpoints/$USER/$SLURM_JOB_NAME/$SLURM_JOB_ID
mkdir -p "$CKPT_DIR"
```

### 25.6 配置 SSH 登录

有两种方式。

#### 方式 1：密码登录

管理员创建用户时设置密码后，用户可以直接：

```bash
ssh user5@服务器IP
```

如果服务器禁用了密码登录，则使用 SSH key。

#### 方式 2：SSH key 登录

让用户在自己电脑上生成 SSH key：

```powershell
ssh-keygen -t ed25519 -C "user5"
```

用户把公钥内容发给管理员。

公钥通常在用户本地电脑：

```powershell
type C:\Users\用户名\.ssh\id_ed25519.pub
```

管理员在服务器上创建：

```bash
sudo mkdir -p /home/user5/.ssh
sudo vim /home/user5/.ssh/authorized_keys
```

把用户公钥粘贴进去。

设置权限：

```bash
sudo chown -R user5:user5 /home/user5/.ssh
sudo chmod 700 /home/user5/.ssh
sudo chmod 600 /home/user5/.ssh/authorized_keys
```

测试：

```bash
ssh user5@服务器IP
```

### 25.7 初始化用户 Conda 环境

用户第一次登录后，可以安装自己的 Miniconda，或者使用管理员提供的共享 Conda。

如果使用个人 Miniconda：

```bash
cd ~
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
```

重新登录后创建环境：

```bash
conda create -n seg python=3.10
conda activate seg
```

如果使用共享环境，只允许读取，不建议普通用户修改共享环境。

### 25.8 给用户一份默认 debug.sh

管理员可以在用户项目目录放一个模板：

```bash
sudo -u user5 vim /data/users/user5/project/debug.sh
```

内容：

```bash
#!/bin/bash
set -euo pipefail

#SBATCH --job-name=debug_test
#SBATCH --partition=debug_shared
#SBATCH --gres=shard:25
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

echo "Job ID: $SLURM_JOB_ID"
echo "User: $USER"
echo "Node: $SLURMD_NODENAME"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo ""
nvidia-smi

source ~/miniconda3/etc/profile.d/conda.sh
conda activate seg

cd /data/users/$USER/project

python debug.py
```

### 25.9 测试新用户 Slurm 权限

切换到新用户：

```bash
su - user5
```

测试队列：

```bash
sinfo
squeue
```

测试 debug 共享 GPU：

```bash
srun --partition=debug_shared --gres=shard:10 nvidia-smi
```

如果可以看到 GPU 信息，说明 Slurm 可以正常使用。

提交一个测试任务：

```bash
cd /data/users/user5/project
sbatch debug.sh
squeue -u user5
```

查看日志：

```bash
ls -lh /data/logs/user5
tail -f /data/logs/user5/debug_test-任务ID.out
```

### 25.10 新用户 VS Code 连接配置

让用户在自己电脑的 VS Code 安装：

```text
Remote - SSH
```

本地 SSH 配置示例：

```sshconfig
Host lab-gpu-user5
  HostName 服务器IP
  User user5
  Port 22
```

如果使用 SSH key：

```sshconfig
Host lab-gpu-user5
  HostName 服务器IP
  User user5
  Port 22
  IdentityFile C:\Users\用户名\.ssh\id_ed25519
```

连接后打开目录：

```bash
/data/users/user5/project
```

告诉用户：

- VS Code 用来写代码。
- 长任务必须通过 `sbatch` 提交。
- 不要直接在 VS Code 终端长期运行 `python train.py`。
- 不要修改 `/data/datasets`。
- 不要进入其他用户目录修改文件。

### 25.11 新用户管理员检查清单

新增用户后，管理员检查：

```bash
groups user5
ls -ld /data/users/user5
ls -ld /data/logs/user5
ls -ld /data/checkpoints/user5
ls -ld /home/user5/.ssh
ls -l /home/user5/.ssh/authorized_keys
```

应该满足：

- `user5` 不在 `sudo` 组。
- `/data/users/user5` 归 `user5:user5`。
- `/data/logs/user5` 归 `user5:user5`。
- `/data/checkpoints/user5` 归 `user5:user5`。
- `.ssh` 权限是 `700`。
- `authorized_keys` 权限是 `600`。

再测试：

```bash
su - user5
srun --partition=debug_shared --gres=shard:10 nvidia-smi
```

如果通过，新用户就可以正常使用服务器。

---

## 26. 最后 Tips：用户不按规则使用会怎样

### 26.1 直接在 VS Code 终端跑长任务的问题

如果用户不通过 Slurm，直接在 VS Code 终端运行：

```bash
python train.py
```

可能出现这些问题：

- 任务不会进入 Slurm 队列。
- 不会按 `debug_shared/train_exclusive/bigtrain` 规则申请资源。
- 不会自动排队，可能直接抢占 GPU。
- 不会自动保存标准日志到 `/data/logs/%u/%x-%j.out`。
- 管理员不容易从 `squeue` 里看到这个任务。
- SSH 或 VS Code 断开后，任务可能中断。
- 如果直接占用任意一张 GPU，会影响 Slurm 的共享和独占调度。
- 如果直接占用原本可用于 train_exclusive 的空闲 GPU，会影响正式训练。
- 如果长期占用两张 GPU，会影响整个组的使用。

所以长任务必须使用：

```bash
sbatch train.sh
```

或者：

```bash
sbatch debug.sh
sbatch bigtrain.sh
```

### 26.2 如果用户修改公共数据或别人目录

如果权限设置正确，普通用户不能修改：

```bash
/data/datasets
/data/users/其他用户
/etc/slurm
/etc/munge
```

如果权限没有设置好，例如某些目录用了：

```bash
chmod 777
```

就可能出现：

- 误删公共数据集。
- 覆盖别人的代码。
- 覆盖别人的日志。
- 覆盖别人的 checkpoint。
- 修改共享 Conda 环境导致别人代码跑不起来。

所以管理员必须避免对关键目录使用长期 `777` 权限。

### 26.3 管理员如何发现违规 GPU 进程

先查看 GPU：

```bash
nvidia-smi
```

找到进程 ID 后查看是谁：

```bash
ps -fp 进程ID
```

也可以查看该用户当前 Slurm 任务：

```bash
squeue -u 用户名
```

如果 `nvidia-smi` 里有 GPU 进程，但 `squeue -u 用户名` 没有对应任务，通常说明用户可能绕过 Slurm 直接运行了训练。

### 26.4 管理员处理顺序

建议按这个顺序处理：

1. 先提醒用户，要求停止直接运行的长任务。
2. 要求用户改用 `sbatch` 提交。
3. 如果影响他人训练，管理员可以终止该进程。
4. 多次违规，可以临时暂停该用户账号。
5. 严重破坏数据或环境时，恢复备份并重新检查目录权限。

提醒所有在线用户：

```bash
wall "请停止未通过 Slurm 提交的 GPU 长任务，长任务必须使用 sbatch。"
```

正常终止进程：

```bash
sudo kill 进程ID
```

如果进程无响应，再强制终止：

```bash
sudo kill -9 进程ID
```

### 26.5 临时暂停违规用户

如果用户多次违规，可以临时锁定账号密码登录：

```bash
sudo usermod -L user5
```

恢复：

```bash
sudo usermod -U user5
```

注意：

- 锁定账号是管理措施，不建议随便使用。
- 组内服务器一般先提醒，再处理。
- 更重要的是把目录权限、Slurm 规则和日志追踪做好。

### 26.6 最简规则

可以直接发给所有用户：

```text
1. VS Code 只负责写代码和看日志。
2. 长任务必须 sbatch。
3. 小实验走 debug_shared。
4. 正式训练走 train_exclusive。
5. 双卡训练走 bigtrain。
6. 不要修改 /data/datasets。
7. 不要修改别人的 /data/users/用户名。
8. 不要修改共享 Conda 环境。
9. checkpoint 写到自己的 /data/checkpoints/用户名。
10. 违规占用 GPU 的进程会被管理员停止。
```

