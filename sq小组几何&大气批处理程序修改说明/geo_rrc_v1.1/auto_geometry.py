# -*- coding: utf-8 -*-
"""
Standalone geometric correction runner for GF-like satellite images.

This is a clean rewrite of the geometry orchestration logic. It does not call
the old batch_geom_process.py script. It still relies on the existing external
geometry engines:

* satellite-geom
* ba
* optional gdaladdo

Those executables perform the actual tie-point matching, bundle adjustment,
and DEM-based orthorectification.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

try:
    from osgeo import gdal, osr
except ImportError:
    print("GDAL Python bindings are required: from osgeo import gdal", file=sys.stderr)
    sys.exit(1)


IMAGE_PATTERNS = (
    re.compile(r"^GF[1-2]_.*_HRMS_REG\.TIF$", re.IGNORECASE),
    re.compile(r"^GF[6-7]_.*_HRMS_REG\.TIF$", re.IGNORECASE),
    re.compile(r"^GF1[B-D]_.*_HRMS_REG\.TIF$", re.IGNORECASE),
    re.compile(r"^SV\d.*_HRMS_REG\.TIF$", re.IGNORECASE),
    re.compile(r"^TRIPLESAT_\d.*_fuse\.tif$", re.IGNORECASE),
)


@dataclass
class GeometryConfig:
    in_folder: str
    out_folder: str
    reference: str
    dem: str
    projection: Optional[str]
    overwrite: bool
    build_overviews: bool
    satellite_geom: str
    ba: str
    gdaladdo: str


def find_images(folder: str) -> List[str]:
    images = []
    for root, _, files in os.walk(folder):
        for name in files:
            if any(pattern.search(name) for pattern in IMAGE_PATTERNS):
                images.append(os.path.join(root, name))
    return sorted(images)


def run_command(cmd: Sequence[str]) -> None:
    print(" ".join(f'"{part}"' if " " in part else part for part in cmd))
    subprocess.run(list(cmd), check=True)


def get_reference_projection(reference: str, out_folder: str) -> str:
    ds = gdal.Open(reference)
    if ds is None:
        raise RuntimeError(f"Cannot open reference raster: {reference}")
    projection = ds.GetProjection()
    if not projection:
        raise RuntimeError(f"Reference raster has no projection: {reference}")
    path = os.path.join(out_folder, "reference_projection.wkt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(projection)
    return path


def is_geographic_projection(projection_file: str) -> bool:
    with open(projection_file, "r", encoding="utf-8") as handle:
        wkt = handle.read()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    return bool(srs.IsGeographic())


def output_resolution(name: str, geographic: bool = False) -> float:
    rules = (
        (re.compile(r"^GF(1|6)_", re.IGNORECASE), 2.0),
        (re.compile(r"^GF(2|7)_", re.IGNORECASE), 0.8),
        (re.compile(r"^GF1[B-D]_", re.IGNORECASE), 2.0),
        (re.compile(r"^SV\d_", re.IGNORECASE), 0.5),
        (re.compile(r"^TRIPLESAT_\d_", re.IGNORECASE), 0.8),
        (re.compile(r"^GF6_WFV_", re.IGNORECASE), 16.0),
        (re.compile(r"^GF1_WFV", re.IGNORECASE), 16.0),
    )
    for pattern, resolution in rules:
        if pattern.search(name):
            return resolution * 0.00001 if geographic else resolution
    raise RuntimeError(f"Unsupported image name for resolution detection: {name}")


def write_image_list(images: Iterable[str], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for image in images:
            handle.write(image + "\n")


def run_matching(config: GeometryConfig, images: Sequence[str], image_list: str, gcp_file: str) -> None:
    if os.path.exists(gcp_file):
        os.remove(gcp_file)
    write_image_list(images, image_list)

    print("Multiple view matching...")
    run_command(
        [
            config.satellite_geom,
            "-dem",
            config.dem,
            "-nt",
            "1",
            "-mv",
            "-i",
            image_list,
            "-gcp",
            gcp_file,
            "-np",
            "64",
            "-ts",
            "360",
            "-ep",
            "0",
        ]
    )

    print("Single view matching...")
    total = len(images)
    for index, image in enumerate(images, start=1):
        print(f"[{index}/{total}] {image}")
        run_command(
            [
                config.satellite_geom,
                "-append",
                "-dem",
                config.dem,
                "-r",
                config.reference,
                "-i",
                image,
                "-gcp",
                gcp_file,
                "-np",
                "25",
                "-rt1",
                "4",
                "-rt2",
                "4",
                "-sr",
                "500",
            ]
        )


def run_bundle_adjustment(config: GeometryConfig, gcp_file: str, report_file: str) -> None:
    print("Bundle adjustment...")
    run_command([config.ba, "-i", gcp_file, "-report", report_file, "-dem", config.dem])


def model_path_for(image: str) -> str:
    folder = os.path.dirname(image)
    stem = os.path.splitext(os.path.basename(image))[0]
    return os.path.join(folder, stem + ".model")


def ortho_output_path(image: str, out_folder: str) -> str:
    stem = os.path.splitext(os.path.basename(image))[0]
    return os.path.join(out_folder, stem + "_ORTHO.TIF")


def run_orthorectification(
    config: GeometryConfig,
    images: Sequence[str],
    projection_file: Optional[str],
) -> None:
    geographic = is_geographic_projection(projection_file) if projection_file else False
    total = len(images)

    for index, image in enumerate(images, start=1):
        name = os.path.basename(image)
        out_path = ortho_output_path(image, config.out_folder)
        if os.path.exists(out_path) and not config.overwrite:
            print(f"[{index}/{total}] skipped existing: {out_path}")
            continue

        model = model_path_for(image)
        resolution = output_resolution(name, geographic=geographic)
        print(f"[{index}/{total}] orthorectifying: {image}")

        cmd = [
            config.satellite_geom,
            "-dem",
            config.dem,
            "-o",
            out_path,
            "-i",
            image,
            "-model",
            model,
        ]
        if projection_file:
            cmd.extend(["-t_srs", projection_file])
        else:
            cmd.extend(["-t_srs", "+proj=utm +datum=WGS84"])
        cmd.extend(["-tr", str(resolution), str(resolution), "-overwrite"])
        run_command(cmd)

        if config.build_overviews:
            run_command(
                [
                    config.gdaladdo,
                    out_path,
                    "2",
                    "4",
                    "8",
                    "16",
                    "32",
                    "64",
                    "128",
                    "256",
                    "512",
                    "1024",
                ]
            )


def cleanup(config: GeometryConfig, paths: Sequence[str], gcp_file: str) -> None:
    try:
        if os.path.exists(gcp_file):
            run_command([config.ba, "-i", gcp_file, "-clean"])
    finally:
        for path in paths:
            if path and os.path.exists(path):
                os.remove(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone GF geometric correction runner.")
    parser.add_argument("-i", "--in-folder", required=True, help="Input folder with renamed/fused GF images")
    parser.add_argument("-o", "--out-folder", required=True, help="Output folder for *_ORTHO.TIF")
    parser.add_argument("-r", "--reference", required=True, help="Reference raster")
    parser.add_argument("-d", "--dem", required=True, help="DEM raster")
    parser.add_argument("-p", "--projection", default=None, help="Projection WKT file, or 'ref'")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing ortho outputs")
    parser.add_argument("--build-overviews", action="store_true", help="Build image pyramids")
    parser.add_argument("--satellite-geom", default="satellite-geom", help="satellite-geom executable")
    parser.add_argument("--ba", default="ba", help="ba executable")
    parser.add_argument("--gdaladdo", default="gdaladdo", help="gdaladdo executable")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = GeometryConfig(
        in_folder=args.in_folder,
        out_folder=args.out_folder,
        reference=args.reference,
        dem=args.dem,
        projection=args.projection,
        overwrite=args.overwrite,
        build_overviews=args.build_overviews,
        satellite_geom=args.satellite_geom,
        ba=args.ba,
        gdaladdo=args.gdaladdo,
    )

    os.makedirs(config.out_folder, exist_ok=True)
    images = find_images(config.in_folder)
    if not images:
        raise RuntimeError(f"No supported GF images found in {config.in_folder}")

    image_list = os.path.join(config.out_folder, "geometry_image_list.txt")
    gcp_file = os.path.join(config.out_folder, "geometry_gcp.xml")
    report_file = os.path.join(config.out_folder, "geometry_ba_report.txt")
    generated_projection = None

    projection_file = config.projection
    if projection_file == "ref":
        generated_projection = get_reference_projection(config.reference, config.out_folder)
        projection_file = generated_projection

    try:
        run_matching(config, images, image_list, gcp_file)
        run_bundle_adjustment(config, gcp_file, report_file)
        run_orthorectification(config, images, projection_file)
    finally:
        cleanup(config, [image_list, report_file, gcp_file, generated_projection], gcp_file)

    print("Geometry finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
