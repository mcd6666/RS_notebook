import argparse
import datetime as dt
import re
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path


TIME_TAG_HINTS = (
    "centertime",
    "center_time",
    "imagingtime",
    "imaging_time",
    "scenecentertime",
    "starttime",
    "start_time",
    "endtime",
    "end_time",
    "acquisitiontime",
    "acquisition_time",
)

LON_TAG_HINTS = ("centerlongitude", "center_lon", "centerlong", "longitude")
LAT_TAG_HINTS = ("centerlatitude", "center_lat", "centerlat", "latitude")


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_time(value):
    text = value.strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%dT%H:%M:%S",
        "%Y%m%d%H%M%S",
    ):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def read_xml_members(scene_path):
    with tarfile.open(scene_path, "r:*") as archive:
        for member in archive:
            if member.isfile() and member.name.lower().endswith(".xml"):
                fileobj = archive.extractfile(member)
                if fileobj is None:
                    continue
                yield member.name, fileobj.read()


def collect_fields(xml_bytes):
    root = ET.fromstring(xml_bytes)
    times = []
    lons = []
    lats = []
    all_fields = []

    for elem in root.iter():
        tag = strip_ns(elem.tag)
        value = (elem.text or "").strip()
        if not value:
            continue
        all_fields.append((tag, value))
        if any(hint in tag for hint in TIME_TAG_HINTS):
            parsed = parse_time(value)
            if parsed:
                times.append((tag, parsed, value))
        if any(hint in tag for hint in LON_TAG_HINTS):
            try:
                lons.append((tag, float(value), value))
            except ValueError:
                pass
        if any(hint in tag for hint in LAT_TAG_HINTS):
            try:
                lats.append((tag, float(value), value))
            except ValueError:
                pass

    return times, lons, lats, all_fields


def parse_name(scene_path):
    name = Path(scene_path).name
    match = re.search(r"_E(?P<lon>\d+(?:\.\d+)?)_N(?P<lat>\d+(?:\.\d+)?)_(?P<date>\d{8})_", name)
    if not match:
        return None
    return float(match.group("lon")), float(match.group("lat")), match.group("date")


def main():
    parser = argparse.ArgumentParser(description="Extract GF2 scene time and center coordinates from a .tar.gz package.")
    parser.add_argument("scene", help="GF2 .tar.gz scene path")
    args = parser.parse_args()

    scene_path = Path(args.scene)
    if not scene_path.exists():
        raise SystemExit(f"File not found: {scene_path}")

    name_info = parse_name(scene_path)
    if name_info:
        lon, lat, ymd = name_info
        print(f"filename_center_lon = {lon}")
        print(f"filename_center_lat = {lat}")
        print(f"filename_date = {ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}")

    found_xml = False
    for xml_name, xml_bytes in read_xml_members(scene_path):
        found_xml = True
        print(f"\nxml = {xml_name}")
        try:
            times, lons, lats, _ = collect_fields(xml_bytes)
        except ET.ParseError as exc:
            print(f"xml_parse_error = {exc}")
            continue

        if times:
            print("time_candidates:")
            for tag, parsed, raw in times:
                print(f"  {tag} = {raw}  ->  {parsed.isoformat()}")
        else:
            print("time_candidates: none")

        if lons:
            print("longitude_candidates:")
            for tag, value, raw in lons[:12]:
                print(f"  {tag} = {raw}  ->  {value}")
        if lats:
            print("latitude_candidates:")
            for tag, value, raw in lats[:12]:
                print(f"  {tag} = {raw}  ->  {value}")

    if not found_xml:
        print("\nNo XML metadata file found inside the archive.")


if __name__ == "__main__":
    main()
