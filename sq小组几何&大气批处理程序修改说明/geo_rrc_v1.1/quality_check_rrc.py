# -*- coding: utf-8 -*-
"""
Batch quality check for GF RRC outputs.

The script scans an RRC output folder, reads each *_pif_report.json and
corrected *_RRC.tif, then writes a quality_summary.csv. If a Sentinel-2
reference raster is supplied, it also compares each corrected GF image with the
reference on a sampled common grid.
"""

import argparse
import csv
import json
import math
import os
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    from osgeo import gdal, osr
except ImportError:
    raise SystemExit("GDAL Python bindings are required: from osgeo import gdal")


gdal.UseExceptions()
gdal.PushErrorHandler("CPLQuietErrorHandler")


def parse_bands(value: str) -> List[int]:
    bands = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not bands or any(band < 1 for band in bands):
        raise argparse.ArgumentTypeError("bands must be 1-based positive integers")
    return bands


def open_ds(path: str) -> gdal.Dataset:
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Cannot open raster: {path}")
    return ds


def dataset_bounds(ds: gdal.Dataset) -> Tuple[float, float, float, float]:
    gt = ds.GetGeoTransform()
    width = ds.RasterXSize
    height = ds.RasterYSize
    corners = [(0, 0), (width, 0), (0, height), (width, height)]
    xs = [gt[0] + x * gt[1] + y * gt[2] for x, y in corners]
    ys = [gt[3] + x * gt[4] + y * gt[5] for x, y in corners]
    return min(xs), min(ys), max(xs), max(ys)


def same_projection(a: gdal.Dataset, b: gdal.Dataset) -> bool:
    pa = a.GetProjection()
    pb = b.GetProjection()
    if not pa or not pb:
        return False
    sa = osr.SpatialReference()
    sb = osr.SpatialReference()
    sa.ImportFromWkt(pa)
    sb.ImportFromWkt(pb)
    return bool(sa.IsSame(sb))


def transform_bounds(bounds, src_wkt: str, dst_wkt: str):
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
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def overlap_in_reference_crs(reference: gdal.Dataset, target: gdal.Dataset):
    ref_bounds = dataset_bounds(reference)
    target_bounds = dataset_bounds(target)
    if not same_projection(reference, target):
        target_bounds = transform_bounds(target_bounds, target.GetProjection(), reference.GetProjection())
    xmin = max(ref_bounds[0], target_bounds[0])
    ymin = max(ref_bounds[1], target_bounds[1])
    xmax = min(ref_bounds[2], target_bounds[2])
    ymax = min(ref_bounds[3], target_bounds[3])
    if xmin >= xmax or ymin >= ymax:
        raise RuntimeError("Reference and target rasters do not overlap")
    return xmin, ymin, xmax, ymax


def normalize_stack(arr: np.ndarray, band_count: int) -> np.ndarray:
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim == 4 and arr.shape[0] == band_count and arr.shape[1] == band_count:
        arr = np.stack([arr[idx, idx, :, :] for idx in range(band_count)], axis=0)
    elif arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    elif arr.ndim == 4 and arr.shape[1] == 1:
        arr = arr[:, 0, :, :]
    arr = np.squeeze(arr)
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise RuntimeError(f"Cannot normalize raster stack shape {arr.shape}")
    if arr.shape[0] != band_count and arr.shape[-1] == band_count:
        arr = np.moveaxis(arr, -1, 0)
    if arr.shape[0] != band_count:
        raise RuntimeError(f"Cannot normalize raster stack shape {arr.shape} for {band_count} bands")
    return arr


