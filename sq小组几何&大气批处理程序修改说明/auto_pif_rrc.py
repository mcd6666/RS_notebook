# -*- coding: utf-8 -*-
"""
Automatic PIF-based relative radiometric correction.

The script uses a Sentinel-2 reference image to normalize a GF image without
manual ROI selection. It:

1. Warps the GF image to the Sentinel-2 grid over their common extent.
2. Filters cloud/shadow/water/vegetation-like pixels with spectral rules.
3. Selects pseudo-invariant features (PIFs) from the lowest multiband change
   scores.
4. Fits per-band robust linear models: S2 = slope * GF + intercept.
5. Applies the fitted models to the full-resolution GF image.

Dependencies: Python 3, GDAL Python bindings, NumPy.
"""

import argparse
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from osgeo import gdal, osr
except ImportError:
    print("GDAL Python bindings are required: from osgeo import gdal", file=sys.stderr)
    sys.exit(1)


gdal.UseExceptions()


@dataclass
class BandFit:
    band: int
    slope: float
    intercept: float
    r2: float
    rmse: float
    n_pixels: int


def _parse_bands(value: str) -> List[int]:
    bands = [int(item.strip()) for item in value.split(",") if item.strip()]
    if len(bands) < 2:
        raise argparse.ArgumentTypeError("at least two bands are required")
    if any(band < 1 for band in bands):
        raise argparse.ArgumentTypeError("band numbers are 1-based")
    return bands


def _open(path: str) -> gdal.Dataset:
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Cannot open raster: {path}")
    return ds


