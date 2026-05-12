# 两种自动大气/相对辐射校正方法对比与选择建议

本文说明当前程序中两种大气/相对辐射校正方法的原理差异、优缺点和推荐使用场景。

当前两种方法都基于同一个基本思想：

```text
以 Sentinel-2 作为参考影像
以几何校正后的 GF 影像作为待校正影像
筛选伪不变地物 PIF
建立 GF -> Sentinel-2 的波段线性关系
将关系应用到整景 GF
```

线性关系为：

```text
Sentinel-2_band = slope * GF_band + intercept
```

最终输出：

```text
*_RRC.TIF
```

## 1. 方法 A：自动 PIF + 鲁棒线性回归

该方法对应较早的自动版本，流程为：

```text
NDVI / NDWI / 亮度过滤
        |
        v
自动稳定 ROI 网格筛选
        |
        v
多波段差异分数选 PIF
        |
        v
鲁棒线性回归
        |
        v
整景应用校正系数
```

### 1.1 筛选逻辑

程序首先用光谱规则排除明显不适合作为 PIF 的像元：

```text
水体
强植被
阴影
过亮或异常像元
```

然后在剩余候选像元中划分 ROI 网格，选择 GF 与 Sentinel-2 多波段差异较小、候选像元比例较高的稳定区域。

在自动 ROI 中，程序计算多波段差异分数，并选取差异分数最低的一批像元作为 PIF。

### 1.2 回归方式

该方法使用鲁棒线性回归：

```text
Sentinel-2 = slope * GF + intercept
```

拟合时会迭代剔除残差异常点，使 PIF 样本上的普通残差更低。

### 1.3 优点

```text
速度较快
实现简单
R2 往往较高
RMSE 往往较低
适合快速批量预览
适合对 Sentinel-2 数值贴合要求较强的场景
```

### 1.4 缺点

```text
更偏向让 PIF 点上的数值拟合最优
对非 PIF 地物的泛化不一定最好
斜率可能更激进
水体、冰面、阴影、农田等区域可能被拉伸得更明显
理论上不如 iMAD + radcal 标准
```

### 1.5 典型现象

该方法的 JSON 报告中常见：

```text
R2 更高
RMSE 更低
slope 略大
影像可能更接近 Sentinel-2 数值
```

但视觉上不一定总是最自然。

## 2. 方法 B：iMAD + ncp=0.95 + 正交回归

该方法是当前更接近原始 `iMadBatch.py + radcalBatch.py` 的版本。

流程为：

```text
NDVI / NDWI / 亮度过滤
        |
        v
自动稳定 ROI 网格筛选
        |
        v
iMAD 迭代变化检测
        |
        v
no-change probability > 0.95 筛选 PIF
        |
        v
正交回归 orthogonal regression
        |
        v
整景应用校正系数
```

### 2.1 iMAD 筛选

iMAD 是一种多变量变化检测方法。它不是只看单个波段差异，而是把 GF 和 Sentinel-2 的多波段信息作为整体比较。

程序会迭代计算两幅影像的多波段差异，并在每次迭代中：

```text
给变化小的像元更高权重
给变化大的像元更低权重
```

当前参数与原始 `iMadBatch.py` 对齐：

```text
IMAD_ITER=100
IMAD_DELTA=0.001
```

也就是最多迭代 100 次，当 canonical correlations 的变化量小于 0.001 时提前停止。

### 2.2 ncp 筛选

iMAD 会得到变化统计量。程序将其转换为 no-change probability：

```text
ncp = 1 - chi2.cdf(chisqr)
```

默认筛选条件为：

```text
ncp > 0.95
```

这与原始 `radcalBatch.py` 的逻辑一致。

### 2.3 正交回归

该方法默认使用正交回归：

```text
REGRESSION_METHOD=orthogonal
```

正交回归同时考虑 GF 和 Sentinel-2 两侧误差，比普通最小二乘更适合两个传感器都有误差的归一化场景。

这与原始 `radcalBatch.py` 中的：

```python
auxil.orthoregress(y[trn], x[trn])
```

