# -*- coding: utf-8 -*-
"""
批量遥感影像切片脚本（最终整合版，仅输出 GeoTIFF）
------------------------------------------------
功能：
1. 从输入目录递归读取所有 tif/tiff 文件（不区分扩展名大小写）
2. 不修改原始影像
3. 将切片结果另存到新的输出目录
4. 保留每个切片的 GeoTIFF 地理信息
5. 可选使用 shp 约束切片范围
6. shp 坐标系自动对齐到影像坐标系（仅内存中处理，不改原始 shp）
7. 自动判断 shp 与 tif 的空间关系
8. 保存总索引 CSV
9. 跳过空白块
10. 可选将 shp 外区域置为 nodata

依赖：
pip install rasterio geopandas shapely numpy pandas tqdm
"""

from pathlib import Path
import traceback

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from rasterio.features import geometry_mask
from rasterio.transform import xy
import geopandas as gpd
from shapely.geometry import box
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


def generate_positions(length, tile_size, stride):
    """
    生成切片起点，保证覆盖到边缘
    """
    if length <= tile_size:
        return [0]

    pos = list(range(0, length - tile_size + 1, stride))
    if pos[-1] != length - tile_size:
        pos.append(length - tile_size)
    return pos


def is_mostly_empty(tile, nodata=None, empty_ratio_threshold=0.98, std_threshold=2.0):
    """
    判断切片是否大部分为空
    tile: [C, H, W]
    """
    if tile.ndim != 3:
        raise ValueError("tile 必须为 [C, H, W]")

    zero_mask = np.all(tile == 0, axis=0)

    if nodata is not None:
        nodata_mask = np.all(tile == nodata, axis=0)
        empty_mask = zero_mask | nodata_mask
    else:
        empty_mask = zero_mask

    empty_ratio = empty_mask.mean()
    if empty_ratio >= empty_ratio_threshold:
        return True

    use_c = min(3, tile.shape[0])
    gray = tile[:use_c].astype(np.float32).mean(axis=0)
    gray_valid = gray[~empty_mask]
    if gray_valid.size > 0 and np.std(gray_valid) < std_threshold:
        return True

    return False


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


def window_intersects_shp(src, window, shp_union_geom):
    """
    判断当前切片窗口是否与 shp 相交
    """
    wt = window_transform(window, src.transform)
    left, top = xy(wt, 0, 0, offset="ul")
    right, bottom = xy(wt, window.height, window.width, offset="lr")

    win_geom = box(left, bottom, right, top)
    return shp_union_geom.intersects(win_geom)


def mask_outside_shp(tile, src, window, shp_geoms, nodata_value=0):
    """
    将 tile 中 shp 外区域置为 nodata
    tile: [C, H, W]
    """
    wt = window_transform(window, src.transform)
    outside_mask = geometry_mask(
        shp_geoms,
        out_shape=(tile.shape[1], tile.shape[2]),
        transform=wt,
        invert=False
    )

    tile2 = tile.copy()
    tile2[:, outside_mask] = nodata_value
    return tile2


