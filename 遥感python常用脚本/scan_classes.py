import os
import glob
import cv2
import numpy as np
from tqdm import tqdm
from collections import defaultdict


def scan_dataset_for_classes(label_dir, file_ext="png"):
    """
    盲扫数据集，找出所有存在的像素值类别ID
    """
    # 1. 查找文件
    search_path = os.path.join(label_dir, f"**/*.{file_ext}")
    files = glob.glob(search_path, recursive=True)

    if not files:
        print(f"❌ 未找到 .{file_ext} 文件，请检查路径: {label_dir}")
        return

    print(f"🔍 准备扫描 {len(files)} 个文件...")

    # 用于记录全局发现的所有唯一值
    global_unique_values = set()
    # 用于记录每个值的像素总量（辅助判断哪个是背景）
    pixel_counts = defaultdict(int)

    # 2. 循环读取
    for file_path in tqdm(files, desc="Scanning"):
        # 必须使用 UNCHANGED 读取，防止 opencv 自动把单通道转成 3 通道
        mask = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)

        if mask is None:
            continue

        # 处理多通道情况 (有些软件存掩码也是3通道，通常R=G=B)
        if mask.ndim == 3:
            mask = mask[:, :, 0]

        # 获取当前图片的唯一值
        unique_vals, counts = np.unique(mask, return_counts=True)

        # 更新全局记录
        for val, count in zip(unique_vals, counts):
            global_unique_values.add(val)
            pixel_counts[val] += count

    # 3. 输出报告
    sorted_ids = sorted(list(global_unique_values))

    print("\n" + "=" * 40)
    print("📊 扫描结果报告 (Dataset Scan Report)")
    print("=" * 40)
    print(f"发现的唯一像素值 (Class IDs): {sorted_ids}")
    print("-" * 40)
    print(f"{'Value (ID)':<12} | {'Total Pixels':<15} | {'Guess'}")
    print("-" * 40)

    # 找出像素最多的值（通常是背景）
    max_pixels = max(pixel_counts.values()) if pixel_counts else 0

    for val in sorted_ids:
        count = pixel_counts[val]
        guess = "可能是背景 (Background)" if count == max_pixels else "目标类别 (Class)"
        if val == 255: guess = "可能是忽略区域 (Ignore)"

        print(f"{val:<12} | {count:<15,} | {guess}")

    print("=" * 40)
    return sorted_ids


# ================= 配置区 =================
if __name__ == "__main__":
    # 🔴 把这里改成你的标签文件夹路径
    LABEL_DIR = r"/mnt/e/syf/shuicao/shuicao/val/labels"

    # 🔴 如果是 tif 格式，这里改成 "tif"
    EXT = "png"

    found_classes = scan_dataset_for_classes(LABEL_DIR, EXT)

#
# import cv2
# import numpy as np
# import matplotlib.pyplot as plt
# import glob
# import os
# import random
#
#
# def quick_visualize(label_dir, ext="png", num_samples=11):
#     # 1. 找到所有文件
#     files = glob.glob(os.path.join(label_dir, f"*.{file_ext}"))
#     if not files:
#         print("没找到文件，请检查路径！")
#         return
#
#     # 2. 随机抽查几张 (或者你可以指定 index)
#     samples = random.sample(files, min(len(files), num_samples))
#
#     for file_path in samples:
#         # 读取掩码 (必须用 flag 0 或 -1 原样读取)
#         mask = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
#
#         # 处理多通道
#         if mask.ndim == 3: mask = mask[:, :, 0]
#
#         # 获取里面有哪些类别
#         unique_ids = np.unique(mask)
#         print(f"文件名: {os.path.basename(file_path)} | 包含类别: {unique_ids}")
#
#         # 3. 画图 (使用 'jet' 或 'tab10' 彩色映射)
#         plt.figure(figsize=(10, 6))
#
#         # 这里是核心：使用 cmap='jet' 自动给不同数字上色
#         # interpolation='nearest' 保证边缘是锐利的，没有模糊
#         plt.imshow(mask, cmap='tab10', interpolation='nearest')
#         plt.colorbar(label='Class ID')  # 显示色条，告诉你哪个颜色是哪个数字
#
#         plt.title(f"File: {os.path.basename(file_path)}\nClasses found: {unique_ids}")
#         plt.show()
#
#
# # ================= 配置 =================
# if __name__ == "__main__":
#     # 改成你的标签文件夹
#     LABEL_DIR = r"E:\DLmodels\dataset\val\labels"
#     file_ext = "png"  # 或 tif
#
#     quick_visualize(LABEL_DIR, file_ext, num_samples=11)