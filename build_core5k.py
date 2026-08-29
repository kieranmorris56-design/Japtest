#!/usr/bin/env python3
"""
Build a "top N Japanese words" Anki deck: dictionary form in kanji, furigana
above it, an English gloss, and a real example sentence with its translation.

Data sources (both openly licensed, attributed on every card):
  * JMdict / jmdict-simplified  - dictionary forms, readings, English glosses.
    (C) Electronic Dictionary Research and Development Group, CC BY-SA 4.0.
  * Tatoeba / Tanaka Corpus     - Japanese-English example sentences, with
    per-word dictionary-form annotations. CC BY 2.0 FR.

Ranking comes from `wordfreq`, whose Japanese frequencies aggregate subtitles,
Wikipedia, news and web text — so the order reflects real usage rather than the
composition of the example corpus. Only words that actually occur in the corpus
are eligible, which guarantees every card has a genuine example sentence.

Particles and auxiliary verbs are excluded: content words only.
"""

import argparse
import collections
import html
import json
import os
import re
import shutil
import sys
import tempfile

try:
    from janome.tokenizer import Tokenizer
    from wordfreq import top_n_list
    from anki.collection import (Collection, ExportAnkiPackageOptions,
                                 DeckIdLimit)
except ImportError as exc:
    sys.exit(f"Missing dependency ({exc.name}). "
             "Run: pip3 install janome wordfreq anki")

from readings import find_override

KANJI_RE = re.compile(r"[一-鿿々〆ヶ]")


def kata_to_hira(t):
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in t)


def has_kanji(t):
    return bool(KANJI_RE.search(t))


# ------------------------------------------------------------------ furigana

def segment(word):
    runs = []
    for ch in word:
        k = bool(KANJI_RE.match(ch))
        if runs and runs[-1][1] == k:
            runs[-1][0] += ch
        else:
            runs.append([ch, k])
    return runs


def furigana(word, reading):
    """Anki ruby notation: 食べる + たべる -> 食[た]べる.

    A space precedes a kanji run that follows kana so each reading attaches to
    its own kanji: 持[も]って 来[く]る, not 持[も]って来[く]る.
    """
    reading = kata_to_hira(reading or "")
    if not reading or not has_kanji(word) or reading == word:
        return word
    runs = segment(word)
    pattern = "".join("(.+?)" if k else re.escape(kata_to_hira(t)) for t, k in runs)
    m = re.fullmatch(pattern, reading)
    if not m:
        return f"{word}[{reading}]"
    out, g, prev_kana = "", 0, False
    for text, kanji_run in runs:
        if kanji_run:
            g += 1
            if out and prev_kana:
                out += " "
            out += f"{text}[{m.group(g)}]"
            prev_kana = False
        else:
            out += text
            prev_kana = True
    return out


# -------------------------------------------------------------------- JMdict

# JMdict part-of-speech codes -> display label. Particles/auxiliaries map to
# None so they are dropped (content words only).
POS_MAP = {
    "n": "noun", "n-adv": "noun", "n-t": "noun", "adv-to": "adverb",
    "pn": "pronoun", "adj-i": "i-adjective", "adj-na": "na-adjective",
    "adj-no": "adjective", "adj-pn": "adjective", "adv": "adverb",
    "conj": "conjunction", "int": "interjection", "exp": "expression",
    "num": "number", "ctr": "counter", "pref": "prefix", "suf": "suffix",
    "vs": "verb (suru)", "vk": "verb", "vz": "verb",
    "prt": None, "aux": None, "aux-v": None, "aux-adj": None, "cop": None,
}


# Kana strings whose frequency in any corpus is overwhelmingly their
# particle/auxiliary use. JMdict also lists rare homograph content words for
# several of them (の "arrow shaft", し "teacher"), and those entries must not
# inherit the particle's frequency. POS filtering cannot catch this: the
# homograph entries are legitimately tagged as nouns.
FUNCTION_WORDS = set("""
は が を に へ と で や か の も ね よ な さ ぞ ぜ わ し ば ん だ ぬ り つ ら
です ます ない なかっ から まで より など ほど ばかり だけ しか こそ でも ても
とか やら かしら のに ので けど けれど けれども ちゃ じゃ って とも たり
だろう でしょう ながら つつ どの まし たら たい てる とく ちゃう
""".split())


