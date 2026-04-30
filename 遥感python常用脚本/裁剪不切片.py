# -*- coding: utf-8 -*-
"""
批量按 shp 裁剪遥感影像脚本（仅输出 GeoTIFF，不切片）
------------------------------------------------
功能：
1. 从输入目录递归读取所有 tif/tiff 文件（不区分扩展名大小写）
2. 不修改原始影像
3. 将按 shp 裁剪后的结果另存到新的输出目录
4. 保留 GeoTIFF 地理信息
5. shp 坐标系自动对齐到影像 CRS（仅内存中处理，不改原始 shp）
6. 自动判断 shp 与 tif 的空间关系
7. 支持：
   - crop=True：按 shp 外接范围裁剪，并仅保留 shp 内像元
   - crop=False：保持原图大小，仅将 shp 外区域置为 nodata
8. 保存总索引 CSV
9. 保存失败记录 CSV

依赖：
pip install rasterio geopandas shapely numpy pandas tqdm
"""

from pathlib import Path
import traceback

import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from rasterio.features import geometry_mask
import geopandas as gpd
from shapely.geometry import box, mapping
from shapely.ops import unary_union
from tqdm import tqdm


def find_all_tifs(input_dir, recursive=True):
    """
    查找目录下所有 tif/tiff 文件，不区分扩展名大小写
    """
    input_dir = Path(input_dir)
    if recursive:
        files = [
            p for p in input_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in [".tif", ".tiff"]
        ]
    else:
        files = [
            p for p in input_dir.glob("*")
            if p.is_file() and p.suffix.lower() in [".tif", ".tiff"]
        ]
    return sorted(files)


def load_shp_geoms(shp_path, target_crs):
    """
    读取 shp，并自动对齐到影像 CRS
    注意：这里只在内存中投影，不会修改原始 shp 文件
    """
    gdf = gpd.read_file(shp_path)

    if gdf.empty:
        raise ValueError(f"shp 为空: {shp_path}")

    if gdf.crs is None:
        raise ValueError(f"shp 没有定义坐标系: {shp_path}")

    if target_crs is None:
        raise ValueError("影像没有定义 CRS，无法将 shp 自动对齐到影像坐标系")

    if str(gdf.crs) != str(target_crs):
        print(f"  检测到坐标系不一致：shp={gdf.crs}，影像={target_crs}")
        print("  正在自动将 shp 对齐到影像坐标系...")
        gdf = gdf.to_crs(target_crs)
    else:
        print(f"  shp 与影像坐标系一致：{target_crs}")

    geoms = [g for g in gdf.geometry if g is not None and not g.is_empty]
    if len(geoms) == 0:
        raise ValueError(f"shp 没有有效几何: {shp_path}")

    union_geom = unary_union(geoms)
    return geoms, union_geom


def check_tif_shp_relation(src, shp_union_geom):
    """
    判断 tif 与 shp 的空间关系
    返回：
    - inside: tif 完全在 shp 内（shp 覆盖 tif）
    - intersect: tif 与 shp 部分相交
    - disjoint: tif 与 shp 不相交
    """
    left, bottom, right, top = src.bounds
    tif_geom = box(left, bottom, right, top)

    if shp_union_geom.contains(tif_geom):
        return "inside"
    elif shp_union_geom.intersects(tif_geom):
        return "intersect"
    else:
        return "disjoint"


