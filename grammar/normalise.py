#!/usr/bin/env python3
"""
Merge grammar points that appear at more than one JLPT level.

The same construction is legitimately listed at different levels by different
sources (〜得る turns up as both N3 and N2), and authoring level by level
produces genuine duplicates. Two copies of one point would mean two cards
teaching the same thing, so each point is reduced to a single entry:

  * keep whichever copy carries the most explanation and examples, and
  * file it at the earliest level that teaches it, since that is when the
    learner first needs it.

Run after editing any data file; validate.py then confirms the result.
"""

import glob
import json
import os

ORDER = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}


def richness(e):
    return (len(e.get("notes", "")) + len(e.get("contrast", "")) +
            sum(len(x.get("jp", "")) + len(x.get("en", ""))
                for x in e.get("examples", [])))


def main():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    files = {p: json.load(open(p, encoding="utf-8"))
             for p in sorted(glob.glob(os.path.join(data_dir, "*.json")))}

    occurrences = {}
    for path, entries in files.items():
        for e in entries:
            occurrences.setdefault(e["point"], []).append(e)

    drop, merged = set(), 0
    for point, occ in occurrences.items():
        if len(occ) < 2:
            continue
        keep = max(occ, key=richness)
        keep["level"] = min((e["level"] for e in occ), key=lambda l: ORDER[l])
        for e in occ:
            if e is not keep:
                drop.add(id(e))
        merged += 1
        print(f"  {point}: {len(occ)} copies -> kept richest at {keep['level']}")

    for path, entries in files.items():
        kept = [e for e in entries if id(e) not in drop]
        kept.sort(key=lambda e: e["point"])
        json.dump(kept, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)
        print(f"{os.path.basename(path)}: {len(kept)} entries")

    print(f"\nmerged {merged} duplicated point(s)")


if __name__ == "__main__":
    main()
