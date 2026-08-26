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
3. **Deduplicates** — one entry per dictionary form. Particles and auxiliary
   verbs are dropped by default, leaving content words only.
4. **Ranks by usage**, most frequent first.
5. **Picks an example sentence** for each word from the transcript, preferring a
   comfortable study length and bolding the word as it actually appeared
   (行き is highlighted on the 行く card).
6. **Writes `deck.apkg`** ready to import into Anki, plus a `.tsv` word list.

## Usage

### One command (Whisper)

```bash
pip3 install yt-dlp openai-whisper janome genanki   # plus ffmpeg
./make_deck.sh https://youtu.be/VIDEO_ID
```

Downloads the audio, transcribes it with Whisper, and builds the deck.
Pass a model as the second argument (`tiny`/`base`/`small`/`medium`/`large-v3`);
`medium` is the default and is usually the right accuracy/speed trade-off for
conversational Japanese.

### Or, if the video has published captions

Captions are far faster than Whisper and, when human-written, more accurate:

```bash
./fetch_transcript.sh https://youtu.be/VIDEO_ID
python3 build_deck.py --transcript transcript.ja.vtt
```

Then in Anki: **File → Import → japanese_deck.apkg**.

### Options

| Flag | Effect |
|---|---|
| `--transcript` | Input `.txt` / `.vtt` / `.srt` (required) |
| `--out` | Output `.apkg` path (default `japanese_deck.apkg`) |
| `--title` | Deck name shown in Anki |
| `--include-particles` | Also make cards for particles and auxiliary verbs (は, が, ます, です…). **Off by default** — they otherwise occupy most of the top of the ranking |
| `--min-frequency N` | Only include words used at least N times |

### Card layout

- **Front:** the word + its part of speech.
- **Back:** reading in hiragana, part of speech, its usage rank and count, and the
  example sentence from the video with a hiragana reading underneath.

Cards are tagged `freq::high` (5+ uses), `freq::medium` (2–4) and `freq::once`,
plus `pos::verb`, `pos::noun` and so on, so you can study a subset.

## Why the download step runs locally

This repo was built in a Claude Code sandbox whose network egress policy blocks
`youtube.com`, `youtu.be` and `googlevideo.com` (the host the audio actually
streams from). Whisper transcribes an audio file that already exists on disk, so
it cannot work around a blocked *download* — which is why `make_deck.sh` is
meant to be run on your own machine. Everything downstream of the transcript
runs anywhere.

## Requirements

- Python 3.8+
- `janome` — pure-Python Japanese tokeniser, dictionary bundled
- `genanki` — writes `.apkg` files
- `yt-dlp`, `openai-whisper` and `ffmpeg` — for the transcription step only
