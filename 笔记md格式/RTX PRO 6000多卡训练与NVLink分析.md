# RTX PRO 6000 多卡训练、NVLink 与采购方案分析

## 一、核心结论

当前目标是用一台服务器配置 2 张或 4 张 RTX PRO 6000 96GB 显卡，训练 GF2 遥感数据，并可能使用 DINOv3-7B 这类大视觉 backbone。

简要结论：

```text
1. RTX PRO 6000 96GB 适合 GF2 遥感训练，尤其适合大 patch、大 batch、视觉基础模型冻结或轻量微调。

2. 普通 DDP 不会把 2 张 96GB 合成 192GB，也不会把 4 张合成 384GB。

3. 没有 NVLink 不等于不能多卡训练。对普通 DDP 来说，PCIe 多卡通常仍然明显快于单卡。

4. 如果模型单卡 96GB 放得下，优先用 DDP；如果模型单卡放不下，再考虑 FSDP / ZeRO-3。

5. DINOv3-7B 不建议一开始全量微调，更推荐冻结 backbone、训练分割头，或者 LoRA / adapter 微调。

6. Spectrum-X 不是 NVLink 替代品。它主要解决多台服务器之间的网络通信，不解决单机内部 GPU 互联。

7. 如果主要是 GF2 遥感训练，2 卡 RTX PRO 6000 已经很强；如果多人共用、频繁扫实验、DINOv3-7B 轻量微调较多，4 卡更合适。
```

---

## 二、任务背景和关键问题

计划场景：

```text
数据：GF2 高分辨率遥感影像
任务：语义分割、变化检测、目标检测、地物分类等
模型：UNet、DeepLabV3+、HRNet、SegFormer、Swin、Mask2Former、DINOv3-7B 等
硬件：2 张或 4 张 RTX PRO 6000 96GB
```

主要问题：

```text
NVLink 是什么
没有 NVLink 会不会影响多卡训练
96GB + 96GB 能不能当 192GB 用
DDP、FSDP、ZeRO-3、Tensor Parallel 分别干什么
RTX PRO 6000 和 A100、H100、H200、L40S 等训练卡怎么选
DINOv3-7B 加进来后是否还能高效训练
Spectrum-X 能不能解决没有 NVLink 的问题
目前可落地方案和成本如何
```

---

## 三、几个核心概念

### 1. NVLink

NVLink 是 NVIDIA 的 GPU 间高速互联技术。

简单理解：

```text
PCIe：普通 GPU 和主机、GPU 和 GPU 之间的数据通道
NVLink：更快的 GPU 和 GPU 直连通道
```

多卡训练时，GPU 之间需要同步梯度、传输参数或激活值。NVLink 可以提高 GPU 间通信速度，降低通信瓶颈。

但是：

```text
没有 NVLink 不等于不能多卡训练。
```

普通 DDP 多卡训练即使只走 PCIe，也通常比单卡快。NVLink 对 FSDP、ZeRO-3、Tensor Parallel 这类通信更频繁的方法更重要。

### 2. Spectrum-X

Spectrum-X 是 NVIDIA 面向 AI 数据中心的高速以太网平台，主要用于多台服务器之间的通信。

它通常包括：

```text
Spectrum Ethernet switch
BlueField / SuperNIC
ConnectX 网卡
LinkX 线缆
RoCE / RDMA
NCCL 网络通信优化
```

它和 NVLink 的区别：

```text
NVLink：解决同一台服务器内部 GPU 和 GPU 的高速互联
Spectrum-X：解决多台服务器之间的高速 AI 网络通信
```

所以：

```text
单台 2 卡或 4 卡 RTX PRO 6000 服务器：
Spectrum-X 不能替代 NVLink，也不是刚需。

多台 GPU 服务器组成训练集群：
Spectrum-X 才有明显价值。
```

### 3. 显存是否能合并

普通 DDP 不能把多张显卡显存自动合并。

两张 96GB 显卡做 DDP 时：

```text
GPU 0：一份完整模型 + 一部分 batch
GPU 1：一份完整模型 + 另一部分 batch
```

每张卡仍然只能使用自己的 96GB。

如果想让大模型分摊到多张卡上，需要：

```text
FSDP
DeepSpeed ZeRO-3
Tensor Parallel
Pipeline Parallel
transformers device_map
vLLM tensor parallel
```

这些是软件层面的模型切分，不是硬件把显存自动合并。

