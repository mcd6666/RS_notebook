# Python 大气校正程序打包为 EXE 安装包教程

本文说明如何将 `GFAtmosphere` Python 大气校正程序打包成可交付给甲方的 Windows 安装包。最终交付物为一个 `.exe` 安装程序，甲方双击安装后即可使用图形界面，无需另外安装 Python、GDAL、NumPy 或 SciPy。

## 1. 打包流程概览

本程序采用两步打包：

```text
Python 源码及依赖
    |
    | PyInstaller
    v
可独立运行的程序目录 dist\GFAtmosphere\
    |
    | Inno Setup
    v
单文件安装包 GFAtmosphere_Setup_v1.0.0.exe
```

两步工具的作用不同：

| 工具 | 作用 | 生成结果 |
| --- | --- | --- |
| PyInstaller | 将 Python 程序、解释器及依赖库一起封装 | `dist\GFAtmosphere\GFAtmosphere.exe` 及其依赖文件 |
| Inno Setup | 将整个可运行目录制作成标准 Windows 安装包 | `installer\output\GFAtmosphere_Setup_v1.0.0.exe` |

不能只把 PyInstaller 生成的主程序 `GFAtmosphere.exe` 单独发送给甲方，因为 `--onedir` 模式下它需要旁边的 `_internal` 依赖目录、文档及参考影像目录。正式交付应发送 Inno Setup 生成的安装包。

## 2. 当前产品目录结构

工作目录中的产品工程为：

```text
GFAtmosphere\
|-- atmosphere_app.py                 # 图形界面入口
|-- auto_pif_rrc.py                   # 单景大气校正核心算法
|-- batch_auto_pif_rrc.py             # 批量处理入口
|-- build_pyinstaller_code_env.bat    # 第一步：生成独立运行程序
|-- build_installer.bat               # 第二步：生成安装包
|-- references\
|   `-- README.txt                    # 默认参考影像放置说明
|-- docs\
|   `-- 用户说明.md                   # 交付给用户的操作说明
|-- installer\
|   |-- GFAtmosphere.iss              # Inno Setup 安装配置
|   `-- output\                       # 最终安装包输出位置
`-- dist\
    `-- GFAtmosphere\                 # PyInstaller 生成的运行目录
```

## 3. 打包前需要准备的软件

### 3.1 Python 运行环境

本工程使用已有的 Conda 环境 `code` 打包，其 Python 路径为：

```text
D:\anaconda\envs\code\python.exe
```

该环境中需要包含：

```text
numpy
scipy
GDAL / osgeo
PyInstaller
```

可在命令提示符中检查关键环境：

```bat
D:\anaconda\envs\code\python.exe -V
D:\anaconda\envs\code\python.exe -c "from osgeo import gdal; import numpy, scipy; print(gdal.VersionInfo())"
D:\anaconda\envs\code\python.exe -m PyInstaller --version
```

若只缺少 PyInstaller，可安装：

```bat
D:\anaconda\envs\code\python.exe -m pip install pyinstaller
```

### 3.2 Inno Setup

Inno Setup 用于将运行目录封装为具有安装、开始菜单快捷方式和卸载功能的安装包。

安装 `Inno Setup 6` 后，本工程脚本会依次查找以下路径：

```text
C:\Program Files (x86)\Inno Setup 6\ISCC.exe
C:\Program Files\Inno Setup 6\ISCC.exe
%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
```

也可以使用 Windows 包管理器安装：

```bat
winget install --id JRSoftware.InnoSetup -e
```

## 4. 准备默认参考影像

程序支持用户在界面中手动选择 Sentinel-2 参考影像，也支持随安装包附带一个默认参考影像。

如果需要安装后默认识别固定参考影像，将实际 Sentinel-2 文件放入：

```text
GFAtmosphere\references\sentinel2_ref.tif
```

注意：

- 默认文件名必须为 `sentinel2_ref.tif`。
- 如果不放该文件，软件仍能运行，但甲方每次需要在界面中手动指定参考影像。
- 更换参考影像后，需要重新执行下面两步打包，新的影像才会进入安装包。

## 5. 第一步：使用 PyInstaller 打包 Python 程序

### 5.1 执行方式

双击运行：

```text
GFAtmosphere\build_pyinstaller_code_env.bat
```

也可以在命令提示符中进入产品目录后执行：

```bat
cd /d E:\进行时\空天院\高分预处理\几何大气校正\GFAtmosphere
build_pyinstaller_code_env.bat
```

### 5.2 脚本完成的工作

该脚本实际执行以下核心打包命令：

```bat
"D:\anaconda\envs\code\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "GFAtmosphere" ^
  --hidden-import osgeo.gdal ^
  --hidden-import osgeo.osr ^
  --hidden-import osgeo.gdal_array ^
  --hidden-import scipy.stats ^
  --exclude-module torch ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module sklearn ^
  --exclude-module skimage ^
  --exclude-module panel ^
  --exclude-module bokeh ^
  --exclude-module plotly ^
  --exclude-module geopandas ^
  --exclude-module cv2 ^
  --exclude-module pytest ^
  --exclude-module dask ^
  atmosphere_app.py