def crop_one_raster(
    image_path,
    out_dir,
    shp_path,
    crop=True,
    nodata_value=0,
    compress="lzw",
):
    """
    对单个影像按 shp 裁剪
    参数：
    - crop=True:
        输出范围缩到 shp 外接矩形范围，且 shp 外区域置 nodata
    - crop=False:
        保持原图大小，仅将 shp 外区域置 nodata
    """
    image_path = Path(image_path)
    out_dir = Path(out_dir)

    out_subdir = out_dir / "cropped_tif"
    out_subdir.mkdir(parents=True, exist_ok=True)

    stem = image_path.stem
    out_tif = out_subdir / f"{stem}_crop.tif"

    with rasterio.open(image_path) as src:
        src_crs = src.crs
        src_nodata = src.nodata if src.nodata is not None else nodata_value

        print(f"\n开始处理: {image_path.name}")
        print(f"  尺寸: {src.width} x {src.height}")
        print(f"  波段数: {src.count}")
        print(f"  CRS: {src_crs}")
        print(f"  nodata: {src.nodata}")

        shp_geoms, shp_union_geom = load_shp_geoms(shp_path, src_crs)
        relation = check_tif_shp_relation(src, shp_union_geom)

        if relation == "inside":
            print("  空间关系: shp 完全覆盖当前影像")
        elif relation == "intersect":
            print("  空间关系: shp 与当前影像部分相交")
        else:
            print("  空间关系: shp 与当前影像不相交，跳过")
            return None

        shp_geojson = [mapping(g) for g in shp_geoms]

        if crop:
            # 裁剪到 shp 范围，并将 shp 外区域置 nodata
            out_image, out_transform = mask(
                src,
                shp_geojson,
                crop=True,
                nodata=src_nodata,
                filled=True
            )

            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "count": out_image.shape[0],
                "nodata": src_nodata,
                "compress": compress
            })

        else:
            # 保持原图尺寸，仅将 shp 外区域置 nodata
            out_image = src.read()

            outside_mask = geometry_mask(
                shp_geojson,
                out_shape=(src.height, src.width),
                transform=src.transform,
                invert=False
            )
            out_image[:, outside_mask] = src_nodata

            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": src.transform,
                "count": out_image.shape[0],
                "nodata": src_nodata,
                "compress": compress
            })

        with rasterio.open(out_tif, "w", **out_meta) as dst:
            dst.write(out_image)

        print(f"  输出完成: {out_tif}")

        record = {
            "source_image": str(image_path),
            "output_image": str(out_tif),
            "width": out_meta["width"],
            "height": out_meta["height"],
            "count": out_meta["count"],
            "crs": str(src_crs),
            "nodata": src_nodata,
            "crop_mode": crop,
        }

        return record


def batch_crop_rasters(
    input_dir,
    out_dir,
    shp_path,
    recursive=True,
    crop=True,
    nodata_value=0,
    compress="lzw",
):
    """
    批量处理输入目录下所有 tif/tiff，按 shp 裁剪
    """
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tif_files = find_all_tifs(input_dir, recursive=recursive)
    if len(tif_files) == 0:
        print("没有找到任何 tif/tiff 文件")
        return

    print(f"共发现 {len(tif_files)} 个影像文件")
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {out_dir}")
    print(f"shp: {shp_path}")
    print(f"crop 模式: {crop}  ({'裁剪到 shp 范围' if crop else '保持原图大小，仅掩膜 shp 外区域'})")

    all_records = []
    failed_files = []

    for image_path in tqdm(tif_files, desc="总进度"):
        try:
            record = crop_one_raster(
                image_path=image_path,
                out_dir=out_dir,
                shp_path=shp_path,
                crop=crop,
                nodata_value=nodata_value,
                compress=compress,
            )
            if record is not None:
                all_records.append(record)
        except Exception as e:
            failed_files.append((str(image_path), str(e)))
            print(f"\n处理失败: {image_path}")
            print(f"原因: {e}")
            print(traceback.format_exc())

    if all_records:
        csv_path = out_dir / "crop_index_all.csv"
        pd.DataFrame(all_records).to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n全部处理完成，成功输出 {len(all_records)} 个裁剪结果")
        print(f"总索引文件: {csv_path}")
    else:
        print("\n没有生成任何有效裁剪结果")

    if failed_files:
        fail_csv = out_dir / "failed_files.csv"
        pd.DataFrame(failed_files, columns=["file", "error"]).to_csv(
            fail_csv, index=False, encoding="utf-8-sig"
        )
        print(f"失败文件数: {len(failed_files)}")
        print(f"失败记录: {fail_csv}")


if __name__ == "__main__":
    # =========================
    # 参数区：按需修改
    # =========================
    input_dir = r"G:\美丽海湾数据\select"   # 输入目录
    out_dir = r"G:\美丽海湾数据\crop_result"        # 输出目录
    shp_path = r"E:\进行时\美丽海湾\研究区\研究区shp手画\研究区域.shp"  # shp 路径

    batch_crop_rasters(
        input_dir=input_dir,
        out_dir=out_dir,
        shp_path=shp_path,
        recursive=True,     # 是否递归搜索子目录
        crop=False,          # True=裁剪到 shp 范围；False=保持原图大小，仅掩膜 shp 外区域
        nodata_value=0,
        compress="lzw",
    )