---

## 四、多卡训练方法怎么选

最简单记法：

```text
DDP：分数据
FSDP / ZeRO-3：分模型参数、梯度、优化器状态
Tensor Parallel：分模型内部的大矩阵计算
```

### 1. DDP

DDP 全称 DistributedDataParallel。

分工方式：

```text
GPU 0：完整模型 + 第 1 份数据
GPU 1：完整模型 + 第 2 份数据
GPU 2：完整模型 + 第 3 份数据
GPU 3：完整模型 + 第 4 份数据
```

每张卡都有完整模型，各自处理不同数据，反向传播后同步梯度。

适合：

```text
模型单卡能放下
想提高训练速度
想增大总 batch size
普通遥感分割、检测、分类任务
DINOv3-7B 冻结 backbone 或轻量微调
```

不适合：

```text
模型单卡放不下
```

对 GF2 普通遥感模型，DDP 是最推荐、最稳定的多卡训练方式。

### 2. FSDP / ZeRO-3

FSDP 和 DeepSpeed ZeRO-3 的目标是让单卡放不下的大模型可以训练。

它们会拆分：

```text
模型参数
梯度
优化器状态
```

适合：

```text
DINOv3-7B 这类大模型
单卡 96GB 放不下全量训练
需要全量微调或较重微调
```

代价：

```text
通信更多
配置更复杂
checkpoint 更麻烦
没有 NVLink 时更容易被 PCIe 限制
训练速度不一定线性提升
```

简单理解：

```text
DDP 主要是为了快
FSDP / ZeRO-3 主要是为了放得下
```

### 3. Tensor Parallel

Tensor Parallel 是把模型内部的一次大矩阵计算拆给多张卡。

例如 Transformer 中：

```text
Y = XW
```

Tensor Parallel 会把大矩阵 `W` 切开，交给多张卡一起算。

适合：

```text
超大 Transformer
大模型推理
大模型预训练
单层太大，需要多卡一起算
```

问题：

```text
每一层都可能跨卡通信
通信频率很高
没有 NVLink / NVSwitch 时效率容易下降
```

对当前 GF2 遥感训练，Tensor Parallel 不是首选。

---

## 五、RTX PRO 6000 的定位和应用场景

RTX PRO 6000 Blackwell 不是传统意义上专门给大模型训练集群准备的 H100/H200/B200，也不是普通消费级游戏卡。它更像是一张通用型专业 GPU：

```text
大显存
强 AI 计算
强图形/渲染能力
支持 ECC
适合工作站和企业服务器
```

适合场景：

```text
计算机视觉训练
遥感语义分割 / 检测 / 分类
医学影像训练
大分辨率图像模型
多模态模型推理
中小规模大模型微调
DINOv3-7B 冻结或 LoRA / adapter
3D 渲染 / Omniverse / 数字孪生
视频编解码和 AI 视频处理
虚拟工作站 / vGPU
单机多任务训练和推理
```

不太适合：

```text
超大模型预训练
长期大规模 LLM 全量训练
强依赖 NVLink / NVSwitch 的 Tensor Parallel
需要 HBM 极高带宽的 HPC 或大模型训练
多节点大规模 AI 集群
```

对 GF2 遥感数据的优势：

```text
96GB 显存适合大 patch
适合大 batch DDP
适合高分辨率遥感图像
适合同时跑多个实验
适合 DINOv3-7B 冻结特征或轻量微调
```

主要短板：

```text
GDDR7 显存带宽低于 H100/H200 的 HBM
单机 GPU 间通常不如 HGX 平台的 NVLink / NVSwitch
4 卡满载功耗和散热压力大
不是最优的大模型全量训练卡
```

---

## 六、常见训练卡对比

