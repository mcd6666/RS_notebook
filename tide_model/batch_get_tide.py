import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import netCDF4

import pyTMD.io.model as tide_model


# Set these paths, then run:
#   E:\tide_model\.venv\Scripts\python.exe batch_get_tide.py
SCENE_INFO_CSV = r"E:\tide_model\gf2_scene_info.csv"
OUTPUT_CSV = r"E:\tide_model\gf2_scene_tide.csv"
FES_ROOT = r"E:\tide_model"
MODEL_NAME = "FES2022_extrapolated"

# GF2 metadata time is commonly Beijing time for domestic products.
# Set to 0 if your selected_time values are already UTC.
INPUT_TIME_UTC_OFFSET_HOURS = 8
MAX_NEAREST_VALID_DEGREES = 2.0


def parse_scene_time(value):
    if pd.isna(value) or not str(value).strip():
        return None
    text = str(value).strip()
    return dt.datetime.fromisoformat(text)


def days_since_1992_utc(scene_time, utc_offset_hours):
    utc_time = scene_time - dt.timedelta(hours=utc_offset_hours)
    epoch = dt.datetime(1992, 1, 1)
    days = (utc_time - epoch).total_seconds() / 86400.0
    return utc_time, days


def haversine_km(lon1, lat1, lon2, lat2):
    radius_km = 6371.0088
    lon1 = np.deg2rad(lon1)
    lat1 = np.deg2rad(lat1)
    lon2 = np.deg2rad(lon2)
    lat2 = np.deg2rad(lat2)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * np.arcsin(np.sqrt(a))


def nearest_valid_fes_point(lon, lat, m2_file, max_degrees=2.0):
    with netCDF4.Dataset(m2_file) as ds:
        lons = ds.variables["lon"][:]
        lats = ds.variables["lat"][:]

        for radius in (0.25, 0.5, 1.0, max_degrees):
            lon_idx = np.where((lons >= lon - radius) & (lons <= lon + radius))[0]
            lat_idx = np.where((lats >= lat - radius) & (lats <= lat + radius))[0]
            if len(lon_idx) == 0 or len(lat_idx) == 0:
                continue

            amp = ds.variables["amplitude"][
                lat_idx.min() : lat_idx.max() + 1,
                lon_idx.min() : lon_idx.max() + 1,
            ]
            phase = ds.variables["phase"][
                lat_idx.min() : lat_idx.max() + 1,
                lon_idx.min() : lon_idx.max() + 1,
            ]
            amp = np.asarray(amp.filled(np.nan) if hasattr(amp, "filled") else amp)
            phase = np.asarray(phase.filled(np.nan) if hasattr(phase, "filled") else phase)
            valid = np.isfinite(amp) & np.isfinite(phase) & (amp > 0.001)
            if not valid.any():
                continue

            lon_grid, lat_grid = np.meshgrid(lons[lon_idx], lats[lat_idx])
            distance = haversine_km(lon, lat, lon_grid, lat_grid)
            distance = np.where(valid, distance, np.inf)
            iy, ix = np.unravel_index(np.argmin(distance), distance.shape)
            return float(lon_grid[iy, ix]), float(lat_grid[iy, ix]), float(distance[iy, ix])

    return np.nan, np.nan, np.nan


def extract_pairwise_tides(values, n_points):
    values = np.asarray(values)
    if values.ndim == 2 and values.shape[0] == n_points and values.shape[1] == n_points:
        return np.diag(values).copy()
    return values.reshape(n_points, -1)[:, 0].copy()


def classify_by_quantile(values):
    q25, q50, q75 = np.nanquantile(values, [0.25, 0.50, 0.75])
    classes = []
    for value in values:
        if not np.isfinite(value):
            classes.append("")
        elif value <= q25:
            classes.append("低潮")
        elif value <= q50:
            classes.append("中低潮")
        elif value <= q75:
            classes.append("中高潮")
        else:
            classes.append("高潮")
    return classes, q25, q50, q75


def classify_by_threshold(value):
    if not np.isfinite(value):
        return ""
    if value <= -1.0:
        return "低潮"
    if value <= 0.0:
        return "中低潮"
    if value < 0.6:
        return "中高潮"
    return "高潮"


