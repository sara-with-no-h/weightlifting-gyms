#!/usr/bin/env python3
"""
Restore a Google Maps saved list from a gyms.json backup using direct HTTP calls.

HOW TO GET FRESH TOKENS (do this each session):
  1. Open Google Maps in your browser and navigate to the list
  2. Open DevTools → Network tab → filter by Fetch/XHR
  3. Manually save ONE place to the list (click Save → pick the list)
  4. Right-click that createitem request → Save all as HAR with content
  5. Copy your cookie header: click the createitem request → Headers →
     scroll to Request Headers → copy the Cookie value
  6. Save the HAR as, e.g., import-automation/tokens.har
  7. Save the cookie string into a file, e.g., import-automation/cookies.txt

HOW TO RUN:
  python3 scripts/restore-list.py 2026-05-05/gyms.json \\
      --from-har import-automation/tokens.har \\
      --cookies import-automation/cookies.txt \\
      --export-har 2026-05-05/2026-05-05.har

  Resume after interruption:
    ... same command + --resume

  Dry run (print URLs, don't send requests):
    ... same command + --dry-run

OPTIONS:
  --from-har        HAR captured while manually saving one place (extracts
                    list-id, session-token, auth-token automatically)
  --cookies         Path to file containing the Cookie header value, OR
                    pass the value directly as a string
  --export-har      HAR from your list export (extracts place ID pairs).
                    Falls back to --additional if not provided.
  --additional      additionalResponse.json file (alternative source for
                    place ID pairs)
  --list-id         List ID (only needed if not using --from-har)
  --session-token   Session token (only needed if not using --from-har)
  --auth-token      Auth token  (only needed if not using --from-har)
  --resume          Skip places already recorded in the progress file
  --workers         Concurrent requests (default: 5)
  --delay           Seconds between request submissions (default: 0)
  --dry-run         Print URLs without sending requests
  --progress        Path to progress file (default: restore_progress.json
                    next to the input gyms.json)
"""

import argparse
import base64
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus, quote

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

_thread_local = threading.local()


CREATEITEM_URL = "https://www.google.com/maps/preview/entitylist/createitem"
ADDITIONAL_URL = "maps/preview/entitylist/getlist"
CREATEITEM_PATH = "entitylist/createitem"


# ---------------------------------------------------------------------------
# HAR helpers
# ---------------------------------------------------------------------------

def _decode_har_body(content: dict) -> str:
    text = content.get("text", "")
    if content.get("encoding") == "base64" and text:
        text = base64.b64decode(text).decode("utf-8", errors="replace")
    return text


def extract_tokens_from_har(har_path: Path) -> dict:
    """
    Find the createitem request in a HAR and extract:
      list_id, session_token, auth_token
    """
    har = json.loads(har_path.read_text())
    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        if CREATEITEM_PATH not in url:
            continue
        # Parse the pb parameter
        from urllib.parse import urlparse, parse_qs, unquote
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        pb = params.get("pb", [""])[0]
        # pb is already URL-decoded by parse_qs

        tokens = {}

        # list_id: !1s<ID>!
        import re
        m = re.search(r"!1s([^!]+)!2e1", pb)
        if m:
            tokens["list_id"] = m.group(1)

        # session_token: !1s<TOKEN>!7e81
        m = re.search(r"!1s([^!]+)!7e81", pb)
        if m:
            tokens["session_token"] = m.group(1)

        # auth_token: !4s<TOKEN> (at end, no trailing !)
        m = re.search(r"!4s(.+)$", pb)
        if m:
            tokens["auth_token"] = unquote(m.group(1))

        if tokens:
            print(f"Extracted from HAR: list_id={tokens.get('list_id')}, "
                  f"session_token={tokens.get('session_token')}, "
                  f"auth_token={tokens.get('auth_token', '')[:30]}...")
            return tokens

    raise ValueError(f"No createitem request found in {har_path}")


def extract_id_pairs_from_har(har_path: Path) -> dict:
    """
    Extract place name → (id1, id2, lat, lng) from the getlist response in a HAR.
    Returns dict keyed by place name.
    """
    har = json.loads(har_path.read_text())
    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        if ADDITIONAL_URL not in url:
            continue
        text = _decode_har_body(entry["response"]["content"])
        if not text:
            continue
        try:
            pairs = _parse_id_pairs(text)
            if pairs:
                print(f"Extracted {len(pairs)} place ID pairs from HAR")
                return pairs
        except Exception as e:
            print(f"Warning: failed to parse getlist response: {e}")
            continue
    return {}


