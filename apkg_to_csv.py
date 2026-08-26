#!/usr/bin/env python3
"""
Convert the generated .apkg into a plain-text file Anki/AnkiDroid can import
directly, as a workaround for AnkiDroid issue #21430 ("stream did not contain
valid UTF-8"), where the app fails to hand a valid .apkg to its Rust core.

Two differences from the .apkg make this robust:

  * Two columns only (Front / Back), so it imports into the stock Basic
    notetype with no field mapping.
  * Furigana is emitted as real HTML ruby (<ruby>食<rt>た</rt></ruby>) rather
    than Anki's 食[た]べる notation, which only renders through the
    {{furigana:}} template filter that Basic does not have.

Usage:
    python3 apkg_to_csv.py --apkg japanese_core5000.apkg \
        --out japanese_core5000.txt
"""

import argparse
import html
import os
import re
import sqlite3
import tempfile
import zipfile

# " 食[た]" -> ruby. The character class excludes <, > and [ so HTML tags and
# adjacent groups are never swallowed. The optional leading space is the
# delimiter Anki's own filter consumes, so it is dropped here too.
RUBY_RE = re.compile(r" ?([^ \[\]<>]+)\[([^\[\]]+)\]")


def to_html_ruby(text):
    return RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", text)


FRONT = ('<div style="font-size:44px;line-height:2.0">{word}</div>'
         '<div style="font-size:13px;color:#8b93a3;letter-spacing:.06em">{pos}</div>')

BACK = (
    '<div style="font-size:24px;color:#14532d;margin-bottom:6px">{meaning}</div>'
    '<div style="font-size:12px;color:#a7aebb">frequency rank {rank}</div>'
    '<hr>'
    '<div style="font-size:22px;line-height:2.2">{example}</div>'
    '<div style="font-size:16px;color:#5b6472;font-style:italic;margin-top:10px">'
    '{translation}</div>'
    '<div style="font-size:10px;color:#c9cfd9;margin-top:18px">'
    'Sentence: Tatoeba / Tanaka Corpus (CC BY 2.0 FR) &middot; '
    'Definition: JMdict, EDRDG (CC BY-SA 4.0)</div>'
)


def clean(text):
    """Fields must not contain tabs or newlines: they delimit the file."""
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apkg", default="japanese_core5000.apkg")
    ap.add_argument("--out", default="japanese_core5000.txt")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp()
    zipfile.ZipFile(args.apkg).extractall(tmp)
    # Prefer the newer collection when the package carries both.
    db = next(os.path.join(tmp, n) for n in
              ("collection.anki21", "collection.anki2")
              if os.path.exists(os.path.join(tmp, n)))

    con = sqlite3.connect(db)
    rows = []
    for (flds, tags) in con.execute("select flds, tags from notes"):
        f = flds.split("\x1f")
        word, _, _, pos, meaning, rank, example, translation = f[:8]
        rows.append((
            int(rank),
            clean(FRONT.format(word=to_html_ruby(word), pos=html.escape(pos))),
            clean(BACK.format(meaning=meaning, rank=rank,
                              example=to_html_ruby(example),
                              translation=translation)),
            clean(tags),
        ))
    rows.sort(key=lambda r: r[0])

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        # Anki reads these directives to configure the import automatically.
        fh.write("#separator:tab\n")
        fh.write("#html:true\n")
        fh.write("#columns:Front\tBack\tTags\n")
        fh.write("#tags column:3\n")
        for _, front, back, tags in rows:
            fh.write(f"{front}\t{back}\t{tags}\n")

    print(f"Wrote {len(rows)} notes to {args.out}")
    print(f"Size: {os.path.getsize(args.out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
