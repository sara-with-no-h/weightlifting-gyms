# weightlifting-gyms

A toolset for exporting and syncing a personal Google Maps saved list of weightlifting gyms.

## Project structure

```
scripts/
  parse-list-response.py  ← main script: parse raw API responses → CSV/JSON
2026-04-13/               ← example: one folder per export date
  response1-4.json        ← raw API responses captured from Chrome DevTools
  gyms.csv                ← parsed output (63 places)
  gyms.json               ← parsed output (63 places)
```

## Workflows

### 1. Parsing a Google Maps saved list (main workflow)

Google Maps saved lists (e.g. "Weightlifting gyms") are not publicly exportable,
but you can capture the raw XHR responses from the browser and parse them locally.

**Step 1 — capture responses**

1. Open Chrome DevTools → Network tab → filter "Fetch/XHR"
2. Navigate to your Google Maps saved list
3. Scroll to the bottom — each scroll triggers a paginated request
4. For each request: right-click → Copy → Copy response → paste into `responseN.json`

**Step 2 — parse and export**

```bash
python3 scripts/parse-list-response.py 2026-04-13/response*.json --out 2026-04-13
```

This produces `gyms.csv` and `gyms.json` in the output folder.

Organise exports by date: create a new `YYYY-MM-DD/` folder for each session
and pass `--out YYYY-MM-DD` when running the script.


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