def extract_id_pairs_from_file(path: Path) -> dict:
    """Parse a standalone additionalResponse.json file."""
    text = path.read_text(encoding="utf-8")
    pairs = _parse_id_pairs(text)
    print(f"Loaded {len(pairs)} place ID pairs from {path.name}")
    return pairs


def _parse_id_pairs(text: str) -> dict:
    """
    Parse a getlist response body → { name: {id1, id2, lat, lng} }
    """
    idx = text.index("[[[")
    data, _ = json.JSONDecoder().raw_decode(text[idx:])
    entries = data[0][8]
    result = {}
    for e in entries:
        name = e[2] if len(e) > 2 else None
        if not name:
            continue
        coords = e[1][5] if len(e) > 1 and len(e[1]) > 5 else None
        pairs  = e[1][6] if len(e) > 1 and len(e[1]) > 6 else None
        if not pairs or len(pairs) < 2:
            continue
        lat = coords[2] if coords and len(coords) > 2 else None
        lng = coords[3] if coords and len(coords) > 3 else None
        result[name] = {"id1": pairs[0], "id2": pairs[1], "lat": lat, "lng": lng}
    return result


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------

def build_pb(list_id: str, lat: float, lng: float,
             id1: str, id2: str, name: str,
             session_token: str, auth_token: str) -> str:
    name_enc = quote_plus(name)
    auth_enc = quote(auth_token, safe="")
    return (
        f"!1m4!1s{list_id}!2e1!3m1!1e1"
        f"!2m14!2m6!6m2!3d{lat}!4d{lng}!7m2!1y{id1}!2y{id2}!3s{name_enc}"
        f"!9m5!1m1!1e1!2m2!1y{id1}!2y{id2}"
        f"!3m3!1s{session_token}!7e81!28e2"
        f"!4s{auth_enc}"
    )


def build_url(list_id, lat, lng, id1, id2, name, session_token, auth_token) -> str:
    pb = build_pb(list_id, lat, lng, id1, id2, name, session_token, auth_token)
    return f"{CREATEITEM_URL}?authuser=0&hl=en&gl=pt&pb={pb}"


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def load_progress(path: Path) -> tuple:
    if path.exists():
        data = json.loads(path.read_text())
        return set(data.get("saved", [])), data.get("failed", [])
    return set(), []


