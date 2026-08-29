#!/usr/bin/env python3
"""
Build the JLPT N5-N1 grammar deck as a tab-separated file AnkiDroid can import
on the phone alone (the .apkg path is broken on Android 16 -- see
ankidroid/Anki-Android#21430).

Example sentences are drawn from the Tatoeba / Tanaka Corpus (CC BY 2.0 FR)
wherever a grammar pattern occurs there, so the Japanese is human-written
rather than invented. Where the corpus has no usable instance of a pattern,
the entry's own authored example is used instead, and the build report says
exactly how many cards fall into each bucket.

Furigana appears on the BACK of the card only, as HTML ruby, so it renders in
any notetype without the {{furigana:}} template filter.
"""

import argparse
import collections
import glob
import html
import json
import os
import re
import shutil
import sys
import tempfile

try:
    from janome.tokenizer import Tokenizer
except ImportError:
    sys.exit("Missing dependency. Run: pip3 install janome")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from readings import find_override
from functions import classify

KANJI_RE = re.compile(r"[一-鿿々〆ヶ]")


def kata_to_hira(t):
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in t)


def has_kanji(t):
    return bool(KANJI_RE.search(t))


# ------------------------------------------------------------------ furigana

def _segment(word):
    runs = []
    for ch in word:
        k = bool(KANJI_RE.match(ch))
        if runs and runs[-1][1] == k:
            runs[-1][0] += ch
        else:
            runs.append([ch, k])
    return runs


def ruby(word, reading):
    """<ruby>食<rt>た</rt></ruby>べる -- readings sit over their own kanji.

    Emitted as HTML rather than Anki's 食[た]べる notation so it renders in a
    plain notetype with no template filter.
    """
    reading = kata_to_hira(reading or "")
    if not reading or not has_kanji(word) or reading == word:
        return html.escape(word)
    runs = _segment(word)
    pattern = "".join("(.+?)" if k else re.escape(kata_to_hira(t)) for t, k in runs)
    m = re.fullmatch(pattern, reading)
    if not m:                                    # alignment failed: whole-word ruby
        return f"<ruby>{html.escape(word)}<rt>{html.escape(reading)}</rt></ruby>"
    out, g = "", 0
    for text, kanji_run in runs:
        if kanji_run:
            g += 1
            out += (f"<ruby>{html.escape(text)}"
                    f"<rt>{html.escape(m.group(g))}</rt></ruby>")
        else:
            out += html.escape(text)
    return out


def ruby_sentence(text, tok):
    """Annotate every kanji token in a sentence.

    Irregular counter compounds are matched first, before the tokeniser sees
    them: Janome splits 九時 into 九 + 時 and reads it きゅうじ rather than くじ.
    """
    out, i, buf = [], 0, ""

    def flush():
        if buf:
            for t in tok.tokenize(buf):
                s = t.surface
                if has_kanji(s) and t.reading and t.reading != "*":
                    out.append(ruby(s, kata_to_hira(t.reading)))
                else:
                    out.append(html.escape(s))

    while i < len(text):
        key, reading = find_override(text, i)
        if key:
            flush()
            buf = ""
            out.append(ruby(key, reading))
            i += len(key)
        else:
            buf += text[i]
            i += 1
    flush()
    return "".join(out)


# ------------------------------------------------------------------ corpus

def load_corpus(path):
    print("Loading example corpus ...")
    data = json.load(open(path, encoding="utf-8"))
    rows = [(s["text"], s["translation"],
             [w.get("headword") for w in s.get("words", []) if w.get("headword")])
            for s in data if s.get("translation")]
    print(f"  {len(rows)} sentences with translations")
    return rows


# A search pattern is only trustworthy when it is long and distinctive enough
# that finding it really means the grammar point is present. Bare particles
# match every sentence in the corpus, and short kana runs hit unrelated words:
# たり matches 当たり前, と matches the quotative と. Those points take
# authored examples only.
BARE = set("は が を に へ で と や も の か ね よ さ ぞ わ から まで より".split())

# Sentences that are not usable as study material.
JUNK_RE = re.compile(r"[A-Za-z0-9/=_]{3,}")


def pattern_is_specific(pattern):
    if not pattern or pattern in BARE:
        return False
    literal = re.sub(r"[.*+?{}()\[\]\\|^$]", "", pattern)
    return len(literal) >= 4


def sentence_ok(jp, en):
    """Reject corpus junk and anything too long to read on a phone."""
    if not jp.endswith(("。", "！", "？", "」")):
        return False
    # Only the Japanese side is checked: the corpus junk this catches is Latin
    # text leaking into the Japanese field ("as may be の文法解釈"). An English
    # translation is of course all Latin letters, so testing it here rejected
    # every sentence in the corpus.
    if JUNK_RE.search(jp):
        return False
    if not en.strip():
        return False
    return 8 <= len(jp) <= 44


