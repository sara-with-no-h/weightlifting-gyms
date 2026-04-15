# weightlifting-gyms

Export your Google Maps saved list to CSV or JSON. Google doesn't offer a native export, so this script captures the raw API responses from the browser and parses them locally.

## How to export your list

### Step 1 — capture the responses

1. Open **Chrome DevTools** (`Cmd+Option+I`) → **Network** tab → filter by **Fetch/XHR**
2. Navigate to your Google Maps saved list
3. **Scroll slowly to the bottom** — each scroll triggers a new paginated request (~20 places each). Scrolling too fast causes requests to be skipped and places to be missing from the export
4. Sanity check: you should end up with roughly `number of places ÷ 20` response files (e.g. 137 places → 7 files)
5. For each request: right-click → **Copy** → **Copy response** → paste into a file named `response0.json`, `response1.json`, etc.
6. Put all the files in a folder named with today's date, e.g. `2026-04-15/`

### Step 2 — capture the additional response (optional but recommended)

There is a separate request that contains contributor names and fuller notes.
Look for a request with a payload containing `"Weightlifting gyms"` and the list owner's name.
Save it as `additionalResponse.json` in the same folder.

### Step 3 — run the script

```bash
# Without contributor names
python3 scripts/parse-list-response.py 2026-04-13/response*.json --out 2026-04-13

# With contributor names + full notes
python3 scripts/parse-list-response.py 2026-04-13/response*.json \
    --additional 2026-04-13/additionalResponse.json --out 2026-04-13
```

This produces two files in your output folder:

- `gyms.csv` — open in Excel, Google Sheets, etc.
- `gyms.json` — clean JSON array

### Options

```
python3 scripts/parse-list-response.py <files> --out <folder> --stem <name>

  files   one or more response JSON files (supports wildcards)
  --out   output directory (default: current directory)
  --stem  output filename without extension (default: gyms)
```

## Output fields

| Field | Description |
|---|---|
| `name` | Place name |
| `added_by` | Name of the person who added the place to the list |
| `note` | Note on the place (if any) |
| `address` | Full formatted address |
| `street` | Street line only |
| `city_state_zip` | City, state/region, postcode |
| `country` | Country |
| `latitude` / `longitude` | Coordinates |
| `rating` | Star rating (1–5) |
| `review_count` | Number of Google reviews |
| `website` | Place website URL |
| `phone` | Phone number |
| `place_id` | Google Place ID (`ChIJ...`) |
| `categories` | Comma-separated place categories |
| `timezone` | IANA timezone string |

## Diffing two exports

To see what changed between two exports:

```bash
python3 scripts/diff-exports.py 2026-03-01/gyms.json 2026-04-13/gyms.json --out 2026-04-13
```

This writes into the newer folder:
- `diff_2026-03-01_2026-04-13.md` — human-readable summary grouped by contributor
- `diff_2026-03-01_2026-04-13.json` — structured diff data

The diff tracks: places added, places removed, and changes to notes, ratings, website, phone, and address.

## Project structure

```
scripts/
  parse-list-response.py  ← export a saved list to CSV/JSON
  diff-exports.py         ← diff two exports
YYYY-MM-DD/               ← one folder per export session
  response0.json          ← raw responses from DevTools
  response1.json
  ...
  gyms.csv                ← output
  gyms.json               ← output
```
