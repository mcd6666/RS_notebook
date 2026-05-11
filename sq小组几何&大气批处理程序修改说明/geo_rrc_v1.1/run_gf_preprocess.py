# -*- coding: utf-8 -*-
"""
One-command GF preprocessing pipeline.

This script combines the standalone geometric correction workflow with the
automatic Sentinel-2 based PIF correction workflow:

1. auto_geometry.py:
   GF *_HRMS_REG.TIF -> *_ORTHO.TIF
2. batch_auto_pif_rrc.py:
   *_ORTHO.TIF -> *_RRC.TIF

It keeps geometry and radiometric/PIF correction as separate modules internally
so each stage can still be inspected and rerun independently.
"""

import argparse
import os
import subprocess
import sys
from typing import List, Optional, Sequence


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GEOM_SCRIPT = os.path.join(THIS_DIR, "auto_geometry.py")
RRC_SCRIPT = os.path.join(THIS_DIR, "batch_auto_pif_rrc.py")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run GF geometry + automatic PIF correction.")
    parser.add_argument("-i", "--in-folder", required=True, help="Input folder with renamed/fused GF images")
    parser.add_argument(
        "-g",
        "--geom-folder",
        required=True,
        help="Geometry output folder; contains *_ORTHO.TIF after stage 1",
    )
    parser.add_argument(
        "-o",
        "--rrc-folder",
        required=True,
        help="Final PIF correction output folder; contains *_RRC.TIF after stage 2",
    )
    parser.add_argument(
        "-r",
        "--reference",
        required=True,
        help="Sentinel-2 reference raster. Used by both geometry matching and PIF correction.",
    )
    parser.add_argument("-d", "--dem", required=True, help="DEM raster used by geometric correction")
    parser.add_argument(
        "-p",
        "--prj",
        default=None,
        help="Optional output projection for geometry. Use 'ref' to use reference projection.",
    )
    parser.add_argument("--skip-geometry", action="store_true", help="Only run automatic PIF correction")
    parser.add_argument("--skip-rrc", action="store_true", help="Only run geometric correction")
    parser.add_argument("--overwrite-geometry", action="store_true", help="Overwrite existing *_ORTHO.TIF outputs")
    parser.add_argument("--build-overviews", action="store_true", help="Build image pyramids for geometry outputs")
    parser.add_argument("--overwrite-rrc", action="store_true", help="Overwrite existing *_RRC.TIF outputs")
    parser.add_argument("--satellite-geom", default="satellite-geom", help="satellite-geom executable")
    parser.add_argument("--ba", default="ba", help="ba executable")
    parser.add_argument("--gdaladdo", default="gdaladdo", help="gdaladdo executable")
    parser.add_argument("--target-suffix", default="_ORTHO.TIF", help="Geometry output suffix to process")
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
    parser.add_argument("--pif-method", default="imad", choices=("imad", "score"), help="PIF selection method")
    parser.add_argument("--imad-iter", default="100", help="Maximum iMAD reweighting iterations")
    parser.add_argument("--imad-delta", default="0.001", help="iMAD convergence threshold")
    parser.add_argument("--pif-ncp-thresh", default="0.95", help="No-change probability threshold")
    parser.add_argument("--regression-method", default="orthogonal", choices=("orthogonal", "robust"), help="Fit method")
    parser.add_argument("--sample-step", default="4", help="Use every Nth reference-grid pixel for PIF fitting")
    parser.add_argument("--no-auto-roi", action="store_true", help="Disable automatic stable ROI selection")
    parser.add_argument("--roi-tile-size", default="256", help="Automatic ROI tile size on sampled grid")
    parser.add_argument("--roi-top-percent", default="20", help="Percent of most stable ROI tiles to keep")
    parser.add_argument("--roi-max-tiles", default="20", help="Maximum automatic ROI tiles to keep")
    parser.add_argument("--roi-min-candidate-ratio", default="0.15", help="Minimum candidate ratio in ROI tile")
    parser.add_argument("--output-dtype", default="UInt16", help="RRC output GDAL data type")
    return parser


def run_command(cmd: List[str], env: Optional[dict] = None) -> None:
    print(" ".join(f'"{part}"' if " " in part else part for part in cmd))
    subprocess.run(cmd, check=True, env=env)


def run_geometry(args: argparse.Namespace) -> None:
    if not os.path.exists(GEOM_SCRIPT):
        raise RuntimeError(f"Missing geometry script: {GEOM_SCRIPT}")

    os.makedirs(args.geom_folder, exist_ok=True)
    cmd = [
        sys.executable,
        GEOM_SCRIPT,
        "-i",
        args.in_folder,
        "-o",
        args.geom_folder,
        "-r",
        args.reference,
        "-d",
        args.dem,
    ]
    if args.prj:
        cmd.extend(["-p", args.prj])
    if args.overwrite_geometry:
        cmd.append("--overwrite")
    if args.build_overviews:
        cmd.append("--build-overviews")
    cmd.extend(["--satellite-geom", args.satellite_geom])
    cmd.extend(["--ba", args.ba])
    cmd.extend(["--gdaladdo", args.gdaladdo])
    run_command(cmd)


def run_rrc(args: argparse.Namespace) -> None:
    if not os.path.exists(RRC_SCRIPT):
        raise RuntimeError(f"Missing RRC script: {RRC_SCRIPT}")

    os.makedirs(args.rrc_folder, exist_ok=True)
    cmd = [
        sys.executable,
        RRC_SCRIPT,
        "-r",
        args.reference,
        "-i",
        args.geom_folder,
        "-o",
        args.rrc_folder,
        "--target-suffix",
        args.target_suffix,
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
        "--pif-method",
        args.pif_method,
        "--imad-iter",
        args.imad_iter,
        "--imad-delta",
        args.imad_delta,
        "--pif-ncp-thresh",
        args.pif_ncp_thresh,
        "--regression-method",
        args.regression_method,
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
    ]
    if args.no_auto_roi:
        cmd.append("--no-auto-roi")
    if args.overwrite_rrc:
        cmd.append("--overwrite")
    run_command(cmd)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.skip_geometry and args.skip_rrc:
        parser.error("--skip-geometry and --skip-rrc cannot both be set")

    if not args.skip_geometry:
        print("=== Stage 1/2: geometric correction ===")
        run_geometry(args)

    if not args.skip_rrc:
        print("=== Stage 2/2: automatic PIF correction ===")
        run_rrc(args)

    print("Pipeline finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