思路一致。

### 2.4 优点

```text
更接近原始 iMAD/radcal 理论流程
PIF 筛选更有统计意义
对多波段联合变化更敏感
结果通常更保守
视觉上往往更自然
对非 PIF 地物的泛化更稳
更适合正式成果和工程生产
```

### 2.5 缺点

```text
速度慢于方法 A
R2 可能低一些
RMSE 可能高一些
正交回归不以普通垂直残差最小为目标
如果 ncp>0.95 的像元太少，可能需要退回百分位筛选
```

### 2.6 典型现象

该方法的 JSON 报告中可能出现：

```text
R2 略低
RMSE 略高
slope 更保守
影像整体色调更自然
水体、冰面、阴影等区域不容易被过度拉伸
```

因此，不应只用 R2/RMSE 判断它是否较差。

## 3. 为什么 R2/RMSE 更高不一定代表效果更好

报告中的 R2 和 RMSE 是在筛选出来的 PIF 像元上计算的。

它们反映的是：

```text
在这些 PIF 点上，GF 映射到 Sentinel-2 后的拟合程度
```

但它们不能完全代表：

```text
整景所有地物的校正效果
水体/冰面/植被/阴影等非 PIF 地物的表现
影像整体视觉自然程度
不同景之间的稳定性
```

方法 A 往往会让 PIF 点上的残差更低，因此 R2/RMSE 更好。但它可能更激进。

方法 B 的 R2/RMSE 可能略差，但其 PIF 筛选和回归更接近标准 iMAD/radcal，泛化可能更稳。

## 4. 推荐选择

### 4.1 正式成果推荐

推荐使用：

```bat
set "PIF_METHOD=imad"
set "IMAD_ITER=100"
set "IMAD_DELTA=0.001"
set "PIF_NCP_THRESH=0.95"
set "REGRESSION_METHOD=orthogonal"
```

也就是：

```text
自动 ROI + iMAD + ncp=0.95 + 正交回归
```

适合：

```text
正式生产
成果入库
项目交付
需要尽量接近原始 iMAD/radcal 方法的场景
```

### 4.2 快速预览推荐

如果只是快速测试流程、查看大致结果，可以使用：

```bat
set "PIF_METHOD=score"
set "REGRESSION_METHOD=robust"
```

适合：

```text
快速批量预览
参数调试
检查几何是否正常
大范围初筛
```

### 4.3 速度与精度参数

调试建议：

```bat
set "SAMPLE_STEP=8"
set "ROI_TILE_SIZE=256"
```

正式较高精度处理建议：

```bat
set "SAMPLE_STEP=4"
set "ROI_TILE_SIZE=512"
```

其中：

```text
SAMPLE_STEP 越小，采样越密，速度越慢，结果通常更稳
ROI_TILE_SIZE 越大，ROI 块越大，更接近人工选择较大稳定区域
```

## 5. 判断哪个结果更好

不建议只看单一指标。建议综合判断：

```text
1. 影像整体色调是否自然
2. 是否有明显过亮、过暗或偏色
3. 是否有大片 0 或 65535 饱和
4. 建筑、道路、裸地光谱是否平稳
5. 水体、冰面、阴影等区域是否被过度拉伸
6. PIF 像元数是否足够
7. R2 是否过低
8. RMSE 是否过大
9. slope/intercept 是否异常
10. 多景之间参数是否稳定
```

一般建议阈值：

```text
PIF 像元数 > 1000
R2 > 0.94
RMSE * 10000 < 100
输出无大片饱和
典型地物光谱合理
```

如果方法 A 的 R2/RMSE 更好，但方法 B 的影像视觉和典型地物光谱更自然，应优先考虑方法 B。

## 6. 当前建议

对于当前高分批处理流程，建议采用：

```text
默认主流程：方法 B
快速测试：方法 A
异常场景：两种方法都跑，对比 JSON 报告和典型地物光谱
```

最终选择优先级：

```text
影像视觉和地物光谱合理性
>
多景参数稳定性
>
PIF 数量
>
R2 / RMSE
```

