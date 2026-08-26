# Adding audio with device text-to-speech

`japanese_core5000_tts.txt` carries two extra plain-text fields, `WordAudio`
and `SentenceAudio`, that exist purely to be spoken. Anki strips HTML before
handing text to TTS, so reading the display fields directly would flatten
`<ruby>東京<rt>とうきょう</rt></ruby>` to "東京とうきょう" and say it twice.

No audio files are involved: the device's own Japanese voice speaks the text
at review time, so the deck stays small and there is nothing to license.

## 1. Install a Japanese voice (once)

Android: **Settings → General management → Text-to-speech**, pick the Google
speech engine, then install the Japanese voice data. Without it Anki silently
plays nothing.

## 2. Create the note type

AnkiDroid: **⋮ → Manage Note Types → Add → Clone: Basic**, name it
`Japanese Core`, then under **Fields** add these six, in this order:

    Word   WordAudio   Meaning   Sentence   SentenceAudio   Translation

Order matters — the import maps columns to fields positionally.

## 3. Paste the card templates

Under **Cards** for that note type:

**Front**

    <div style="font-size:44px;line-height:2">{{Word}}</div>
    {{tts ja_JP:WordAudio}}

**Back**

    <div style="font-size:44px;line-height:2">{{Word}}</div>
    <hr>
    <div style="font-size:22px;color:#14532d">{{Meaning}}</div>
    <div style="font-size:22px;line-height:2.2;margin-top:14px">{{Sentence}}</div>
    {{tts ja_JP:SentenceAudio}}
    <div style="font-size:16px;color:#5b6472;font-style:italic;margin-top:10px">{{Translation}}</div>

## 4. Import

**⋮ → Import**, choose `japanese_core5000_tts.txt`, and select the
`Japanese Core` note type. The `#columns:` and `#tags column:` directives in
the file handle the rest.

## Notes

Tap the speaker icon to replay; automatic playback is controlled by the deck's
**Audio → Don't play audio automatically** option.

Synthesised speech gets Japanese pitch accent wrong a fair amount of the time.
It is good for reinforcing what a word sounds like, but do not treat it as an
accent model.
