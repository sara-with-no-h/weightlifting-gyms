#!/usr/bin/env python3
"""
Parse Google Maps saved-list API responses and export to CSV + JSON.

WHAT IS THIS?
  When you view a Google Maps saved list (e.g. "Weightlifting gyms"), the page
  makes XHR requests that return place data in a proprietary XSSI-protected
  format. This script parses those raw response files and extracts structured
  place data (name, address, coordinates, rating, phone, website, etc.).

HOW TO CAPTURE THE RESPONSES:
  1. Open Chrome DevTools → Network tab → filter by "Fetch/XHR"
  2. Open your Google Maps saved list
  3. Scroll to the bottom (each scroll triggers a new paginated request)
  4. Right-click each request named something like "preview" or with a long
     token in the URL → Copy → Copy response
  5. Paste into a file, e.g. response1.json, response2.json, etc.

HOW TO RUN:
  # Single file
  python3 scripts/parse-list-response.py 2026-04-13/response1.json

  # Multiple files → merged output in a folder
  python3 scripts/parse-list-response.py 2026-04-13/response*.json --out 2026-04-13

  # Custom output name stem
  python3 scripts/parse-list-response.py response*.json --out exports --stem gyms

OUTPUT:
  <out>/<stem>.csv   (default: gyms.csv)
  <out>/<stem>.json  (default: gyms.json)
"""

import argparse
import csv
import json
from pathlib import Path


XSSI_PREFIX = ")]}'\n"


def safe_get(obj, *keys):
    try:
        for k in keys:
            obj = obj[k]
        return obj
    except (TypeError, IndexError, KeyError):
        return None


def extract_place(item: list) -> dict:
    d = safe_get(item, 14)
    if d is None:
        return {}

    review_count_raw = safe_get(d, 4, 8)
    review_count = int(review_count_raw) if review_count_raw is not None else None
    categories = safe_get(d, 13) or []

    return {
        "name":           safe_get(d, 11),
        "note":           safe_get(d, 25, 15, 0, 2),
        "address":        safe_get(d, 18),
        "street":         safe_get(d, 2, 0),
        "city_state_zip": safe_get(d, 2, 1),
        "country":        safe_get(d, 2, 2),
        "latitude":       safe_get(d, 9, 2),
        "longitude":      safe_get(d, 9, 3),
        "rating":         safe_get(d, 4, 7),
        "review_count":   review_count,
        "website":        safe_get(d, 7, 0),
        "phone":          safe_get(d, 178, 0, 0),
        "place_id":       safe_get(d, 78),
        "categories":     ", ".join(categories),
        "timezone":       safe_get(d, 30),
    }


def parse_response(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    envelope = json.loads(raw)
    d_val = envelope.get("d", "")

    if not d_val.startswith(XSSI_PREFIX):
        raise ValueError(f"{path}: unexpected format — 'd' field missing XSSI prefix.")

    inner = json.loads(d_val[len(XSSI_PREFIX):])
    places_raw = safe_get(inner, 0, 1) or []

    places = []
    for item in places_raw:
        if not isinstance(item, list):
            continue
        place = extract_place(item)
        if place.get("name"):
            places.append(place)
    return places


FIELDNAMES = [
    "name", "note", "address", "street", "city_state_zip", "country",
    "latitude", "longitude", "rating", "review_count",
    "website", "phone", "place_id", "categories", "timezone",
]


def write_csv(places: list[dict], path: Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(places)
    print(f"Saved CSV  → {path}  ({len(places)} rows)")


def write_json(places: list[dict], path: Path):
    path.write_text(json.dumps(places, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved JSON → {path}  ({len(places)} entries)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="One or more response JSON files")
    parser.add_argument("--out", type=Path, default=Path("."), help="Output directory (default: current dir)")
    parser.add_argument("--stem", default="gyms", help="Output filename stem (default: gyms)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    all_places = []
    for path in sorted(args.files):
        places = parse_response(path)
        print(f"{path.name}: {len(places)} places")
        all_places.extend(places)

    print(f"\nTotal: {len(all_places)} places")
    write_csv(all_places,  args.out / f"{args.stem}.csv")
    write_json(all_places, args.out / f"{args.stem}.json")


if __name__ == "__main__":
    main()