def pos_label(codes):
    for c in codes:
        if c.startswith("v") and (c.startswith("v1") or c.startswith("v5")
                                  or c in ("vt", "vi", "vk", "vz")):
            return "verb"
        if c in POS_MAP:
            if POS_MAP[c] is None:
                return None
            return POS_MAP[c]
    return None


POS_PRIORITY = {
    "noun": 0, "verb": 0, "i-adjective": 0, "na-adjective": 0, "pronoun": 0,
    "adverb": 1, "adjective": 1, "conjunction": 1, "interjection": 1,
    "verb (suru)": 1, "expression": 2, "number": 2, "counter": 3,
    "prefix": 4, "suffix": 4,
}


def load_jmdict(path):
    """form-text -> canonical entry {display, reading, meaning, pos}."""
    print("Loading JMdict ...")
    words = json.load(open(path, encoding="utf-8"))["words"]
    index = {}
    for e in words:
        senses = e.get("sense") or []
        if not senses:
            continue

        pos = None
        for s in senses:
            pos = pos_label(s.get("partOfSpeech") or [])
            if pos:
                break
        if not pos:
            continue                       # particle / auxiliary / unknown

        kana = [k for k in e.get("kana", []) if "sk" not in
                [t.lower() for t in k.get("tags", [])]]
        kanji = [k for k in e.get("kanji", []) if "sK" not in k.get("tags", [])]
        if not kana:
            continue

        read = next((k["text"] for k in kana if k.get("common")), kana[0]["text"])
        # "uk" = usually written in kana: show the kana form, as Japanese does.
        usually_kana = any("uk" in (s.get("misc") or []) for s in senses)
        common_kanji = next((k["text"] for k in kanji if k.get("common")), None)
        if usually_kana or not common_kanji:
            display = read
        else:
            display = common_kanji

        glosses = [g["text"] for g in senses[0].get("gloss", [])
                   if g.get("lang") == "eng"][:3]
        if not glosses:
            continue

        rec = {
            "_score": (POS_PRIORITY.get(pos, 2),
                       0 if any(k.get("common") for k in kana + kanji) else 1,
                       -len(senses)),
            "display": display,
            "reading": read,
            "meaning": "; ".join(glosses),
            "pos": pos,
            "common": any(k.get("common") for k in kana + kanji),
        }
        # Kanji forms always map to their entry (the corpus writes 為る for する).
        # Kana forms map ONLY when the word is genuinely written in kana --
        # otherwise the particle の would resolve to the noun 野, whose reading
        # merely happens to be の, and inherit the particle's huge frequency.
        forms = [k["text"] for k in kanji]
        if display == read:
            forms += [k["text"] for k in kana]
        for form in forms:
            prev = index.get(form)
            if prev is None or rec["_score"] < prev["_score"]:
                index[form] = rec
    print(f"  {len(index)} lookup forms")
    return index


# ------------------------------------------------------------------ sentences

def sentence_score(words, rank_of, target, text):
    """Prefer short sentences built from words the learner already knows."""
    n = len(text)
    base = (8 - n) * 5 + 40 if n < 8 else (abs(n - 20) if n <= 34 else 30 + (n - 34) * 2)
    unknown = 0
    for w in words:
        h = w.get("headword")
        if not h or h == target:
            continue
        if rank_of.get(h, 99999) > 6000:
            unknown += 1
    return base + unknown * 6


# ---------------------------------------------------------------------- deck

CSS = """
.card { font-family:"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif;
  font-size:22px; text-align:center; color:#1f2430; background:#fbfbfd; }
.word { font-size:52px; font-weight:600; line-height:1.9; margin-bottom:2px; }
.pos { font-size:13px; color:#8b93a3; letter-spacing:.08em; text-transform:uppercase; }
.meaning { font-size:26px; color:#14532d; margin:14px 0 2px; }
.rank { font-size:13px; color:#a7aebb; margin-top:6px; }
hr { border:none; border-top:1px solid #dfe3ea; margin:18px 0; }
.label { font-size:11px; color:#a7aebb; letter-spacing:.1em; text-transform:uppercase; }
.example { font-size:25px; line-height:2.2; margin-top:8px; }
.example b { color:#b4491f; }
.translation { font-size:18px; color:#5b6472; margin-top:12px; font-style:italic; }
.attrib { font-size:10px; color:#c9cfd9; margin-top:26px; line-height:1.5; }
ruby rt { font-size:.5em; color:#6b7280; font-weight:400; }
"""

