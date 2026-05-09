# -*- coding: utf-8 -*-
r"""
Batch runner for automatic PIF-based GF correction.

Example:
    python batch_auto_pif_rrc.py ^
      -r F:\pre_process\GYY\s2_ref.tif ^
      -i F:\pre_process\GYY\2 ^
      -o F:\pre_process\GYY\3_rrc
"""

import argparse
import csv
import os
from typing import List, Sequence

import auto_pif_rrc


def find_targets(in_folder: str, pattern_suffix: str) -> List[str]:
    targets = []
    suffix = pattern_suffix.lower()
    for root, _, files in os.walk(in_folder):
        for name in files:
            lower = name.lower()
            if lower.endswith(suffix) and "_rrc" not in lower and "_radcal" not in lower:
                targets.append(os.path.join(root, name))
    return sorted(targets)


def output_name(target: str, in_folder: str, out_folder: str, suffix: str) -> str:
    rel = os.path.relpath(target, in_folder)
    base, _ = os.path.splitext(rel)
    return os.path.join(out_folder, base + suffix + ".tif")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch automatic Sentinel-2 based PIF correction.")
    parser.add_argument("-r", "--reference", required=True, help="Sentinel-2 reference raster")
    parser.add_argument("-i", "--in-folder", required=True, help="Folder containing GF rasters")
    parser.add_argument("-o", "--out-folder", required=True, help="Output folder")
    parser.add_argument(
        "--target-suffix",
        default="_ORTHO.TIF",
        help="Input filename suffix to process; default: _ORTHO.TIF",
    )
    parser.add_argument("--output-suffix", default="_RRC", help="Output filename suffix; default: _RRC")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing corrected rasters")
    parser.add_argument("--reference-bands", default="1,2,3,4", help="S2 Blue,Green,Red,NIR bands")
    parser.add_argument("--target-bands", default="1,2,3,4", help="GF bands matching S2 bands")
    parser.add_argument("--scale", default="10000", help="Reflectance scale factor")
    parser.add_argument("--max-ndvi", default="0.35", help="Max absolute NDVI for PIF candidates")
    parser.add_argument("--max-ndwi", default="0.0", help="Max S2 NDWI to exclude water")
    parser.add_argument(
        "--brightness-quantiles",
        nargs=2,
        default=("0.05", "0.95"),
        metavar=("LOW", "HIGH"),
        help="Brightness quantiles used to reject shadow/saturation",
    )
    parser.add_argument("--pif-percentile", default="5.0", help="Lowest change-score percentile kept")
    parser.add_argument("--min-pixels", default="100", help="Minimum PIF pixels required")
    parser.add_argument("--sample-step", default="4", help="Use every Nth reference-grid pixel for fitting")
    parser.add_argument("--no-auto-roi", action="store_true", help="Disable automatic stable ROI selection")
    parser.add_argument("--roi-tile-size", default="256", help="Automatic ROI tile size on sampled grid")
    parser.add_argument("--roi-top-percent", default="20", help="Percent of most stable ROI tiles to keep")
    parser.add_argument("--roi-max-tiles", default="20", help="Maximum automatic ROI tiles to keep")
    parser.add_argument("--roi-min-candidate-ratio", default="0.15", help="Minimum candidate ratio in ROI tile")
    parser.add_argument("--output-dtype", default="UInt16", help="Output GDAL data type")
    return parser


def run_one(args: argparse.Namespace, target: str, out_path: str) -> None:
    report = os.path.splitext(out_path)[0] + "_pif_report.json"
    cmd_args = [
        "-r",
        args.reference,
        "-t",
        target,
        "-o",
        out_path,
        "--reference-bands",
        args.reference_bands,
        "--target-bands",
        args.target_bands,
        "--scale",
        args.scale,
        "--max-ndvi",
        args.max_ndvi,
        "--max-ndwi",
        args.max_ndwi,
        "--brightness-quantiles",
        args.brightness_quantiles[0],
        args.brightness_quantiles[1],
        "--pif-percentile",
        args.pif_percentile,
        "--min-pixels",
        args.min_pixels,
        "--sample-step",
        args.sample_step,
        "--roi-tile-size",
        args.roi_tile_size,
        "--roi-top-percent",
        args.roi_top_percent,
        "--roi-max-tiles",
        args.roi_max_tiles,
        "--roi-min-candidate-ratio",
        args.roi_min_candidate_ratio,
        "--output-dtype",
        args.output_dtype,
        "--report",
        report,
    ]
    if args.no_auto_roi:
        cmd_args.append("--no-auto-roi")
    auto_pif_rrc.main(cmd_args)


def main(argv: Sequence[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    os.makedirs(args.out_folder, exist_ok=True)
    targets = find_targets(args.in_folder, args.target_suffix)
    if not targets:
        print(f"No targets found in {args.in_folder} with suffix {args.target_suffix}")
        return 1

    summary_path = os.path.join(args.out_folder, "batch_auto_pif_rrc_summary.csv")
    rows = []
    for idx, target in enumerate(targets, start=1):
        out_path = output_name(target, args.in_folder, args.out_folder, args.output_suffix)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        print(f"[{idx}/{len(targets)}] {target}")
        print(f"  output: {out_path}")

        if os.path.exists(out_path) and not args.overwrite:
            rows.append([target, out_path, "skipped", "output exists"])
            print("  skipped: output exists")
            continue

        try:
            run_one(args, target, out_path)
            rows.append([target, out_path, "ok", ""])
        except Exception as exc:
            rows.append([target, out_path, "failed", str(exc)])
            print(f"  failed: {exc}")

    with open(summary_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["target", "output", "status", "message"])
        writer.writerows(rows)

    ok_count = sum(1 for row in rows if row[2] == "ok")
    fail_count = sum(1 for row in rows if row[2] == "failed")
    skip_count = sum(1 for row in rows if row[2] == "skipped")
    print(f"Summary: {summary_path}")
    print(f"OK={ok_count}, failed={fail_count}, skipped={skip_count}")
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
