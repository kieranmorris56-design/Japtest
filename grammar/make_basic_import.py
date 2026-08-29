#!/usr/bin/env python3
"""
Rebuild the grammar deck as a two-column file that imports into Anki's stock
Basic note type with no setup at all.

The nine-column export needs a purpose-built note type and two pasted
templates before anything renders; miss either step and the back of the card
comes out blank, because a cloned Basic type still has templates pointing at
{{Front}} and {{Back}}, fields the new type no longer has.

Here everything is folded into Front and Back, and every style is inlined,
since the Basic type's own styling knows nothing of this deck's CSS classes.
Furigana stays on the back only.

Usage:
    python3 make_basic_import.py --src jlpt_grammar.txt \
        --out jlpt_grammar_basic.txt
"""

import argparse
import os
import re

# The nine-column export, by position.
POINT, POINT_RUBY, LEVEL, MEANING, FORMATION, NOTES, CONTRAST, EXAMPLES, TAGS = range(9)

S_LVL = ("display:inline-block;font-size:11px;letter-spacing:.12em;"
         "color:#6b7280;border:1px solid #d8dde6;border-radius:99px;"
         "padding:2px 10px;margin-bottom:14px")
S_PT = "font-size:36px;font-weight:600;line-height:1.9;margin-bottom:10px"
S_MEAN = "font-size:22px;color:#14532d;margin-bottom:14px"
S_FORM = ("font-size:15px;color:#475569;background:#f1f4f9;border-radius:8px;"
          "padding:8px 12px;display:inline-block")
S_NOTE = "font-size:15px;color:#5b6472;margin-top:14px;line-height:1.7"
S_VS = ("font-size:14px;color:#8a5a2b;background:#fdf6ec;border-radius:8px;"
        "padding:8px 12px;margin-top:12px;line-height:1.6")
S_EXLBL = ("font-size:11px;letter-spacing:.1em;text-transform:uppercase;"
           "color:#a7aebb;margin:22px 0 6px")
S_EX = "border-top:1px solid #e6eaf0;padding:12px 0"
S_JP = "font-size:21px;line-height:2.2"
S_EN = "font-size:15px;color:#5b6472;font-style:italic;margin-top:4px"


def inline_examples(html):
    """Swap the class-based example markup for inline styles."""
    html = html.replace('<div class="ex">', f'<div style="{S_EX}">')
    html = html.replace('<div class="jp">', f'<div style="{S_JP}">')
    html = html.replace('<div class="en">', f'<div style="{S_EN}">')
    return html


def clean(t):
    return t.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="jlpt_grammar.txt")
    ap.add_argument("--out", default="jlpt_grammar_basic.txt")
    args = ap.parse_args()

    rows = []
    for line in open(args.src, encoding="utf-8"):
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) != 9:
            continue

        front = (f'<div style="{S_LVL}">{c[LEVEL]}</div>'
                 f'<div style="{S_PT}">{c[POINT]}</div>')

        back = [f'<div style="{S_LVL}">{c[LEVEL]}</div>',
                f'<div style="{S_PT}">{c[POINT_RUBY]}</div>',
                f'<div style="{S_MEAN}">{c[MEANING]}</div>',
                f'<div style="{S_FORM}">{c[FORMATION]}</div>']
        if c[NOTES]:
            back.append(f'<div style="{S_NOTE}">{c[NOTES]}</div>')
        if c[CONTRAST]:
            back.append(f'<div style="{S_VS}">{c[CONTRAST]}</div>')
        if c[EXAMPLES]:
            back.append(f'<div style="{S_EXLBL}">Examples</div>')
            back.append(inline_examples(c[EXAMPLES]))

        rows.append((clean(front), clean("".join(back)), clean(c[TAGS])))

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#separator:tab\n")
        fh.write("#html:true\n")
        fh.write("#columns:Front\tBack\tTags\n")
        fh.write("#tags column:3\n")
        for front, back, tags in rows:
            fh.write(f"{front}\t{back}\t{tags}\n")

    print(f"Wrote {len(rows)} cards to {args.out} "
          f"({os.path.getsize(args.out)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
