# 高分影像几何校正 + 自动 PIF 大气/相对辐射校正

本目录整理了一套 Python 批处理流程，用于把原来分散在 `.bat`、Python、IDL/ENVI 和手工 ROI 里的高分预处理流程合并起来。

当前流程包括两步：

1. 几何校正：调用 `satellite-geom.exe` 和 `ba.exe`，输出 `*_ORTHO.TIF`
2. 自动 PIF 校正：用 Sentinel-2 作为参考，自动选择稳定 ROI、筛选伪不变地物，输出 `*_RRC.TIF`

几何校正底层仍依赖已有封装程序：

```text
C:\satgeom\v0.1\satellite-geom.exe
C:\satgeom\v0.1\ba.exe
```

大气/相对辐射校正不再需要手工选择 ROI，也不再调用 IDL 脚本。

详细处理原理见：
PROCESS_PRINCIPLE.md

## 文件说明

```text
run_gf_preprocess.bat     推荐入口，改顶部路径后双击或命令行运行
run_gf_preprocess.py      总入口，串联几何校正和自动 PIF 校正
auto_geometry.py          几何校正流程封装
batch_auto_pif_rrc.py     批量自动 PIF 校正
auto_pif_rrc.py           单景自动 PIF 校正核心
PROCESS_PRINCIPLE.md      几何校正和自动 PIF 校正原理说明
```

## 运行前准备

需要准备：

1. 已融合、重命名后的 GF 影像目录，文件名应类似：

```text
GF1B_..._HRMS_REG.TIF
GF2_..._HRMS_REG.TIF
GF6_..._HRMS_REG.TIF
```

2. Sentinel-2 参考影像。

建议使用已经完成大气校正的 Sentinel-2 反射率影像，并包含 Blue、Green、Red、NIR 四个波段。

3. DEM 文件。

4. `satellite-geom.exe` 和 `ba.exe`。

通常在：

```text
C:\satgeom\v0.1\
```

5. Python 环境。

需要能导入 GDAL：

```powershell
python -c "from osgeo import gdal; print(gdal.VersionInfo())"
```

## 最简单用法

打开 [run_gf_preprocess.bat](</run_gf_preprocess.bat>)，修改顶部这些路径：

```bat
set "IN_FOLDER=F:\pre_process\GYY\RENAME"
set "GEOM_FOLDER=F:\pre_process\GYY\2_geom"
set "RRC_FOLDER=F:\pre_process\GYY\3_rrc"
set "REFERENCE=F:\pre_process\GYY\s2_ref.tif"
set "DEM=F:\pre_process\GYY\dem\N50E120.TIF"
set "SATELLITE_GEOM=C:\satgeom\v0.1\satellite-geom.exe"
set "BA=C:\satgeom\v0.1\ba.exe"
set "SAMPLE_STEP=8"
set "PIF_METHOD=imad"
set "IMAD_ITER=100"
set "IMAD_DELTA=0.001"
set "PIF_NCP_THRESH=0.95"
set "REGRESSION_METHOD=orthogonal"
set "ROI_TILE_SIZE=256"
set "ROI_TOP_PERCENT=20"
set "ROI_MAX_TILES=20"
```

然后在当前目录运行：

```powershell
.\run_gf_preprocess.bat
```

也可以直接双击 `.bat` 文件运行。

## 输出结果

几何校正目录 `GEOM_FOLDER` 中会生成：

```text
*_ORTHO.TIF
```

最终输出目录 `RRC_FOLDER` 中会生成：

```text
*_RRC.TIF
*_RRC_pif_report.json
batch_auto_pif_rrc_summary.csv
```

其中：

```text
*_RRC.TIF
```

是最终校正结果。

```text
*_RRC_pif_report.json
```

记录每个波段的校正参数和质量指标，包括：

```text
slope       斜率
intercept   截距
r2          拟合优度
rmse        均方根误差
n_pixels    参与拟合的 PIF 像元数
```

```text
batch_auto_pif_rrc_summary.csv
```