| GPU | 显存 | 典型定位 | 适合场景 | 主要短板 |
|---|---:|---|---|---|
| RTX 4090 | 24GB | 消费级高性能 | 个人实验、小模型、推理、普通视觉训练 | 显存小、无 ECC、服务器部署不友好 |
| RTX 5090 | 32GB | 消费级高性能 | 个人 AI、推理、中小模型训练 | 显存仍偏小、无企业特性 |
| RTX 6000 Ada | 48GB | 专业工作站 | 视觉训练、渲染、推理、工作站 | 显存比 PRO 6000 小 |
| L40S | 48GB | 数据中心通用卡 | 推理、渲染、视频、部分训练 | 无 NVLink，显存 48GB |
| RTX PRO 6000 Blackwell | 96GB | 专业 AI + 图形 + 企业服务器 | 遥感、视觉大模型、推理、轻量微调、渲染 | 不如 H100/H200 适合大模型全量训练 |
| A100 80GB | 80GB | 数据中心训练卡 | 深度学习训练、HPC、FSDP、DDP | 架构较老，FP8 能力不如 Hopper/Blackwell |
| H100 80GB / H100 NVL | 80GB / 94GB | 高端 AI 训练/推理 | 大模型训练、FSDP、Tensor Parallel、HPC | 成本高 |
| H200 | 141GB | 高端大模型训练/推理 | LLM、大模型推理、HPC、大显存任务 | 成本很高 |
| B200 / GB200 | 更高 | 最新一代大模型平台 | 大规模训练、推理集群、AI 工厂 | 成本和平台要求最高 |

### 1. RTX PRO 6000 和 A100

RTX PRO 6000 优势：

```text
96GB 显存，比 A100 80GB 更大
Blackwell 架构更新
图形、渲染、视频能力更强
适合工作站和通用企业 AI
```

A100 优势：

```text
HBM2e 带宽更高
数据中心训练生态成熟
SXM / HGX 平台有 NVLink
更适合传统深度学习训练和 HPC
```

### 2. RTX PRO 6000 和 H100/H200

H100/H200 是更明确的大模型训练和 HPC 卡。

H100/H200 优势：

```text
HBM 显存带宽高很多
NVLink / NVSwitch 生态成熟
FP8 Transformer Engine 适合大模型
FSDP / ZeRO / Tensor Parallel 更合适
多机多卡训练生态更强
```

RTX PRO 6000 优势：

```text
96GB 显存很大
单卡性价比可能更好
图形和视频能力强
部署在工作站或通用服务器更灵活
适合视觉和多模态任务
```

### 3. RTX PRO 6000 和 L40S / RTX 6000 Ada

L40S 和 RTX 6000 Ada 常见于推理、渲染、视频、普通视觉训练。

RTX PRO 6000 相比它们：

```text
显存从 48GB 提升到 96GB
显存带宽更高
Blackwell 架构更新
AI 低精度能力更强
更适合大图像、大 batch 和较大模型
```

### 4. RTX PRO 6000 和 RTX 4090/5090

RTX 4090/5090 优势是便宜、单卡性能强，适合个人实验。

正式训练服务器里，消费卡的问题是：

```text
显存小
没有 ECC
散热和多卡密度不如服务器卡
长时间满载稳定性和保修策略不如专业卡
多卡服务器集成不友好
```

---

## 七、GF2 遥感训练速度估计

GF2 遥感训练通常会把大图切成 patch：

```text
512 x 512
1024 x 1024
2048 x 2048
```

粗略吞吐估计：

| 场景 | 单张 RTX PRO 6000 | 2 卡 DDP | 4 卡 DDP |
|---|---:|---:|---:|
| 512 patch，UNet/DeepLab 类 | 150-400 patch/s | 250-750 patch/s | 450-1300 patch/s |
| 1024 patch，UNet/DeepLab 类 | 35-120 patch/s | 60-220 patch/s | 100-400 patch/s |
| 1024 patch，Transformer 类 | 8-40 patch/s | 14-75 patch/s | 25-140 patch/s |
| 2048 patch，大模型 | 2-15 patch/s | 3.5-28 patch/s | 6-50 patch/s |

这些不是保证值，只是工程估算。真实速度需要用自己的代码和数据 benchmark。

例如切出 10 万个 1024 patch，单卡速度是 60 patch/s：

```text
单卡：
100000 / 60 = 1667 秒，约 28 分钟/epoch

2 卡，按 1.8 倍：
60 x 1.8 = 108 patch/s
100000 / 108 = 926 秒，约 15 分钟/epoch

4 卡，按 3.3 倍：
60 x 3.3 = 198 patch/s
100000 / 198 = 505 秒，约 8.4 分钟/epoch
```

实际加速比可以先按下面估计：

```text
2 卡 DDP：约 1.5x - 1.9x 单卡
4 卡 DDP：约 2.4x - 3.5x 单卡
```

---

## 八、DINOv3-7B 加入后的判断

DINOv3-7B 是 7B 参数级别的大视觉 backbone，和普通 UNet、DeepLab、SegFormer 不是一个量级。

