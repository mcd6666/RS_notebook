import os
import rasterio
import numpy as np
import albumentations as A
from tqdm import tqdm


def augment_dataset(img_dir, lbl_dir, out_img_dir, out_lbl_dir, aug_times=3, ignore_index=255):
    os.makedirs(out_img_dir, exist_ok=True)
    os.makedirs(out_lbl_dir, exist_ok=True)

    # ==========================================
    # 🌟 全面适配最新版 Albumentations API
    # ==========================================
    aug_pipeline = A.Compose([
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.5),
        A.RandomRotate90(p=0.5),

        A.Affine(
            scale=(0.9, 1.1),
            translate_percent=(-0.0625, 0.0625),
            rotate=(-30, 30),
            cval=0,
            cval_mask=ignore_index,
            p=0.5
        ),

        A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.3),

        A.OneOf([
            A.GaussianBlur(blur_limit=(3, 5), p=1.0),
            A.MotionBlur(blur_limit=5, p=1.0),
        ], p=0.3),

        A.CoarseDropout(
            num_holes_range=(1, 8),
            hole_height_range=(8, 64),
            hole_width_range=(8, 64),
            fill=0,
            mask_fill=ignore_index,
            p=0.4
        )
    ], is_check_shapes=False)

    img_files = [f for f in os.listdir(img_dir) if f.endswith(('.tif', '.tiff'))]
    print(f"📦 发现 {len(img_files)} 张原图，准备扩充...")

    for img_name in tqdm(img_files, desc="数据增强进度"):

        # 🌟 极简读取：因为影像和标签名字已经完全一致，直接用同一个名字！
        lbl_name = img_name

        img_path = os.path.join(img_dir, img_name)
        lbl_path = os.path.join(lbl_dir, lbl_name)

        if not os.path.exists(lbl_path):
            continue

        # 1. 拷贝原图到输出文件夹
        import shutil
        shutil.copy(img_path, os.path.join(out_img_dir, img_name))
        shutil.copy(lbl_path, os.path.join(out_lbl_dir, lbl_name))

        with rasterio.open(img_path) as src_img, rasterio.open(lbl_path) as src_lbl:
            img_data = src_img.read()
            lbl_data = src_lbl.read(1)

            img_meta = src_img.meta.copy()
            lbl_meta = src_lbl.meta.copy()

            # 💡 极其关键的一步：记住原始数据类型！
            original_dtype = img_data.dtype

        # ==========================================
        # 🌟 强转 float32，拯救 OpenCV 底层崩溃！
        # ==========================================
        img_data_hwc = np.transpose(img_data, (1, 2, 0)).astype(np.float32)

        for i in range(aug_times):
            # 执行增强
            augmented = aug_pipeline(image=img_data_hwc, mask=lbl_data)

            aug_img_hwc = augmented['image']
            aug_lbl = augmented['mask']

            # 恢复通道排列，并【强转回原始类型】
            aug_img_chw = np.transpose(aug_img_hwc, (2, 0, 1)).astype(original_dtype)

            # 🌟 极简输出：不再添加 _image 或 _label 后缀，影像和掩膜共用同一名字
            base_name = os.path.splitext(img_name)[0]
            shared_aug_name = f"{base_name}_aug_{i}.tif"

            with rasterio.open(os.path.join(out_img_dir, shared_aug_name), 'w', **img_meta) as dst_img:
                dst_img.write(aug_img_chw)
            with rasterio.open(os.path.join(out_lbl_dir, shared_aug_name), 'w', **lbl_meta) as dst_lbl:
                dst_lbl.write(aug_lbl, 1)

    print(f"\n✅ 数据扩充完成！原数据扩大了 {aug_times + 1} 倍！文件名保持绝对干净！")


# ==========================================
# 🚀 运行配置区
# ==========================================
if __name__ == "__main__":
    # 读取你刚切好、分好比例、名字干干净净的数据集
    TRAIN_IMG_DIR = r"/mnt/d/sc_data/2_final_dataset/train/images"
    TRAIN_LBL_DIR = r"/mnt/d/sc_data/2_final_dataset/train/labels"

    # 输出到你指定的最终训练集目录
    AUG_IMG_DIR = r"/mnt/d/sc_data/train/images"
    AUG_LBL_DIR = r"/mnt/d/sc_data/train/labels"

    augment_dataset(
        img_dir=TRAIN_IMG_DIR,
        lbl_dir=TRAIN_LBL_DIR,
        out_img_dir=AUG_IMG_DIR,
        out_lbl_dir=AUG_LBL_DIR,
        aug_times=3,  # 👈 1张原图生成3张增强图，总计4倍数据量
        ignore_index=255
    )