def tile_one_raster(
    image_path,
    out_dir,
    shp_path=None,
    tile_size=512,
    overlap=128,
    empty_ratio_threshold=0.98,
    std_threshold=2.0,
    mask_outside_geometry=False,
    nodata_value=0,
):
    """
    对单个影像切片
    返回 records 列表
    """
    image_path = Path(image_path)
    out_dir = Path(out_dir)

    stem = image_path.stem
    tif_dir = out_dir / "tiles_tif" / stem
    tif_dir.mkdir(parents=True, exist_ok=True)

    stride = tile_size - overlap
    if stride <= 0:
        raise ValueError("overlap 必须小于 tile_size")

    records = []

    with rasterio.open(image_path) as src:
        width, height = src.width, src.height
        src_crs = src.crs
        src_nodata = src.nodata if src.nodata is not None else nodata_value

        print(f"\n开始处理: {image_path.name}")
        print(f"  尺寸: {width} x {height}")
        print(f"  波段数: {src.count}")
        print(f"  CRS: {src_crs}")
        print(f"  nodata: {src.nodata}")

        shp_geoms = None
        shp_union_geom = None

        if shp_path is not None:
            shp_geoms, shp_union_geom = load_shp_geoms(shp_path, src_crs)
            relation = check_tif_shp_relation(src, shp_union_geom)

            if relation == "inside":
                print(f"  空间关系: shp 完全覆盖当前影像，将按整幅影像范围切片。")
            elif relation == "intersect":
                print(f"  空间关系: shp 与当前影像部分相交，将仅对相交区域切片。")
            else:
                print(f"  空间关系: shp 与当前影像不相交，该影像不会生成切片。")
                return []

        xs = generate_positions(width, tile_size, stride)
        ys = generate_positions(height, tile_size, stride)

        theoretical_count = len(xs) * len(ys)
        print(f"  理论切片窗口数: {theoretical_count}")

        tile_id = 0

        for y in tqdm(ys, desc=f"{image_path.name}"):
            for x in xs:
                window = Window(x, y, tile_size, tile_size)

                # 若有 shp，则要求窗口与 shp 相交
                if shp_union_geom is not None:
                    if not window_intersects_shp(src, window, shp_union_geom):
                        continue

                tile = src.read(window=window)  # [C, H, W]
                c, h, w = tile.shape

                # 边缘不足 tile_size 时 pad
                if h != tile_size or w != tile_size:
                    padded = np.full(
                        (c, tile_size, tile_size),
                        fill_value=src_nodata,
                        dtype=tile.dtype
                    )
                    padded[:, :h, :w] = tile
                    tile = padded

                # 若设置 mask_outside_geometry=True，则把 shp 外区域置为 nodata
                if shp_geoms is not None and mask_outside_geometry:
                    tile = mask_outside_shp(
                        tile=tile,
                        src=src,
                        window=window,
                        shp_geoms=shp_geoms,
                        nodata_value=src_nodata
                    )

                # 跳过空白块
                if is_mostly_empty(
                    tile,
                    nodata=src_nodata,
                    empty_ratio_threshold=empty_ratio_threshold,
                    std_threshold=std_threshold
                ):
                    continue

                wt = window_transform(window, src.transform)

                tile_name = f"{stem}_x{x}_y{y}_id{tile_id:06d}"
                out_tif = tif_dir / f"{tile_name}.tif"

                profile = src.profile.copy()
                profile.update({
                    "driver": "GTiff",
                    "height": tile.shape[1],
                    "width": tile.shape[2],
                    "transform": wt,
                    "count": tile.shape[0],
                    "nodata": src_nodata
                })

                # 写入新文件，不修改原始影像
                with rasterio.open(out_tif, "w", **profile) as dst:
                    dst.write(tile)

                left, top = xy(wt, 0, 0, offset="ul")
                right, bottom = xy(wt, tile.shape[1], tile.shape[2], offset="lr")

                records.append({
                    "source_image": str(image_path),
                    "tile_name": tile_name,
                    "tile_tif": str(out_tif),
                    "x_offset": x,
                    "y_offset": y,
                    "tile_size": tile_size,
                    "overlap": overlap,
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "crs": str(src_crs),
                    "transform_a": wt.a,
                    "transform_b": wt.b,
                    "transform_c": wt.c,
                    "transform_d": wt.d,
                    "transform_e": wt.e,
                    "transform_f": wt.f,
                })

                tile_id += 1

        print(f"  完成: {image_path.name}，输出切片数: {tile_id}")

    return records


def batch_tile_rasters(
    input_dir,
    out_dir,
    shp_path=None,
    recursive=True,
    tile_size=512,
    overlap=128,
    empty_ratio_threshold=0.98,
    std_threshold=2.0,
    mask_outside_geometry=False,
    nodata_value=0,
):
    """
    批量处理输入目录下所有 tif/tiff
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
    print(f"shp: {shp_path if shp_path else '未使用'}")

    all_records = []
    failed_files = []

    for image_path in tif_files:
        try:
            records = tile_one_raster(
                image_path=image_path,
                out_dir=out_dir,
                shp_path=shp_path,
                tile_size=tile_size,
                overlap=overlap,
                empty_ratio_threshold=empty_ratio_threshold,
                std_threshold=std_threshold,
                mask_outside_geometry=mask_outside_geometry,
                nodata_value=nodata_value,
            )
            all_records.extend(records)
        except Exception as e:
            failed_files.append((str(image_path), str(e)))
            print(f"\n处理失败: {image_path}")
            print(f"原因: {e}")
            print(traceback.format_exc())

    if all_records:
        csv_path = out_dir / "tile_index_all.csv"
        pd.DataFrame(all_records).to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n全部处理完成，总切片数: {len(all_records)}")
        print(f"总索引文件: {csv_path}")
    else:
        print("\n没有生成任何有效切片")

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
    input_dir = r"G:\GF2原始数据_reg"   # 输入目录，可包含多个 tif/tiff
    out_dir = r"E:\cut_patch"      # 输出目录（新目录，不改原始数据）

    shp_path = r"E:\进行时\美丽海湾\研究区\研究区shp手画\研究区域.shp"          # 可选；不用就改成 None
    # shp_path = None

    batch_tile_rasters(
        input_dir=input_dir,
        out_dir=out_dir,
        shp_path=shp_path,
        recursive=True,              # 是否递归搜索子目录
        tile_size=512,               # 切片大小
        overlap=128,                 # 重叠像素
        empty_ratio_threshold=0.98,  # 空白比例阈值
        std_threshold=2.0,           # 低纹理阈值
        mask_outside_geometry=False, # True: shp 外区域置 nodata；False: 仅筛选相交切片
        nodata_value=0,
    )