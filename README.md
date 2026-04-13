# weightlifting-gyms

Export your Google Maps saved list to CSV or JSON. Google doesn't offer a native export, so this script captures the raw API responses from the browser and parses them locally.

## How to export your list

### Step 1 — capture the responses

1. Open **Chrome DevTools** (`Cmd+Option+I`) → **Network** tab → filter by **Fetch/XHR**
2. Navigate to your Google Maps saved list
3. **Scroll slowly to the bottom** — each scroll triggers a new paginated request (~20 places each)
4. For each new request that appears: right-click → **Copy** → **Copy response** → paste into a file named `response0.json`, `response1.json`, etc.
5. Put all the files in a folder named with today's date, e.g. `2026-04-13/`

### Step 2 — run the script

```bash
python3 scripts/parse-list-response.py 2026-04-13/response*.json --out 2026-04-13
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

## Project structure

```
scripts/
  parse-list-response.py  ← the script
YYYY-MM-DD/               ← one folder per export session
  response0.json          ← raw responses from DevTools
  response1.json
  ...
  gyms.csv                ← output
  gyms.json               ← output
```
