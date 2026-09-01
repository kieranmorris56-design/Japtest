#!/usr/bin/env python3
"""
Build the Core Japanese vocabulary deck.

The previous builder chose an example sentence by looking for the word's
characters in the text. That is not the same as the sentence using the word:
上 taught as うえ ("above") was illustrated by 職業上 where it reads じょう, and
345 cards had an example in which the word never appeared as a word at all.
Together, 8% of the deck was wrong.

Here the whole corpus is tokenised once and indexed by (dictionary form,
reading). A sentence is only eligible for a card when the tokeniser actually
finds that word, with that reading, in it. Words with no qualifying sentence
are dropped and the next word by frequency takes the slot, so every card in
the finished deck has an example that genuinely demonstrates it.

Furigana appears on the back only. Output is a two-column file that imports
into Anki's stock Basic note type with no setup, plus an .apkg.

Data (both openly licensed, attributed on every card):
  * JMdict / jmdict-simplified - dictionary forms, readings, English glosses.
    (C) Electronic Dictionary Research and Development Group, CC BY-SA 4.0.
  * Tatoeba / Tanaka Corpus - example sentences. CC BY 2.0 FR.
Ranking comes from wordfreq (MIT).
"""

import argparse
import collections
import html
import json
import os
import pickle
import re
import shutil
import sys
import tempfile

try:
    from janome.tokenizer import Tokenizer
    from wordfreq import top_n_list
except ImportError as exc:
    sys.exit(f"Missing dependency ({exc.name}). "
             "Run: pip3 install janome wordfreq anki")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from readings import find_override                       # noqa: E402

KANJI_RE = re.compile(r"[一-鿿々〆ヶ]")
JAPANESE_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿々ー]")
LATIN_RUN = re.compile(r"[A-Za-z0-9/=_]{3,}")
FOREIGN = re.compile(r"[Ѐ-ӿ가-힯ᄀ-ᇿ؀-ۿ฀-๿]")


def hira(t):
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
                   for c in (t or ""))


def has_kanji(t):
    return bool(KANJI_RE.search(t))


# ------------------------------------------------------------------ furigana

def _runs(word):
    out = []
    for ch in word:
        k = bool(KANJI_RE.match(ch))
        if out and out[-1][1] == k:
            out[-1][0] += ch
        else:
            out.append([ch, k])
    return out


def ruby(word, reading):
    """<ruby>食<rt>た</rt></ruby>べる - each reading over its own kanji."""
    reading = hira(reading)
    if not reading or not has_kanji(word) or reading == word:
        return html.escape(word)
    runs = _runs(word)
    pattern = "".join("(.+?)" if k else re.escape(hira(t)) for t, k in runs)
    m = re.fullmatch(pattern, reading)
    if not m:
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


def ruby_sentence(text, tok, target=None):
    """Annotate a sentence, bolding the target word where it occurs.

    Counter compounds are resolved before tokenising: a tokeniser splits 九時
    into 九 + 時 and reads it きゅうじ rather than くじ.
    """
    out, i, buf = [], 0, ""
    bolded = [False]

    def emit(piece, is_target=False):
        if is_target and not bolded[0]:
            piece = f'<b style="color:#b4491f">{piece}</b>'
            bolded[0] = True
        out.append(piece)

    def flush():
        nonlocal buf
        for t in tok.tokenize(buf):
            s = t.surface
            piece = (ruby(s, hira(t.reading))
                     if has_kanji(s) and t.reading and t.reading != "*"
                     else html.escape(s))
            emit(piece, target is not None and t.base_form == target)
        buf = ""

    while i < len(text):
        key, reading = find_override(text, i)
        if key:
            flush()
            emit(ruby(key, reading), key == target)
            i += len(key)
        else:
            buf += text[i]
            i += 1
    flush()
    return "".join(out)


# JMdict's part of speech -> the tokeniser's major categories that may
# legitimately realise it in a sentence. A card's example must use the word in
# a compatible role, or the "example" is a different word that merely looks the
# same.
POS_COMPATIBLE = {
    "noun": {"名詞"}, "pronoun": {"名詞"}, "na-adjective": {"名詞", "形容動詞"},
    "counter": {"名詞"}, "number": {"名詞"},
    "verb": {"動詞", "名詞"},            # 名詞 covers the する-noun pattern
    "i-adjective": {"形容詞"},
    "adverb": {"副詞", "名詞"},
    "adjective": {"連体詞", "名詞", "形容詞"},
    "conjunction": {"接続詞"},
    "interjection": {"感動詞"},
}


