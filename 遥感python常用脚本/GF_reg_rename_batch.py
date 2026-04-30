import os
import glob
import shutil
import tkinter as tk
from tkinter import filedialog


def get_base_filename_from_pms(pms_rpb_path):
    """
    从多光谱RPB文件路径中提取基础文件名。
    例如: GF6_PMS_E123.4_N45.6_20240101_L1A0000123456-MSS.rpb
    返回: GF6_PMS_E123.4_N45.6_20240101_L1A0000123456
    """
    filename = os.path.basename(pms_rpb_path)
    # 移除 .rpb 扩展名
    base = os.path.splitext(filename)[0]
    # 移除 -MSS 或 -PAN 后缀
    if "-MSS" in base:
        base = base.split("-MSS")[0]
    elif "-PAN" in base:
        base = base.split("-PAN")[0]
    return base


def get_base_filename_from_xml(xml_path):
    """
    从多光谱XML文件路径中提取基础文件名。
    例如: GF2_PMS2_xxx-MSS2.xml 或 GF2_PMS2_xxx-MUX.xml
    返回: GF2_PMS2_xxx
    """
    filename = os.path.basename(xml_path)
    # 移除 .xml 扩展名
    base = os.path.splitext(filename)[0]
    # 移除 -MSS1, -MSS2, -MUX 后缀
    if "-MSS" in base:
        base = base.split("-MSS")[0]
    elif "-MUX" in base:
        base = base.split("-MUX")[0]
    return base


def is_gf6(filename):
    """
    判断文件是否为GF6卫星数据。
    通过检查文件名第3位字符是否为'6'来判断。
    """
    name = os.path.basename(filename)
    # GF6 文件名格式: GF6_...
    if len(name) >= 3 and name[2] == '6':
        return True
    return False


