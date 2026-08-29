#!/usr/bin/env python3
"""
Check the grammar data before it is ever built into a deck.

Authoring hundreds of entries by hand invites two kinds of silent damage:
stray non-Japanese text landing inside a Japanese sentence, and placeholder
rows left behind. Neither is visible when skimming a large JSON file, and both
would reach the learner as a wrong card, so they are caught mechanically here.

Exits non-zero if anything is wrong, so a build cannot run on bad data.
"""

import glob
import json
import os
import re
import sys

# Scripts that have no business appearing in a Japanese sentence.
FOREIGN = re.compile(
    r"[Ѐ-ӿ"      # Cyrillic
    r"가-힯"       # Hangul syllables
    r"ᄀ-ᇿ"       # Hangul jamo
    r"؀-ۿ"       # Arabic
    r"฀-๿]"      # Thai
)

# A run of Latin letters. Japanese sentences do use the odd acronym, but a
# lower-case English word inside a Japanese sentence is authoring damage.
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")

JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

REQUIRED = ("level", "point", "meaning", "formation")
LEVELS = {"N5", "N4", "N3", "N2", "N1"}


def check_entry(e, where, errors):
    point = e.get("point", "<no point>")

    for key in REQUIRED:
        if not e.get(key):
            errors.append(f"{where}: {point}: missing or empty '{key}'")

    if e.get("level") not in LEVELS:
        errors.append(f"{where}: {point}: bad level {e.get('level')!r}")

    if not JAPANESE.search(point):
        errors.append(f"{where}: {point}: point contains no Japanese")

    # Placeholder rows left in during authoring.
    if e.get("formation") == "-" or e.get("meaning") == "placeholder":
        errors.append(f"{where}: {point}: placeholder entry")

    for field in ("point", "meaning", "formation", "notes", "contrast"):
        val = e.get(field, "")
        if FOREIGN.search(val):
            errors.append(f"{where}: {point}: foreign script in '{field}': {val[:40]!r}")

    examples = e.get("examples", [])
    if not examples:
        errors.append(f"{where}: {point}: no example sentences")

    for i, ex in enumerate(examples):
        jp, en = ex.get("jp", ""), ex.get("en", "")
        tag = f"{where}: {point}: example {i+1}"
        if not jp or not en:
            errors.append(f"{tag}: empty jp or en")
            continue
        if FOREIGN.search(jp):
            errors.append(f"{tag}: foreign script in jp: {jp[:40]!r}")
        if LATIN_WORD.search(jp):
            errors.append(f"{tag}: latin word in jp: {jp[:40]!r}")
        if not JAPANESE.search(jp):
            errors.append(f"{tag}: jp has no Japanese: {jp[:40]!r}")
        if not jp.endswith(("。", "！", "？", "」")):
            errors.append(f"{tag}: jp does not end with sentence punctuation: {jp[:40]!r}")
        if JAPANESE.search(en):
            errors.append(f"{tag}: Japanese text in the English translation: {en[:40]!r}")


def main():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    errors, seen, total = [], {}, 0

    for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        where = os.path.basename(path)
        try:
            entries = json.load(open(path, encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{where}: invalid JSON: {exc}")
            continue
        for e in entries:
            total += 1
            check_entry(e, where, errors)
            key = e.get("point")
            if key in seen:
                errors.append(f"{where}: duplicate point {key!r} (also in {seen[key]})")
            else:
                seen[key] = where

    print(f"checked {total} entries across {len(glob.glob(os.path.join(data_dir,'*.json')))} files")
    if errors:
        print(f"\n{len(errors)} PROBLEM(S):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("all clean")


if __name__ == "__main__":
    main()