# -------------------------------------------------------------------- JMdict

POS_MAP = {
    "n": "noun", "n-adv": "noun", "n-t": "noun", "pn": "pronoun",
    "adj-i": "i-adjective", "adj-na": "na-adjective", "adj-no": "adjective",
    "adj-pn": "adjective", "adv": "adverb", "adv-to": "adverb",
    "conj": "conjunction", "int": "interjection",
    "num": "number", "ctr": "counter", "pref": None, "suf": None,
    "exp": None,
    "vs": "verb", "vk": "verb", "vz": "verb",
    "prt": None, "aux": None, "aux-v": None, "aux-adj": None, "cop": None,
}

# Senses that should never be the headline meaning of an everyday card.
BAD_MISC = {"arch", "obs", "obsc", "rare", "derog", "vulg", "sl", "X",
            "joc", "poet", "dated", "male-sl"}

POS_PRIORITY = {"noun": 0, "verb": 0, "i-adjective": 0, "na-adjective": 0,
                "pronoun": 0, "adverb": 1, "adjective": 1, "conjunction": 1,
                "interjection": 1, "expression": 2, "number": 2,
                "counter": 3, "prefix": 4, "suffix": 4}

# Kana strings whose corpus frequency is overwhelmingly their particle use;
# JMdict lists rare homograph nouns for several (の "arrow shaft", し "teacher")
# which must not inherit that frequency.
FUNCTION_WORDS = set("""
は が を に へ と で や か の も ね よ な さ ぞ ぜ わ し ば ん だ ぬ り つ ら
です ます ない なかっ から まで より など ほど ばかり だけ しか こそ でも ても
とか やら かしら のに ので けど けれど けれども ちゃ じゃ って とも たり
だろう でしょう ながら つつ どの まし たら たい てる とく ちゃう そう よう
う い え お く げ ど べ ぶ ぱ ちょ にゃ
""".split())


def pos_label(codes):
    for c in codes:
        if c.startswith("v"):          # v1, v5*, vs, vs-i, vk, vz, vt, vi ...
            return "verb"
        if c in POS_MAP:
            return POS_MAP[c]
    return None


def load_jmdict(path):
    """written form -> {display, reading, meaning, pos}."""
    print("Loading JMdict ...")
    words = json.load(open(path, encoding="utf-8"))["words"]
    index = {}
    for e in words:
        senses = e.get("sense") or []
        kana = [k for k in e.get("kana", [])
                if "sk" not in [t.lower() for t in k.get("tags", [])]]
        kanji = [k for k in e.get("kanji", []) if "sK" not in k.get("tags", [])]
        if not senses or not kana:
            continue

        # Prefer the first sense that is ordinary modern Japanese; a card
        # headed "archaic" or "obscure" is not everyday vocabulary.
        chosen = None
        for s in senses:
            if set(s.get("misc") or []) & BAD_MISC:
                continue
            if pos_label(s.get("partOfSpeech") or []):
                chosen = s
                break
        if chosen is None:
            continue
        pos = pos_label(chosen.get("partOfSpeech") or [])
        if not pos:
            continue

        glosses = [g["text"] for g in chosen.get("gloss", [])
                   if g.get("lang") == "eng"][:3]
        if not glosses:
            continue

        read = next((k["text"] for k in kana if k.get("common")), kana[0]["text"])
        usually_kana = "uk" in (chosen.get("misc") or [])
        common_kanji = next((k["text"] for k in kanji if k.get("common")), None)
        display = read if (usually_kana or not common_kanji) else common_kanji
        common = any(k.get("common") for k in kana + kanji)

        rec = {
            "_score": (POS_PRIORITY.get(pos, 2), 0 if common else 1, -len(senses)),
            "display": display, "reading": read, "pos": pos,
            "meaning": "; ".join(glosses), "common": common,
        }
        forms = [k["text"] for k in kanji]
        if display == read:
            forms.append(display)
        for form in forms:
            prev = index.get(form)
            if prev is None or rec["_score"] < prev["_score"]:
                index[form] = rec
    print(f"  {len(index)} lookup forms")
    return index


# ------------------------------------------------------------------- corpus

def sentence_usable(jp, en):
    """Everyday, readable, and free of corpus junk."""
    if not jp.endswith(("。", "！", "？", "」")):
        return False
    if LATIN_RUN.search(jp) or FOREIGN.search(jp) or FOREIGN.search(en):
        return False
    if not en.strip() or JAPANESE_RE.search(en):
        return False
    return 8 <= len(jp) <= 40


