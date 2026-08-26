#!/usr/bin/env python3
"""
Produce a tab-separated import file with separate plain-text fields for
speech, so Anki's {{tts}} tag can read the word and the example sentence
aloud using the device's own Japanese voice. No audio files are involved.

Why separate fields: Anki strips HTML before handing text to TTS, so a ruby
annotation like <ruby>東京<rt>とうきょう</rt></ruby> flattens to "東京とうきょう"
and is spoken twice — once as kanji, once as the reading. The display fields
keep their ruby; the audio fields carry clean text.

Fields written (in column order):
    1 Word           kanji with HTML ruby furigana, for display
    2 WordAudio      the same word as plain text, for {{tts}}
    3 Meaning        English gloss plus a small part-of-speech / rank line
    4 Sentence       example sentence with ruby, target word in bold
    5 SentenceAudio  the same sentence as plain text, for {{tts}}
    6 Translation    English translation of the sentence
    7 (tags)         rank:: and pos:: tags

Usage:
    python3 make_tts_import.py --apkg japanese_core5000.apkg \
        --out japanese_core5000_tts.txt
"""

import argparse
import html
import os
import re
import sqlite3
import tempfile
import zipfile

RUBY_RE = re.compile(r" ?([^ \[\]<>]+)\[([^\[\]]+)\]")
TAG_RE = re.compile(r"<[^>]+>")


def to_html_ruby(text):
    return RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", text)


def to_plain(text):
    """Recover speakable text: drop the readings, then any markup."""
    text = RUBY_RE.sub(r"\1", text)      # 食[た]べる -> 食べる
    text = TAG_RE.sub("", text)          # strip <b> etc.
    return html.unescape(text).strip()


def clean(text):
    """Tabs and newlines delimit the file, so they must not appear in a field."""
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


MEANING = ('{gloss}'
           '<div style="font-size:12px;color:#a7aebb;margin-top:4px">'
           '{pos} &middot; frequency rank {rank}</div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apkg", default="japanese_core5000.apkg")
    ap.add_argument("--out", default="japanese_core5000_tts.txt")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp()
    zipfile.ZipFile(args.apkg).extractall(tmp)
    db = next(os.path.join(tmp, n) for n in ("collection.anki21", "collection.anki2")
              if os.path.exists(os.path.join(tmp, n)))

    rows = []
    for flds, tags in sqlite3.connect(db).execute("select flds, tags from notes"):
        f = flds.split("\x1f")
        word_ruby, word_plain, _reading, pos, meaning, rank, ex_ruby, trans = f[:8]
        rows.append((
            int(rank),
            clean(to_html_ruby(word_ruby)),
            clean(word_plain),
            clean(MEANING.format(gloss=meaning, pos=html.escape(pos), rank=rank)),
            clean(to_html_ruby(ex_ruby)),
            clean(to_plain(ex_ruby)),
            clean(trans),
            clean(tags),
        ))
    rows.sort(key=lambda r: r[0])

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#separator:tab\n")
        fh.write("#html:true\n")
        fh.write("#columns:Word\tWordAudio\tMeaning\tSentence\tSentenceAudio\t"
                 "Translation\tTags\n")
        fh.write("#tags column:7\n")
        for r in rows:
            fh.write("\t".join(r[1:]) + "\n")

    print(f"Wrote {len(rows)} notes to {args.out}")
    print(f"Size: {os.path.getsize(args.out) / 1024:.0f} KB")
    print("\nSample audio fields (what TTS will speak):")
    for r in rows[:2] + rows[119:120]:
        print(f"   word: {r[2]!r}")
        print(f"   sent: {r[5]!r}")


if __name__ == "__main__":
    main()
