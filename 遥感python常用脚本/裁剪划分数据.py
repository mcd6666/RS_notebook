import os
import shutil
import numpy as np
import rasterio
from rasterio.windows import Window
import random
from tqdm import tqdm


# ==========================================
# 模块 1：核心数学与误差计算工具
# ==========================================
def get_proportions(counts):
    total = np.sum(counts)
    return counts / total if total > 0 else np.zeros_like(counts, dtype=float)


def calculate_total_error(train_counts, val_counts, global_proportions_target):
    train_prop = get_proportions(train_counts)
    val_prop = get_proportions(val_counts)
    train_mse = np.sum((train_prop - global_proportions_target) ** 2)
    val_mse = np.sum((val_prop - global_proportions_target) ** 2)
    return train_mse + val_mse


# ==========================================
# 模块 2：滑动窗口切片引擎
# ==========================================
def crop_to_patches(img_dir, label_dir, patch_img_dir, patch_lbl_dir, patch_size=512, overlap=0.25):
    print("\n" + "=" * 40)
    print("🚀 第一阶段：开始滑动窗口切片 (已启用统一命名机制)")
    print("=" * 40)

    os.makedirs(patch_img_dir, exist_ok=True)
    os.makedirs(patch_lbl_dir, exist_ok=True)

    stride = int(patch_size * (1 - overlap))
    label_files = [f for f in os.listdir(label_dir) if f.endswith(('.tif', '.png'))]

    for lbl_filename in tqdm(label_files, desc="整图切片进度"):

        # 🌟 核心修复 1：提取干净的核心前缀
        base_name = lbl_filename.replace('_label.tif', '').replace('.tif', '')
        img_filename = base_name + '_image.tif'

        img_path = os.path.join(img_dir, img_filename)
        lbl_path = os.path.join(label_dir, lbl_filename)

        if not os.path.exists(img_path):
            continue

        with rasterio.open(img_path) as src_img, rasterio.open(lbl_path) as src_lbl:
            img_width, img_height = src_img.width, src_img.height
            img_meta, lbl_meta = src_img.meta.copy(), src_lbl.meta.copy()

            img_meta.update({"width": patch_size, "height": patch_size})
            lbl_meta.update({"width": patch_size, "height": patch_size})

            patch_idx = 0
            for y in range(0, img_height, stride):
                for x in range(0, img_width, stride):
                    y_start, x_start = y, x
                    if y_start + patch_size > img_height: y_start = max(0, img_height - patch_size)
                    if x_start + patch_size > img_width:  x_start = max(0, img_width - patch_size)

                    window = Window(col_off=x_start, row_off=y_start, width=patch_size, height=patch_size)

                    img_patch = src_img.read(window=window)
                    lbl_patch = src_lbl.read(1, window=window)

                    if np.all(img_patch == 0):
                        continue

                    # 🌟 核心修复 2：废除 _image 和 _label 后缀，影像和掩膜共用一个极简名字！
                    shared_patch_name = f"{base_name}_{patch_idx:04d}.tif"

                    img_meta.update({"transform": rasterio.windows.transform(window, src_img.transform)})
                    lbl_meta.update({"transform": rasterio.windows.transform(window, src_lbl.transform)})

                    # 分别存入 image 和 label 文件夹，但名字一模一样
                    with rasterio.open(os.path.join(patch_img_dir, shared_patch_name), 'w', **img_meta) as dest_img:
                        dest_img.write(img_patch)
                    with rasterio.open(os.path.join(patch_lbl_dir, shared_patch_name), 'w', **lbl_meta) as dest_lbl:
                        dest_lbl.write(lbl_patch, 1)

                    patch_idx += 1
    print(f"✅ 切片完成！所有小图已临时存放在: {patch_img_dir}")