def build_index(corpus_path, cache_path):
    """(dictionary form, reading) -> [sentence ids], tokenising the corpus once.

    Indexing by the pair is the whole point: it is what makes "this sentence
    uses 上 as うえ" answerable, rather than merely "the character 上 appears".
    """
    if os.path.exists(cache_path):
        print("Loading cached corpus index ...")
        with open(cache_path, "rb") as fh:
            return pickle.load(fh)

    print("Loading corpus ...")
    data = json.load(open(corpus_path, encoding="utf-8"))
    sentences = [(s["text"], s["translation"]) for s in data
                 if s.get("translation") and sentence_usable(s["text"],
                                                             s["translation"])]
    print(f"  {len(sentences)} usable sentences (of {len(data)})")

    print("Tokenising corpus (one pass, then cached) ...")
    tok = Tokenizer()
    index = collections.defaultdict(list)
    difficulty = []
    lemma_freq = collections.Counter()

    readable = []
    for i, (jp, _en) in enumerate(sentences):
        lemmas = []
        ok = True
        for t in tok.tokenize(jp):
            if t.surface == "々":
                ok = False
            elif KANJI_RE.search(t.surface) and (
                    not t.reading or t.reading == "*"):
                ok = False
            base = t.base_form if t.base_form and t.base_form != "*" else t.surface
            major = t.part_of_speech.split(",")[0]
            reading = hira(t.reading) if t.reading and t.reading != "*" else t.surface
            # Verbs and adjectives inflect, so the surface reading differs from
            # the lemma's; key those on the lemma alone.
            key = ((base, "", major) if major in ("動詞", "形容詞")
                   else (base, reading, major))
            index[key].append(i)
            lemmas.append(base)
            lemma_freq[base] += 1
        difficulty.append(lemmas)
        readable.append(ok)
        if (i + 1) % 25000 == 0:
            print(f"  {i+1} ...")

    common = {w for w, _ in lemma_freq.most_common(6000)}
    print(f"  {sum(readable)} of {len(sentences)} sentences fully annotatable")
    payload = (sentences, dict(index), difficulty, common, readable)
    with open(cache_path, "wb") as fh:
        pickle.dump(payload, fh, protocol=4)
    print(f"  indexed {len(index)} (form, reading) keys")
    return payload


def is_inflected(word, tok):
    """True if this is a conjugated form of another word, not a word itself.

    受け is the 連用形 of 受ける and 続き of 続く; presented as nouns they inherit
    the verb's frequency and teach a form rather than a word.
    """
    ts = list(tok.tokenize(word))
    if len(ts) != 1:
        return False
    t = ts[0]
    major = t.part_of_speech.split(",")[0]
    return (major in ("動詞", "形容詞", "助動詞")
            and t.base_form and t.base_form != "*" and t.base_form != word)


def pick_sentences(word, reading, pos, index, sentences, difficulty, common,
                   readable, want=2):
    """Up to `want` distinct sentences that genuinely use this word.

    Every returned sentence has passed the same test as the first: the
    tokeniser found this word, in a compatible part of speech and with this
    reading, in it. Adding a second example is only worth anything if it is a
    different context, so candidates too similar to one already chosen are
    skipped -- two near-identical sentences teach the shape of the sentence
    rather than the word.
    """
    majors = POS_COMPATIBLE.get(pos)
    if not majors:
        return [], 0
    readings = [""] if pos in ("verb", "i-adjective") else [hira(reading), ""]
    ids = []
    for major in majors:
        for rd in readings:
            ids.extend(index.get((word, rd, major), []))
    ids = list(dict.fromkeys(ids))
    support = len(ids)
    if not ids:
        return [], 0

    scored = []
    for i in ids:
        if not readable[i]:
            continue
        jp, en = sentences[i]
        unknown = sum(1 for l in difficulty[i] if l not in common)
        scored.append((unknown * 5 + abs(len(jp) - 20), i, jp, en))
    scored.sort(key=lambda t: (t[0], t[2]))

    chosen, chosen_sets = [], []
    for _score, i, jp, en in scored:
        lemmas = set(difficulty[i])
        if any(len(lemmas & prev) / max(1, len(lemmas | prev)) > 0.6
               for prev in chosen_sets):
            continue                       # near-duplicate of one already taken
        chosen.append((jp, en))
        chosen_sets.append(lemmas)
        if len(chosen) >= want:
            break
    return chosen, support