7B 参数只看权重：

```text
FP16 / BF16 权重：
7B x 2 bytes = 14GB 左右
```

但训练时还要保存：

```text
梯度
优化器状态
activation
临时 buffer
分割头 / decoder
```

所以全量微调时，显存需求可能远超 96GB。

建议路线：

```text
第一选择：冻结 DINOv3-7B，只训练分割头
第二选择：冻结大部分层，只微调后几层
第三选择：LoRA / adapter
第四选择：FSDP / ZeRO-3 全量微调
```

对不同硬件的判断：

```text
2 张 RTX PRO 6000：
适合 DINOv3-7B 冻结、特征提取、分割头训练、LoRA / adapter。
不建议全量微调。

4 张 RTX PRO 6000：
适合 DINOv3-7B 冻结、LoRA / adapter。
可以尝试 FSDP / ZeRO-3 全量微调，但不是最优方案。

H100 / H200：
更适合 DINOv3-7B 全量微调和更大模型训练。
```

### 遥感 patch 尺寸问题

假设 ViT patch size 是 14：

```text
518 x 518：
约 37 x 37 = 1369 tokens

1024 x 1024：
约 73 x 73 = 5329 tokens

2048 x 2048：
约 146 x 146 = 21316 tokens
```

Transformer attention 的计算量大致和 token 数平方相关。

所以：

```text
518 patch：比较现实
768 patch：开始吃紧
1024 patch：7B backbone 会很重
2048 patch：不建议直接用 7B ViT 全局 attention 跑
```

GF2 + DINOv3-7B 更实际的路线：

```text
切 patch
冻结 backbone
缓存特征
训练轻量分割头
做多尺度推理和滑窗融合
```

---

## 九、没有 NVLink 怎么办

没有 NVLink 时，不是不能做多卡，而是要避免选择强依赖卡间通信的训练方式。

核心思路：

```text
能用 DDP 就优先 DDP
能冻结 backbone 就冻结 backbone
能用 LoRA / adapter 就不要直接全量微调
能减少跨卡通信就减少跨卡通信
```

### 1. 优先确认 PCIe 拓扑

采购服务器时要问清楚：

```text
2 卡或 4 卡是否都是 PCIe x16
显卡之间是否经过同一个 PCIe switch
是否跨 CPU
是否有足够 PCIe lane
是否会降到 x8 或更低
```

机器到手后执行：

```powershell
nvidia-smi topo -m
```

优先级大致是：

```text
NV# > PIX > PXB > PHB > SYS
```

如果没有 NVLink，至少希望多张卡之间尽量是：

```text
PIX 或 PXB
```

尽量避免 4 卡之间大量出现：

```text
PHB 或 SYS
```

### 2. 优先使用 DDP

对 GF2 普通遥感任务：

```text
DDP + AMP + 大 batch
```

DDP 的通信主要发生在反向传播同步梯度时，不像 Tensor Parallel 那样每一层都频繁跨卡通信。

如果模型单卡 96GB 能放下，优先不要用 FSDP / ZeRO-3。

### 3. 增大每卡 batch，减少通信占比

多卡训练是否高效，取决于：

```text
计算时间 / 通信时间
```

建议：

```text
尽量提高 per-GPU batch size
使用 AMP / BF16
必要时使用梯度累积
使用 no_sync() 减少不必要同步
```

### 4. 优化数据读取

很多时候多卡没有跑满，不是因为没有 NVLink，而是因为数据喂不动。

建议：

```text
使用 NVMe SSD
提前切好 patch
必要时缓存为 LMDB / WebDataset / Zarr / HDF5
DataLoader 设置 num_workers
开启 pin_memory
训练时监控 GPU 利用率
```

如果 GPU 利用率经常低于 70%，优先查数据管线。

### 5. 避免在 PCIe 上强行 Tensor Parallel

对当前场景：

```text
GF2 普通模型：不要用 Tensor Parallel
DINOv3-7B 冻结或 LoRA：优先 DDP
DINOv3-7B 全量微调：优先 FSDP / ZeRO-3，而不是 Tensor Parallel
大模型推理单卡放不下：再考虑 Tensor Parallel 或 device_map
```

---

## 十、可选解决方案和成本估算

下面成本是按 2026 年 5 月公开价格粗略估算，实际采购要以国内代理商、整机厂商、税费、保修和交付周期为准。