def move_with_retry(src, dst, max_retries=3, delay=1):
    """
    带重试的文件移动操作，处理文件被占用的情况
    """
    import time
    for attempt in range(max_retries):
        try:
            shutil.move(src, dst)
            return True
        except (PermissionError, OSError) as e:
            if attempt < max_retries - 1:
                print(f"  文件被占用，等待 {delay} 秒后重试... (尝试 {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise e


def get_unique_filepath(output_dir, filename):
    """
    生成唯一的文件路径，处理重名情况。
    如果文件已存在，添加序号后缀，如 file_1.rpb, file_2.rpb
    """
    base, ext = os.path.splitext(filename)
    counter = 1
    new_path = os.path.join(output_dir, filename)

    while os.path.exists(new_path):
        new_filename = f"{base}_{counter}{ext}"
        new_path = os.path.join(output_dir, new_filename)
        counter += 1

    return new_path


def find_file_case_insensitive(directory, filename):
    """
    在目录中查找文件（不区分大小写）
    返回完整路径或None
    """
    if not os.path.isdir(directory):
        return None

    # 首先尝试直接访问
    direct_path = os.path.join(directory, filename)
    if os.path.exists(direct_path):
        return direct_path

    # 列出目录中的所有文件，进行不区分大小写匹配
    try:
        files = os.listdir(directory)
        for f in files:
            if f.lower() == filename.lower():
                return os.path.join(directory, f)
    except Exception:
        pass

    return None


def find_files_case_insensitive(input_dir, pattern):
    """
    不区分大小写查找文件
    """
    files = glob.glob(os.path.join(input_dir, pattern), recursive=True)
    # 同时尝试小写扩展名
    lower_pattern = pattern.lower()
    if lower_pattern != pattern:
        files.extend(glob.glob(os.path.join(input_dir, lower_pattern), recursive=True))
    # 尝试大写扩展名
    upper_pattern = pattern.upper()
    if upper_pattern != pattern:
        files.extend(glob.glob(os.path.join(input_dir, upper_pattern), recursive=True))
    # 去重
    return list(set(files))


def process_scene_files(input_dir, output_dir):
    """
    处理场景文件：
    1. 筛选多光谱和全色RPB文件
    2. 找到对应的融合后HRMS文件
    3. 复制到输出目录并重命名为 *_HRMS_REG.RPB 和 *_HRMS_REG.TIF
    4. 移动reg文件到输出目录
    """
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    print("开始处理文件...")

    # 筛选多光谱RPB文件 (GF*PMS*M*.rpb) - 不区分大小写
    pms_rpbs = find_files_case_insensitive(input_dir, "**/GF*PMS*M*.rpb")
    pms_rpbs.extend(find_files_case_insensitive(input_dir, "**/GF*PMS*M*.RPB"))
    pms_rpbs = list(set(pms_rpbs))

    # 筛选全色RPB文件 (GF*PAN*.rpb) - 不区分大小写
    pan_rpbs = find_files_case_insensitive(input_dir, "**/GF*PAN*.rpb")
    pan_rpbs.extend(find_files_case_insensitive(input_dir, "**/GF*PAN*.RPB"))
    pan_rpbs = list(set(pan_rpbs))

    # 筛选融合后的HRMS文件 - 不区分大小写
    hrms_rpbs = []
    hrms_rpbs.extend(find_files_case_insensitive(input_dir, "**/HRMS*.RPB"))
    hrms_rpbs.extend(find_files_case_insensitive(input_dir, "**/HRMS*.rpb"))
    hrms_rpbs = list(set(hrms_rpbs))

    hrms_tifs = []
    hrms_tifs.extend(find_files_case_insensitive(input_dir, "**/HRMS*.TIF"))
    hrms_tifs.extend(find_files_case_insensitive(input_dir, "**/HRMS*.tif"))
    hrms_tifs = list(set(hrms_tifs))

    # 筛选reg文件 - 不区分大小写
    reg_rpbs = []
    reg_rpbs.extend(find_files_case_insensitive(input_dir, "**/GF*reg.RPB"))
    reg_rpbs.extend(find_files_case_insensitive(input_dir, "**/GF*reg.rpb"))
    reg_rpbs = list(set(reg_rpbs))

    reg_tifs = []
    reg_tifs.extend(find_files_case_insensitive(input_dir, "**/GF*reg.TIF"))
    reg_tifs.extend(find_files_case_insensitive(input_dir, "**/GF*reg.tif"))
    reg_tifs = list(set(reg_tifs))

    print(f"找到 {len(pms_rpbs)} 个多光谱RPB文件")
    print(f"找到 {len(pan_rpbs)} 个全色RPB文件")
    print(f"找到 {len(hrms_rpbs)} 个HRMS RPB文件")
    print(f"找到 {len(hrms_tifs)} 个HRMS TIF文件")
    print(f"找到 {len(reg_rpbs)} 个reg RPB文件")
    print(f"找到 {len(reg_tifs)} 个reg TIF文件")

    # 筛选多光谱XML文件 (GF*PMS*-MSS*.xml, GF*PMS*-MUX.xml) - 不区分大小写
    mss_xmls = []
    mss_xmls.extend(find_files_case_insensitive(input_dir, "**/GF*PMS*-MSS*.xml"))
    mss_xmls.extend(find_files_case_insensitive(input_dir, "**/GF*PMS*-MUX.xml"))
    mss_xmls = list(set(mss_xmls))

    # 处理融合后的HRMS文件
    processed_count = 0

    # 遍历所有多光谱RPB文件对应的场景
    all_scenes = set()
    for pms_rpb in pms_rpbs:
        base_filename = get_base_filename_from_pms(pms_rpb)
        all_scenes.add((base_filename, pms_rpb))

    for base_filename, pms_rpb in all_scenes:
        # 判断是否为GF6
        scene_dir = os.path.dirname(pms_rpb)

        if is_gf6(pms_rpb):
            # GF6 融合后文件名是 PAN.rpb 和 PAN.tif (不区分大小写)
            hrms_rpb_path = find_file_case_insensitive(scene_dir, "PAN.rpb")
            hrms_tif_path = find_file_case_insensitive(scene_dir, "PAN.tif")
        else:
            # 其他卫星使用 HRMS.rpb / HRMS.tif 或 HRMS_REG.RPB / HRMS_REG.TIF (不区分大小写)
            # 先尝试 HRMS.rpb/tif
            hrms_rpb_path = find_file_case_insensitive(scene_dir, "HRMS.rpb")
            hrms_tif_path = find_file_case_insensitive(scene_dir, "HRMS.tif")

            # 如果没找到，尝试 HRMS_REG.RPB/TIF
            if not hrms_rpb_path:
                hrms_rpb_path = find_file_case_insensitive(scene_dir, "HRMS_REG.RPB")
            if not hrms_tif_path:
                hrms_tif_path = find_file_case_insensitive(scene_dir, "HRMS_REG.TIF")

        # 生成新的文件名
        new_rpb_name = f"{base_filename}_HRMS_REG.RPB"
        new_tif_name = f"{base_filename}_HRMS_REG.TIF"

        # 移动RPB文件（重命名并移动）
        if hrms_rpb_path:
            dest_rpb = get_unique_filepath(output_dir, new_rpb_name)
            move_with_retry(hrms_rpb_path, dest_rpb)
            print(f"移动: {hrms_rpb_path} -> {dest_rpb}")
            processed_count += 1
        else:
            print(f"警告: 未找到 HRMS RPB 文件 (场景: {base_filename})")

        # 移动TIF文件（重命名并移动）
        if hrms_tif_path:
            dest_tif = get_unique_filepath(output_dir, new_tif_name)
            move_with_retry(hrms_tif_path, dest_tif)
            print(f"移动: {hrms_tif_path} -> {dest_tif}")
        else:
            print(f"警告: 未找到 HRMS TIF 文件 (场景: {base_filename})")

    # 移动reg文件到输出目录
    for reg_rpb in reg_rpbs:
        filename = os.path.basename(reg_rpb)
        dest_path = get_unique_filepath(output_dir, filename)
        move_with_retry(reg_rpb, dest_path)
        print(f"移动reg RPB: {reg_rpb} -> {dest_path}")

    for reg_tif in reg_tifs:
        filename = os.path.basename(reg_tif)
        dest_path = get_unique_filepath(output_dir, filename)
        move_with_retry(reg_tif, dest_path)
        print(f"移动reg TIF: {reg_tif} -> {dest_path}")

    # 处理多光谱XML文件，复制并重命名为 *_HRMS_REG.xml
    xml_processed = 0
    for xml_path in mss_xmls:
        base_filename = get_base_filename_from_xml(xml_path)
        new_xml_name = f"{base_filename}_HRMS_REG.xml"
        dest_xml = get_unique_filepath(output_dir, new_xml_name)
        shutil.copy2(xml_path, dest_xml)
        print(f"复制XML: {xml_path} -> {dest_xml}")
        xml_processed += 1

    print(f"\n处理完成！共处理 {processed_count} 个场景的HRMS文件")
    print(f"共复制 {xml_processed} 个XML文件")
    print(f"所有文件已移动/复制到输出目录: {output_dir}")


def select_folder(title="选择文件夹"):
    """
    打开文件夹选择对话框
    返回选中的文件夹路径，如果取消则返回None
    """
    # 创建隐藏的主窗口
    root = tk.Tk()
    root.withdraw()
    # 设置窗口在最前面
    root.attributes('-topmost', True)
    # 打开文件夹选择对话框
    folder_path = filedialog.askdirectory(title=title)
    # 销毁窗口
    root.destroy()
    return folder_path if folder_path else None


def main():
    """
    主函数：获取输入输出目录并执行处理
    """
    print("=" * 50)
    print("GF卫星影像文件重命名工具")
    print("=" * 50)

    # 选择输入目录
    print("\n请选择输入目录（包含GF影像文件的文件夹）...")
    input_dir = select_folder("选择输入目录（包含GF影像文件的文件夹）")
    if not input_dir:
        print("未选择输入目录，程序退出。")
        return

    # 选择输出目录
    print("\n请选择输出目录（处理后文件的保存位置）...")
    output_dir = select_folder("选择输出目录（处理后文件的保存位置）")
    if not output_dir:
        print("未选择输出目录，程序退出。")
        return

    os.makedirs(output_dir, exist_ok=True)

    # 确认信息
    print("\n" + "=" * 50)
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print("=" * 50)

    confirm = input("\n确认开始处理? (y/n): ").strip().lower()
    if confirm == 'y':
        process_scene_files(input_dir, output_dir)
    else:
        print("操作已取消。")


if __name__ == "__main__":
    main()
