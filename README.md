# Japanese Video → Anki Deck

Turn the Japanese spoken in a video into a frequency-ranked Anki deck, where every
card carries an example sentence taken from that same video.

## What it does

1. **Reads the transcript** — `.txt`, `.srt`, or YouTube's `.vtt` captions
   (timestamps, cue numbers and the rolling-window duplication that auto-captions
   produce are all stripped automatically).
2. **Tokenises and lemmatises** with Janome, so every conjugated form collapses
   onto its dictionary form:
   食べました / 食べて / 食べない → **食べる**.
3. **Deduplicates** — one entry per dictionary form.
4. **Ranks by usage**, most frequent first.
5. **Picks an example sentence** for each word from the transcript, preferring a
   comfortable study length and bolding the word as it actually appeared
   (行き is highlighted on the 行く card).
6. **Writes `deck.apkg`** ready to import into Anki, plus a `.tsv` word list.

## Usage

```bash
pip3 install janome genanki

# Step 1 — get the Japanese captions (see note below)
./fetch_transcript.sh https://youtu.be/VIDEO_ID

# Step 2 — build the deck
python3 build_deck.py \
    --transcript transcript.ja.vtt \
    --out japanese_deck.apkg \
    --title "Japanese Video Vocabulary" \
    --content-words-only
```

Then in Anki: **File → Import → japanese_deck.apkg**.

### Options

| Flag | Effect |
|---|---|
| `--transcript` | Input `.txt` / `.vtt` / `.srt` (required) |
| `--out` | Output `.apkg` path (default `japanese_deck.apkg`) |
| `--title` | Deck name shown in Anki |
| `--content-words-only` | Drop particles and auxiliary verbs (は, が, ます, です…). Recommended — otherwise grammar particles dominate the top of the ranking |
| `--min-frequency N` | Only include words used at least N times |

### Card layout

- **Front:** the word + its part of speech.
- **Back:** reading in hiragana, part of speech, its usage rank and count, and the
  example sentence from the video with a hiragana reading underneath.

Cards are tagged `freq::high` (5+ uses), `freq::medium` (2–4) and `freq::once`,
plus `pos::verb`, `pos::noun` and so on, so you can study a subset.

## Note on fetching captions

`fetch_transcript.sh` must be run on your own machine. It uses `yt-dlp` to pull
the Japanese caption track, and falls back to printing Whisper instructions if
the video has no published Japanese captions.

## Requirements

- Python 3.8+
- `janome` (pure-Python Japanese tokeniser, dictionary bundled)
- `genanki` (writes `.apkg` files)
- `yt-dlp`, for the caption-fetching step only
