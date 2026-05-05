# weightlifting-gyms

Tools for backing up, diffing, and restoring a Google Maps saved list. Google doesn't offer native export or restore, so these scripts capture and replay the browser's own API requests.

## How to export your list

There are two ways to capture the data. HAR mode is easier.

### Option A — HAR file (recommended)

1. Open **Chrome DevTools** (`Cmd+Option+I`) → **Network** tab → filter by **Fetch/XHR**
2. Navigate to your Google Maps saved list
3. **Scroll slowly to the bottom** — each scroll triggers a paginated request. Scrolling too fast skips requests and loses places
4. Right-click anywhere in the request list → **Save all as HAR with content**
5. Put the `.har` file in a folder named with today's date, e.g. `2026-05-05/`

```bash
python3 scripts/parse-list-response.py --har 2026-05-05/capture.har --out 2026-05-05
```

### Option B — manual copy-paste

1. Open **Chrome DevTools** (`Cmd+Option+I`) → **Network** tab → filter by **Fetch/XHR**
2. Navigate to your Google Maps saved list
3. **Scroll slowly to the bottom** — each scroll triggers a new paginated request (~20 places each). Scrolling too fast causes requests to be skipped
4. Sanity check: you should end up with roughly `number of places ÷ 20` response files (e.g. 138 places → 7 files)
5. For each paginated request: right-click → **Copy** → **Copy response** → paste into `response0.json`, `response1.json`, etc.
6. Also save the `getlist` request as `additionalResponse.json` (contains contributor names + fuller notes)
7. Put all files in a folder named with today's date

```bash
python3 scripts/parse-list-response.py 2026-05-05/response*.json \
    --additional 2026-05-05/additionalResponse.json --out 2026-05-05
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

## Restoring the list from backup

If the list gets vandalized or accidentally deleted, you can restore all places from a `gyms.json` backup. The script uses the same internal API that Google Maps calls when you manually save a place — no browser automation, just direct HTTP requests.

**Dependency:** `pip install requests`

### How it works

The script replays the exact HTTP request Google Maps sends when you click "Save". It needs three ingredients:

- **Session + auth tokens** — short-lived, extracted from a HAR of one manual save
- **Cookies** — your Google login session (long-lived, copied from DevTools)
- **Place ID pairs** — internal numeric IDs Google uses for each place, extracted from your export HAR

### Step 1 — install the dependency

```bash
pip install requests
```

### Step 2 — capture fresh tokens

Do this once at the start of each restore session (tokens expire after a few hours):

1. Open Google Maps in your browser → navigate to the target saved list
2. Open **DevTools** (`Cmd+Option+I`) → **Network** tab → filter by **Fetch/XHR**
3. **Manually save one place** to the list (click Save → select the list — it can already be in the list)
4. Find the `createitem` request that appears → right-click it → **Save all as HAR with content**
   → save as `import-automation/tokens.har`
5. With the same `createitem` request selected → **Headers** tab → scroll to **Request Headers**
   → find **Cookie** → copy the entire value
   → paste into `import-automation/cookies.txt`

> `cookies.txt` and `tokens.har` are in `.gitignore` — never commit them, they're auth credentials.

### Step 3 — run the restore script

```bash
python3 scripts/restore-list.py 2026-05-05/gyms.json \
    --from-har import-automation/tokens.har \
    --cookies import-automation/cookies.txt \
    --export-har 2026-05-05/2026-05-05.har
```

| Argument | What it does |
|---|---|
| `gyms.json` | The backup to restore from |
| `--from-har` | HAR from Step 2 — extracts list ID, session token, auth token |
| `--cookies` | File from Step 2 — your Google login session |
| `--export-har` | The HAR used to generate that `gyms.json` — provides internal place IDs |

The script prints each place as it's saved and writes progress to `restore_progress.json` after every request.

**Resume after interruption:**
```bash
... same command + --resume
```

**Dry run** (prints what would be sent, no requests):
```bash
... same command + --dry-run
```

### If tokens expire mid-run

The script stops immediately on a 401/403 and tells you. Grab fresh tokens (Step 2 again) and re-run with `--resume` — already-saved places are skipped.

## Project structure

```
scripts/
  parse-list-response.py  ← export a saved list to CSV/JSON
  diff-exports.py         ← diff two exports
  restore-list.py         ← restore a list from a gyms.json backup
YYYY-MM-DD/               ← one folder per export session
  YYYY-MM-DD.har          ← HAR file from DevTools (input for parse + restore)
  gyms.csv                ← parsed output
  gyms.json               ← parsed output
  restore_progress.json   ← written by restore-list.py to track progress
import-automation/
  tokens.har              ← HAR from one manual save (tokens for restore) — gitignored
  cookies.txt             ← Google auth cookies (for restore) — gitignored
```