公开价格粗略参考：

```text
RTX PRO 6000 Blackwell Workstation Edition：
美国零售大约 8000-9500 美元/张

RTX PRO 6000 Blackwell Server Edition：
海外渠道大约 8600 欧元或 11600 美元/张

汇率粗略按：
1 美元 ≈ 6.8 元人民币
```

单张 RTX PRO 6000 96GB 裸卡可以粗略理解为：

```text
约 5.5 万 - 8 万元人民币/张
```

国内实际采购可能更高，因为会叠加：

```text
增值税
代理商利润
服务器整机集成
电源和散热设计
保修服务
交付周期
```

### 方案 A：2 卡 RTX PRO 6000 本地服务器

适合：

```text
GF2 普通语义分割/检测训练
DINOv3-7B 冻结 backbone
DINOv3-7B LoRA / adapter
个人或小团队主要训练机器
```

成本估算：

```text
GPU 成本：
2 x RTX PRO 6000 ≈ 11 万 - 16 万元

整机其他部分：
CPU、主板、内存、NVMe、电源、机箱、散热 ≈ 8 万 - 15 万元

整机大致：
约 20 万 - 35 万元
```

评价：

```text
最稳妥的起点。
成本相对可控，DDP 效率通常较好，供电和散热压力比 4 卡小。
```

### 方案 B：4 卡 RTX PRO 6000 本地服务器

适合：

```text
大规模 GF2 实验
多人共用
频繁扫参数
DINOv3-7B 冻结、LoRA、adapter
尝试 FSDP / ZeRO-3
```

成本估算：

```text
GPU 成本：
4 x RTX PRO 6000 ≈ 22 万 - 32 万元

整机其他部分：
服务器平台、双路 CPU 或高 PCIe 通道平台、512GB 内存、高速 NVMe、电源、散热 ≈ 15 万 - 30 万元

整机大致：
约 40 万 - 70 万元
```

评价：

```text
吞吐量更高，更适合多人共用。
但单卡约 600W，4 卡 GPU 功耗约 2400W，对电源、散热、机房环境要求高。
没有 NVLink 时，4 卡 FSDP / ZeRO-3 效率会打折。
```

### 方案 C：本地 2 卡 + 云端 H100/A100 验证

适合：

```text
本地长期训练 GF2
偶尔验证 DINOv3-7B 全量微调是否值得做
不想一开始就投入 4 卡服务器
```

云 GPU 粗略价格：

```text
A100 80GB：约 2 美元/小时上下
H100 80GB：约 2.5 - 3.5 美元/小时

4 张 H100 连续跑 100 小时：
约 7000 - 9500 元人民币
```

评价：

```text
适合先做工程验证。
避免买了 4 卡后发现主要瓶颈在数据和代码。
```

### 方案 D：H100/H200/B200 数据中心服务器

适合：

```text
明确要做 DINOv3-7B 全量微调
需要更强 NVLink / NVSwitch
未来可能做更大模型训练
预算充足
```

评价：

```text
最适合大模型训练，但对普通 GF2 遥感模型可能性能过剩。
采购成本、机房、电力、散热、运维要求都更高。
```

---

## 十一、推荐采购路线

如果目前还没有真实 benchmark，不建议直接按最贵方案买。

更稳妥的路线：

```text
第一步：
先用 2 卡 RTX PRO 6000 建立稳定训练平台

第二步：
把 GF2 常规模型的 DDP、AMP、DataLoader、NVMe 读取调好

第三步：
用 DINOv3-7B 冻结 backbone 或 LoRA 跑通完整流程

第四步：
如果确实需要全量微调 7B，再租云端 H100 做 50-100 小时验证

第五步：
确认 4 卡收益明显后，再采购 4 卡本地服务器
```

简化选择：

```text
性价比优先：
2 卡 RTX PRO 6000 本地服务器

吞吐和多人共用优先：
4 卡 RTX PRO 6000 本地服务器

验证大模型全量微调：
先租 H100/A100 云 GPU

明确长期做大模型训练：
再考虑 H100/H200/B200 服务器
```

---

## 十二、采购和验收清单

采购 RTX PRO 6000 多卡服务器时，建议要求厂商明确：