def pick_examples(pattern, corpus, want, common, exclude_re=None):
    """Authentic sentences containing the pattern, easiest first.

    Only called for specific patterns. Sentences are ranked by how many of
    their words fall outside the common-word set, so an N5 card does not get
    a sentence about 千切り and 白菜.
    """
    if not want or not pattern_is_specific(pattern):
        return []
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        print(f"  ! bad search pattern {pattern!r}: {exc}")
        return []
    ex_rx = re.compile(exclude_re) if exclude_re else None

    hits = []
    for jp, en, words in corpus:
        if not rx.search(jp) or (ex_rx and ex_rx.search(jp)):
            continue
        if not sentence_ok(jp, en):
            continue
        hard = sum(1 for w in words if w not in common)
        hits.append((hard * 4 + abs(len(jp) - 20), jp, en))
    hits.sort(key=lambda h: (h[0], h[1]))

    out = []
    for _, jp, en in hits[:want]:
        out.append({"jp": jp, "en": en})
    return out


# ---------------------------------------------------------------------- card

EX_BLOCK = (
    '<div class="ex">'
    '<div class="jp">{jp}</div>'
    '<div class="en">{en}</div>'
    '</div>'
)


def clean(t):
    """Tabs and newlines delimit the import file and must not appear inside a field."""
    return t.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def build_rows(points, corpus, tok, per_card, common):
    rows, stats = [], {"corpus": 0, "authored": 0, "mixed": 0, "none": 0}
    for p in points:
        # Authored examples come first: they are written to demonstrate this
        # exact point. The corpus can then add one attested sentence, but only
        # when the pattern is specific enough for a match to mean anything.
        authored = p.get("examples", [])
        room = max(0, per_card - len(authored))
        found = pick_examples(p.get("search", ""), corpus, room,
                              common, p.get("exclude"))
        used = list(authored) + list(found)
        n_auth = len(authored)

        if not used:
            stats["none"] += 1
        elif n_auth and found:
            stats["mixed"] += 1
        elif n_auth:
            stats["authored"] += 1
        else:
            stats["corpus"] += 1
        p["_corpus_attested"] = bool(found)

        ex_html = "".join(
            EX_BLOCK.format(jp=ruby_sentence(e["jp"], tok),
                            en=html.escape(e["en"]))
            for e in used
        )

        point_plain = p["point"]
        point_back = (ruby(point_plain, p["reading"]) if p.get("reading")
                      else html.escape(point_plain))

        rows.append({
            "level": p["level"],
            "point": clean(html.escape(point_plain)),
            "point_ruby": clean(point_back),
            "meaning": clean(html.escape(p["meaning"])),
            "formation": clean(html.escape(p["formation"])),
            "notes": clean(html.escape(p.get("notes", ""))),
            "contrast": clean(html.escape(p.get("contrast", ""))),
            "examples": clean(ex_html),
            "fn": classify(p),
            "n_corpus": len(found),
            "n_authored": n_auth,
        })
    return rows, stats


LEVEL_ORDER = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}

FIELDS = ("Point", "PointRuby", "Level", "Meaning", "Formation", "Notes",
          "Contrast", "Examples")

APKG_CSS = """
.card { font-family:"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif;
  font-size:20px; color:#1f2430; background:#fbfbfd; text-align:center;
  padding:16px; }
.lvl { display:inline-block; font-size:11px; letter-spacing:.12em;
  color:#6b7280; border:1px solid #d8dde6; border-radius:99px;
  padding:2px 10px; margin-bottom:14px; }
.pt { font-size:38px; font-weight:600; line-height:1.9; margin-bottom:10px; }
.mean { font-size:22px; color:#14532d; margin-bottom:14px; }
.form { font-size:15px; color:#475569; background:#f1f4f9; border-radius:8px;
  padding:8px 12px; display:inline-block; }
.note { font-size:15px; color:#5b6472; margin-top:14px; line-height:1.7; }
.vs { font-size:14px; color:#8a5a2b; background:#fdf6ec; border-radius:8px;
  padding:8px 12px; margin-top:12px; line-height:1.6; }
.exlabel { font-size:11px; letter-spacing:.1em; text-transform:uppercase;
  color:#a7aebb; margin:22px 0 6px; }
.ex { border-top:1px solid #e6eaf0; padding:12px 0; }
.ex .jp { font-size:21px; line-height:2.2; }
.ex .en { font-size:15px; color:#5b6472; font-style:italic; margin-top:4px; }
ruby rt { font-size:.5em; color:#6b7280; font-weight:400; }
"""

# Front carries no furigana, by request: {{Point}} is the bare form and
# {{PointRuby}} (back only) is the annotated one.
APKG_FRONT = ('<div class="lvl">{{Level}}</div>'
              '<div class="pt">{{Point}}</div>')

APKG_BACK = """<div class="lvl">{{Level}}</div>
<div class="pt">{{PointRuby}}</div>
<div class="mean">{{Meaning}}</div>
<div class="form">{{Formation}}</div>
{{#Notes}}<div class="note">{{Notes}}</div>{{/Notes}}
{{#Contrast}}<div class="vs">{{Contrast}}</div>{{/Contrast}}
<div class="exlabel">Examples</div>
{{Examples}}
"""


