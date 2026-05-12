# GF2 影像潮位批量计算说明

本目录用于批量提取 GF2 影像元数据，并基于 FES2022 潮汐模型计算每景影像成像时刻的天文潮位。
通过网盘分享的文件：tide_model
链接: https://pan.baidu.com/s/1wmwDh04fh6z_VuC-rovBYg?pwd=5bej 提取码: 5bej 
--来自百度网盘超级会员v9的分享
## 1. 当前目录内容

主要脚本：

| 文件 | 作用 |
|---|---|
| `extract_gf2_scene_info.py` | 从单个 GF2 `.tar.gz` 中读取 XML 元数据 |
| `batch_gf2_scene_info.py` | 批量扫描 GF2 `.tar.gz`，生成影像时间和中心坐标表 |
| `batch_get_tide.py` | 基于 FES2022 计算每景影像潮位 |
| `analyze_tide_class_consistency.py` | 分析两种高低潮分类方法的一致性 |

主要结果文件：

| 文件 | 作用 |
|---|---|
| `gf2_scene_info.csv` | GF2 影像元数据提取结果 |
| `gf2_scene_tide.csv` | 每景影像潮位结果 |
| `tide_class_consistency_report.txt` | 高低潮分类一致性报告 |
| `tide_class_consistency_mismatches.csv` | 两种分类不一致的影像列表 |

## 2. 环境准备

当前已在本目录下创建独立 Python 虚拟环境：

```powershell
E:\tide_model\.venv
```

运行脚本时建议使用这个 Python：

```powershell
E:\tide_model\.venv\Scripts\python.exe
```

已安装的主要依赖：

```text
pyTMD
netCDF4
pandas
xarray
dask
numpy
```

如果换电脑或环境丢失，可重新创建环境并安装：

```powershell
cd E:\tide_model
python -m venv .venv
E:\tide_model\.venv\Scripts\python.exe -m pip install pyTMD netCDF4 pandas xarray dask numpy
```

## 3. FES2022 数据要求

当前使用的潮汐模型是：

```text
FES2022_extrapolated
```

对应数据目录：

```text
E:\tide_model\fes2022b\ocean_tide_extrapolated
```

该目录下需要有 34 个已解压的 `.nc` 分潮文件，例如：

```text
m2_fes2022.nc
s2_fes2022.nc
k1_fes2022.nc
o1_fes2022.nc
...
```

如果只有 `.nc.xz`，需要先解压：

```powershell
cd E:\tide_model\fes2022b\ocean_tide_extrapolated
Get-ChildItem -Filter *.nc.xz | ForEach-Object {
    if (-not (Test-Path ($_.FullName -replace '\.xz$',''))) {
        xz -dk $_.FullName
    }
}
```

说明：

- `FES2022_extrapolated` 更适合近岸区域。
- 非外推版在海岸附近容易出现无效值。

## 4. 第一步：提取 GF2 影像元数据

脚本：

```text
batch_gf2_scene_info.py
```

脚本顶部有默认路径配置：

```python
SCENE_FOLDER = r"E:\进行时\美丽海湾\数据样本\GF2原始数据"
OUTPUT_CSV = r"E:\tide_model\gf2_scene_info.csv"
RECURSIVE = True
```

直接运行：

```powershell
cd E:\tide_model
python batch_gf2_scene_info.py
```

或显式指定路径：

```powershell
python batch_gf2_scene_info.py "E:\进行时\美丽海湾\数据样本\GF2原始数据" -o "E:\tide_model\gf2_scene_info.csv" --recursive
```

输出：

```text
E:\tide_model\gf2_scene_info.csv
```

这个表会包含：

- 原始影像路径
- 文件名中的粗略经纬度和日期
- XML 中的成像中心时间
- XML 中的中心坐标
- 如果 XML 没有中心坐标，则用四角坐标平均得到中心点

## 5. 第二步：计算每景影像潮位

脚本：

```text
batch_get_tide.py
```

脚本顶部关键配置：

```python
SCENE_INFO_CSV = r"E:\tide_model\gf2_scene_info.csv"
OUTPUT_CSV = r"E:\tide_model\gf2_scene_tide.csv"
FES_ROOT = r"E:\tide_model"
MODEL_NAME = "FES2022_extrapolated"
INPUT_TIME_UTC_OFFSET_HOURS = 8
```

默认认为 GF2 XML 中的时间是北京时间，因此计算时会减 8 小时转 UTC：

```text
selected_time_utc = selected_time_local - 8 小时
```

运行：

```powershell
cd E:\tide_model
E:\tide_model\.venv\Scripts\python.exe batch_get_tide.py
```

输出：

```text
E:\tide_model\gf2_scene_tide.csv
```

如果确认 XML 时间本身就是 UTC，则运行：

```powershell
E:\tide_model\.venv\Scripts\python.exe batch_get_tide.py --time-offset-hours 0
```

## 6. 潮位计算逻辑

每景影像使用以下输入：

```text
成像 UTC 时间
影像中心经度
影像中心纬度
```

计算过程：

```text
读取 FES2022_extrapolated 34 个分潮文件
↓
将分潮振幅和相位插值到影像中心点
↓
按成像时刻进行潮汐调和合成
↓
输出 tide_ocean_m
```

`tide_ocean_m` 表示：

```text
FES2022 模型预测的天文潮位，单位 m
```

注意：

- 它不是岸边可见潮位线高度。
- 它不是验潮站实测水位。
- 它不包含风暴增水、气压、浪高、河口径流等非天文潮影响。

