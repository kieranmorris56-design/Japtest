#!/usr/bin/env python3
"""
Build a frequency-ranked Anki deck from a Japanese transcript.

Pipeline:
  1. Read the transcript (.txt, .vtt or .srt) and normalise it to plain text.
  2. Split into sentences.
  3. Tokenise with Janome (MeCab/IPADIC), taking each token's *dictionary form*
     so conjugated verbs/adjectives collapse onto their lemma
     (e.g. 食べました / 食べて / 食べない  ->  食べる).
  4. Deduplicate: one entry per dictionary form.
  5. Rank by number of occurrences, highest first.
  6. Attach an example sentence taken from the transcript itself.
  7. Write out deck.apkg (importable into Anki) plus a TSV for review.

Usage:
    python3 build_deck.py --transcript transcript.txt \
        --out japanese_deck.apkg --title "Japanese Video Vocabulary"
"""

import argparse
import csv
import html
import os
import random
import re
import sys
from collections import Counter, defaultdict

try:
    from janome.tokenizer import Tokenizer
except ImportError:
    sys.exit("Missing dependency. Run: pip3 install janome genanki")

try:
    import genanki
except ImportError:
    sys.exit("Missing dependency. Run: pip3 install janome genanki")


# --------------------------------------------------------------------------
# Transcript loading
# --------------------------------------------------------------------------

TIMESTAMP_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?([.,]\d{1,3})?\s*-->")
CUE_INDEX_RE = re.compile(r"^\d+$")
TAG_RE = re.compile(r"<[^>]+>")


def load_transcript(path):
    """Read .txt/.vtt/.srt and return plain text with cue metadata stripped."""
    with open(path, encoding="utf-8-sig") as fh:
        raw_lines = fh.read().splitlines()

    lines = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("Kind:", "Language:", "NOTE ", "STYLE")):
            continue
        if TIMESTAMP_RE.match(line) or CUE_INDEX_RE.match(line):
            continue
        line = TAG_RE.sub("", line)          # strip <c>, <00:00:01.000> karaoke tags
        line = html.unescape(line).strip()
        if line:
            lines.append(line)

    # YouTube auto-captions repeat the previous line as a rolling window.
    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return "\n".join(deduped)


SENT_SPLIT_RE = re.compile(r"(?<=[。．！？!?…])\s*|\n+")


def split_sentences(text):
    """Split Japanese text into sentences on 。！？ and newlines."""
    parts = [p.strip() for p in SENT_SPLIT_RE.split(text) if p and p.strip()]

    # Captions often have no punctuation at all; fall back to merging short
    # fragments so example sentences are not single words.
    merged = []
    buf = ""
    for part in parts:
        if len(part) < 6 and not part[-1:] in "。．！？!?…":
            buf = (buf + " " + part).strip() if buf else part
            if len(buf) >= 12:
                merged.append(buf)
                buf = ""
        else:
            if buf:
                merged.append((buf + " " + part).strip())
                buf = ""
            else:
                merged.append(part)
    if buf:
        merged.append(buf)
    return merged


# --------------------------------------------------------------------------
# Tokenising / lemmatising
# --------------------------------------------------------------------------

# Parts of speech that carry no standalone dictionary meaning worth a card.
SKIP_POS = {"記号", "フィラー", "その他"}

# Function words: kept by default, dropped with --content-words-only.
FUNCTION_POS = {"助詞", "助動詞"}

POS_EN = {
    "名詞": "noun",
    "動詞": "verb",
    "形容詞": "i-adjective",
    "副詞": "adverb",
    "連体詞": "adnominal",
    "接続詞": "conjunction",
    "感動詞": "interjection",
    "助詞": "particle",
    "助動詞": "auxiliary verb",
    "接頭詞": "prefix",
    "記号": "symbol",
    "フィラー": "filler",
    "その他": "other",
}

JAPANESE_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿々ー]")


def kata_to_hira(text):
    out = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:       # katakana block -> hiragana
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def is_wanted(token, content_words_only):
    pos_parts = token.part_of_speech.split(",")
    major = pos_parts[0]
    sub = pos_parts[1] if len(pos_parts) > 1 else ""

    if major in SKIP_POS:
        return False
    if content_words_only and major in FUNCTION_POS:
        return False
    if sub in {"数", "接尾", "非自立"}:        # bare numbers, suffixes, bound forms
        return False

    lemma = dictionary_form(token)
    if not lemma or not JAPANESE_RE.search(lemma):
        return False
    if len(lemma) == 1 and major == "名詞" and lemma in "々ヶヵ":
        return False
    return True


