import os

def rename_files_in_directory(root_directory):
    """
    遍历根目录及其所有子目录，重命名符合条件的文件。
    如果文件名中包含关键词 'mask'，则跳过重命名。
    """
    print("开始重命名文件...")
    for subdir, dirs, files in os.walk(root_directory):
        for file in files:
            # 拼接完整的文件路径
            file_path = os.path.join(subdir, file)

            # 如果文件名中包含 'mask'，跳过该文件
            if "mask" in file.lower():
                print(f"跳过文件（包含 'mask'）: {file_path}")
                continue

            # 检查文件名是否符合 GF02_MS*.tif 或 GF02_MS*.rpb
            if file.startswith("GF02_MS") and file.endswith(".tif"):
                # 提取文件名（不包含扩展名）
                base_name = os.path.splitext(file)[0]
                # 替换 GF02 为 GF2，并构造新的文件名
                new_name = base_name.replace("GF02", "GF2") + "-MSS.tiff"
                new_file_path = os.path.join(subdir, new_name)
                # 重命名文件
                os.rename(file_path, new_file_path)
                print(f"Renamed: {file_path} -> {new_file_path}")

            elif file.startswith("GF02_MS") and file.endswith(".rpb"):
                base_name = os.path.splitext(file)[0]
                new_name = base_name.replace("GF02", "GF2") + "-MSS.rpb"
                new_file_path = os.path.join(subdir, new_name)
                os.rename(file_path, new_file_path)
                print(f"Renamed: {file_path} -> {new_file_path}")

            # 检查文件名是否符合 GF02_PA*.tif 或 GF02_PA*.rpb
            elif file.startswith("GF02_PA") and file.endswith(".tif"):
                base_name = os.path.splitext(file)[0]
                new_name = base_name.replace("GF02", "GF2") + "-PAN.tiff"
                new_file_path = os.path.join(subdir, new_name)
                os.rename(file_path, new_file_path)
                print(f"Renamed: {file_path} -> {new_file_path}")

            elif file.startswith("GF02_PA") and file.endswith(".rpb"):
                base_name = os.path.splitext(file)[0]
                new_name = base_name.replace("GF02", "GF2") + "-PAN.rpb"
                new_file_path = os.path.join(subdir, new_name)
                os.rename(file_path, new_file_path)
                print(f"Renamed: {file_path} -> {new_file_path}")

    print("所有符合条件的文件已成功重命名。")


# 用户指定根目录
if __name__ == "__main__":
    root_directory = input("请输入根目录路径：")
    if not os.path.isdir(root_directory):
        print("指定的路径不是一个有效的目录！")
    else:
        rename_files_in_directory(root_directory)