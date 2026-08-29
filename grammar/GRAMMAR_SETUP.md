# JLPT Grammar N5–N1 — import guide

`jlpt_grammar.txt` holds 413 grammar cards, one per grammar point, importable
on the phone alone. Furigana is baked in as HTML ruby and appears on the **back
only**, so the front stays a clean recognition prompt.

## 1. Create the note type (once)

AnkiDroid: **⋮ → Manage Note Types → Add → Clone: Basic**, name it
`JLPT Grammar`, then under **Fields** add these eight, in this exact order —
the import maps columns to fields positionally:

    Point   PointRuby   Level   Meaning   Formation   Notes   Contrast   Examples

## 2. Paste the card templates

Under **Cards** for that note type.

**Front** — no furigana here, by design:

    <div class="lvl">{{Level}}</div>
    <div class="pt">{{Point}}</div>

**Back**:

    <div class="lvl">{{Level}}</div>
    <div class="pt">{{PointRuby}}</div>
    <div class="mean">{{Meaning}}</div>
    <div class="form">{{Formation}}</div>
    {{#Notes}}<div class="note">{{Notes}}</div>{{/Notes}}
    {{#Contrast}}<div class="vs">{{Contrast}}</div>{{/Contrast}}
    <div class="exlabel">Examples</div>
    {{Examples}}

**Styling** (the *Styling* box, shared by both sides):

    .card { font-family:"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif;
      font-size:20px; color:#1f2430; background:#fbfbfd; text-align:center;
      padding:16px; }
    .lvl { display:inline-block; font-size:11px; letter-spacing:.12em;
      color:#6b7280; border:1px solid #d8dde6; border-radius:99px;
      padding:2px 10px; margin-bottom:14px; }
    .pt { font-size:38px; font-weight:600; line-height:1.9; margin-bottom:10px; }
    .mean { font-size:22px; color:#14532d; margin-bottom:14px; }
    .form { font-size:15px; color:#475569; background:#f1f4f9;
      border-radius:8px; padding:8px 12px; display:inline-block; }
    .note { font-size:15px; color:#5b6472; margin-top:14px; line-height:1.7; }
    .vs { font-size:14px; color:#8a5a2b; background:#fdf6ec; border-radius:8px;
      padding:8px 12px; margin-top:12px; line-height:1.6; }
    .exlabel { font-size:11px; letter-spacing:.1em; text-transform:uppercase;
      color:#a7aebb; margin:22px 0 6px; }
    .ex { border-top:1px solid #e6eaf0; padding:12px 0; }
    .ex .jp { font-size:21px; line-height:2.2; }
    .ex .en { font-size:15px; color:#5b6472; font-style:italic; margin-top:4px; }
    ruby rt { font-size:.5em; color:#6b7280; font-weight:400; }

## 3. Import

**⋮ → Import**, choose `jlpt_grammar.txt`, select the `JLPT Grammar` note type.
The `#columns:` and `#tags column:` lines in the file do the rest. Cards arrive
tagged `jlpt::N5` … `jlpt::N1`, so you can study one level at a time.

## What each card shows

- **Front** — the grammar point and its level. No furigana.
- **Back** — the point with furigana, the English meaning, how it attaches
  (Formation), a usage note, a contrast against the grammar most often confused
  with it, and two or more example sentences with furigana and translations.

## Where the content comes from

Explanations, formation rules and contrast notes are written for this deck.
Example sentences are authored to demonstrate the point at its own level; where
a pattern is distinctive enough for a corpus match to be meaningful, an attested
sentence from the Tatoeba / Tanaka Corpus (CC BY 2.0 FR) is added alongside.
240 of the 413 cards carry such an attested sentence.

## Checks that run before every build

`validate.py` refuses to build if any entry has a missing field, a placeholder,
a sentence with no closing punctuation, a duplicate point, or stray non-Japanese
text inside a Japanese sentence. `normalise.py` merges any point that appears at
more than one level, keeping the fullest version at the earliest level.
