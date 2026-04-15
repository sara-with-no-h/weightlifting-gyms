#!/usr/bin/env python3
"""
Diff two gyms.json exports and summarise what changed, grouped by contributor.

HOW TO RUN:
  python3 scripts/diff-exports.py 2026-03-01/gyms.json 2026-04-13/gyms.json

  # Custom output location
  python3 scripts/diff-exports.py old/gyms.json new/gyms.json --out 2026-04-13

OUTPUT:
  <out>/diff_<old-date>_<new-date>.md    human-readable summary
  <out>/diff_<old-date>_<new-date>.json  structured diff data
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


# Fields that represent a deliberate user action — grouped by contributor in the diff
USER_FIELDS = ["note"]
# Fields that change automatically (Google data) — shown in a separate section
AUTO_FIELDS = ["rating", "review_count", "website", "phone", "address"]
TRACKED_FIELDS = USER_FIELDS + AUTO_FIELDS


def load(path: Path) -> dict:
    """Load gyms.json → dict keyed by place_id (fallback: name)."""
    places = json.loads(path.read_text(encoding="utf-8"))
    return {p.get("place_id") or p["name"]: p for p in places}


def diff(old: dict, new: dict) -> dict:
    old_keys = set(old)
    new_keys = set(new)

    added   = [new[k] for k in sorted(new_keys - old_keys, key=lambda k: new[k].get("name", ""))]
    removed = [old[k] for k in sorted(old_keys - new_keys, key=lambda k: old[k].get("name", ""))]

    changed = []
    for k in old_keys & new_keys:
        o, n = old[k], new[k]
        user_changes = {}
        auto_changes = {}
        for f in USER_FIELDS:
            ov, nv = o.get(f), n.get(f)
            if ov != nv:
                user_changes[f] = {"from": ov, "to": nv}
        for f in AUTO_FIELDS:
            ov, nv = o.get(f), n.get(f)
            if ov != nv:
                auto_changes[f] = {"from": ov, "to": nv}
        if user_changes or auto_changes:
            changed.append({"place": n, "user_changes": user_changes, "auto_changes": auto_changes})

    changed.sort(key=lambda x: x["place"].get("name", ""))
    return {"added": added, "removed": removed, "changed": changed}


def group_by(places: list, key: str, fallback: str = "Unknown") -> dict:
    groups: dict[str, list] = {}
    for p in places:
        k = p.get(key) or fallback
        groups.setdefault(k, []).append(p)
    return dict(sorted(groups.items()))


def star(rating) -> str:
    return f"⭐ {rating}" if rating else ""


def fmt_place(p: dict) -> str:
    parts = [f"**{p.get('name', '?')}**"]
    loc = ", ".join(filter(None, [p.get("city_state_zip"), p.get("country")]))
    if loc:
        parts.append(f"— {loc}")
    if p.get("rating"):
        parts.append(star(p["rating"]))
    return " ".join(parts)


def build_markdown(result: dict, old_path: Path, new_path: Path) -> str:
    old_label = old_path.parent.name
    new_label = new_path.parent.name

    lines = [
        f"# Gyms list diff: {old_label} → {new_label}",
        f"",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**{len(result['added'])} added · {len(result['removed'])} removed · "
        f"{len([e for e in result['changed'] if e['user_changes']])} edited · "
        f"{len([e for e in result['changed'] if e['auto_changes']])} Google data updates**",
        "",
    ]

    # --- Added ---
    lines.append(f"## Added ({len(result['added'])})")
    if result["added"]:
        for contributor, places in group_by(result["added"], "added_by").items():
            lines.append(f"\n### {contributor} ({len(places)})")
            for p in places:
                lines.append(f"- {fmt_place(p)}")
                if p.get("note"):
                    lines.append(f"  > {p['note']}")
    else:
        lines.append("\n_No new places._")

    # --- Removed ---
    lines.append(f"\n## Removed ({len(result['removed'])})")
    if result["removed"]:
        for contributor, places in group_by(result["removed"], "added_by").items():
            lines.append(f"\n### {contributor} ({len(places)})")
            for p in places:
                lines.append(f"- {fmt_place(p)}")
    else:
        lines.append("\n_No places removed._")

    # --- User-driven changes (note, added_by) ---
    user_changed = [e for e in result["changed"] if e["user_changes"]]
    lines.append(f"\n## Edited ({len(user_changed)})")
    if user_changed:
        by_contributor: dict[str, list] = {}
        for entry in user_changed:
            contributor = entry["place"].get("added_by") or "Unknown"
            by_contributor.setdefault(contributor, []).append(entry)
        for contributor in sorted(by_contributor):
            entries = by_contributor[contributor]
            lines.append(f"\n### {contributor} ({len(entries)})")
            for entry in entries:
                lines.append(f"\n#### {entry['place'].get('name', '?')}")
                for field, change in entry["user_changes"].items():
                    old_val = change["from"] or "_empty_"
                    new_val = change["to"] or "_empty_"
                    lines.append(f"- **{field}:** {old_val} → {new_val}")
    else:
        lines.append("\n_No notes or contributors edited._")

    # --- Auto changes (rating, review_count, etc.) ---
    auto_changed = [e for e in result["changed"] if e["auto_changes"]]
    lines.append(f"\n## Google data updates ({len(auto_changed)})")
    if auto_changed:
        for entry in auto_changed:
            lines.append(f"\n#### {entry['place'].get('name', '?')}")
            for field, change in entry["auto_changes"].items():
                old_val = change["from"] if change["from"] is not None else "_empty_"
                new_val = change["to"] if change["to"] is not None else "_empty_"
                lines.append(f"- **{field}:** {old_val} → {new_val}")
    else:
        lines.append("\n_No Google data changes._")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old", type=Path, help="Older gyms.json")
    parser.add_argument("new", type=Path, help="Newer gyms.json")
    parser.add_argument("--out", type=Path, help="Output directory (default: parent dir of newer file)")
    args = parser.parse_args()

    out_dir = args.out or args.new.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    old_label = args.old.parent.name
    new_label = args.new.parent.name
    stem = f"diff_{old_label}_{new_label}"

    old = load(args.old)
    new = load(args.new)

    print(f"Loaded {len(old)} places from {args.old}")
    print(f"Loaded {len(new)} places from {args.new}")

    result = diff(old, new)
    print(f"\n{len(result['added'])} added, {len(result['removed'])} removed, {len(result['changed'])} changed")

    md_path   = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"

    md_path.write_text(build_markdown(result, args.old, args.new), encoding="utf-8")
    print(f"\nSaved MD   → {md_path}")

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved JSON → {json_path}")


if __name__ == "__main__":
    main()
