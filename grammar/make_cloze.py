#!/usr/bin/env python3
"""
Build production cards: the example sentence with the grammar blanked out.

The recognition deck asks you to turn 〜ざるを得ない into "have no choice but to".
That is the easy direction, and passing it does not mean you could produce the
pattern yourself. These cards run the other way — you are given the sentence
with a gap and the English, and must supply the grammar:

    雨のため、中止 ____ 。          ->   せざるを得ない
    "have no choice but to cancel"

Only authored examples are used, since those were written to sit at the card's
own level. Locating the pattern inside the sentence is done with the entry's
own search expression first, then by matching the point itself; anything that
cannot be located confidently is skipped and reported rather than guessed at,
because a card blanking the wrong span teaches the wrong thing.

Front carries no furigana, matching the recognition deck; the back has it.
Output imports into Anki's stock Basic note type with no setup.
"""

import argparse
import glob
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_grammar import ruby_sentence, clean          # noqa: E402
from functions import classify                          # noqa: E402
from janome.tokenizer import Tokenizer                  # noqa: E402

BLANK = '<span style="color:#b4491f;font-weight:600">［ ？ ］</span>'

S_Q = "font-size:23px;line-height:2.0;margin-bottom:14px"
S_HINT = "font-size:16px;color:#5b6472;font-style:italic"
S_ANS = "font-size:32px;font-weight:600;color:#b4491f;margin-bottom:6px"
S_LVL = ("display:inline-block;font-size:11px;letter-spacing:.12em;"
         "color:#6b7280;border:1px solid #d8dde6;border-radius:99px;"
         "padding:2px 10px;margin-bottom:12px")
S_FULL = "font-size:21px;line-height:2.2;margin-top:16px"
S_EN = "font-size:15px;color:#5b6472;font-style:italic;margin-top:6px"
S_FORM = ("font-size:14px;color:#475569;background:#f1f4f9;border-radius:8px;"
          "padding:7px 11px;display:inline-block;margin-top:14px")


def strip_point(point):
    """〜ざるを得ない -> ざるを得ない; drop the tilde and any gloss in brackets."""
    p = re.sub(r"\s*\([^)]*\)", "", point)
    return p.replace("〜", "").strip()


def locate(sentence, entry):
    """(start, end) of the grammar inside the sentence, or None.

    Tried in order of how much a match tells us: the entry's own search
    expression, then the full point, then progressively shorter tails of it.
    A tail below three characters is not attempted -- ば or と would match
    almost anywhere and blank an unrelated span.
    """
    search = entry.get("search", "")
    if search:
        try:
            m = re.search(search, sentence)
            if m and m.end() - m.start() >= 2:
                return m.span()
        except re.error:
            pass

    core = strip_point(entry["point"])
    if not core:
        return None

    if core in sentence:
        i = sentence.index(core)
        return (i, i + len(core))

    # 〜なければならない appears as 飲まなければなりません: match the longest tail
    # of the point that is still specific enough to be meaningful.
    for cut in range(1, len(core) - 2):
        tail = core[cut:]
        if len(tail) < 3:
            break
        if tail in sentence:
            i = sentence.index(tail)
            return (i, i + len(tail))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"))
    ap.add_argument("--out", default="jlpt_grammar_cloze.txt")
    args = ap.parse_args()

    entries = []
    for p in sorted(glob.glob(os.path.join(args.data, "*.json"))):
        entries.extend(json.load(open(p, encoding="utf-8")))

    tok = Tokenizer()
    rows, skipped = [], []

    for e in entries:
        examples = e.get("examples", [])
        made = False
        for ex in examples:
            span = locate(ex["jp"], e)
            if not span:
                continue
            start, end = span
            answer = ex["jp"][start:end]
            gapped = (html.escape(ex["jp"][:start]) + BLANK +
                      html.escape(ex["jp"][end:]))

            front = (f'<div style="{S_Q}">{gapped}</div>'
                     f'<div style="{S_HINT}">{html.escape(ex["en"])}</div>')
            back = (f'<div style="{S_LVL}">{e["level"]}</div>'
                    f'<div style="{S_ANS}">{html.escape(answer)}</div>'
                    f'<div style="{S_FORM}">{html.escape(e["formation"])}</div>'
                    f'<div style="{S_FULL}">{ruby_sentence(ex["jp"], tok)}</div>'
                    f'<div style="{S_EN}">{html.escape(ex["en"])}</div>')

            tags = ["cloze", f"jlpt::{e['level']}"] + \
                   [f"fn::{t}" for t in classify(e)]
            rows.append((clean(front), clean(back), " ".join(tags)))
            made = True
            break                       # one production card per point
        if not made:
            skipped.append(f"{e['level']} {e['point']}")

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#separator:tab\n")
        fh.write("#html:true\n")
        fh.write("#columns:Front\tBack\tTags\n")
        fh.write("#tags column:3\n")
        for front, back, tags in rows:
            fh.write(f"{front}\t{back}\t{tags}\n")

    total = len(entries)
    print(f"Wrote {len(rows)} cloze cards to {args.out} "
          f"({os.path.getsize(args.out)/1024:.0f} KB)")
    print(f"  located the grammar in {len(rows)}/{total} points "
          f"({100*len(rows)//total}%)")
    if skipped:
        print(f"  {len(skipped)} skipped (pattern not locatable in its example):")
        for s in skipped[:20]:
            print("   ", s)
        if len(skipped) > 20:
            print(f"    ... and {len(skipped)-20} more")


if __name__ == "__main__":
    main()