# ---------------------------------------------------------------------- card

S_POS = ("display:inline-block;font-size:11px;letter-spacing:.12em;"
         "text-transform:uppercase;color:#6b7280;border:1px solid #d8dde6;"
         "border-radius:99px;padding:2px 10px;margin-bottom:16px")
S_WORD = "font-size:46px;font-weight:600;line-height:1.9"
S_READ = "font-size:19px;color:#6b7280;margin-top:2px"
S_MEAN = "font-size:24px;color:#14532d;margin:16px 0 4px"
S_RANK = "font-size:12px;color:#a7aebb;margin-top:8px"
S_EXLBL = ("font-size:11px;letter-spacing:.1em;text-transform:uppercase;"
           "color:#a7aebb;margin:24px 0 8px")
S_EX = "border-top:1px solid #e6eaf0;padding-top:14px"
S_JP = "font-size:22px;line-height:2.3"
S_EN = "font-size:15px;color:#5b6472;font-style:italic;margin-top:8px"
S_ATTR = "font-size:10px;color:#c9cfd9;margin-top:22px;line-height:1.5"

ATTRIB = ("Sentence: Tatoeba / Tanaka Corpus (CC BY 2.0 FR) &middot; "
          "Definition: JMdict, EDRDG (CC BY-SA 4.0)")