def _dataset_bounds(ds: gdal.Dataset) -> Tuple[float, float, float, float]:
    gt = ds.GetGeoTransform()
    width = ds.RasterXSize
    height = ds.RasterYSize
    corners = [
        (0, 0),
        (width, 0),
        (0, height),
        (width, height),
    ]
    xs = [gt[0] + x * gt[1] + y * gt[2] for x, y in corners]
    ys = [gt[3] + x * gt[4] + y * gt[5] for x, y in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _same_projection(a: gdal.Dataset, b: gdal.Dataset) -> bool:
    pa = a.GetProjection()
    pb = b.GetProjection()
    if not pa or not pb:
        return False
    sa = osr.SpatialReference()
    sb = osr.SpatialReference()
    sa.ImportFromWkt(pa)
    sb.ImportFromWkt(pb)
    return bool(sa.IsSame(sb))


def _transform_bounds(
    bounds: Tuple[float, float, float, float], src_wkt: str, dst_wkt: str
) -> Tuple[float, float, float, float]:
    src = osr.SpatialReference()
    dst = osr.SpatialReference()
    src.ImportFromWkt(src_wkt)
    dst.ImportFromWkt(dst_wkt)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(src, dst)
    xmin, ymin, xmax, ymax = bounds
    points = [
        transform.TransformPoint(xmin, ymin),
        transform.TransformPoint(xmin, ymax),
        transform.TransformPoint(xmax, ymin),
        transform.TransformPoint(xmax, ymax),
    ]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap_in_reference_crs(
    reference: gdal.Dataset, target: gdal.Dataset
) -> Tuple[float, float, float, float]:
    ref_bounds = _dataset_bounds(reference)
    target_bounds = _dataset_bounds(target)
    if not _same_projection(reference, target):
        target_bounds = _transform_bounds(
            target_bounds, target.GetProjection(), reference.GetProjection()
        )

    xmin = max(ref_bounds[0], target_bounds[0])
    ymin = max(ref_bounds[1], target_bounds[1])
    xmax = min(ref_bounds[2], target_bounds[2])
    ymax = min(ref_bounds[3], target_bounds[3])
    if xmin >= xmax or ymin >= ymax:
        raise RuntimeError("Reference and target rasters do not overlap")
    return xmin, ymin, xmax, ymax


def _aligned_temp_raster(
    source: str,
    reference: gdal.Dataset,
    bounds: Tuple[float, float, float, float],
    bands: Sequence[int],
    tmp_dir: str,
    prefix: str,
    resample_alg: str,
    sample_step: int,
    progress: bool,
) -> str:
    gt = reference.GetGeoTransform()
    xres = abs(gt[1]) * sample_step
    yres = abs(gt[5]) * sample_step
    out_path = os.path.join(tmp_dir, f"{prefix}.tif")

    selected_path = os.path.join(tmp_dir, f"{prefix}_selected.tif")
    translate_options = gdal.TranslateOptions(
        format="GTiff",
        bandList=list(bands),
        creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
        callback=_gdal_progress(f"{prefix}: selecting bands") if progress else None,
    )
    selected = gdal.Translate(selected_path, source, options=translate_options)
    if selected is None:
        raise RuntimeError(f"Failed to select bands from raster: {source}")
    selected.FlushCache()
    selected = None

    options = gdal.WarpOptions(
        format="GTiff",
        outputBounds=bounds,
        dstSRS=reference.GetProjection(),
        xRes=xres,
        yRes=yres,
        targetAlignedPixels=True,
        resampleAlg=resample_alg,
        multithread=True,
        creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
        callback=_gdal_progress(f"{prefix}: warping sample") if progress else None,
    )
    result = gdal.Warp(out_path, selected_path, options=options)
    if result is None:
        raise RuntimeError(f"Failed to warp raster: {source}")
    result.FlushCache()
    result = None
    return out_path


def _gdal_progress(label: str):
    last = {"pct": -1}

    def callback(complete, message, data):
        pct = int(complete * 100)
        if pct >= last["pct"] + 10 or pct == 100:
            print(f"  {label}: {pct}%")
            last["pct"] = pct
        return 1

    return callback


def _read_stack(path: str, scale: float) -> np.ndarray:
    ds = _open(path)
    arr = ds.ReadAsArray().astype(np.float32)
    arr = _normalize_stack_shape(arr, ds.RasterCount)
    for idx in range(1, ds.RasterCount + 1):
        band_arr = arr[idx - 1]
        band = ds.GetRasterBand(idx)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            band_arr[band_arr == nodata] = np.nan
    return arr / scale


def _normalize_stack_shape(arr: np.ndarray, band_count: int) -> np.ndarray:
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim == 4 and arr.shape[0] == band_count and arr.shape[1] == band_count:
        arr = np.stack([arr[idx, idx, :, :] for idx in range(band_count)], axis=0)
    elif arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    elif arr.ndim == 4 and arr.shape[1] == 1:
        arr = arr[:, 0, :, :]
    if arr.ndim != 3:
        arr = np.squeeze(arr)
    if arr.ndim != 3:
        raise RuntimeError(f"Expected raster stack with 3 dimensions, got shape {arr.shape}")

    # GDAL returns multiband arrays as band,row,col. Some drivers can expose
    # row,col,band, so normalize by matching RasterCount.
    if arr.shape[0] != band_count and arr.shape[-1] == band_count:
        arr = np.moveaxis(arr, -1, 0)
    if arr.shape[0] != band_count:
        raise RuntimeError(
            f"Cannot normalize raster stack shape {arr.shape} for {band_count} bands"
        )
    return arr


def _normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    den = a + b
    out = np.full(a.shape, np.nan, dtype=np.float32)
    np.divide(a - b, den, out=out, where=np.abs(den) > 1e-6)
    return out


def _valid_mask(stack: np.ndarray) -> np.ndarray:
    return np.all(np.isfinite(stack), axis=0) & np.all(stack > 0, axis=0)


def _spectral_candidate_mask(
    reference: np.ndarray,
    target: np.ndarray,
    blue_idx: int,
    green_idx: int,
    red_idx: int,
    nir_idx: int,
    max_ndvi: float,
    max_ndwi: float,
    min_brightness_q: float,
    max_brightness_q: float,
) -> np.ndarray:
    ref_valid = _valid_mask(reference)
    tgt_valid = _valid_mask(target)
    valid = ref_valid & tgt_valid

    ref_blue = reference[blue_idx]
    ref_green = reference[green_idx]
    ref_red = reference[red_idx]
    ref_nir = reference[nir_idx]
    tgt_red = target[red_idx]
    tgt_nir = target[nir_idx]

    ref_ndvi = _normalized_difference(ref_nir, ref_red)
    tgt_ndvi = _normalized_difference(tgt_nir, tgt_red)
    ref_ndwi = _normalized_difference(ref_green, ref_nir)
    brightness = ref_blue + ref_green + ref_red + ref_nir

    finite_brightness = brightness[np.isfinite(brightness) & valid]
    if finite_brightness.size == 0:
        raise RuntimeError("No valid overlap pixels after nodata filtering")

    low = float(np.nanquantile(finite_brightness, min_brightness_q))
    high = float(np.nanquantile(finite_brightness, max_brightness_q))

    return (
        valid
        & (np.abs(ref_ndvi) <= max_ndvi)
        & (np.abs(tgt_ndvi) <= max_ndvi)
        & (ref_ndwi <= max_ndwi)
        & (brightness >= low)
        & (brightness <= high)
    )


def _robust_zscore(values: np.ndarray) -> np.ndarray:
    med = np.nanmedian(values, axis=(1, 2))[:, None, None]
    mad = np.nanmedian(np.abs(values - med), axis=(1, 2))[:, None, None]
    scale = np.where(mad > 1e-6, 1.4826 * mad, np.nanstd(values, axis=(1, 2))[:, None, None])
    scale = np.where(scale > 1e-6, scale, 1.0)
    return (values - med) / scale


def _change_score(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    reference = _normalize_stack_shape(np.asarray(reference), reference.shape[0])
    target = _normalize_stack_shape(np.asarray(target), target.shape[0])
    diff = np.asarray(_robust_zscore(reference) - _robust_zscore(target), dtype=np.float32)
    if diff.ndim != 3:
        raise RuntimeError(f"Expected multiband stack with 3 dimensions, got shape {diff.shape}")
    with np.errstate(invalid="ignore"):
        score = np.sqrt(np.nanmean(diff * diff, axis=0))
    if score.ndim != 2:
        raise RuntimeError(f"Expected 2D change score, got shape {score.shape}")
    return score


def select_pif_mask(
    reference: np.ndarray,
    target: np.ndarray,
    candidate_mask: np.ndarray,
    pif_percentile: float,
    min_pixels: int,
) -> np.ndarray:
    score = _change_score(reference, target)
    candidate_scores = score[candidate_mask & np.isfinite(score)]
    if candidate_scores.size < min_pixels:
        raise RuntimeError(
            f"Only {candidate_scores.size} candidate pixels found; need at least {min_pixels}"
        )

    threshold = float(np.nanpercentile(candidate_scores, pif_percentile))
    pif = candidate_mask & np.isfinite(score) & (score <= threshold)

    if int(np.count_nonzero(pif)) < min_pixels:
        order = np.argsort(candidate_scores)
        threshold = float(candidate_scores[order[min_pixels - 1]])
        pif = candidate_mask & np.isfinite(score) & (score <= threshold)
    return pif


def select_auto_roi_mask(
    reference: np.ndarray,
    target: np.ndarray,
    candidate_mask: np.ndarray,
    tile_size: int,
    top_percent: float,
    max_tiles: int,
    min_candidate_ratio: float,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Select stable candidate blocks before pixel-level PIF extraction."""
    if tile_size < 16:
        raise RuntimeError("--roi-tile-size should be at least 16")

    score = _change_score(reference, target)
    height, width = candidate_mask.shape
    tile_infos = []

    for y0 in range(0, height, tile_size):
        y1 = min(height, y0 + tile_size)
        for x0 in range(0, width, tile_size):
            x1 = min(width, x0 + tile_size)
            tile_candidates = candidate_mask[y0:y1, x0:x1]
            total = tile_candidates.size
            candidate_count = int(np.count_nonzero(tile_candidates))
            if total == 0:
                continue
            ratio = candidate_count / float(total)
            if ratio < min_candidate_ratio or candidate_count < 50:
                continue
            tile_score = score[y0:y1, x0:x1][tile_candidates]
            tile_score = tile_score[np.isfinite(tile_score)]
            if tile_score.size < 50:
                continue
            tile_infos.append(
                {
                    "y0": y0,
                    "y1": y1,
                    "x0": x0,
                    "x1": x1,
                    "median_score": float(np.nanmedian(tile_score)),
                    "candidate_count": candidate_count,
                    "candidate_ratio": ratio,
                }
            )

    if not tile_infos:
        raise RuntimeError("No suitable automatic ROI tiles found")

    tile_infos.sort(key=lambda item: (item["median_score"], -item["candidate_count"]))
    keep_count = max(1, int(math.ceil(len(tile_infos) * top_percent / 100.0)))
    keep_count = min(keep_count, max_tiles, len(tile_infos))
    selected = tile_infos[:keep_count]

    roi_mask = np.zeros(candidate_mask.shape, dtype=bool)
    for item in selected:
        roi_mask[item["y0"] : item["y1"], item["x0"] : item["x1"]] = True
    roi_mask &= candidate_mask

    stats = {
        "roi_tiles_total": float(len(tile_infos)),
        "roi_tiles_selected": float(keep_count),
        "roi_candidate_pixels": float(np.count_nonzero(roi_mask)),
        "roi_best_median_score": float(selected[0]["median_score"]),
        "roi_worst_selected_median_score": float(selected[-1]["median_score"]),
    }
    return roi_mask, stats


def _linear_fit(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    denom = float(np.sum((x - x_mean) ** 2))
    if denom <= 1e-12:
        raise RuntimeError("Degenerate PIF values; cannot fit linear model")
    slope = float(np.sum((x - x_mean) * (y - y_mean)) / denom)
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _fit_one_band(x: np.ndarray, y: np.ndarray, max_iter: int) -> BandFit:
    keep = np.isfinite(x) & np.isfinite(y)
    x = x[keep]
    y = y[keep]
    if x.size < 2:
        raise RuntimeError("Not enough pixels to fit band")

    for _ in range(max_iter):
        slope, intercept = _linear_fit(x, y)
        residual = y - (slope * x + intercept)
        med = float(np.median(residual))
        mad = float(np.median(np.abs(residual - med)))
        if mad <= 1e-12:
            break
        new_keep = np.abs(residual - med) <= 3.5 * 1.4826 * mad
        if int(np.count_nonzero(new_keep)) == x.size:
            break
        if int(np.count_nonzero(new_keep)) < max(20, x.size // 10):
            break
        x = x[new_keep]
        y = y[new_keep]

    slope, intercept = _linear_fit(x, y)
    pred = slope * x + intercept
    residual = y - pred
    rmse = float(math.sqrt(np.mean(residual * residual)))
    ss_res = float(np.sum(residual * residual))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return BandFit(band=-1, slope=slope, intercept=intercept, r2=r2, rmse=rmse, n_pixels=int(x.size))


def fit_models(
    reference: np.ndarray,
    target: np.ndarray,
    pif_mask: np.ndarray,
    output_band_numbers: Sequence[int],
    min_pixels: int,
    max_iter: int,
) -> List[BandFit]:
    models = []
    for idx, band_number in enumerate(output_band_numbers):
        x = target[idx][pif_mask]
        y = reference[idx][pif_mask]
        if x.size < min_pixels:
            raise RuntimeError(
                f"Band {band_number}: only {x.size} PIF pixels available; need {min_pixels}"
            )
        fit = _fit_one_band(x, y, max_iter=max_iter)
        fit.band = int(band_number)
        models.append(fit)
    return models


def _create_output_like(
    source: gdal.Dataset,
    out_path: str,
    dtype: int,
    creation_options: Sequence[str],
) -> gdal.Dataset:
    driver = gdal.GetDriverByName("GTiff")
    out = driver.Create(
        out_path,
        source.RasterXSize,
        source.RasterYSize,
        source.RasterCount,
        dtype,
        list(creation_options),
    )
    if out is None:
        raise RuntimeError(f"Cannot create output raster: {out_path}")
    out.SetGeoTransform(source.GetGeoTransform())
    out.SetProjection(source.GetProjection())
    return out


def apply_models(
    target_path: str,
    output_path: str,
    models: Sequence[BandFit],
    scale: float,
    output_dtype: str,
    block_size: int = 512,
    progress: bool = True,
) -> None:
    source = _open(target_path)
    model_by_band = {model.band: model for model in models}
    gdal_dtype = gdal.GetDataTypeByName(output_dtype)
    if gdal_dtype == gdal.GDT_Unknown:
        raise RuntimeError(f"Unsupported GDAL data type: {output_dtype}")
    dtype_ranges = {
        gdal.GDT_Byte: (np.uint8, 0, 255),
        gdal.GDT_UInt16: (np.uint16, 0, 65535),
        gdal.GDT_Int16: (np.int16, -32768, 32767),
        gdal.GDT_UInt32: (np.uint32, 0, 4294967295),
        gdal.GDT_Int32: (np.int32, -2147483648, 2147483647),
    }
    integer_output = dtype_ranges.get(gdal_dtype)

    out = _create_output_like(
        source,
        output_path,
        gdal_dtype,
        ["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
    )

    for band_idx in range(1, source.RasterCount + 1):
        src_band = source.GetRasterBand(band_idx)
        out_band = out.GetRasterBand(band_idx)
        nodata = src_band.GetNoDataValue()
        if nodata is not None:
            out_band.SetNoDataValue(nodata)

        model = model_by_band.get(band_idx)
        if progress:
            if model is None:
                print(f"Writing band {band_idx}/{source.RasterCount} without correction...")
            else:
                print(f"Writing corrected band {band_idx}/{source.RasterCount}...")
        for yoff in range(0, source.RasterYSize, block_size):
            ysize = min(block_size, source.RasterYSize - yoff)
            if progress:
                pct = min(100.0, (yoff + ysize) * 100.0 / source.RasterYSize)
                print(f"  band {band_idx}: {pct:5.1f}%")
            for xoff in range(0, source.RasterXSize, block_size):
                xsize = min(block_size, source.RasterXSize - xoff)
                arr = src_band.ReadAsArray(xoff, yoff, xsize, ysize)
                if model is None:
                    out_band.WriteArray(arr, xoff, yoff)
                    continue

                work = arr.astype(np.float32)
                valid = np.isfinite(work)
                if nodata is not None:
                    valid &= work != nodata
                corrected = work.copy()
                corrected[valid] = (model.slope * (work[valid] / scale) + model.intercept) * scale

                if integer_output is not None:
                    np_dtype, min_value, max_value = integer_output
                    corrected = np.clip(np.rint(corrected), min_value, max_value)
                    corrected = corrected.astype(np_dtype)
                else:
                    corrected = corrected.astype(np.float32)
                out_band.WriteArray(corrected, xoff, yoff)

        out_band.FlushCache()

    out.FlushCache()
    out = None
    source = None


def write_report(
    path: str,
    args: argparse.Namespace,
    overlap: Tuple[float, float, float, float],
    candidate_count: int,
    roi_stats: Optional[Dict[str, float]],
    pif_count: int,
    models: Sequence[BandFit],
) -> None:
    data = {
        "reference": os.path.abspath(args.reference),
        "target": os.path.abspath(args.target),
        "output": os.path.abspath(args.output),
        "overlap_bounds_reference_crs": list(overlap),
        "reference_bands": args.reference_bands,
        "target_bands": args.target_bands,
        "scale": args.scale,
        "candidate_pixels": int(candidate_count),
        "auto_roi": bool(args.auto_roi),
        "roi": roi_stats or {},
        "pif_pixels": int(pif_count),
        "models": [
            {
                "band": model.band,
                "slope": model.slope,
                "intercept": model.intercept,
                "r2": model.r2,
                "rmse": model.rmse,
                "n_pixels": model.n_pixels,
            }
            for model in models
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automatic Sentinel-2 based PIF correction for GF imagery."
    )
    parser.add_argument("-r", "--reference", required=True, help="Sentinel-2 reference raster")
    parser.add_argument("-t", "--target", required=True, help="GF target raster to correct")
    parser.add_argument("-o", "--output", required=True, help="Corrected GF output raster")
    parser.add_argument(
        "--reference-bands",
        type=_parse_bands,
        default=[1, 2, 3, 4],
        help="1-based S2 band order used for Blue,Green,Red,NIR; default: 1,2,3,4",
    )
    parser.add_argument(
        "--target-bands",
        type=_parse_bands,
        default=[1, 2, 3, 4],
        help="1-based GF band order matching reference bands; default: 1,2,3,4",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=10000.0,
        help="Reflectance scale factor. Use 1 if inputs are already 0-1 reflectance.",
    )
    parser.add_argument("--max-ndvi", type=float, default=0.35, help="Max absolute NDVI for PIF candidates")
    parser.add_argument("--max-ndwi", type=float, default=0.0, help="Max S2 NDWI to exclude water")
    parser.add_argument(
        "--brightness-quantiles",
        type=float,
        nargs=2,
        default=(0.05, 0.95),
        metavar=("LOW", "HIGH"),
        help="Brightness quantiles used to reject shadow/saturation; default: 0.05 0.95",
    )
    parser.add_argument(
        "--pif-percentile",
        type=float,
        default=5.0,
        help="Lowest multiband change-score percentile kept as PIF; default: 5",
    )
    parser.add_argument("--min-pixels", type=int, default=100, help="Minimum PIF pixels required")
    parser.add_argument("--max-iter", type=int, default=8, help="Robust regression iterations")
    parser.add_argument(
        "--sample-step",
        type=int,
        default=4,
        help="Use every Nth reference-grid pixel for fitting; larger is faster. Default: 4",
    )
    parser.add_argument(
        "--auto-roi",
        dest="auto_roi",
        action="store_true",
        default=True,
        help="Automatically select stable ROI blocks before PIF extraction; default: enabled",
    )
    parser.add_argument(
        "--no-auto-roi",
        dest="auto_roi",
        action="store_false",
        help="Disable automatic ROI block selection",
    )
    parser.add_argument(
        "--roi-tile-size",
        type=int,
        default=256,
        help="Automatic ROI tile size on the sampled reference grid; default: 256",
    )
    parser.add_argument(
        "--roi-top-percent",
        type=float,
        default=20.0,
        help="Keep the most stable ROI tiles by this percent; default: 20",
    )
    parser.add_argument(
        "--roi-max-tiles",
        type=int,
        default=20,
        help="Maximum automatic ROI tiles used for fitting; default: 20",
    )
    parser.add_argument(
        "--roi-min-candidate-ratio",
        type=float,
        default=0.15,
        help="Minimum candidate-pixel ratio in an ROI tile; default: 0.15",
    )
    parser.add_argument(
        "--output-dtype",
        default="UInt16",
        help="Output GDAL data type, for example UInt16 or Float32; default: UInt16",
    )
    parser.add_argument("--report", default=None, help="JSON report path")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary aligned rasters")
    parser.add_argument("--quiet", action="store_true", help="Reduce progress output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if len(args.reference_bands) != len(args.target_bands):
        parser.error("--reference-bands and --target-bands must have the same length")
    if len(args.reference_bands) < 4:
        parser.error("Blue,Green,Red,NIR bands are required")
    if not (0.0 < args.pif_percentile <= 100.0):
        parser.error("--pif-percentile must be in (0, 100]")
    low_q, high_q = args.brightness_quantiles
    if not (0.0 <= low_q < high_q <= 1.0):
        parser.error("--brightness-quantiles must satisfy 0 <= LOW < HIGH <= 1")
    if args.sample_step < 1:
        parser.error("--sample-step must be >= 1")
    if not (0.0 < args.roi_top_percent <= 100.0):
        parser.error("--roi-top-percent must be in (0, 100]")
    if args.roi_max_tiles < 1:
        parser.error("--roi-max-tiles must be >= 1")
    if not (0.0 <= args.roi_min_candidate_ratio <= 1.0):
        parser.error("--roi-min-candidate-ratio must be in [0, 1]")

    reference = _open(args.reference)
    target = _open(args.target)
    overlap = _overlap_in_reference_crs(reference, target)

    output_dir = os.path.dirname(os.path.abspath(args.output))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    report_path = args.report
    if report_path is None:
        report_path = os.path.splitext(args.output)[0] + "_pif_report.json"

    if args.keep_temp:
        tmp_dir = tempfile.mkdtemp(prefix="auto_pif_rrc_")
        tmp_ctx = None
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="auto_pif_rrc_")
        tmp_dir = tmp_ctx.name
    try:
        if not args.quiet:
            print("Finding raster overlap...")
            print(f"Overlap bounds: {overlap}")
            print(f"Fitting sample step: {args.sample_step}")
            print("Preparing aligned Sentinel-2 sample...")
        ref_aligned = _aligned_temp_raster(
            args.reference,
            reference,
            overlap,
            args.reference_bands,
            tmp_dir,
            "reference_overlap",
            "near",
            args.sample_step,
            not args.quiet,
        )
        if not args.quiet:
            print("Preparing aligned GF sample...")
        tgt_aligned = _aligned_temp_raster(
            args.target,
            reference,
            overlap,
            args.target_bands,
            tmp_dir,
            "target_overlap",
            "bilinear",
            args.sample_step,
            not args.quiet,
        )

        if not args.quiet:
            print("Reading aligned samples...")
        ref_stack = _read_stack(ref_aligned, args.scale)
        tgt_stack = _read_stack(tgt_aligned, args.scale)

        if not args.quiet:
            print("Building spectral candidate mask...")
        candidate_mask = _spectral_candidate_mask(
            ref_stack,
            tgt_stack,
            blue_idx=0,
            green_idx=1,
            red_idx=2,
            nir_idx=3,
            max_ndvi=args.max_ndvi,
            max_ndwi=args.max_ndwi,
            min_brightness_q=low_q,
            max_brightness_q=high_q,
        )
        if not args.quiet:
            print(f"Candidate pixels: {int(np.count_nonzero(candidate_mask))}")
        roi_stats = None
        pif_candidate_mask = candidate_mask
        if args.auto_roi:
            if not args.quiet:
                print("Selecting automatic stable ROI tiles...")
            pif_candidate_mask, roi_stats = select_auto_roi_mask(
                ref_stack,
                tgt_stack,
                candidate_mask,
                tile_size=args.roi_tile_size,
                top_percent=args.roi_top_percent,
                max_tiles=args.roi_max_tiles,
                min_candidate_ratio=args.roi_min_candidate_ratio,
            )
            if not args.quiet:
                print(
                    "ROI tiles: {selected:.0f}/{total:.0f}, ROI candidate pixels: {pixels:.0f}".format(
                        selected=roi_stats["roi_tiles_selected"],
                        total=roi_stats["roi_tiles_total"],
                        pixels=roi_stats["roi_candidate_pixels"],
                    )
                )
        if not args.quiet:
            print("Selecting PIF pixels...")
        pif_mask = select_pif_mask(
            ref_stack,
            tgt_stack,
            pif_candidate_mask,
            pif_percentile=args.pif_percentile,
            min_pixels=args.min_pixels,
        )
        if not args.quiet:
            print(f"PIF pixels: {int(np.count_nonzero(pif_mask))}")
            print("Fitting per-band correction models...")

        models = fit_models(
            ref_stack,
            tgt_stack,
            pif_mask,
            output_band_numbers=args.target_bands,
            min_pixels=args.min_pixels,
            max_iter=args.max_iter,
        )
        if not args.quiet:
            for model in models:
                print(
                    "  Band {band}: slope={slope:.8f}, intercept={intercept:.8f}, "
                    "R2={r2:.4f}, RMSE={rmse:.6f}, N={n_pixels}".format(**model.__dict__)
                )
            print("Applying correction to full GF raster...")

        apply_models(
            args.target,
            args.output,
            models,
            scale=args.scale,
            output_dtype=args.output_dtype,
            progress=not args.quiet,
        )
        write_report(
            report_path,
            args,
            overlap,
            candidate_count=int(np.count_nonzero(candidate_mask)),
            roi_stats=roi_stats,
            pif_count=int(np.count_nonzero(pif_mask)),
            models=models,
        )

        print(f"Corrected raster: {args.output}")
        print(f"Report: {report_path}")
        for model in models:
            print(
                "Band {band}: y={slope:.8f}*x+{intercept:.8f}, "
                "R2={r2:.4f}, RMSE={rmse:.6f}, N={n_pixels}".format(**model.__dict__)
            )
        return 0
    finally:
        if args.keep_temp:
            print(f"Temporary rasters kept in: {tmp_dir}")
        else:
            tmp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