FRONT = ('<div class="word">{{furigana:WordFurigana}}</div>'
         '<div class="pos">{{PartOfSpeech}}</div>')

BACK = """<div class="word">{{furigana:WordFurigana}}</div>
<div class="pos">{{PartOfSpeech}}</div>
<div class="meaning">{{Meaning}}</div>
<div class="rank">Frequency rank {{Rank}}</div>
<hr>
<div class="label">Example sentence</div>
<div class="example">{{furigana:ExampleFurigana}}</div>
<div class="translation">{{Translation}}</div>
<div class="attrib">Sentence: Tatoeba / Tanaka Corpus (CC BY 2.0 FR)<br>
Definition: JMdict, EDRDG (CC BY-SA 4.0)</div>
"""


FIELDS = ("WordFurigana", "Word", "Reading", "PartOfSpeech",
          "Meaning", "Rank", "ExampleFurigana", "Translation")


def build(rows, title, out_path):
    """Write the .apkg using Anki's own library, so the package is valid by
    construction.

    genanki produced a legacy schema-11 collection in which notes.sfld is
    declared `integer`; a purely numeric sort field ("00001") therefore hit
    SQLite's type affinity and was stored as an INTEGER rather than TEXT.
    AnkiDroid's backend reads that column as a UTF-8 string and rejected the
    whole file. Letting Anki build and export the collection avoids hand-
    writing the schema at all.
    """
    tmp = tempfile.mkdtemp()
    try:
        col = Collection(os.path.join(tmp, "collection.anki2"))

        mm = col.models
        nt = mm.new("Japanese Core Vocabulary (furigana)")
        for name in FIELDS:
            mm.add_field(nt, mm.new_field(name))
        tpl = mm.new_template("Recognition")
        tpl["qfmt"], tpl["afmt"] = FRONT, BACK
        mm.add_template(nt, tpl)
        nt["css"] = CSS
        mm.add(nt)
        nt = mm.by_name("Japanese Core Vocabulary (furigana)")

        deck_id = col.decks.id(title)

        # Notes are added in rank order, so new cards are introduced most
        # frequent first.
        for r in rows:
            note = col.new_note(nt)
            lo = ((r["rank"] - 1) // 500) * 500
            values = (r["word_furigana"], r["word"], r["reading"], r["pos"],
                      r["meaning"], str(r["rank"]), r["example_furigana"],
                      r["translation"])
            for name, value in zip(FIELDS, values):
                note[name] = value
            note.tags = [f"rank::{lo+1:04d}-{lo+500:04d}",
                         "pos::" + re.sub(r"[^a-z-]", "", r["pos"].replace(" ", "-"))]
            col.add_note(note, deck_id)

        # legacy=True emits the widely-compatible collection.anki2 +
        # collection.anki21 pair that every current AnkiDroid build imports.
        col.export_anki_package(
            out_path=out_path,
            options=ExportAnkiPackageOptions(
                with_scheduling=False, with_deck_configs=False,
                with_media=True, legacy=True),
            limit=DeckIdLimit(deck_id))
        col.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="/home/user/data/jpn-eng-examples.json")
    ap.add_argument("--jmdict", default="/home/user/data/jmdict-eng-3.6.2.json")
    ap.add_argument("--count", type=int, default=5000)
    ap.add_argument("--out", default="japanese_core5000.apkg")
    ap.add_argument("--title", default="Japanese Core 5000")
    args = ap.parse_args()

    jm = load_jmdict(args.jmdict)

    print("Loading example corpus ...")
    corpus = json.load(open(args.corpus, encoding="utf-8"))
    where = collections.defaultdict(list)
    surfaces = collections.defaultdict(set)
    for i, s in enumerate(corpus):
        if not s.get("translation"):
            continue
        for w in s.get("words", []):
            h = w.get("headword")
            if h:
                where[h].append(i)
                surfaces[h].add(w.get("surfaceForm") or h)
    print(f"  {len(corpus)} sentences, {len(where)} headwords")

    print("Ranking by real-world frequency ...")
    # top_n_list returns tokens in descending frequency order, so position IS
    # the rank. It reads wordfreq's table directly and needs no tokeniser,
    # unlike word_frequency() which requires MeCab for Japanese input.
    freq_rank = {w: i for i, w in enumerate(top_n_list("ja", 60000))}
    MISSING = 10 ** 9

    best = {}                       # display form -> [rank, entry, headwords]
    for head in where:
        rec = jm.get(head)
        if not rec:
            continue
        disp = rec["display"]
        # Drop function words, plus any single kana character: genuine
        # single-kana content words do not exist (絵 "picture" is written
        # with kanji), so a bare kana hit is always a particle collision.
        if disp in FUNCTION_WORDS or not rec["common"]:
            continue
        if len(disp) == 1 and not has_kanji(disp):
            continue
        rank = freq_rank.get(disp, MISSING)
        if rank >= MISSING:
            continue
        cur = best.get(disp)
        if cur is None:
            best[disp] = [rank, rec, [head]]
        else:
            cur[0] = min(cur[0], rank)
            cur[2].append(head)

    ordered = sorted(best.items(), key=lambda kv: kv[1][0])[:args.count]
    print(f"  selected {len(ordered)} words")

    rank_of = {}
    for i, (disp, (_, _, heads)) in enumerate(ordered):
        for h in heads:
            rank_of.setdefault(h, i + 1)

    print("Selecting example sentences ...")
    tok = Tokenizer()
    rows = []
    for rank, (disp, (_freq, rec, heads)) in enumerate(ordered, 1):
        cands = []
        for h in heads:
            cands.extend((i, h) for i in where[h][:300])
        if not cands:
            continue
        pick, score = None, None
        for i, h in cands:
            s = corpus[i]
            sc = sentence_score(s.get("words", []), rank_of, h, s["text"])
            if score is None or sc < score:
                pick, score = s, sc

        forms = set()
        for h in heads:
            forms |= surfaces[h]
        rows.append({
            "rank": rank,
            "word": disp,
            "reading": rec["reading"],
            "word_furigana": furigana(disp, rec["reading"]),
            "pos": rec["pos"],
            "meaning": html.escape(rec["meaning"], quote=False),
            "example_furigana": sentence_furigana(pick["text"], tok, forms, disp),
            "example_plain": pick["text"],
            "translation": html.escape(pick["translation"], quote=False),
        })
        if rank % 1000 == 0:
            print(f"  {rank} ...")

    print("Writing deck ...")
    build(rows, args.title, args.out)

    tsv = os.path.splitext(args.out)[0] + "_wordlist.tsv"
    with open(tsv, "w", encoding="utf-8") as fh:
        fh.write("rank\tword\treading\tpart_of_speech\tmeaning\texample\ttranslation\n")
        for r in rows:
            fh.write(f"{r['rank']}\t{r['word']}\t{r['reading']}\t{r['pos']}\t"
                     f"{html.unescape(r['meaning'])}\t{r['example_plain']}\t"
                     f"{html.unescape(r['translation'])}\n")

    print(f"\nCards : {len(rows)}\nDeck  : {args.out}\nList  : {tsv}")


