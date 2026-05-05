#!/usr/bin/env python3
"""
Parse Google Maps saved-list API responses and export to CSV + JSON.

Supports two input modes — both can be used together:

  MANUAL MODE (copy-paste from DevTools):
    Capture each XHR response manually and save as response0.json, response1.json, etc.
    Pass them as positional arguments.

  HAR MODE (export from DevTools):
    Export a HAR file from DevTools (Network tab → right-click → Save all as HAR).
    Pass it via --har. The script extracts the relevant requests automatically.

HOW TO CAPTURE MANUALLY:
  1. Open Chrome DevTools → Network tab → filter by Fetch/XHR
  2. Open your Google Maps saved list
  3. Scroll slowly to the bottom — each scroll triggers a paginated request (~20 places)
     Scrolling too fast skips requests. Expect ~7 files for 138 places.
  4. For each paginated request: right-click → Copy → Copy response → paste into responseN.json
  5. Also save the getlist request as additionalResponse.json (has contributor names + notes)
  6. Put all files in a YYYY-MM-DD/ folder

HOW TO CAPTURE VIA HAR:
  1. Open Chrome DevTools → Network tab → filter by Fetch/XHR
  2. Open your Google Maps saved list and scroll slowly to the bottom
  3. Right-click anywhere in the request list → Save all as HAR with content
  4. Save the .har file into your YYYY-MM-DD/ folder

HOW TO RUN:
  # Manual mode
  python3 scripts/parse-list-response.py 2026-05-05/response*.json \\
      --additional 2026-05-05/additionalResponse.json --out 2026-05-05

  # HAR mode (additionalResponse extracted automatically)
  python3 scripts/parse-list-response.py --har 2026-05-05/capture.har --out 2026-05-05

  # Both combined (manual files + HAR, deduped)
  python3 scripts/parse-list-response.py 2026-05-05/response*.json \\
      --har 2026-05-05/capture.har --out 2026-05-05

OUTPUT:
  <out>/<stem>.csv   (default: gyms.csv)
  <out>/<stem>.json  (default: gyms.json)
"""

import argparse
import base64
import csv
import json
from pathlib import Path


XSSI_PREFIX    = ")]}'\n"
PAGINATED_URL  = "google.com/search?tbm=map"
PAGINATED_MARK = "tch=1"
ADDITIONAL_URL = "maps/preview/entitylist/getlist"