def main():
    parser = argparse.ArgumentParser(description="Batch predict FES tide height for GF2 scene centers.")
    parser.add_argument("--scene-info", default=SCENE_INFO_CSV, help="Input gf2_scene_info.csv")
    parser.add_argument("-o", "--output", default=OUTPUT_CSV, help="Output CSV")
    parser.add_argument("--fes-root", default=FES_ROOT, help="FES model root folder, usually E:\\tide_model")
    parser.add_argument("--model", default=MODEL_NAME, help="pyTMD model name")
    parser.add_argument(
        "--time-offset-hours",
        type=float,
        default=INPUT_TIME_UTC_OFFSET_HOURS,
        help="Input time offset from UTC. Beijing time = 8; UTC = 0.",
    )
    parser.add_argument(
        "--max-nearest-valid-degrees",
        type=float,
        default=MAX_NEAREST_VALID_DEGREES,
        help="Search radius for replacing land/NaN center points with nearest valid FES point.",
    )
    args = parser.parse_args()

    scene_info = Path(args.scene_info)
    if not scene_info.exists():
        raise SystemExit(f"Input CSV not found: {scene_info}")

    df = pd.read_csv(scene_info, encoding="utf-8-sig")
    required = {"selected_time", "xml_center_lon", "xml_center_lat"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    good = (
        df["selected_time"].notna()
        & df["xml_center_lon"].notna()
        & df["xml_center_lat"].notna()
    )
    if not good.all():
        print(f"Skipping {(~good).sum()} rows with missing time/coordinates.")
    work = df.loc[good].copy()

    scene_times = [parse_scene_time(v) for v in work["selected_time"]]
    utc_times = []
    tide_days = []
    for scene_time in scene_times:
        utc_time, days = days_since_1992_utc(scene_time, args.time_offset_hours)
        utc_times.append(utc_time)
        tide_days.append(days)

    lons = work["xml_center_lon"].astype(float).to_numpy()
    lats = work["xml_center_lat"].astype(float).to_numpy()
    tide_lons = lons.copy()
    tide_lats = lats.copy()
    tide_point_source = np.full(len(work), "scene_center", dtype=object)
    tide_point_distance_km = np.zeros(len(work), dtype=float)
    tide_days = np.asarray(tide_days, dtype=float)

    print(f"Loading {args.model} from {args.fes_root} ...", flush=True)
    model = tide_model(args.fes_root).from_database(args.model, group="z")
    ds = model.open_dataset(group="z", chunks={"lat": 512, "lon": 512})

    print(f"Interpolating {len(work)} scene centers ...", flush=True)
    x = xr.DataArray(lons, dims="point")
    y = xr.DataArray(lats, dims="point")
    points = ds.tmd.interp(x, y, method="linear", extrapolate=False)

    print("Predicting tides ...", flush=True)
    predicted = points.tmd.predict(tide_days, corrections=model.corrections)
    tide_m = extract_pairwise_tides(predicted.values, len(work))

    nan_mask = ~np.isfinite(tide_m)
    interpolation_method = np.full(len(work), "linear", dtype=object)
    if nan_mask.any():
        print(f"Filling {int(nan_mask.sum())} NaN tides with nearest-neighbor interpolation ...", flush=True)
        nearest_points = ds.tmd.interp(x, y, method="nearest", extrapolate=False)
        nearest_predicted = nearest_points.tmd.predict(tide_days, corrections=model.corrections)
        nearest_tide_m = extract_pairwise_tides(nearest_predicted.values, len(work))
        tide_m[nan_mask] = nearest_tide_m[nan_mask]
        interpolation_method[nan_mask] = "nearest"

    nan_mask = ~np.isfinite(tide_m)
    if nan_mask.any():
        print(f"Finding nearest valid FES grid point for {int(nan_mask.sum())} remaining NaN tides ...", flush=True)
        m2_file = Path(args.fes_root) / "fes2022b" / "ocean_tide_extrapolated" / "m2_fes2022.nc"
        missing_indices = np.where(nan_mask)[0]
        fallback_lons = []
        fallback_lats = []
        fallback_days = []
        fallback_original_indices = []
        for idx in missing_indices:
            fallback_lon, fallback_lat, distance_km = nearest_valid_fes_point(
                tide_lons[idx],
                tide_lats[idx],
                m2_file,
                max_degrees=args.max_nearest_valid_degrees,
            )
            if np.isfinite(fallback_lon) and np.isfinite(fallback_lat):
                tide_lons[idx] = fallback_lon
                tide_lats[idx] = fallback_lat
                tide_point_distance_km[idx] = distance_km
                tide_point_source[idx] = "nearest_valid_fes_grid"
                fallback_lons.append(fallback_lon)
                fallback_lats.append(fallback_lat)
                fallback_days.append(tide_days[idx])
                fallback_original_indices.append(idx)

        if fallback_original_indices:
            fx = xr.DataArray(np.asarray(fallback_lons), dims="point")
            fy = xr.DataArray(np.asarray(fallback_lats), dims="point")
            fallback_points = ds.tmd.interp(fx, fy, method="nearest", extrapolate=False)
            fallback_predicted = fallback_points.tmd.predict(
                np.asarray(fallback_days),
                corrections=model.corrections,
            )
            fallback_tide_m = extract_pairwise_tides(fallback_predicted.values, len(fallback_original_indices))
            for original_idx, value in zip(fallback_original_indices, fallback_tide_m):
                tide_m[original_idx] = value
                interpolation_method[original_idx] = "nearest_valid_grid"

    work["selected_time_local"] = [t.isoformat(sep=" ") for t in scene_times]
    work["selected_time_utc"] = [t.isoformat(sep=" ") for t in utc_times]
    work["time_offset_hours_applied"] = args.time_offset_hours
    work["tide_model"] = args.model
    work["tide_interpolation"] = interpolation_method
    work["tide_query_lon"] = tide_lons
    work["tide_query_lat"] = tide_lats
    work["tide_point_source"] = tide_point_source
    work["tide_point_distance_km"] = tide_point_distance_km
    work["tide_ocean_m"] = tide_m
    quantile_class, q25, q50, q75 = classify_by_quantile(tide_m)
    work["tide_level_class"] = quantile_class
    work["tide_level_class_threshold"] = [classify_by_threshold(v) for v in tide_m]
    work["tide_q25_m"] = q25
    work["tide_q50_m"] = q50
    work["tide_q75_m"] = q75

    output = Path(args.output)
    work.to_csv(output, index=False, encoding="utf-8-sig")

    valid = np.isfinite(tide_m)
    print(f"rows = {len(work)}")
    print(f"valid_tide = {int(valid.sum())}")
    print(f"nan_tide = {int((~valid).sum())}")
    if valid.any():
        print(f"min_tide_m = {float(np.nanmin(tide_m)):.4f}")
        print(f"max_tide_m = {float(np.nanmax(tide_m)):.4f}")
    print(f"output = {output.resolve()}")


if __name__ == "__main__":
    main()
