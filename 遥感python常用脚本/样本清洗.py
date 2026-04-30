import os
import numpy as np
from osgeo import gdal
from tqdm import tqdm


def read_label(label_path):
    """使用 GDAL 读取标签数据"""
    ds = gdal.Open(label_path)
    if ds is None:
        return None
    data = ds.ReadAsArray()
    del ds  # 释放内存
    return data


def clean_background_and_nodata(image_dir, label_dir):
    """
    清洗切片数据：
    1. 剔除标签全为 0 的样本（纯水体/背景）
    2. 剔除标签全为 255 的样本（NoData）
    """
    # 获取所有标签文件
    label_files = [f for f in os.listdir(label_dir) if f.endswith('.tif')]

    remove_0_count = 0
    remove_255_count = 0
    keep_count = 0

    print(f"开始清洗数据，总计检测到 {len(label_files)} 个切片...")

    for lbl_name in tqdm(label_files):
        lbl_path = os.path.join(label_dir, lbl_name)
        # 假设影像和标签文件名一一对应
        img_path = os.path.join(image_dir, lbl_name)

        # 1. 读取标签内容
        label_data = read_label(lbl_path)
        if label_data is None:
            continue

        # 2. 判别逻辑
        is_all_0 = np.all(label_data == 0)
        is_all_255 = np.all(label_data == 255)

        if is_all_0 or is_all_255:
            # 执行删除
            if os.path.exists(lbl_path):
                os.remove(lbl_path)
            if os.path.exists(img_path):
                os.remove(img_path)

            if is_all_0:
                remove_0_count += 1
            else:
                remove_255_count += 1
        else:
            keep_count += 1

    print("\n" + "=" * 30)
    print(f"清洗完成！统计结果如下：")
    print(f"保留有效切片: {keep_count}")
    print(f"删除全0(水体)切片: {remove_0_count}")
    print(f"删除全255(无效)切片: {remove_255_count}")
    print("=" * 30)


if __name__ == "__main__":
    # 填入你已经切好的切片文件夹路径
    IMAGE_DIR = r'D:\sc_data\test\images'
    LABEL_DIR = r'D:\sc_data\test\labels'

    # 执行清洗
    clean_background_and_nodata(IMAGE_DIR, LABEL_DIR)