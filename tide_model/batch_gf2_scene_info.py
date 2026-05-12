import argparse
import csv
import datetime as dt
from pathlib import Path

from extract_gf2_scene_info import collect_fields, parse_name, read_xml_members


# Set these paths, then run:
#   python batch_gf2_scene_info.py
SCENE_FOLDER = r"E:\进行时\美丽海湾\数据样本\GF2原始数据"
OUTPUT_CSV = r"E:\tide_model\gf2_scene_info.csv"
RECURSIVE = True


def choose_time(times):
    if not times:
        return "", "", ""

    priority = (
        "centertime",
        "center_time",
        "scenecentertime",
        "imagingtime",
        "imaging_time",
        "acquisitiontime",
        "acquisition_time",
        "starttime",
        "start_time",
    )
    lowered = [(tag.lower(), parsed, raw) for tag, parsed, raw in times]
    for key in priority:
        for tag, parsed, raw in lowered:
            if key in tag:
                return tag, parsed.isoformat(sep=" "), raw
    tag, parsed, raw = lowered[0]
    return tag, parsed.isoformat(sep=" "), raw


def average_time_if_possible(times):
    starts = [parsed for tag, parsed, _ in times if "start" in tag.lower()]
    ends = [parsed for tag, parsed, _ in times if "end" in tag.lower()]
    if not starts or not ends:
        return ""
    start = starts[0]
    end = ends[0]
    if start.tzinfo != end.tzinfo:
        return ""
    return (start + (end - start) / 2).isoformat(sep=" ")


def choose_coordinate(fields, axis, filename_value):
    axis = axis.lower()
    center_tag = f"center{axis}"
    corner_tags = (
        f"topleft{axis}",
        f"topright{axis}",
        f"bottomright{axis}",
        f"bottomleft{axis}",
    )

    values = {}
    for tag, raw in fields:
        tag_lower = tag.lower()
        if axis not in tag_lower:
            continue
        try:
            values[tag_lower] = float(raw)
        except ValueError:
            continue

    if center_tag in values:
        return center_tag, values[center_tag], "xml_center"

    corners = [values[tag] for tag in corner_tags if tag in values]
    if len(corners) == 4:
        return "corner_average_" + axis, sum(corners) / 4.0, "xml_corner_average"

    if filename_value != "":
        return "filename_" + axis, filename_value, "filename"

    return "", "", ""


def summarize_scene(scene_path):
    name_info = parse_name(scene_path)
    filename_lon = filename_lat = filename_date = ""
    if name_info:
        filename_lon, filename_lat, ymd = name_info
        filename_date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"

    row = {
        "file": str(scene_path),
        "filename_center_lon": filename_lon,
        "filename_center_lat": filename_lat,
        "filename_date": filename_date,
        "xml": "",
        "selected_time_tag": "",
        "selected_time": "",
        "selected_time_raw": "",
        "mid_time_from_start_end": "",
        "xml_lon_tag": "",
        "xml_center_lon": "",
        "xml_lat_tag": "",
        "xml_center_lat": "",
        "coordinate_source": "",
        "status": "ok",
        "message": "",
    }

    best = None
    best_score = -1
    best_name = ""
    saw_xml = False
    try:
        xml_iter = read_xml_members(scene_path)
        for xml_name, xml_bytes in xml_iter:
            saw_xml = True
            try:
                times, lons, lats, fields = collect_fields(xml_bytes)
            except Exception as exc:
                if best is None:
                    row["status"] = "warning"
                    row["message"] = f"xml_parse_failed: {xml_name}: {exc}"
                continue

            score = len(times) * 4 + len(lons) + len(lats)
            if score > best_score:
                best = (times, fields)
                best_score = score
                best_name = xml_name

            if times and lons and lats:
                break
    except Exception as exc:
        row["status"] = "error"
        row["message"] = f"open_archive_failed: {exc}"
        return row

    if not saw_xml:
        row["status"] = "warning"
        row["message"] = "no_xml_found"
        return row

    if best is None:
        row["status"] = "warning"
        if not row["message"]:
            row["message"] = "no_readable_xml"
        return row

    times, fields = best
    row["xml"] = best_name
    tag, selected, raw = choose_time(times)
    row["selected_time_tag"] = tag
    row["selected_time"] = selected
    row["selected_time_raw"] = raw
    row["mid_time_from_start_end"] = average_time_if_possible(times)

    lon_tag, lon_value, lon_source = choose_coordinate(fields, "longitude", filename_lon)
    lat_tag, lat_value, lat_source = choose_coordinate(fields, "latitude", filename_lat)
    row["xml_lon_tag"] = lon_tag
    row["xml_center_lon"] = lon_value
    row["xml_lat_tag"] = lat_tag
    row["xml_center_lat"] = lat_value
    row["coordinate_source"] = lon_source if lon_source == lat_source else f"{lon_source}/{lat_source}"

    if not selected:
        row["status"] = "warning"
        row["message"] = "no_time_candidate"

    return row


def main():
    parser = argparse.ArgumentParser(description="Batch extract GF2 scene time and center coordinates to CSV.")
    parser.add_argument("folder", nargs="?", default=SCENE_FOLDER, help="Folder containing GF2 .tar.gz scenes")
    parser.add_argument("-o", "--output", default=OUTPUT_CSV, help="Output CSV path")
    parser.add_argument("--recursive", action="store_true", default=RECURSIVE, help="Search recursively")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="Do not search recursively")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        raise SystemExit(f"Folder not found: {folder}")

    pattern = "**/GF2*.tar.gz" if args.recursive else "GF2*.tar.gz"
    scenes = sorted(folder.glob(pattern))
    if not scenes:
        raise SystemExit(f"No GF2*.tar.gz files found in: {folder}")

    rows = []
    for index, scene in enumerate(scenes, start=1):
        print(f"[{index}/{len(scenes)}] reading {scene.name}", flush=True)
        rows.append(summarize_scene(scene))
    output = Path(args.output)
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for row in rows if row["status"] == "ok")
    warnings = sum(1 for row in rows if row["status"] == "warning")
    errors = sum(1 for row in rows if row["status"] == "error")
    print(f"scenes = {len(rows)}")
    print(f"ok = {ok}")
    print(f"warnings = {warnings}")
    print(f"errors = {errors}")
    print(f"output = {output.resolve()}")


if __name__ == "__main__":
    main()