def build_apkg(rows, title, out_path):
    """Write an .apkg through Anki's own library, so it is valid by
    construction. Notes are added in N5-to-N1 order, so new cards are
    introduced easiest first."""
    try:
        from anki.collection import (Collection, ExportAnkiPackageOptions,
                                     DeckIdLimit)
    except ImportError:
        sys.exit("Missing dependency for --apkg. Run: pip3 install anki")

    tmp = tempfile.mkdtemp()
    try:
        col = Collection(os.path.join(tmp, "collection.anki2"))
        mm = col.models
        nt = mm.new("JLPT Grammar")
        for name in FIELDS:
            mm.add_field(nt, mm.new_field(name))
        tpl = mm.new_template("Recognition")
        tpl["qfmt"], tpl["afmt"] = APKG_FRONT, APKG_BACK
        mm.add_template(nt, tpl)
        nt["css"] = APKG_CSS
        mm.add(nt)
        nt = mm.by_name("JLPT Grammar")

        deck_id = col.decks.id(title)
        for r in rows:
            note = col.new_note(nt)
            values = (r["point"], r["point_ruby"], r["level"], r["meaning"],
                      r["formation"], r["notes"], r["contrast"], r["examples"])
            for name, value in zip(FIELDS, values):
                note[name] = value
            note.tags = ([f"jlpt::{r['level']}"] +
                         [f"fn::{t}" for t in r["fn"]])
            col.add_note(note, deck_id)

        # legacy=True emits the widely compatible collection.anki2 +
        # collection.anki21 pair that current AnkiDroid and desktop both read.
        col.export_anki_package(
            out_path=out_path,
            options=ExportAnkiPackageOptions(
                with_scheduling=False, with_deck_configs=False,
                with_media=True, legacy=True),
            limit=DeckIdLimit(deck_id))
        col.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--corpus", default="/home/user/data/jpn-eng-examples.json")
    ap.add_argument("--out", default="jlpt_grammar.txt")
    ap.add_argument("--examples-per-card", type=int, default=4)
    ap.add_argument("--apkg", help="also write an .apkg for desktop Anki")
    ap.add_argument("--title", default="JLPT Grammar N5-N1")
    args = ap.parse_args()

    points, seen = [], {}
    for path in sorted(glob.glob(os.path.join(args.data, "*.json"))):
        for p in json.load(open(path, encoding="utf-8")):
            key = p["point"]
            if key in seen:
                print(f"  ! duplicate grammar point {key!r} "
                      f"({seen[key]} and {p['level']})")
                continue
            seen[key] = p["level"]
            points.append(p)
    points.sort(key=lambda p: (LEVEL_ORDER.get(p["level"], 9), p["point"]))
    print(f"{len(points)} grammar points loaded")

    corpus = load_corpus(args.corpus)
    # The 6000 most frequent headwords: used to keep example sentences at a
    # readable difficulty rather than merely a convenient length.
    freq = collections.Counter()
    for _jp, _en, words in corpus:
        freq.update(words)
    common = {w for w, _ in freq.most_common(6000)}
    tok = Tokenizer()

    print("Matching example sentences ...")
    rows, stats = build_rows(points, corpus, tok, args.examples_per_card, common)

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#separator:tab\n")
        fh.write("#html:true\n")
        fh.write("#columns:Point\tPointRuby\tLevel\tMeaning\tFormation\tNotes\t"
                 "Contrast\tExamples\tTags\n")
        fh.write("#tags column:9\n")
        for r in rows:
            fh.write("\t".join([
                r["point"], r["point_ruby"], r["level"], r["meaning"],
                r["formation"], r["notes"], r["contrast"], r["examples"],
                " ".join([f"jlpt::{r['level']}"] +
                         [f"fn::{t}" for t in r["fn"]]),
            ]) + "\n")

    by_level = {}
    for r in rows:
        by_level[r["level"]] = by_level.get(r["level"], 0) + 1

    if args.apkg:
        build_apkg(rows, args.title, args.apkg)
        print(f"Deck  : {args.apkg} "
              f"({os.path.getsize(args.apkg)/1024:.0f} KB)")

    print(f"\nWrote {len(rows)} cards to {args.out} "
          f"({os.path.getsize(args.out)/1024:.0f} KB)")
    print("  per level:", ", ".join(
        f"{lv} {by_level.get(lv,0)}" for lv in ("N5", "N4", "N3", "N2", "N1")))
    print(f"  examples all from corpus : {stats['corpus']}")
    print(f"  corpus + authored        : {stats['mixed']}")
    print(f"  authored only            : {stats['authored']}")
    print(f"  NO examples              : {stats['none']}")
    if stats["none"]:
        print("\ncards with no example sentence:")
        for r in rows:
            if not r["examples"]:
                print("   ", r["level"], html.unescape(r["point"]))


if __name__ == "__main__":
    main()