def clean(t):
    return t.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def make_card(rank, rec, examples, tok):
    word, reading, pos = rec["display"], rec["reading"], rec["pos"]
    # Front deliberately carries no furigana: reading it is the recall task.
    front = (f'<div style="{S_POS}">{html.escape(pos)}</div>'
             f'<div style="{S_WORD}">{html.escape(word)}</div>')
    back = (f'<div style="{S_POS}">{html.escape(pos)}</div>'
            f'<div style="{S_WORD}">{ruby(word, reading)}</div>'
            f'<div style="{S_READ}">{html.escape(hira(reading))}</div>'
            f'<div style="{S_MEAN}">{html.escape(rec["meaning"])}</div>'
            f'<div style="{S_RANK}">frequency rank {rank}</div>'
            f'<div style="{S_EXLBL}">'
            f'{"Examples" if len(examples) > 1 else "Example"}</div>'
            + "".join(
                f'<div style="{S_EX}">'
                f'<div style="{S_JP}">{ruby_sentence(jp, tok, word)}</div>'
                f'<div style="{S_EN}">{html.escape(en)}</div></div>'
                for jp, en in examples)
            + f'<div style="{S_ATTR}">{ATTRIB}</div>')
    band = ((rank - 1) // 500) * 500
    tags = f"rank::{band+1:04d}-{band+500:04d} pos::{pos.replace(' ', '-')}"
    return clean(front), clean(back), tags


# ---------------------------------------------------------------------- main

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--jmdict", default="/home/user/data/jmdict-eng-3.6.2.json")
    ap.add_argument("--corpus", default="/home/user/data/jpn-eng-examples.json")
    ap.add_argument("--cache", default="/home/user/data/corpus_index3.pkl")
    ap.add_argument("--count", type=int, default=5000)
    ap.add_argument("--examples", type=int, default=2)
    ap.add_argument("--out", default="japanese_core5000_v2.txt")
    ap.add_argument("--apkg", default=None)
    ap.add_argument("--tsv", default="japanese_core5000_v2_wordlist.tsv")
    ap.add_argument("--title", default="Japanese Core 5000")
    args = ap.parse_args()

    jm = load_jmdict(args.jmdict)
    sentences, index, difficulty, common, readable = build_index(
        args.corpus, args.cache)

    print("Ranking and selecting examples ...")
    freq_rank = {w: i for i, w in enumerate(top_n_list("ja", 60000))}
    tok = Tokenizer()

    rows, seen, dropped = [], set(), collections.Counter()
    for word in sorted(freq_rank, key=freq_rank.get):
        if len(rows) >= args.count:
            break
        if word in FUNCTION_WORDS:
            dropped["function word"] += 1
            continue
        rec = jm.get(word)
        if rec is None:
            dropped["not in dictionary"] += 1
            continue
        disp = rec["display"]
        if disp in seen:
            continue
        if disp in FUNCTION_WORDS or not rec["common"]:
            dropped["function word / uncommon"] += 1
            continue
        if len(disp) == 1 and not has_kanji(disp):
            dropped["bare kana"] += 1
            continue

        if is_inflected(disp, tok):
            dropped["conjugated form, not a word"] += 1
            continue

        # A tokeniser labels 出来 and 教え as nouns, so is_inflected misses
        # them, yet their rank comes from 出来る and 教える. If adding る yields
        # a common verb and the noun itself is barely used, the frequency
        # belongs to the verb. 動画 survives: 動画る is not a word.
        stem_verb = jm.get(disp + "る")
        if (stem_verb and stem_verb["pos"] == "verb" and stem_verb["common"]
                and rec["pos"] != "verb" and len(rows) < 1500):
            _probe, probe_support = pick_sentences(
                disp, rec["reading"], rec["pos"], index, sentences,
                difficulty, common, readable, want=1)
            if probe_support < 25:
                dropped["frequency belongs to the verb form"] += 1
                continue

        examples, support = pick_sentences(
            disp, rec["reading"], rec["pos"], index, sentences, difficulty,
            common, readable, want=args.examples)
        if not examples:
            dropped["no sentence uses this word"] += 1
            continue

        # A genuinely top-ranked word is everywhere in any corpus. A hiragana
        # word ranked near the top but scarcely used in this sense is drawing
        # its rank from a homograph -- かも ranks 33rd as the particle pair,
        # not as 鴨 the duck. Katakana and kanji words are exempt: アニメ and
        # 動画 are legitimately modern and simply rare in an older corpus.
        if (len(rows) < 800 and support < 25
                and all("぀" <= c <= "ゟ" for c in disp)):
            dropped["rank belongs to a homograph"] += 1
            continue

        seen.add(disp)
        rows.append(make_card(len(rows) + 1, rec, examples, tok) +
                    (disp, rec["reading"], rec["pos"], rec["meaning"], examples))
        if len(rows) % 1000 == 0:
            print(f"  {len(rows)} cards ...")

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#separator:tab\n#html:true\n")
        fh.write("#columns:Front\tBack\tTags\n#tags column:3\n")
        for r in rows:
            fh.write(f"{r[0]}\t{r[1]}\t{r[2]}\n")

    with open(args.tsv, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("rank\tword\treading\tpos\tmeaning\texamples\n")
        for i, r in enumerate(rows, 1):
            ex = " || ".join(f"{jp} :: {en}" for jp, en in r[7])
            fh.write("\t".join([str(i), r[3], hira(r[4]), r[5], r[6], ex]) + "\n")

    counts = collections.Counter(len(r[7]) for r in rows)
    print(f"\nexamples per card: " +
          ", ".join(f"{n} example(s): {c}" for n, c in sorted(counts.items())))
    print(f"\nCards : {len(rows)}  ->  {args.out} "
          f"({os.path.getsize(args.out)/1024:.0f} KB)")
    print(f"List  : {args.tsv}")
    for reason, n in dropped.most_common():
        print(f"  skipped, {reason}: {n}")

    if args.apkg:
        build_apkg(rows, args.title, args.apkg)
        print(f"Deck  : {args.apkg} "
              f"({os.path.getsize(args.apkg)/1024:.0f} KB)")


def build_apkg(rows, title, out_path):
    from anki.collection import (Collection, ExportAnkiPackageOptions,
                                 DeckIdLimit)
    tmp = tempfile.mkdtemp()
    try:
        col = Collection(os.path.join(tmp, "collection.anki2"))
        mm = col.models
        nt = mm.new("Japanese Core Vocabulary")
        for name in ("Front", "Back"):
            mm.add_field(nt, mm.new_field(name))
        tpl = mm.new_template("Recognition")
        tpl["qfmt"] = "{{Front}}"
        tpl["afmt"] = "{{Back}}"
        mm.add_template(nt, tpl)
        nt["css"] = ('.card { font-family:"Hiragino Sans","Yu Gothic",'
                     '"Noto Sans JP",sans-serif; background:#fbfbfd;'
                     'color:#1f2430; text-align:center; padding:16px; }'
                     'ruby rt { font-size:.5em; color:#6b7280; font-weight:400; }')
        mm.add(nt)
        nt = mm.by_name("Japanese Core Vocabulary")
        did = col.decks.id(title)
        for r in rows:
            note = col.new_note(nt)
            note["Front"], note["Back"] = r[0], r[1]
            note.tags = r[2].split()
            col.add_note(note, did)
        col.export_anki_package(
            out_path=out_path,
            options=ExportAnkiPackageOptions(
                with_scheduling=False, with_deck_configs=False,
                with_media=True, legacy=True),
            limit=DeckIdLimit(did))
        col.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