```text
1. 提供 nvidia-smi topo -m 样例
2. 确认每张 GPU 至少 PCIe Gen5 x16，或明确实际链路
3. 确认 4 卡是否跨 CPU
4. 确认是否支持长时间满载训练
5. 确认电源、散热、机箱风道
6. 确认 Linux + CUDA + NCCL + PyTorch 多卡环境
7. 交付时跑 DDP benchmark
```

验收时建议跑：

```text
1 卡训练速度
2 卡 DDP 训练速度
4 卡 DDP 训练速度
nvidia-smi topo -m
GPU 利用率
DataLoader 吞吐
长时间满载温度和功耗
```

可接受加速比参考：

```text
2 卡 >= 1.5x 单卡
4 卡 >= 2.4x 单卡
```

如果达到这个水平，说明即使没有 NVLink，这台机器也能用于有效多卡训练。

---

## 十三、最终建议

对当前 GF2 遥感 + DINOv3-7B 设想，建议如下：

```text
1. 如果主要是个人或小团队做 GF2 遥感训练：
   2 张 RTX PRO 6000 96GB 是很强且相对稳妥的方案。

2. 如果需要多人共用、频繁跑实验、DINOv3-7B LoRA / adapter 较多：
   4 张 RTX PRO 6000 96GB 更合适。

3. 如果目标变成长期大模型全量微调或预训练：
   RTX PRO 6000 不是最优，应优先考虑 H100/H200/B200。

4. 如果担心没有 NVLink：
   不要直接否定 RTX PRO 6000，多数 GF2 DDP 训练仍然有效。
   重点验收 PCIe 拓扑和实际 DDP 加速比。

5. 如果考虑 Spectrum-X：
   只有未来扩展到多台 GPU 服务器时才值得重点考虑。
   单机 2 卡或 4 卡不需要把 Spectrum-X 当成 NVLink 替代品。
```

最终一句话：

```text
RTX PRO 6000 适合高分辨率遥感视觉训练和视觉基础模型轻量使用；
H100/H200 更适合重度大模型训练；
没有 NVLink 时，优先把 DDP、PCIe 拓扑、数据读取和 batch size 调好。
```

---

## 参考链接

- NVIDIA RTX PRO 6000 Blackwell Workstation Edition: https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/rtx-pro-6000/
- NVIDIA RTX PRO 6000 Blackwell Server Edition: https://www.nvidia.com/en-eu/data-center/rtx-pro-6000-blackwell-server-edition/
- NVIDIA NVLink Bridges: https://www.nvidia.com/en-us/products/workstations/nvlink-bridges/
- NVIDIA Spectrum Ethernet Platform: https://www.nvidia.com/en-us/networking/products/ethernet
- NVIDIA Spectrum-X Ethernet Networking Platform: https://www.nvidia.com/en-au/networking/spectrumx/
- NVIDIA A100 Tensor Core GPU: https://www.nvidia.com/en-us/data-center/a100/
- NVIDIA H100 Tensor Core GPU: https://www.nvidia.com/en-us/data-center/h100/
- NVIDIA H200 GPU: https://www.nvidia.com/en-us/data-center/h200/
- NVIDIA L40S GPU: https://www.nvidia.com/en-us/data-center/l40s/
- NVIDIA RTX 6000 Ada Generation: https://www.nvidia.com/en-us/products/workstations/rtx-6000/
- NVIDIA GeForce RTX 5090: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/
- PyTorch DistributedDataParallel: https://pytorch.org/docs/stable/generated/torch.nn.parallel.DistributedDataParallel.html
- PyTorch FSDP: https://pytorch.org/docs/stable/fsdp.html
- DeepSpeed ZeRO: https://www.deepspeed.ai/tutorials/zero/
- Meta DINOv3: https://ai.meta.com/dinov3/
- B&H RTX PRO 6000 Blackwell Workstation Edition: https://www.bhphotovideo.com/c/product/1895402-REG/nvidia_900_5g144_2200_000_rtx_pro_6000_blackwell.html
- Newegg RTX PRO 6000 Blackwell Workstation Edition: https://www.newegg.com/p/N82E16888892011
- Hyperscalers RTX PRO 6000 Blackwell Server Edition: https://www.hyperscalers.com/NVIDIA-RTX-PRO-6000-Blackwell-Server-Edition
- Lambda / H100 / A100 cloud price reference: https://www.synpixcloud.com/blog/lambda-labs-gpu-pricing-2026
- USD/CNY exchange rate reference: https://www.exchange-rates.org/exchange-rate-history/usd-cny-2026