def sentence_furigana(text, tok, target_forms, word):
    """Ruby-annotate a sentence token by token, bolding the target word.

    Irregular counter compounds are resolved before tokenisation: Janome
    splits 九時 into 九 + 時 and reads it きゅうじ instead of くじ, and 一人
    as いちにん instead of ひとり.

    Anki's furigana filter consumes at most one space immediately before a
    ruby group, so a space there is invisible and required -- without it the
    ruby swallows the preceding kana. A space anywhere else would show as a
    visible gap, so one is inserted only where the filter eats it, and never
    before a <b> tag, whose ">" already bounds the group.
    """
    out, i, buf, bolded = "", 0, "", False

    def emit(piece):
        nonlocal out
        if out and "[" in piece and piece[0] != "<" and has_kanji(piece[0]):
            out += " "
        out += piece

    def flush():
        nonlocal buf, bolded
        for t in tok.tokenize(buf):
            surf = t.surface
            if has_kanji(surf) and t.reading and t.reading != "*":
                piece = furigana(surf, kata_to_hira(t.reading))
            else:
                piece = html.escape(surf, quote=False)
            if not bolded and (surf in target_forms or t.base_form == word):
                piece = f"<b>{piece}</b>"
                bolded = True
            emit(piece)
        buf = ""

    while i < len(text):
        key, reading = find_override(text, i)
        if key:
            flush()
            piece = furigana(key, reading)
            if not bolded and key in target_forms:
                piece = f"<b>{piece}</b>"
                bolded = True
            emit(piece)
            i += len(key)
        else:
            buf += text[i]
            i += 1
    flush()
    return out


if __name__ == "__main__":
    main()