记录每景处理成功、失败或跳过的状态。

## 常用参数设置

### 1. 波段顺序

默认认为 Sentinel-2 和 GF 的前四个波段顺序都是：

```text
Blue, Green, Red, NIR = 1,2,3,4
```

如果不同，修改 `.bat`：

```bat
set "REFERENCE_BANDS=1,2,3,4"
set "TARGET_BANDS=1,2,3,4"
```

例如 GF 是 `Blue,Green,Red,NIR = 3,2,1,4`，则：

```bat
set "TARGET_BANDS=3,2,1,4"
```

### 2. 反射率缩放

如果影像值是 `0-10000`，保持：

```bat
set "SCALE=10000"
```

如果影像值已经是 `0-1`，改为：

```bat
set "SCALE=1"
```

### 3. 自动 PIF 筛选

当前自动校正分为两层：

```text
自动稳定 ROI 筛选 -> ROI 内 iMAD/PIF 像元筛选 -> 鲁棒线性回归
```

含义：

```text
--max-ndvi        排除高植被像元，越小越严格，默认 0.35
--max-ndwi        排除水体，通常保持 0.0
--pif-percentile  保留 iMAD/差异分数最低的百分比，默认 5
--min-pixels      每个波段至少需要的 PIF 像元数，默认 100
--pif-method      PIF 筛选方法，imad 更稳，score 更快
--imad-iter       iMAD 最大迭代次数，默认 100
--imad-delta      iMAD 收敛阈值，默认 0.001
--pif-ncp-thresh  iMAD no-change probability 阈值，默认 0.95
--regression-method 回归方法，orthogonal 对齐原 radcal，robust 为鲁棒备选
```

`.bat` 中常用的自动 ROI 与采样参数：

```bat
set "SAMPLE_STEP=8"
set "PIF_METHOD=imad"
set "IMAD_ITER=100"
set "IMAD_DELTA=0.001"
set "PIF_NCP_THRESH=0.95"
set "REGRESSION_METHOD=orthogonal"
set "ROI_TILE_SIZE=256"
set "ROI_TOP_PERCENT=20"
set "ROI_MAX_TILES=20"
```

含义：

```text
SAMPLE_STEP      拟合阶段的采样间隔，越小越精细，越大越快
PIF_METHOD       PIF 筛选方法，正式建议 imad，快速测试可用 score
IMAD_ITER        iMAD 最大迭代次数，默认 100
IMAD_DELTA       iMAD 收敛阈值，默认 0.001
PIF_NCP_THRESH   no-change probability 阈值，默认 0.95
REGRESSION_METHOD 回归方法，正式建议 orthogonal
ROI_TILE_SIZE    自动 ROI 网格块大小
ROI_TOP_PERCENT  保留稳定性排名靠前的 ROI 比例
ROI_MAX_TILES    最多使用多少个稳定 ROI 网格块
```

调试建议：

```bat
set "SAMPLE_STEP=8"
set "PIF_METHOD=imad"
set "ROI_TILE_SIZE=256"
```

正式高精度处理可以尝试：

```bat
set "SAMPLE_STEP=4"
set "PIF_METHOD=imad"
set "ROI_TILE_SIZE=512"
```

如果需要退回旧的快速 PIF 方法，可设置：

```bat
set "PIF_METHOD=score"
```

如果经常失败，提示 PIF 像元不足，可以尝试：

```bat
set "EXTRA_FLAGS=--max-ndvi 0.45 --pif-percentile 10 --min-pixels 80"
```

如果结果不稳定，PIF 太杂，可以尝试：

```bat
set "EXTRA_FLAGS=--max-ndvi 0.25 --pif-percentile 3"
```

### 4. 是否覆盖已有结果

默认不覆盖已有结果。

如果要重新生成大气校正结果：

```bat
set "EXTRA_FLAGS=--overwrite-rrc"
```

如果几何和大气都重新生成：

```bat
set "EXTRA_FLAGS=--overwrite-geometry --overwrite-rrc"
```

