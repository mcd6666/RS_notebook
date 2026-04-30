import os
import rasterio
from pathlib import Path

# --- 设置路径 ---
input_dir = '/mnt/d/sc_data/2_final_dataset/train/image'  # 原始 7 波段影像文件夹
output_dir = '/mnt/d/sc_data/2_final_dataset/train/images'  # 存放 4 波段影像的文件夹

# 如果输出文件夹不存在，则创建它
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# --- 开始遍历处理 ---
# 遍历文件夹中所有以 .tif 或 .tiff 结尾的文件
for file_name in os.listdir(input_dir):
    if file_name.lower().endswith(('.tif', '.tiff')):
        input_path = os.path.join(input_dir, file_name)
        output_path = os.path.join(output_dir, file_name)

        print(f"正在处理: {file_name}...")

        try:
            with rasterio.open(input_path) as src:
                # 1. 读取前 4 个波段 (索引从 1 开始)
                data = src.read([4, 3, 2, 1])

                # 2. 准备输出的元数据
                # profile 包含了投影(crs)、变换(transform)、数据类型(dtype)等关键信息
                out_profile = src.profile.copy()
                out_profile.update({
                    "count": 4  # 将波段数改为 4
                })

                # 3. 写入新文件
                with rasterio.open(output_path, 'w', **out_profile) as dst:
                    dst.write(data)

        except Exception as e:
            print(f"处理 {file_name} 时出错: {e}")

print("\n所有文件处理完成！")