# ==========================================
# 模块 3：按比例精细分配引擎
# ==========================================
def split_and_migrate(patch_img_dir, patch_lbl_dir, final_output_dir, train_ratio=0.8, num_classes=4, max_iters=50000):
    print("\n" + "=" * 40)
    print("🚀 第二阶段：启动双子集黄金比例分配")
    print("=" * 40)

    dirs_to_make = [
        os.path.join(final_output_dir, 'train', 'images'),  # 改成了复数 images，更规范
        os.path.join(final_output_dir, 'train', 'labels'),
        os.path.join(final_output_dir, 'val', 'images'),
        os.path.join(final_output_dir, 'val', 'labels')
    ]
    for d in dirs_to_make:
        os.makedirs(d, exist_ok=True)

    # 现在的补丁名字都是干净的 CH_xxx_0000.tif 格式
    label_files = [f for f in os.listdir(patch_lbl_dir) if f.endswith('.tif')]
    image_stats = []
    global_counts = np.zeros(num_classes, dtype=np.int64)

    for file_name in tqdm(label_files, desc="提取像素特征"):

        # 🌟 核心修复 3：直接用同一个名字去找原图，再也不用 replace 了！
        lbl_path = os.path.join(patch_lbl_dir, file_name)
        img_path = os.path.join(patch_img_dir, file_name)

        if not os.path.exists(img_path): continue

        with rasterio.open(lbl_path) as src_lbl, rasterio.open(img_path) as src_img:
            mask = src_lbl.read(1)
            img_data = src_img.read()

        is_valid_image_pixel = ~np.all(img_data == 0, axis=0)
        valid_mask = mask[(mask >= 0) & (mask < num_classes) & is_valid_image_pixel]
        counts = np.bincount(valid_mask, minlength=num_classes)

        if np.sum(counts) == 0: continue

        image_stats.append({
            'file_name': file_name,  # 记录统一的名字
            'target_counts': counts[:num_classes]
        })
        global_counts += counts[:num_classes]

    target_global_counts = global_counts[:num_classes]
    global_proportions_target = target_global_counts / np.sum(target_global_counts)
    print(f"\n[目标] 全局参考比例: {np.round(global_proportions_target, 4)}")

    total_images = len(image_stats)
    target_train_num = int(total_images * train_ratio)

    random.shuffle(image_stats)
    train_list = image_stats[:target_train_num]
    val_list = image_stats[target_train_num:]

    train_counts = np.sum([x['target_counts'] for x in train_list], axis=0) if train_list else np.zeros(num_classes)
    val_counts = np.sum([x['target_counts'] for x in val_list], axis=0) if val_list else np.zeros(num_classes)
    current_error = calculate_total_error(train_counts, val_counts, global_proportions_target)

    print("正在迭代优化数据分布 (请稍候)...")
    datasets = [{'list': train_list, 'counts': train_counts}, {'list': val_list, 'counts': val_counts}]

    for _ in range(max_iters):
        set1, set2 = datasets[0], datasets[1]
        if len(set1['list']) == 0 or len(set2['list']) == 0: break

        i, j = random.randint(0, len(set1['list']) - 1), random.randint(0, len(set2['list']) - 1)
        c1, c2 = set1['list'][i]['target_counts'], set2['list'][j]['target_counts']

        new_counts = [datasets[k]['counts'].copy() for k in range(2)]
        new_counts[0] = new_counts[0] - c1 + c2
        new_counts[1] = new_counts[1] - c2 + c1
        new_error = calculate_total_error(new_counts[0], new_counts[1], global_proportions_target)

        if new_error < current_error:
            set1['list'][i], set2['list'][j] = set2['list'][j], set1['list'][i]
            datasets[0]['counts'], datasets[1]['counts'] = new_counts[0], new_counts[1]
            current_error = new_error

    train_counts, val_counts = datasets[0]['counts'], datasets[1]['counts']
    print(f"\n[结果] 训练集比例: {np.round(get_proportions(train_counts), 3)} (共 {len(train_list)} 张)")
    print(f"[结果] 验证集比例: {np.round(get_proportions(val_counts), 3)} (共 {len(val_list)} 张)")

    def migrate_files(file_list, target_sub_dir):
        img_out_dir = os.path.join(final_output_dir, target_sub_dir, 'images')
        lbl_out_dir = os.path.join(final_output_dir, target_sub_dir, 'labels')
        for item in tqdm(file_list, desc=f"分配 {target_sub_dir} 数据"):
            fname = item['file_name']
            # 拷贝时继续使用同一个名字
            shutil.copy(os.path.join(patch_img_dir, fname), os.path.join(img_out_dir, fname))
            shutil.copy(os.path.join(patch_lbl_dir, fname), os.path.join(lbl_out_dir, fname))

    migrate_files(train_list, 'train')
    migrate_files(val_list, 'val')
    print(f"\n🎉 大功告成！最终用于训练的数据集已存放至: {os.path.abspath(final_output_dir)}")


# ==========================================
# 🚀 程序主入口：在这里配置你的参数
# ==========================================
if __name__ == "__main__":

    # 1. 原始大图文件夹路径 (你刚截图里的那些大 tif)
    LARGE_IMG_DIR = r'/mnt/e/进行时/论文/数据及数据集/syf水草/国产/test/image'
    LARGE_LBL_DIR = r'/mnt/e/进行时/论文/数据及数据集/syf水草/国产/test/labels'

    # 2. 工作空间根目录 (代码会在这个目录下建文件夹)
    WORKSPACE_DIR = r'/mnt/d/sc_data'

    # 自动生成中间文件夹和最终文件夹路径
    PATCHES_TEMP_DIR = os.path.join(WORKSPACE_DIR, '1_patches_temp')
    PATCHES_IMG_DIR = os.path.join(PATCHES_TEMP_DIR, 'images')
    PATCHES_LBL_DIR = os.path.join(PATCHES_TEMP_DIR, 'labels')
    FINAL_DATASET_DIR = os.path.join(WORKSPACE_DIR, '2_final_dataset')

    # ==========================
    # 步骤一：执行大图切片
    # ==========================
    crop_to_patches(
        img_dir=LARGE_IMG_DIR,
        label_dir=LARGE_LBL_DIR,
        patch_img_dir=PATCHES_IMG_DIR,
        patch_lbl_dir=PATCHES_LBL_DIR,
        patch_size=256,  # 👈 在这里修改切片大小
        overlap=0.25  # 👈 在这里修改重叠率
    )

    # ==========================
    # 步骤二：执行比例优化与分配
    # ==========================
    split_and_migrate(
        patch_img_dir=PATCHES_IMG_DIR,
        patch_lbl_dir=PATCHES_LBL_DIR,
        final_output_dir=FINAL_DATASET_DIR,
        train_ratio=0.8,  # 👈 在这里修改训练集比例
        num_classes=4,
        max_iters=50000
    )

    # ==========================
    # 步骤三：自动清理中间缓存文件
    # ==========================
    print("\n" + "=" * 40)
    print("🧹 第三阶段：清理临时切片文件释放空间")
    print("=" * 40)
    if os.path.exists(PATCHES_TEMP_DIR):
        try:
            shutil.rmtree(PATCHES_TEMP_DIR)
            print(f"✅ 已成功销毁临时文件夹: {PATCHES_TEMP_DIR}")
        except Exception as e:
            print(f"⚠️ 清理失败，可能是文件正在被占用: {e}")

    print("\n🚀 所有任务圆满结束！祝模型 mIoU 节节攀升！")