### 5. 只跑大气校正

如果 `GEOM_FOLDER` 里已经有 `*_ORTHO.TIF`，只想跑自动 PIF 校正：

```bat
set "EXTRA_FLAGS=--skip-geometry --overwrite-rrc"
```

### 6. 只跑几何校正

```bat
set "EXTRA_FLAGS=--skip-rrc"
```

## 命令行直接运行

不通过 `.bat`，也可以直接运行 Python：

```powershell
python run_gf_preprocess.py `
  -i F:\pre_process\GYY\RENAME `
  -g F:\pre_process\GYY\2_geom `
  -o F:\pre_process\GYY\3_rrc `
  -r F:\pre_process\GYY\s2_ref.tif `
  -d F:\pre_process\GYY\dem\N50E120.TIF `
  -p ref `
  --satellite-geom C:\satgeom\v0.1\satellite-geom.exe `
  --ba C:\satgeom\v0.1\ba.exe
```

## 质量检查建议

每次先跑一景，检查：

1. 几何结果 `*_ORTHO.TIF` 是否与 Sentinel-2 基本对齐。
2. `*_RRC_pif_report.json` 中 `pif_pixels` 或 `n_pixels` 是否足够，至少建议大于 100。
3. 各波段 `r2` 是否合理，通常可优先关注 Blue、Green、Red，NIR 可以略低。
4. 校正前后典型地物光谱曲线是否合理，例如水体、建筑、植被。

如果几何未对齐，先不要看大气校正结果，应先解决几何问题。

## 批量质量检查

批量处理完成后，可以运行：

```powershell
.\quality_check_rrc.bat
```

或直接运行：

```powershell
python quality_check_rrc.py `
  -i F:\GF2\xiongan\rrc `
  -r F:\GF2\xiongan\1\xionganS2C2348.tif `
  -o F:\GF2\xiongan\rrc\quality_summary.csv
```

该工具会读取每景的：

```text
*_RRC.tif
*_RRC_pif_report.json
```

并输出：

```text
quality_summary.csv
```

汇总内容包括：

```text
PIF 像元数
slope / intercept
R2 / RMSE
输出影像 min / max / mean / std / 分位数
0 值比例
65535 饱和比例
与 Sentinel-2 重叠区差值 RMSE
与 Sentinel-2 重叠区相关系数
PASS / WARN / FAIL 状态
```

建议只人工复查 `WARN` 和 `FAIL` 的影像。

## 常见问题

### 找不到 satellite-geom.exe 或 ba.exe

确认路径是否正确：

```text
C:\satgeom\v0.1\satellite-geom.exe
C:\satgeom\v0.1\ba.exe
```

如果路径不同，修改 `.bat`：

```bat
set "SATELLITE_GEOM=实际路径\satellite-geom.exe"
set "BA=实际路径\ba.exe"
```

### 找不到 GDAL

运行：

```powershell
python -c "from osgeo import gdal"
```

如果报错，需要切换到带 GDAL 的 Python 环境，或安装 GDAL Python 绑定。

### PIF 像元不足

可以先放宽参数：

```bat
set "EXTRA_FLAGS=--max-ndvi 0.45 --pif-percentile 10 --min-pixels 80"
```

也要检查 Sentinel-2 是否覆盖 GF，是否有大量云、阴影、水体，或两期时间差过大。

### 输出过亮或过暗

优先检查：

1. `SCALE` 是否正确。
2. S2 和 GF 的波段顺序是否一致。
3. Sentinel-2 参考影像是否已经是反射率产品。
4. JSON 报告中斜率、截距是否异常。

### TIFFReadDirectory Warning

如果看到类似：

```text
Warning 1: TIFFReadDirectory: Sum of Photometric type-related color channels...
```

通常可以忽略。程序会按 `REFERENCE_BANDS` 和 `TARGET_BANDS` 指定的波段顺序读取影像，不依赖 TIFF 自身的颜色标签。