def raster_stats(path: str, bands: Sequence[int], scale: float, max_pixels: int) -> Dict[str, float]:
    ds = open_ds(path)
    step = max(1, int(math.sqrt(max(ds.RasterXSize * ds.RasterYSize / float(max_pixels), 1.0))))
    stats: Dict[str, float] = {}
    valid_all = None

    for band_number in bands:
        band = ds.GetRasterBand(band_number)
        arr = band.ReadAsArray(buf_xsize=max(1, ds.RasterXSize // step), buf_ysize=max(1, ds.RasterYSize // step))
        arr = arr.astype(np.float32)
        nodata = band.GetNoDataValue()
        valid = np.isfinite(arr)
        if nodata is not None:
            valid &= arr != nodata
        values_raw = arr[valid]
        key = f"b{band_number}"
        if values_raw.size == 0:
            for name in ("min", "max", "mean", "std", "p1", "p5", "p50", "p95", "p99", "zero_ratio", "sat65535_ratio"):
                stats[f"{key}_{name}"] = float("nan")
            continue

        values = values_raw / scale
        stats[f"{key}_min"] = float(np.nanmin(values))
        stats[f"{key}_max"] = float(np.nanmax(values))
        stats[f"{key}_mean"] = float(np.nanmean(values))
        stats[f"{key}_std"] = float(np.nanstd(values))
        for pct in (1, 5, 50, 95, 99):
            stats[f"{key}_p{pct}"] = float(np.nanpercentile(values, pct))
        stats[f"{key}_zero_ratio"] = float(np.count_nonzero(values_raw == 0) / values_raw.size)
        stats[f"{key}_sat65535_ratio"] = float(np.count_nonzero(values_raw >= 65535) / values_raw.size)
        valid_all = valid if valid_all is None else (valid_all & valid)

    if valid_all is not None:
        stats["valid_ratio_sample"] = float(np.count_nonzero(valid_all) / valid_all.size)
    else:
        stats["valid_ratio_sample"] = float("nan")
    return stats


def gdal_progress(label: str):
    last = {"pct": -1}

    def callback(complete, message, data):
        pct = int(complete * 100)
        if pct >= last["pct"] + 10 or pct == 100:
            print(f"    {label}: {pct}%")
            last["pct"] = pct
        return 1

    return callback


def aligned_sample(source: str, reference: gdal.Dataset, bounds, bands, tmp_dir: str, prefix: str, sample_step: int, resample_alg: str, progress: bool):
    gt = reference.GetGeoTransform()
    xres = abs(gt[1]) * sample_step
    yres = abs(gt[5]) * sample_step
    selected_path = os.path.join(tmp_dir, f"{prefix}_selected.tif")
    out_path = os.path.join(tmp_dir, f"{prefix}.tif")
    selected = gdal.Translate(
        selected_path,
        source,
        options=gdal.TranslateOptions(
            format="GTiff",
            bandList=list(bands),
            creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=YES"],
            callback=gdal_progress(f"{prefix}: selecting bands") if progress else None,
        ),
    )
    if selected is None:
        raise RuntimeError(f"Failed to select bands from {source}")
    selected = None
    warped = gdal.Warp(
        out_path,
        selected_path,
        options=gdal.WarpOptions(
            format="GTiff",
            outputBounds=bounds,
            dstSRS=reference.GetProjection(),
            xRes=xres,
            yRes=yres,
            targetAlignedPixels=True,
            resampleAlg=resample_alg,
            multithread=True,
            creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=YES"],
            callback=gdal_progress(f"{prefix}: warping sample") if progress else None,
        ),
    )
    if warped is None:
        raise RuntimeError(f"Failed to warp {source}")
    warped = None
    return out_path


def read_stack(path: str, scale: float) -> np.ndarray:
    ds = open_ds(path)
    arr = normalize_stack(ds.ReadAsArray().astype(np.float32), ds.RasterCount)
    for idx in range(1, ds.RasterCount + 1):
        nodata = ds.GetRasterBand(idx).GetNoDataValue()
        if nodata is not None:
            arr[idx - 1][arr[idx - 1] == nodata] = np.nan
    return arr / scale


def compare_to_reference(reference_path: str, target_path: str, reference_bands, target_bands, scale: float, sample_step: int, progress: bool) -> Dict[str, float]:
    reference = open_ds(reference_path)
    target = open_ds(target_path)
    bounds = overlap_in_reference_crs(reference, target)
    with tempfile.TemporaryDirectory(prefix="rrc_quality_") as tmp_dir:
        if progress:
            print("  comparing with reference: prepare Sentinel-2 sample")
        ref_path = aligned_sample(reference_path, reference, bounds, reference_bands, tmp_dir, "reference", sample_step, "near", progress)
        if progress:
            print("  comparing with reference: prepare RRC sample")
        tgt_path = aligned_sample(target_path, reference, bounds, target_bands, tmp_dir, "target", sample_step, "bilinear", progress)
        if progress:
            print("  comparing with reference: read samples")
        ref = read_stack(ref_path, scale)
        tgt = read_stack(tgt_path, scale)

    out: Dict[str, float] = {}
    for idx, band in enumerate(target_bands):
        if progress:
            print(f"  comparing band {band}")
        x = tgt[idx].ravel()
        y = ref[idx].ravel()
        valid = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
        key = f"cmp_b{band}"
        if np.count_nonzero(valid) < 10:
            out[f"{key}_mean_diff"] = float("nan")
            out[f"{key}_rmse"] = float("nan")
            out[f"{key}_corr"] = float("nan")
            continue
        diff = x[valid] - y[valid]
        out[f"{key}_mean_diff"] = float(np.mean(diff))
        out[f"{key}_rmse"] = float(math.sqrt(np.mean(diff * diff)))
        out[f"{key}_corr"] = float(np.corrcoef(x[valid], y[valid])[0, 1])
    return out


def find_reports(folder: str) -> List[str]:
    reports = []
    for root, _, files in os.walk(folder):
        for name in files:
            if name.lower().endswith("_pif_report.json"):
                reports.append(os.path.join(root, name))
    return sorted(reports)


def model_summary(report: dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    out["pif_pixels"] = float(report.get("pif_pixels", float("nan")))
    out["candidate_pixels"] = float(report.get("candidate_pixels", float("nan")))
    roi = report.get("roi", {}) or {}
    out["roi_tiles_selected"] = float(roi.get("roi_tiles_selected", float("nan")))
    out["roi_candidate_pixels"] = float(roi.get("roi_candidate_pixels", float("nan")))
    out["pif_method"] = report.get("pif_method", "")
    out["regression_method"] = report.get("regression_method", "")
    for model in report.get("models", []):
        band = model.get("band")
        if band is None:
            continue
        key = f"model_b{band}"
        for name in ("slope", "intercept", "r2", "rmse", "n_pixels"):
            out[f"{key}_{name}"] = model.get(name, float("nan"))
    return out


def quality_status(row: Dict[str, object], bands: Sequence[int], args: argparse.Namespace) -> Tuple[str, str]:
    warnings = []
    pif_pixels = float(row.get("pif_pixels") or 0)
    if pif_pixels < args.min_pif_pixels:
        warnings.append(f"pif_pixels<{args.min_pif_pixels}")
    for band in bands:
        r2 = row.get(f"model_b{band}_r2")
        rmse = row.get(f"model_b{band}_rmse")
        sat = row.get(f"b{band}_sat65535_ratio")
        zero = row.get(f"b{band}_zero_ratio")
        cmp_rmse = row.get(f"cmp_b{band}_rmse")
        cmp_corr = row.get(f"cmp_b{band}_corr")
        if isinstance(r2, (int, float)) and np.isfinite(r2) and r2 < args.min_r2:
            warnings.append(f"b{band}_r2<{args.min_r2}")
        if isinstance(rmse, (int, float)) and np.isfinite(rmse) and rmse * args.scale > args.max_model_rmse_scaled:
            warnings.append(f"b{band}_model_rmse>{args.max_model_rmse_scaled}")
        if isinstance(sat, (int, float)) and np.isfinite(sat) and sat > args.max_saturation_ratio:
            warnings.append(f"b{band}_sat>{args.max_saturation_ratio}")
        if isinstance(zero, (int, float)) and np.isfinite(zero) and zero > args.max_zero_ratio:
            warnings.append(f"b{band}_zero>{args.max_zero_ratio}")
        if isinstance(cmp_rmse, (int, float)) and np.isfinite(cmp_rmse) and cmp_rmse * args.scale > args.max_compare_rmse_scaled:
            warnings.append(f"b{band}_cmp_rmse>{args.max_compare_rmse_scaled}")
        if isinstance(cmp_corr, (int, float)) and np.isfinite(cmp_corr) and cmp_corr < args.min_compare_corr:
            warnings.append(f"b{band}_cmp_corr<{args.min_compare_corr}")
    if len(warnings) >= args.fail_warning_count:
        return "FAIL", ";".join(warnings)
    if warnings:
        return "WARN", ";".join(warnings)
    return "PASS", ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch quality check for RRC outputs.")
    parser.add_argument("-i", "--rrc-folder", required=True, help="Folder containing *_RRC.tif and reports")
    parser.add_argument("-o", "--output", default=None, help="Output CSV path")
    parser.add_argument("-r", "--reference", default=None, help="Optional Sentinel-2 reference raster")
    parser.add_argument("--reference-bands", type=parse_bands, default=[1, 2, 3, 4])
    parser.add_argument("--target-bands", type=parse_bands, default=[1, 2, 3, 4])
    parser.add_argument("--scale", type=float, default=10000.0)
    parser.add_argument("--sample-step", type=int, default=16, help="Sampling step for reference comparison")
    parser.add_argument("--max-pixels", type=int, default=1000000, help="Max sampled pixels for per-raster stats")
    parser.add_argument("--min-pif-pixels", type=int, default=1000)
    parser.add_argument("--min-r2", type=float, default=0.94)
    parser.add_argument("--max-model-rmse-scaled", type=float, default=100.0)
    parser.add_argument("--max-zero-ratio", type=float, default=0.05)
    parser.add_argument("--max-saturation-ratio", type=float, default=0.001)
    parser.add_argument("--max-compare-rmse-scaled", type=float, default=800.0)
    parser.add_argument("--min-compare-corr", type=float, default=0.85)
    parser.add_argument("--fail-warning-count", type=int, default=3)
    parser.add_argument("--quiet", action="store_true", help="Reduce progress output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    reports = find_reports(args.rrc_folder)
    if not reports:
        print(f"No *_pif_report.json files found in {args.rrc_folder}")
        return 1

    output = args.output or os.path.join(args.rrc_folder, "quality_summary.csv")
    rows = []
    fieldnames = ["status", "warnings", "report", "target", "output"]

    for idx, report_path in enumerate(reports, start=1):
        print(f"[{idx}/{len(reports)}] {report_path}")
        if not args.quiet:
            print("  reading report")
        with open(report_path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
        row: Dict[str, object] = {
            "report": report_path,
            "target": report.get("target", ""),
            "output": report.get("output", ""),
        }
        row.update(model_summary(report))
        out_path = str(report.get("output") or "")
        try:
            if out_path and os.path.exists(out_path):
                if not args.quiet:
                    print("  calculating output raster statistics")
                row.update(raster_stats(out_path, args.target_bands, args.scale, args.max_pixels))
                if args.reference:
                    row.update(
                        compare_to_reference(
                            args.reference,
                            out_path,
                            args.reference_bands,
                            args.target_bands,
                            args.scale,
                            args.sample_step,
                            progress=not args.quiet,
                        )
                    )
            else:
                row["missing_output"] = 1
        except Exception as exc:
            row["quality_error"] = str(exc)

        status, warnings = quality_status(row, args.target_bands, args)
        if row.get("missing_output"):
            status = "FAIL"
            warnings = (warnings + ";missing_output").strip(";")
        if row.get("quality_error"):
            status = "WARN" if status == "PASS" else status
            warnings = (warnings + ";quality_error").strip(";")
        row["status"] = status
        row["warnings"] = warnings
        print(f"  status: {status}" + (f" ({warnings})" if warnings else ""))
        rows.append(row)
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts = {status: sum(1 for row in rows if row.get("status") == status) for status in ("PASS", "WARN", "FAIL")}
    print(f"Quality summary: {output}")
    print(f"PASS={counts['PASS']}, WARN={counts['WARN']}, FAIL={counts['FAIL']}")
    return 0 if counts["FAIL"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
