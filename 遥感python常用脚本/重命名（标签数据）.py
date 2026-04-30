import os


def rename_in_place(img_dir, lbl_dir):
    print("🚀 开始原地清洗影像文件名...")
    img_count = 0
    for filename in os.listdir(img_dir):
        if not filename.endswith('.tif'):
            continue

        # 核心替换逻辑：洗掉影像名字里所有多余的 '_image'
        new_name = filename.replace('_image_aug_', '_aug_').replace('_image.tif', '.tif')

        # 如果名字发生了改变，就执行原地重命名
        if new_name != filename:
            old_path = os.path.join(img_dir, filename)
            new_path = os.path.join(img_dir, new_name)
            os.rename(old_path, new_path)  # 原地操作，不耗费任何额外空间
            img_count += 1

    print("🚀 开始原地清洗标签文件名...")
    lbl_count = 0
    for filename in os.listdir(lbl_dir):
        if not filename.endswith('.tif'):
            continue

        # 核心替换逻辑：洗掉标签名字里所有多余的 '_label'
        new_name = filename.replace('_label_aug_', '_aug_').replace('_label.tif', '.tif')

        if new_name != filename:
            old_path = os.path.join(lbl_dir, filename)
            new_path = os.path.join(lbl_dir, new_name)
            os.rename(old_path, new_path)
            lbl_count += 1

    print("\n🎉 大功告成！")
    print(f"成功原地重命名了 {img_count} 张影像 和 {lbl_count} 张标签！")
    print("现在随便点开两个文件夹对比一下，它们的名字已经完全一模一样了！")


# ====================
# 运行配置区
# ====================
if __name__ == "__main__":
    # 填入你刚才截图里的真实文件夹路径
    TRAIN_IMG_DIR = r"/mnt/d/sc_data/val/images"
    TRAIN_LBL_DIR = r"/mnt/d/sc_data/val/labels"

    rename_in_place(TRAIN_IMG_DIR, TRAIN_LBL_DIR)