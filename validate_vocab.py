#!/usr/bin/env python3
"""
Verify every finished vocabulary card, independently of how it was built.

This deliberately re-derives the checks from the output files rather than
trusting the builder's own logic: the defect that made this rebuild necessary
(an example sentence that did not actually use the word it taught) was
invisible until something re-read the finished deck and asked the question
directly.

Exits non-zero if anything fails.
"""

import csv
import html
import re
import sys

from janome.tokenizer import Tokenizer

KANJI_RE = re.compile(r"[一-鿿々〆ヶ]")
JAPANESE_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿々ー]")
FOREIGN = re.compile(r"[Ѐ-ӿ가-힯ᄀ-ᇿ؀-ۿ฀-๿]")
LATIN_RUN = re.compile(r"[A-Za-z]{3,}")
INFLECTING = {"動詞", "形容詞"}


def hira(t):
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
                   for c in (t or ""))


def check_wordlist(path, tok):
    """The substantive check: does the example really use this word?"""
    problems = []
    rows = list(csv.reader(open(path, encoding="utf-8"), delimiter="\t"))[1:]
    seen = {}

    for r in rows:
        if len(r) < 6:
            problems.append(f"malformed row: {r[:2]}")
            continue
        rank, word, reading, pos, meaning, examples_raw = r[:6]

        if word in seen:
            problems.append(f"#{rank} {word}: duplicate of #{seen[word]}")
        seen[word] = rank
        if not meaning.strip():
            problems.append(f"#{rank} {word}: empty meaning")
        if FOREIGN.search(word) or LATIN_RUN.search(word):
            problems.append(f"#{rank} {word}: foreign script in the word")

        pairs = [p for p in examples_raw.split(" || ") if p.strip()]
        if not pairs:
            problems.append(f"#{rank} {word}: no example sentences")
            continue

        # EVERY example must independently use the word, not just the first.
        for n, pair in enumerate(pairs, 1):
            if " :: " not in pair:
                problems.append(f"#{rank} {word}: example {n} malformed")
                continue
            example, trans = pair.split(" :: ", 1)
            tag = f"#{rank} {word}: example {n}"

            if FOREIGN.search(example) or LATIN_RUN.search(example):
                problems.append(f"{tag}: foreign script | {example[:28]}")
            if not trans.strip():
                problems.append(f"{tag}: empty translation")
            if JAPANESE_RE.search(trans):
                problems.append(f"{tag}: Japanese text in the translation")
            if not example.endswith(("。", "！", "？", "」")):
                problems.append(f"{tag}: no final punctuation | {example[:28]}")

            hit = None
            for t in tok.tokenize(example):
                if t.base_form == word:
                    hit = t
                    break
            if hit is None:
                problems.append(f"{tag}: does not use the word | {example[:28]}")
                continue
            major = hit.part_of_speech.split(",")[0]
            if major not in INFLECTING:
                got = (hira(hit.reading) if hit.reading and hit.reading != "*"
                       else hit.surface)
                if reading and got and hira(reading) != got:
                    problems.append(f"{tag}: taught {hira(reading)} but read "
                                    f"{got} | {example[:24]}")
        if len(set(p.split(" :: ")[0] for p in pairs)) != len(pairs):
            problems.append(f"#{rank} {word}: duplicate example sentences")
    return len(rows), problems


def check_cards(path):
    """Structural checks on the import file itself."""
    problems = []
    lines = [l.rstrip("\n") for l in open(path, encoding="utf-8")
             if not l.startswith("#")]
    for i, line in enumerate(lines, 1):
        cols = line.split("\t")
        if len(cols) != 3:
            problems.append(f"line {i}: {len(cols)} columns, expected 3")
            continue
        front, back, tags = cols
        if "<ruby>" in front:
            problems.append(f"line {i}: furigana on the FRONT of the card")
        if "Example" not in back:
            problems.append(f"line {i}: back has no example block")
        if not tags.strip():
            problems.append(f"line {i}: no tags")
        # Every kanji on the back should be inside a ruby element.
        stripped = re.sub(r"<ruby>.*?</ruby>", "", back)
        stripped = re.sub(r"<[^>]+>", "", stripped)
        leftover = KANJI_RE.findall(html.unescape(stripped))
        if leftover:
            problems.append(f"line {i}: kanji without furigana on the back: "
                            f"{''.join(leftover[:6])}")
    open(path, "rb").read().decode("utf-8")
    return len(lines), problems


def main():
    tsv = sys.argv[1] if len(sys.argv) > 1 else "japanese_core5000_v2_wordlist.tsv"
    txt = sys.argv[2] if len(sys.argv) > 2 else "japanese_core5000_v2.txt"

    tok = Tokenizer()
    print("Checking word list ...")
    n_rows, p1 = check_wordlist(tsv, tok)
    print("Checking card file ...")
    n_cards, p2 = check_cards(txt)

    problems = p1 + p2
    print(f"\n{n_rows} word-list rows, {n_cards} cards, valid UTF-8")
    if not problems:
        print("all clean")
        return
    print(f"\n{len(problems)} PROBLEM(S):")
    kinds = {}
    for p in problems:
        key = re.sub(r"#\d+ \S+: ", "", p).split("|")[0].split(":")[0][:44]
        kinds[key] = kinds.get(key, 0) + 1
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>5}  {k}")
    print("\nfirst 15:")
    for p in problems[:15]:
        print("   -", p)
    sys.exit(1)


if __name__ == "__main__":
    main()