## 7. 近岸或陆地点处理

部分影像中心可能落在陆地或 FES 网格无有效潮汐常数的位置。

脚本处理方式：

1. 优先使用影像中心点。
2. 中心点线性插值无效时，尝试最近邻插值。
3. 如果仍无效，则搜索附近最近的有效 FES 海潮格点。

结果中会记录：

| 字段 | 含义 |
|---|---|
| `tide_query_lon` | 实际用于计算潮位的经度 |
| `tide_query_lat` | 实际用于计算潮位的纬度 |
| `tide_point_source` | 潮位计算点来源 |
| `tide_point_distance_km` | 实际计算点到影像中心的距离 |

`tide_point_source` 可能为：

| 值 | 含义 |
|---|---|
| `scene_center` | 直接使用影像中心点 |
| `nearest_valid_fes_grid` | 使用最近有效 FES 海潮格点 |

## 8. 高低潮分类

结果表中有两列高低潮分类：

| 字段 | 含义 |
|---|---|
| `tide_level_class` | 按本批影像潮位分位数分类，建议使用 |
| `tide_level_class_threshold` | 按固定阈值分类，仅作对比 |

### 推荐分类：`tide_level_class`

按本批影像的潮位分布四等分：

```text
最低 25%      低潮
25% - 50%    中低潮
50% - 75%    中高潮
最高 25%      高潮
```

当前 488 景的分界值为：

```text
低潮      <= -0.6217 m
中低潮    -0.6217 ~ 0.0305 m
中高潮     0.0305 ~ 0.4035 m
高潮      > 0.4035 m
```

### 固定阈值分类：`tide_level_class_threshold`

规则：

```text
tide_ocean_m <= -1.0 m       低潮
-1.0 m < tide_ocean_m <= 0   中低潮
0 m < tide_ocean_m < 0.6     中高潮
tide_ocean_m >= 0.6 m        高潮
```

该方法不是严格潮汐学标准，只作为敏感性对比。

## 9. 结果表字段说明

`gf2_scene_tide.csv` 主要字段：

| 字段                           | 含义                        |
| ---------------------------- | ------------------------- |
| `file`                       | GF2 原始压缩包路径               |
| `filename_center_lon`        | 从文件名解析出的粗略经度              |
| `filename_center_lat`        | 从文件名解析出的粗略纬度              |
| `filename_date`              | 从文件名解析出的日期                |
| `xml`                        | 实际读取的 XML 元数据文件           |
| `selected_time_tag`          | 使用的时间字段名，通常是 `centertime` |
| `selected_time`              | XML 原始成像时间                |
| `selected_time_local`        | 按本地时间理解的成像时间              |
| `selected_time_utc`          | 转 UTC 后用于潮位计算的时间          |
| `xml_center_lon`             | 影像中心经度                    |
| `xml_center_lat`             | 影像中心纬度                    |
| `coordinate_source`          | 中心坐标来源                    |
| `tide_model`                 | 使用的潮汐模型                   |
| `tide_interpolation`         | 插值方式                      |
| `tide_query_lon`             | 实际计算潮位的经度                 |
| `tide_query_lat`             | 实际计算潮位的纬度                 |
| `tide_point_source`          | 潮位点来源                     |
| `tide_point_distance_km`     | 潮位点与影像中心距离，单位 km          |
| `tide_ocean_m`               | 天文潮位，单位 m                 |
| `tide_level_class`           | 推荐使用的高低潮分类                |
| `tide_level_class_threshold` | 固定阈值分类                    |
| `tide_q25_m`                 | 本批潮位 25% 分位数              |
| `tide_q50_m`                 | 本批潮位 50% 分位数              |
| `tide_q75_m`                 | 本批潮位 75% 分位数              |

## 10. 两种分类一致性分析

脚本：

```text
analyze_tide_class_consistency.py
```

运行：

```powershell
cd E:\tide_model
E:\tide_model\.venv\Scripts\python.exe analyze_tide_class_consistency.py
```

输出：

```text
E:\tide_model\tide_class_consistency_report.txt
E:\tide_model\tide_class_consistency_mismatches.csv
```

当前分析结果：

```text
总样本数：488
完全一致：393
一致率：80.53%
线性加权 Kappa：0.8326
二次加权 Kappa：0.9095
```

说明：

- 两种方法总体一致性较好。
- 不一致样本全部只差一级。
- 没有“低潮 vs 高潮”这种严重冲突。

## 11. 常用命令汇总

重新提取 GF2 元数据：

```powershell
cd E:\tide_model
python batch_gf2_scene_info.py
```

重新计算潮位：

```powershell
cd E:\tide_model
E:\tide_model\.venv\Scripts\python.exe batch_get_tide.py
```

如果 XML 时间是 UTC：

```powershell
E:\tide_model\.venv\Scripts\python.exe batch_get_tide.py --time-offset-hours 0
```

重新做分类一致性分析：

```powershell
E:\tide_model\.venv\Scripts\python.exe analyze_tide_class_consistency.py
```

## 12. 使用建议

如果用于遥感岸线、滩涂或海湾水边线分析，建议优先使用：

```text
tide_ocean_m
tide_level_class
tide_point_source
tide_point_distance_km
```

筛选低潮影像：

```text
tide_level_class = 低潮
```

筛选高潮影像：

```text
tide_level_class = 高潮
```

如果 `tide_point_source = nearest_valid_fes_grid` 且 `tide_point_distance_km` 较大，说明影像中心不在有效海潮网格上，解释结果时应注明使用了最近有效海潮点。

