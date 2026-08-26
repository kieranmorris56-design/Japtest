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

---

# Japanese Core 5000 deck

`build_core5k.py` builds a frequency-ranked deck of the most common Japanese
words — independent of any video. Each card shows the word in its dictionary
form with furigana above the kanji, an English gloss, and a real example
sentence with its translation.

```bash
pip3 install janome wordfreq anki
python3 build_core5k.py --count 5000 --out japanese_core5000.apkg
```

### Card layout

- **Front:** the word with furigana (rendered by Anki's `{{furigana:}}` filter,
  so kana sits above the kanji it belongs to) plus its part of speech.
- **Back:** English gloss, frequency rank, and an example sentence — itself
  fully furigana-annotated — with an English translation.

Cards are tagged `rank::0001-0500`, `rank::0501-1000` … so you can study in
frequency order, and `pos::verb`, `pos::noun` and so on.

### How the ranking works

Ordering comes from [`wordfreq`](https://pypi.org/project/wordfreq/), whose
Japanese frequencies aggregate subtitles, Wikipedia, news and web text, so the
order reflects real usage rather than the makeup of the example corpus. Only
words that actually occur in the sentence corpus are eligible, which guarantees
every card has a genuine example.

Particles and auxiliary verbs are excluded — content words only.

### Data sources

| Source | Used for | Licence |
|---|---|---|
| [JMdict](https://www.edrdg.org/jmdict/j_jmdict.html) via [jmdict-simplified](https://github.com/scriptin/jmdict-simplified) | dictionary forms, readings, English glosses | CC BY-SA 4.0, © EDRDG |
| [Tatoeba](https://tatoeba.org) / Tanaka Corpus via [tatoeba-json](https://github.com/mwhirls/tatoeba-json) | example sentences and translations | CC BY 2.0 FR |
| [wordfreq](https://pypi.org/project/wordfreq/) | frequency ranking | MIT |

The deck is written with Anki's own `anki` library rather than genanki, so the
package is valid by construction and imports on AnkiDroid as well as desktop.

Attribution for both data sources is printed on the back of every card.

### Known limitations

Automated sense selection is not perfect. Where a written form maps to several
dictionary entries, the builder prefers the most central one (`人` resolves to
the noun "person" rather than the suffix "-ian"), but a first-listed gloss can
still be narrower than the word's everyday meaning — `月` glosses as "Moon"
where "month" is often meant. Treat the gloss as a prompt, not a definition.

### If AnkiDroid refuses the .apkg

AnkiDroid 2.24.0 on Android 16 can fail any `.apkg` import with
`500: Failed to read '...': stream did not contain valid UTF-8`
— including decks that import fine on desktop, and even byte-identical
round-trips of a deck that previously worked
([AnkiDroid #21430](https://github.com/ankidroid/Anki-Android/issues/21430)).
It is a bug in the app's Kotlin/JNI layer handing the file to its Rust core,
not a problem with the deck.

Two ways around it:

1. **Import the plain-text file instead.** `apkg_to_csv.py` produces
   `japanese_core5000.txt`, which AnkiDroid's CSV importer reads on affected
   devices. Furigana is baked in as HTML ruby, so it renders in the stock
   Basic notetype with no template filter needed.

   ```bash
   python3 apkg_to_csv.py --apkg japanese_core5000.apkg --out japanese_core5000.txt
   ```

2. **Import the .apkg on desktop Anki and sync.** The package is valid, so
   desktop imports it normally; syncing through AnkiWeb then delivers the deck
   to the phone without AnkiDroid ever reading a file.

### Audio

See [TTS_SETUP.md](TTS_SETUP.md) to have the device speak each word and example
sentence via `{{tts}}`, using `make_tts_import.py` to build the import file.
No audio files are bundled, so nothing needs licensing and the deck stays small.
