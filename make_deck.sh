#!/usr/bin/env bash
# YouTube URL -> Whisper transcript -> frequency-ranked Anki deck, in one command.
#
#   ./make_deck.sh https://youtu.be/Qbk4m1u3E3g
#   ./make_deck.sh https://youtu.be/Qbk4m1u3E3g large-v3
#
# Run this on your own machine. The Claude Code sandbox this repo was built in
# has YouTube (and googlevideo.com, where the audio actually streams from)
# blocked by its network egress policy, so the download step cannot run there.

set -euo pipefail

URL="${1:-}"
MODEL="${2:-medium}"
WORKDIR="${WORKDIR:-.}"

if [[ -z "$URL" ]]; then
  echo "usage: $0 <youtube-url> [whisper-model]" >&2
  echo "  whisper-model: tiny | base | small | medium (default) | large-v3" >&2
  exit 1
fi

# ---------------------------------------------------------------- dependencies
missing=()
command -v yt-dlp  >/dev/null 2>&1 || missing+=("yt-dlp")
command -v ffmpeg  >/dev/null 2>&1 || missing+=("ffmpeg")
command -v whisper >/dev/null 2>&1 || missing+=("openai-whisper")

if (( ${#missing[@]} )); then
  echo "Missing: ${missing[*]}" >&2
  echo >&2
  echo "Install with:" >&2
  echo "  pip3 install yt-dlp openai-whisper janome genanki" >&2
  echo "  # ffmpeg: brew install ffmpeg   |   sudo apt install ffmpeg" >&2
  exit 1
fi

cd "$WORKDIR"

# ---------------------------------------------------------------- 1. audio
echo "== 1/3  Downloading audio =="
yt-dlp -x --audio-format mp3 --audio-quality 0 -o "audio.%(ext)s" "$URL"

if [[ ! -f audio.mp3 ]]; then
  echo "Audio download failed — no audio.mp3 produced." >&2
  exit 1
fi

# ---------------------------------------------------------------- 2. whisper
echo
echo "== 2/3  Transcribing with Whisper (model: $MODEL) =="
echo "   This is the slow step. On CPU, 'medium' runs roughly 1-2x realtime;"
echo "   pass 'small' for a faster pass or 'large-v3' for the best accuracy."
echo

# --task transcribe (not translate) keeps the output in Japanese.
whisper audio.mp3 \
  --language Japanese \
  --task transcribe \
  --model "$MODEL" \
  --output_format txt \
  --output_dir .

if [[ ! -f audio.txt ]]; then
  echo "Whisper produced no audio.txt." >&2
  exit 1
fi

echo
echo "Transcript written to audio.txt ($(wc -l < audio.txt) lines)"

# ---------------------------------------------------------------- 3. deck
echo
echo "== 3/3  Building the Anki deck =="
python3 build_deck.py \
  --transcript audio.txt \
  --out japanese_deck.apkg \
  --title "Japanese Video Vocabulary"

echo
echo "Done. Import japanese_deck.apkg into Anki:  File -> Import"
echo "Review the ranked word list in japanese_deck_wordlist.tsv"