def safe_get(obj, *keys):
    try:
        for k in keys:
            obj = obj[k]
        return obj
    except (TypeError, IndexError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _decode_har_body(content: dict) -> str:
    text = content.get("text", "")
    if content.get("encoding") == "base64" and text:
        text = base64.b64decode(text).decode("utf-8", errors="replace")
    return text


def _parse_envelope(text: str) -> list[dict]:
    """Parse one paginated response body → list of place dicts."""
    # Google appends /*""*/ after the JSON — use raw_decode to stop there
    decoder = json.JSONDecoder()
    envelope, _ = decoder.raw_decode(text)
    d_val = envelope.get("d", "")
    if not d_val.startswith(XSSI_PREFIX):
        return []
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


def _parse_additional_text(text: str) -> dict:
    """Parse an additional response body → name-keyed lookup."""
    stripped = text.lstrip(")\n]}'").lstrip("\n")
    data = json.loads(stripped)
    lookup = {}
    entries = safe_get(data, 0, 8) or []
    for e in entries:
        name = e[2] if len(e) > 2 else None
        if not name:
            continue
        added_by_raw = e[12] if len(e) > 12 else None
        note = e[3] if len(e) > 3 else None
        lookup[name] = {
            "added_by": added_by_raw[0] if added_by_raw else None,
            "note":     note,
        }
    return lookup


# ---------------------------------------------------------------------------
# Public parsing functions
# ---------------------------------------------------------------------------

def extract_place(item: list) -> dict:
    d = safe_get(item, 14)
    if d is None:
        return {}
    review_count_raw = safe_get(d, 4, 8)
    review_count = int(review_count_raw) if review_count_raw is not None else None
    categories = safe_get(d, 13) or []
    return {
        "name":           safe_get(d, 11),
        "added_by":       None,
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


def parse_response_file(path: Path) -> list[dict]:
    """Parse a single manually-saved response JSON file."""
    text = path.read_text(encoding="utf-8")
    places = _parse_envelope(text)
    return places


def parse_additional_file(path: Path) -> dict:
    """Parse a manually-saved additionalResponse.json → name-keyed lookup."""
    return _parse_additional_text(path.read_text(encoding="utf-8"))


def parse_har(path: Path) -> tuple[list[dict], dict]:
    """
    Extract places and additional lookup from a HAR file.
    Returns (places, additional_lookup).
    Deduplicates paginated pages by their first place name.
    """
    har = json.loads(path.read_text(encoding="utf-8"))
    entries = har["log"]["entries"]

    all_places = []
    additional_lookup = {}
    seen_page_keys = set()

    for entry in entries:
        url = entry["request"]["url"]
        content = entry["response"]["content"]
        text = _decode_har_body(content)
        if not text:
            continue

        if PAGINATED_URL in url and PAGINATED_MARK in url:
            try:
                places = _parse_envelope(text)
                if not places:
                    continue
                # Deduplicate pages by first place name
                page_key = places[0]["name"]
                if page_key in seen_page_keys:
                    continue
                seen_page_keys.add(page_key)
                all_places.extend(places)
                print(f"  HAR page '{page_key}': {len(places)} places")
            except Exception:
                continue

        elif ADDITIONAL_URL in url:
            try:
                additional_lookup = _parse_additional_text(text)
                print(f"  HAR additional response: {len(additional_lookup)} entries")
            except Exception:
                continue

    return all_places, additional_lookup


def enrich_places(places: list[dict], lookup: dict) -> int:
    """Join additional lookup into places list by name. Returns match count."""
    matched = 0
    for place in places:
        extra = lookup.get(place["name"])
        if extra:
            place["added_by"] = extra["added_by"]
            if extra["note"]:
                place["note"] = extra["note"]
            matched += 1
    return matched


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "name", "added_by", "note", "address", "street", "city_state_zip", "country",
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files", nargs="*", type=Path,
        help="Manually-saved paginated response JSON files",
    )
    parser.add_argument(
        "--additional", type=Path,
        help="Manually-saved additionalResponse.json (contributor names + notes)",
    )
    parser.add_argument(
        "--har", type=Path,
        help="HAR file exported from DevTools (extracts everything automatically)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("."),
        help="Output directory (default: current dir)",
    )
    parser.add_argument(
        "--stem", default="gyms",
        help="Output filename stem (default: gyms)",
    )
    args = parser.parse_args()

    if not args.files and not args.har:
        parser.error("Provide response files, --har, or both.")

    args.out.mkdir(parents=True, exist_ok=True)

    all_places = []
    additional_lookup = {}
    seen_place_ids = set()

    # Manual files
    for path in sorted(args.files):
        places = parse_response_file(path)
        print(f"{path.name}: {len(places)} places")
        all_places.extend(places)

    if args.additional:
        additional_lookup = parse_additional_file(args.additional)

    # HAR
    if args.har:
        print(f"\nReading {args.har.name}:")
        har_places, har_additional = parse_har(args.har)
        # Merge: HAR places not already seen by place_id
        for p in har_places:
            pid = p.get("place_id") or p["name"]
            if pid not in seen_place_ids:
                seen_place_ids.add(pid)
                all_places.append(p)
        # HAR additional only fills gaps
        for name, data in har_additional.items():
            if name not in additional_lookup:
                additional_lookup[name] = data

    # Mark manual places as seen too (for dedup if both modes used)
    for p in all_places:
        pid = p.get("place_id") or p["name"]
        seen_place_ids.add(pid)

    print(f"\nTotal: {len(all_places)} places")

    if additional_lookup:
        matched = enrich_places(all_places, additional_lookup)
        source = args.additional.name if args.additional else args.har.name if args.har else "lookup"
        print(f"Enriched:  {matched}/{len(all_places)} places matched from {source}")

    write_csv(all_places,  args.out / f"{args.stem}.csv")
    write_json(all_places, args.out / f"{args.stem}.json")


if __name__ == "__main__":
    main()
