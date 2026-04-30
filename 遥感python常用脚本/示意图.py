import os
import rasterio
import numpy as np
import numpy.ma as ma  # <--- 新增：用于生成掩膜屏蔽无效区域
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap


def percent_stretch(img, lower_percent=2, upper_percent=98):
    """遥感影像 2%-98% 拉伸，防止原图发灰发暗"""
    img = np.nan_to_num(img)
    out_img = np.zeros_like(img, dtype=np.float32)
    for i in range(img.shape[2]):
        band = img[:, :, i]
        lower_bound = np.percentile(band, lower_percent)
        upper_bound = np.percentile(band, upper_percent)
        stretched = np.clip(band, lower_bound, upper_bound)
        if upper_bound - lower_bound == 0:
            out_img[:, :, i] = 0
        else:
            out_img[:, :, i] = (stretched - lower_bound) / (upper_bound - lower_bound)
    return out_img


def batch_generate_figures_aquatic(img_dir, label_dir, out_dir, bands_to_extract, label_ext='.png'):
    """生成带图例的水生植被 1x3 SCI 对比图 (自动过滤无效黑边)"""
    os.makedirs(out_dir, exist_ok=True)

    # --- 水生植被配色方案 ---
    # 0: Water, 1: SV (沉水), 2: FV (浮叶), 3: EV (挺水)
    colors = ['#1E90FF', '#20B2AA', '#32CD32', '#228B22']
    class_names = ['Water', 'SV (Submerged)', 'FV (Floating)', 'EV (Emergent)']

    cmap = ListedColormap(colors)
    # <--- 新增：告诉 matplotlib，遇到被掩膜掉的坏数据(无效区)，显示为完全透明
    cmap.set_bad(color='#00000000')

    legend_patches = [mpatches.Patch(color=colors[i], label=class_names[i]) for i in range(len(colors))]

    for img_filename in os.listdir(img_dir):
        if not img_filename.lower().endswith(('.tif', '.tiff')):
            continue

        base_name = os.path.splitext(img_filename)[0]
        label_filename = base_name + label_ext
        img_path = os.path.join(img_dir, img_filename)
        label_path = os.path.join(label_dir, label_filename)
        out_path = os.path.join(out_dir, f"{base_name}_demo.png")

        if not os.path.exists(label_path):
            print(f"⚠️ 跳过 {base_name}: 未找到对应标签 {label_filename}")
            continue

        print(f"正在处理: {base_name} ...")

        try:
            # 1. 读原图
            with rasterio.open(img_path) as src_img:
                img = src_img.read(bands_to_extract)
                img = np.transpose(img, (1, 2, 0))

            # <--- 新增核心逻辑：寻找无效黑边区域
            # 如果某个像素在提取的三个波段上全是0，我们就认为它是无效边界 (NoData)
            invalid_mask = np.all(img == 0, axis=-1)

            # 拉伸原图，并确保黑边区域在拉伸后依然是绝对的黑(0)
            img_show = percent_stretch(img)
            img_show[invalid_mask] = 0

            # 2. 读标签
            with rasterio.open(label_path) as src_label:
                label = src_label.read(1)

            # <--- 新增核心逻辑：屏蔽标签中的黑边区
            # 哪怕标签图里无效区标的是 0(水体)，这里也会强制把它标记为“无效遮罩”
            label_masked = ma.masked_where(invalid_mask, label)

            # 3. 绘图排版
            fig, axes = plt.subplots(1, 3, figsize=(18, 7), dpi=500)

            # (A) 原图
            axes[0].imshow(img_show)
            axes[0].set_title(f"Image (Bands {bands_to_extract})", fontsize=22, pad=10)
            axes[0].axis('off')

            # (B) 真值标签图 + 图例
            # 注意：这里传入的是 label_masked
            axes[1].imshow(label_masked, cmap=cmap, interpolation='nearest', vmin=0, vmax=3)
            axes[1].set_title("Ground Truth", fontsize=22, pad=10)
            axes[1].axis('off')
            axes[1].legend(handles=legend_patches, loc='lower right',
                           fontsize=10, framealpha=0.8, edgecolor='none')

            # (C) 叠加图
            axes[2].imshow(img_show)
            # 注意：这里传入的也是 label_masked
            axes[2].imshow(label_masked, cmap=cmap, alpha=0.45, interpolation='nearest', vmin=0, vmax=3)
            axes[2].set_title("Overlay", fontsize=22, pad=10)
            axes[2].axis('off')

            plt.tight_layout()
            plt.savefig(out_path, bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)

        except Exception as e:
            print(f"❌ 处理 {base_name} 时发生错误: {e}")


# ==========================================
# 🚀 程序的真正入口：修改这里的参数即可运行
# ==========================================
if __name__ == "__main__":
    # 1. 设置你的文件夹路径 (Windows 路径建议前面加 r，Linux/Mac 也可以保持)
    IMG_DIR = r"/mnt/e/进行时/论文/小论文/示例/images"
    LABEL_DIR = r"/mnt/e/进行时/论文/小论文/示例/labels"
    OUT_DIR = r"/mnt/e/进行时/论文/小论文/示例/output_figs"

    # 2. 设置波段和格式
    BAND_ORDER = [4, 3, 2]  # [4,3,2]通常是假彩色，[3,2,1]或[1,2,3]是真彩色。
    LABEL_EXTENSION = ".png"

    print("开始批量生成数据集展示图 (包含黑边过滤)...")
    print("-" * 30)

    # 执行主函数
    batch_generate_figures_aquatic(
        img_dir=IMG_DIR,
        label_dir=LABEL_DIR,
        out_dir=OUT_DIR,
        bands_to_extract=BAND_ORDER,
        label_ext=LABEL_EXTENSION
    )

    print("-" * 30)
    print(f"✅ 全部处理完毕！请前往 {OUT_DIR} 查看生成的图片。")