def dictionary_form(token):
    """Janome's base_form is the dictionary form; '*' means it is uninflected."""
    base = token.base_form
    if not base or base == "*":
        base = token.surface
    return base


def lemma_reading(lemma, tokenizer, cache):
    """Reading of the *dictionary* form.

    token.reading is the reading of the inflected surface (行き -> いき), so for
    a lemma we re-tokenise the lemma itself to get 行く -> いく.
    """
    if lemma in cache:
        return cache[lemma]
    parts = []
    for t in tokenizer.tokenize(lemma):
        r = t.reading
        parts.append(kata_to_hira(r) if r and r != "*" else t.surface)
    reading = "".join(parts)
    if reading == lemma:      # kana-only word: no separate reading to show
        reading = ""
    cache[lemma] = reading
    return reading


def analyse(sentences, content_words_only):
    tokenizer = Tokenizer()
    counts = Counter()
    pos_of = {}
    reading_of = {}
    reading_cache = {}
    occurrences = defaultdict(list)   # lemma -> [(sentence index, surface), ...]
    sentence_readings = []

    for idx, sentence in enumerate(sentences):
        tokens = list(tokenizer.tokenize(sentence))

        reading = "".join(
            kata_to_hira(t.reading) if t.reading and t.reading != "*" else t.surface
            for t in tokens
        )
        sentence_readings.append(reading)

        for token in tokens:
            if not is_wanted(token, content_words_only):
                continue
            lemma = dictionary_form(token)
            counts[lemma] += 1
            occurrences[lemma].append((idx, token.surface))
            if lemma not in pos_of:
                pos_of[lemma] = token.part_of_speech.split(",")[0]
                reading_of[lemma] = lemma_reading(lemma, tokenizer, reading_cache)

    return counts, pos_of, reading_of, occurrences, sentence_readings


# --------------------------------------------------------------------------
# Example-sentence selection
# --------------------------------------------------------------------------

def pick_example(lemma, occ, sentences):
    """Prefer a sentence of comfortable study length that contains the word.

    Returns (sentence_index, sentence, surface_form_as_it_appeared).
    """
    candidates = [(i, sentences[i], surface) for i, surface in occ]

    def score(item):
        _, sent, _ = item
        length = len(sent)
        if 10 <= length <= 45:
            return (0, abs(length - 24))
        if length < 10:
            return (1, 10 - length)
        return (2, length - 45)

    candidates.sort(key=score)
    return candidates[0]


def highlight(sentence, lemma, surface):
    """Bold the word as it actually appears (行き for the lemma 行く)."""
    safe = html.escape(sentence)
    for form in (surface, lemma):
        if form and form in sentence:
            esc = html.escape(form)
            return safe.replace(esc, f"<b>{esc}</b>", 1)
    return safe


# --------------------------------------------------------------------------
# Anki deck
# --------------------------------------------------------------------------

CSS = """
.card {
  font-family: "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif;
  font-size: 22px;
  text-align: center;
  color: #1f2430;
  background: #fbfbfd;
}
.word { font-size: 46px; font-weight: 600; margin-bottom: 6px; }
.reading { font-size: 22px; color: #6b7280; }
.pos { font-size: 15px; color: #8b93a3; letter-spacing: .04em; text-transform: uppercase; }
.freq { font-size: 14px; color: #9aa2b1; margin-top: 10px; }
hr { border: none; border-top: 1px solid #dfe3ea; margin: 16px 0; }
.example { font-size: 24px; line-height: 1.7; margin-top: 4px; }
.example b { color: #b4491f; }
.example-reading { font-size: 17px; color: #7b8494; margin-top: 6px; line-height: 1.6; }
.label { font-size: 12px; color: #a7aebb; letter-spacing: .08em; text-transform: uppercase; }
"""

FRONT = """
<div class="word">{{Word}}</div>
<div class="pos">{{PartOfSpeech}}</div>
"""

