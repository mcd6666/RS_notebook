# 你们组内如果刚开始共享，不建议一上来就搞 K8s。可以分三档。

## 方案 1：最简单，适合 2–5 人

### 管理方式

每个人一个 Linux 用户账号：

adduser user1
adduser user2
adduser user3

大家通过 SSH 登录。

使用时手动指定 GPU：

CUDA_VISIBLE_DEVICES=0 python train.py
CUDA_VISIBLE_DEVICES=1 python train.py

或者在脚本里写：

export CUDA_VISIBLE_DEVICES=0
python train.py
### 适合情况
组里人不多
大家沟通方便
主要是轮流跑实验
暂时不需要严格排队
缺点
容易抢 GPU
有人忘记释放资源
可能一个人占两张卡
需要人工协调

这个方案简单，但管理比较原始。

## 方案 2：推荐，使用 Slurm 管理 GPU

如果你们组有 3 人以上，并且会经常跑实验，我建议直接上 Slurm。

Slurm 是高校、实验室、超算中心常用的任务调度系统。大家不是直接抢 GPU，而是提交任务。

例如用户提交：

sbatch train.sh

train.sh 里面写：

#!/bin/bash
#SBATCH --job-name=seg_train
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --output=logs/%j.out

source ~/miniconda3/bin/activate seg
python train.py

这样系统会自动分配 GPU。

好处
自动排队
自动分配 GPU
可以限制每个人最多用几张卡
可以查看任务状态
可以保留日志
不会互相抢资源
适合组内共享

常用命令：

squeue          # 查看队列
sinfo           # 查看节点状态
scancel 任务ID   # 取消任务
sacct           # 查看历史任务

我认为你们组共享 2 张卡，Slurm 是最合适的方案。

## 方案 3：K8s，不建议一开始就上

K8s 适合：

多台服务器
很多用户
容器化环境成熟
需要 Web 平台
需要自动调度服务
需要模型部署

但如果你现在只有一台 2 卡服务器，上 K8s 反而复杂。

你会遇到：

NVIDIA Device Plugin
镜像构建
PVC 挂载
权限管理
网络配置
日志收集
存储管理
GPU 调度策略

除非你后面要做完整平台，否则现在不建议优先 K8s。

# 组内目录建议

不要让所有人乱放数据。建议这样规划：

/data
  /datasets        # 公共数据集，只读
  /projects        # 项目目录
  /users           # 每个人个人目录
  /checkpoints     # 模型权重
  /logs            # 训练日志
  /shared          # 共享文件

例如：

/data/users/zhangsan
/data/users/lisi
/data/projects/spartina_seg
/data/projects/water_vegetation
/data/datasets/LoveDA
/data/datasets/GF2

权限可以这样：

chmod -R 755 /data/datasets
chmod -R 700 /data/users/zhangsan
chmod -R 775 /data/projects

这样避免：

误删别人的数据
覆盖别人的权重
训练日志混乱
数据集重复存很多份

# GPU 使用规则建议

组内最好一开始就定规则，不然后面容易乱。

可以这样规定：

1. 默认每人最多占用 1 张 GPU。
2. 需要占用 2 张 GPU 时，提前在群里说明。
3. 长任务必须用 Slurm 提交。
4. 禁止直接在登录 shell 里长期跑训练，必须用 tmux/screen/slurm。
5. 每个任务必须写日志。
6. checkpoint 定期清理。
7. 公共数据集目录不允许随意修改。
8. 每周清理无用中间结果。


# 软件管理上：

小组 2–3 人：SSH + CUDA_VISIBLE_DEVICES + tmux
小组 3–8 人：Slurm
多台服务器：Slurm 集群
需要平台化服务：再考虑 K8s

一句话：既然要共享给组内成员跑模型，就按“实验室 GPU 服务器节点”来建设，不要按个人工作站来配。优先服务器 + Slurm，比普通工作站更稳、更好管。