def save_progress(path: Path, saved: set, failed: list):
    path.write_text(json.dumps({"saved": list(saved), "failed": failed}, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input",          type=Path, help="Path to gyms.json backup")
    parser.add_argument("--from-har",     type=Path, help="HAR captured while saving one place (extracts tokens)")
    parser.add_argument("--cookies",      required=True, help="Cookie header value or path to file containing it")
    parser.add_argument("--export-har",   type=Path, help="Export HAR for extracting place ID pairs")
    parser.add_argument("--additional",   type=Path, help="additionalResponse.json for place ID pairs")
    parser.add_argument("--list-id",      help="List ID (if not using --from-har)")
    parser.add_argument("--session-token",help="Session token (if not using --from-har)")
    parser.add_argument("--auth-token",   help="Auth token (if not using --from-har)")
    parser.add_argument("--resume",       action="store_true")
    parser.add_argument("--workers",      type=int, default=5)
    parser.add_argument("--delay",        type=float, default=0)
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--progress",     type=Path)
    args = parser.parse_args()

    # ---- Load tokens ----
    if args.from_har:
        tokens = extract_tokens_from_har(args.from_har)
        list_id       = tokens.get("list_id")       or args.list_id
        session_token = tokens.get("session_token") or args.session_token
        auth_token    = tokens.get("auth_token")    or args.auth_token
    else:
        list_id       = args.list_id
        session_token = args.session_token
        auth_token    = args.auth_token

    if not all([list_id, session_token, auth_token]):
        parser.error("list-id, session-token, and auth-token are required "
                     "(pass --from-har or set them manually)")

    # ---- Load cookies ----
    cookies_raw = args.cookies
    cookies_path = Path(cookies_raw)
    if cookies_path.exists():
        cookies_raw = cookies_path.read_text().strip()

    # ---- Load place ID pairs ----
    id_pairs: dict = {}
    if args.export_har:
        id_pairs = extract_id_pairs_from_har(args.export_har)
    if not id_pairs and args.additional:
        id_pairs = extract_id_pairs_from_file(args.additional)
    if not id_pairs:
        parser.error("Provide --export-har or --additional to supply place ID pairs")

    # ---- Load places ----
    places = json.loads(args.input.read_text())
    progress_path = args.progress or args.input.parent / "restore_progress.json"
    saved_ids, failed = load_progress(progress_path) if args.resume else (set(), [])

    # Match each place to its ID pair (by name, then by lat/lng proximity)
    def find_pair(place):
        name = place["name"]
        if name in id_pairs:
            return id_pairs[name]
        # Fallback: match by lat/lng (within 0.0001 deg ≈ 10m)
        lat = place.get("latitude")
        lng = place.get("longitude")
        if lat is None or lng is None:
            return None
        for pair in id_pairs.values():
            if pair["lat"] is None:
                continue
            if abs(pair["lat"] - lat) < 0.0001 and abs(pair["lng"] - lng) < 0.0001:
                return pair
        return None

    skipped_no_pair = [p for p in places if not find_pair(p)]
    if skipped_no_pair:
        print(f"Warning: {len(skipped_no_pair)} places have no ID pair and will be skipped:")
        for p in skipped_no_pair:
            print(f"  - {p['name']}")
        print()

    to_restore = [p for p in places
                  if find_pair(p) and p.get("place_id") not in saved_ids]
    already_done = len(places) - len(to_restore) - len(skipped_no_pair)

    print(f"Loaded {len(places)} places from {args.input.name}")
    if already_done:
        print(f"Skipping {already_done} already saved")
    print(f"To restore: {len(to_restore)} places → list '{list_id}' "
          f"(workers={args.workers})")
    if args.dry_run:
        print("DRY RUN — no requests will be sent")
    print()

    # ---- Shared state (guarded by lock) ----
    lock      = threading.Lock()
    stop_flag = threading.Event()
    completed = [0]  # list so inner function can mutate it

    def get_session() -> requests.Session:
        """One session per thread — requests.Session is not thread-safe."""
        if not hasattr(_thread_local, "session"):
            s = requests.Session()
            s.headers.update({
                "Cookie":     cookies_raw,
                "Referer":    "https://www.google.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            })
            _thread_local.session = s
        return _thread_local.session

    def restore_one(place):
        if stop_flag.is_set():
            return

        name     = place["name"]
        place_id = place.get("place_id", name)
        pair     = find_pair(place)
        lat = pair["lat"] if pair["lat"] is not None else place.get("latitude")
        lng = pair["lng"] if pair["lng"] is not None else place.get("longitude")
        id1, id2 = pair["id1"], pair["id2"]
        url = build_url(list_id, lat, lng, id1, id2, name, session_token, auth_token)

        if args.dry_run:
            with lock:
                completed[0] += 1
                print(f"[{completed[0]}/{len(to_restore)}] {name} DRY")
                saved_ids.add(place_id)
            return

        try:
            resp = get_session().get(url, timeout=15)
            with lock:
                completed[0] += 1
                n = f"[{completed[0]}/{len(to_restore)}]"
                if resp.status_code == 200:
                    print(f"{n} {name} ✓")
                    saved_ids.add(place_id)
                    save_progress(progress_path, saved_ids, failed)
                elif resp.status_code in (401, 403):
                    print(f"{n} {name} ✗ {resp.status_code} — token expired, stopping")
                    failed.append({"place_id": place_id, "name": name,
                                   "reason": str(resp.status_code)})
                    stop_flag.set()
                    save_progress(progress_path, saved_ids, failed)
                else:
                    print(f"{n} {name} ✗ HTTP {resp.status_code}: {resp.text[:60]}")
                    failed.append({"place_id": place_id, "name": name,
                                   "reason": f"http_{resp.status_code}"})
                    save_progress(progress_path, saved_ids, failed)
        except Exception as e:
            with lock:
                completed[0] += 1
                print(f"[{completed[0]}/{len(to_restore)}] {name} ✗ {e}")
                failed.append({"place_id": place_id, "name": name, "reason": str(e)})
                save_progress(progress_path, saved_ids, failed)

    # ---- Submit all work ----
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for place in to_restore:
            if stop_flag.is_set():
                break
            futures.append(executor.submit(restore_one, place))
            if args.delay:
                time.sleep(args.delay)
        for future in as_completed(futures):
            future.result()  # re-raise any unexpected exceptions

    if stop_flag.is_set():
        print("\nStopped early due to auth error. Re-run with --resume after refreshing tokens.")

    print(f"\n--- Done ---")
    print(f"Saved:  {len(saved_ids)}")
    print(f"Failed: {len(failed)}")
    if failed:
        print("\nFailed places:")
        for f in failed:
            print(f"  - {f['name']} ({f['reason']})")
    print(f"Progress: {progress_path}")


if __name__ == "__main__":
    main()
