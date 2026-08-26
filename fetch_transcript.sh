#!/usr/bin/env bash
# Fetch the Japanese captions for a YouTube video as a .vtt file.
#
# Run this on your own machine — the Claude Code sandbox this repo was built in
# has YouTube blocked by its network egress policy.
#
#   ./fetch_transcript.sh https://youtu.be/Qbk4m1u3E3g
#
# Produces transcript.ja.vtt, which build_deck.py reads directly.

set -euo pipefail

URL="${1:-}"
if [[ -z "$URL" ]]; then
  echo "usage: $0 <youtube-url>" >&2
  exit 1
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "yt-dlp not found. Install it with:  pip3 install yt-dlp" >&2
  exit 1
fi

echo "== Subtitle tracks available =="
yt-dlp --list-subs "$URL" || true

echo
echo "== Downloading Japanese captions =="
# --write-sub grabs human-written captions; --write-auto-sub falls back to
# YouTube's auto-generated ones if no manual Japanese track exists.
yt-dlp \
  --skip-download \
  --write-sub --write-auto-sub \
  --sub-langs "ja,ja-JP,ja-orig" \
  --sub-format "vtt" \
  -o "transcript" \
  "$URL"

echo
if ls transcript*.vtt >/dev/null 2>&1; then
  ls -1 transcript*.vtt
  echo
  echo "Next:  python3 build_deck.py --transcript transcript.ja.vtt --content-words-only"
else
  echo "No Japanese caption track was published for this video." >&2
  echo "Fall back to transcribing the audio locally, e.g. with Whisper:" >&2
  echo >&2
  echo "  pip3 install openai-whisper" >&2
  echo "  yt-dlp -x --audio-format mp3 -o audio.mp3 '$URL'" >&2
  echo "  whisper audio.mp3 --language Japanese --model medium --output_format txt" >&2
  echo >&2
  echo "then run build_deck.py against the resulting audio.txt." >&2
  exit 2
fi