```

主要参数含义如下：

| 参数 | 作用 |
| --- | --- |
| `--onedir` | 生成一个可运行目录，适合包含 GDAL 等复杂依赖的程序，运行可靠性高 |
| `--windowed` | 图形界面启动时不额外显示 Python 控制台窗口 |
| `--name GFAtmosphere` | 设置程序名称及输出目录名 |
| `--hidden-import` | 显式包含 PyInstaller 可能无法自动识别的 GDAL、SciPy 模块 |
| `--exclude-module` | 排除本项目不需要的大型依赖，降低安装包体积 |
| `--clean` | 清除旧缓存后重新打包，避免旧内容干扰 |

脚本还会将以下资源复制到程序目录：

```text
references\  -> dist\GFAtmosphere\references\
docs\        -> dist\GFAtmosphere\docs\
```

### 5.3 输出结果

执行成功后，生成目录：

```text
GFAtmosphere\dist\GFAtmosphere\
```

其中主程序为：

```text
GFAtmosphere\dist\GFAtmosphere\GFAtmosphere.exe
```

此时可以先双击该程序进行本机试运行，确认：

1. 界面能正常打开。
2. 可选择中文路径的输入、输出和参考影像。
3. `Scored` 与 `iMAD` 模式可选择。
4. 使用一景已知影像能够生成 `_RRC.tif` 和报告文件。

## 6. 第二步：使用 Inno Setup 生成安装包

### 6.1 执行方式

确认第一步的 `dist\GFAtmosphere\` 已成功生成后，双击：

```text
GFAtmosphere\build_installer.bat
```

或者在命令提示符中执行：

```bat
cd /d E:\进行时\空天院\高分预处理\几何大气校正\GFAtmosphere
build_installer.bat
```

### 6.2 安装配置文件

安装包规则由下列文件控制：

```text
GFAtmosphere\installer\GFAtmosphere.iss
```

当前配置实现：

| 项目 | 设置 |
| --- | --- |
| 程序名称 | `GF Atmosphere` |
| 版本号 | `1.0.0` |
| 默认安装目录 | `C:\Program Files\GFAtmosphere` |
| 安装包文件名 | `GFAtmosphere_Setup_v1.0.0.exe` |
| 架构 | 64 位 Windows |
| 快捷方式 | 开始菜单，用户可选择桌面快捷方式 |
| 卸载 | Windows 应用卸载列表中可正常卸载 |
| 安装权限 | 需要管理员权限 |

如需变更版本号，只修改 `.iss` 文件顶部：

```iss
#define MyAppVersion "1.0.0"
```

例如发布下一版：

```iss
#define MyAppVersion "1.0.1"
```

### 6.3 输出结果

执行成功后，最终安装包位于：

```text
GFAtmosphere\installer\output\GFAtmosphere_Setup_v1.0.0.exe
```

这一个文件就是可以发送给甲方的正式交付安装包。

## 7. 甲方安装后的使用行为

甲方双击安装包后：

1. 按安装向导完成安装。
2. 从开始菜单或桌面快捷方式运行 `GF Atmosphere`。
3. 选择待处理影像文件夹，程序识别 `.tif` 和 `.tiff` 文件。
4. 选择输出文件夹，或使用默认输出目录。
5. 使用预置参考影像，或手动选择 Sentinel-2 参考影像。
6. 保持默认 `Scored` 模式，或根据项目要求切换为 `iMAD`。
7. 点击运行完成批量大气校正。

未手动填写输出目录时，默认输出位置为：

```text
当前用户\Documents\GFAtmosphere\Outputs
```

程序不会把输出写入安装目录，以避免 `Program Files` 权限导致写入失败。

## 8. 交付前验收清单

打包完成后，不应直接交付。建议至少进行以下验收：

| 检查项 | 检查方法 | 通过标准 |
| --- | --- | --- |
| 安装包可运行 | 在另一台 Windows 64 位电脑上双击安装 | 安装过程无报错 |
| 无本地 Python 环境依赖 | 在未安装 Python/GDAL 的电脑上启动程序 | 界面正常打开 |
| 参考影像 | 检查默认影像或手动选择功能 | 参考文件可正常载入 |
| 输入识别 | 放入 `.tif` 和 `.tiff` 样例 | 能正确识别，跳过已有 `_RRC` 结果 |
| 校正输出 | 运行一景已验证样例 | 生成校正影像和报告 |
| 中文路径 | 使用含中文的输入、输出目录 | 处理正常完成 |
| 模式选择 | 分别测试 `Scored`、`iMAD` | 两种模式均可运行 |
| 卸载 | 从 Windows 设置中卸载 | 可正常卸载 |

建议保留一景经过人工确认的标准样例，后续每次版本更新后均执行同样测试，以避免打包或算法调整引入回归。

## 9. 是否真正隐藏了 Python 源码

交付给甲方的是安装包和安装后的可执行程序，目录中不会直接出现：

```text
atmosphere_app.py
auto_pif_rrc.py
batch_auto_pif_rrc.py
```

因此甲方不能像打开普通 `.py` 文件一样查看源码。

但需要明确：PyInstaller 属于封装和分发工具，不是强加密方案。具备专业逆向能力的人仍有可能从可执行程序中分析出部分 Python 字节码或程序逻辑。如果合同要求较高等级的算法保密，应进一步考虑：

- 核心算法改写为 C++ 动态库或本地可执行模块。
- 使用 Cython/Nuitka 编译核心算法。
- 将关键算法放在受控服务器端，以服务形式调用。
- 配合软件授权、加密和合同保密条款。

对一般项目交付和防止源码直接暴露，当前安装包方式通常足够实用。

## 10. 常见问题

### 10.1 双击 `build_pyinstaller_code_env.bat` 提示找不到 Python

原因：脚本中的 Conda 环境路径与当前电脑不一致。

处理方式：打开脚本，将下面一行修改为实际 Python 路径：

```bat
set "ENV_PYTHON=D:\anaconda\envs\code\python.exe"
```

### 10.2 提示缺少 PyInstaller

执行：

```bat
D:\anaconda\envs\code\python.exe -m pip install pyinstaller
```

然后重新运行第一步打包脚本。

### 10.3 运行 `build_installer.bat` 提示找不到 Inno Setup

先安装 Inno Setup 6：

```bat
winget install --id JRSoftware.InnoSetup -e
```

安装完成后重新运行第二步脚本。

### 10.4 软件安装后找不到默认哨兵参考影像

原因：打包前未将实际参考影像放入 `references` 目录，或者文件名不是指定名称。

处理方式：

```text
将影像放入 GFAtmosphere\references\sentinel2_ref.tif
重新执行 build_pyinstaller_code_env.bat
重新执行 build_installer.bat
```

也可以不重新打包，直接让用户在软件界面中手动选择参考影像。

### 10.5 修改 Python 代码后为什么安装包没有变化

Inno Setup 只是封装 `dist\GFAtmosphere\` 现有内容，不会自动重新编译 Python 代码。源码、界面或资源有任何修改，都应按固定顺序重新执行：

```text
1. build_pyinstaller_code_env.bat
2. build_installer.bat
```

### 10.6 安装包为什么比较大

大气校正依赖 GDAL、NumPy 和 SciPy 等运行库。为了保证甲方机器无需自行安装环境，这些依赖必须一起装入安装包。因此安装包体积明显大于单纯的脚本文件，这是独立部署的正常代价。

## 11. 后续发布建议

每次正式交付建议按以下规则管理版本：

1. 修改程序后先在源码状态下测试一景样例。
2. 放入或确认需随软件交付的默认参考影像。
3. 更新 `GFAtmosphere.iss` 中的版本号。
4. 运行 PyInstaller 打包脚本。
5. 运行 Inno Setup 安装包脚本。
6. 在无 Python 环境的电脑上进行安装验收。
7. 只发送最终安装包及必要的甲方操作说明，不发送源码目录、`build` 目录或开发脚本。

最终对外交付文件通常包括：

```text
GFAtmosphere_Setup_v1.0.0.exe
用户说明.pdf 或 用户说明.md
```