BACK = """
<div class="word">{{Word}}</div>
<div class="reading">{{Reading}}</div>
<div class="pos">{{PartOfSpeech}}</div>
<div class="freq">Rank {{Rank}} &middot; {{Frequency}}&times; in the video</div>
<hr>
<div class="label">Example from the video</div>
<div class="example">{{Example}}</div>
<div class="example-reading">{{ExampleReading}}</div>
"""


def build_deck(rows, deck_title, out_path):
    model = genanki.Model(
        1607392913,
        "Japanese Video Vocabulary",
        fields=[
            {"name": "Word"},
            {"name": "Reading"},
            {"name": "PartOfSpeech"},
            {"name": "Frequency"},
            {"name": "Rank"},
            {"name": "Example"},
            {"name": "ExampleReading"},
        ],
        templates=[{"name": "Recognition", "qfmt": FRONT, "afmt": BACK}],
        css=CSS,
    )

    deck = genanki.Deck(random.Random(deck_title).randrange(1 << 30, 1 << 31), deck_title)

    for row in rows:
        if row["frequency"] >= 5:
            band = "freq::high"
        elif row["frequency"] >= 2:
            band = "freq::medium"
        else:
            band = "freq::once"
        deck.add_note(
            genanki.Note(
                model=model,
                fields=[
                    row["word"],
                    row["reading"],
                    row["pos_en"],
                    str(row["frequency"]),
                    str(row["rank"]),
                    row["example_html"],
                    row["example_reading"],
                ],
                tags=[band, "pos::" + row["pos_en"].replace(" ", "-")],
                sort_field=str(row["rank"]).zfill(5),
            )
        )

    genanki.Package(deck).write_to_file(out_path)


def write_tsv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["rank", "word", "reading", "part_of_speech",
                         "frequency", "example_sentence"])
        for row in rows:
            writer.writerow([row["rank"], row["word"], row["reading"],
                             row["pos_en"], row["frequency"], row["example_plain"]])


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", required=True, help="transcript .txt/.vtt/.srt")
    ap.add_argument("--out", default="japanese_deck.apkg", help="output .apkg path")
    ap.add_argument("--title", default="Japanese Video Vocabulary", help="deck name")
    ap.add_argument("--content-words-only", action="store_true",
                    help="drop particles and auxiliary verbs")
    ap.add_argument("--min-frequency", type=int, default=1,
                    help="only include words appearing at least this many times")
    args = ap.parse_args()

    text = load_transcript(args.transcript)
    if not text.strip():
        sys.exit(f"No usable text found in {args.transcript}")

    sentences = split_sentences(text)
    counts, pos_of, reading_of, occurrences, sent_readings = analyse(
        sentences, args.content_words_only
    )

    if not counts:
        sys.exit("No Japanese vocabulary found — is the transcript actually Japanese?")

    # Rank: frequency desc, then word length desc, then the word itself (stable).
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))

    rows = []
    rank = 0
    for lemma, count in ordered:
        if count < args.min_frequency:
            continue
        rank += 1
        idx, sentence, surface = pick_example(lemma, occurrences[lemma], sentences)
        rows.append({
            "rank": rank,
            "word": lemma,
            "reading": reading_of.get(lemma, ""),
            "pos_en": POS_EN.get(pos_of[lemma], pos_of[lemma]),
            "frequency": count,
            "example_plain": sentence,
            "example_html": highlight(sentence, lemma, surface),
            "example_reading": sent_readings[idx],
        })

    build_deck(rows, args.title, args.out)

    tsv_path = os.path.splitext(args.out)[0] + "_wordlist.tsv"
    write_tsv(rows, tsv_path)

    total_tokens = sum(counts.values())
    print(f"Sentences            : {len(sentences)}")
    print(f"Word instances       : {total_tokens}")
    print(f"Unique dictionary forms: {len(counts)}")
    print(f"Cards written        : {len(rows)}")
    print(f"Deck                 : {args.out}")
    print(f"Word list            : {tsv_path}")
    print()
    print("Top 15 by usage:")
    for row in rows[:15]:
        print(f"  {row['rank']:>3}. {row['word']:<10} {row['reading']:<12} "
              f"{row['frequency']:>3}x  {row['pos_en']}")


if __name__ == "__main__":
    main()
