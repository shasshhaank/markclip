# Extraction with ClipIt (and the gotchas that cost hours)

markclip builds on the **ClipIt** skill (default `~/.claude/skills/clipit`, Python environment `~/.clipit/venv`,
created by ClipIt's `install.sh`). Every markclip script finds it through `CLIPIT_DIR`; set it if ClipIt lives
elsewhere. Check the setup once with `$PY $C doctor`.

markclip uses ClipIt for: fetching sources (`clip.py fetch`), its sentence-snapping transcript (`clipper.transcribe`), the
YuNet face model (`clipper.reframe.MODEL`), audio helpers (`clipper.audio`: effects, fades, ducking, -14 LUFS
normalising) and media I/O (`clipper.media`). It does **not** use ClipIt's `talk` edit or its reframing (see below).

## Commands
Run from the job folder: `fetch` saves into `./input` (video) or `./music` (`--audio`), and ClipIt keeps per-file
working data in `./work/<input name>/`.
```
PY=~/.clipit/venv/bin/python; C=${CLIPIT_DIR:-$HOME/.claude/skills/clipit}/clip.py
$PY $C find "QUERY" --n 5                                  # search YouTube (lists, fetches nothing)
$PY $C fetch --res 1080 --section 1:53:55-1:55:55 URL      # only this window; add ~10 s each side yourself
$PY $C fetch --audio URL                                   # a song as mp3 into ./music
$PY $C analyze input/X.mp4                                 # Whisper transcript -> work/X/transcript.txt
$PY $C sheet input/X.mp4 --times 10,20,30                  # contact sheet -> work/X/sheet.jpg (--n 12 for evenly spaced)
```
`--section` is repeatable (one file per section). Always fetch at `--res 1080`: the text-safe crop boxes in
`frame_base.py` are in 1920x1080 pixels, and a long-form base is 1920x1080 too. The file arrives as
`input/<title> [<id>] <start>-<end>.mp4` (plus a `.subs.json`); rename it to a short name that keeps the source
window (`failure_shame_10010-10115.mp4`).

The first Whisper run fetches `mlx-community/whisper-large-v3-mlx` (about 3 GB); every markclip transcription
(`base_edit.py`, `words.py`, `heard_check.py`, `check.py`) uses that model through mlx-whisper, so an Apple Silicon Mac
is required. For a source in another language set `MARKCLIP_LANG` (e.g. `hi`) for every one of them; the English
prompts that steer disfluent and punctuated transcripts are then switched off.

## Gotchas
- **Bursts get you blocked.** Ten parallel yt-dlp calls led to "Sign in to confirm you're not a bot" for 20+ minutes
  (a browser on the same IP then hit Google's /sorry page too). Run YouTube requests one at a time with a few seconds
  between them. Don't use browser cookies unless the user says so. When blocked: read episode chapters on
  the show's own site or feed, get music from SoundCloud (sound-design.md), retry YouTube later.
- **YouTube auto-subs break sentence snapping.** ClipIt's transcript prefers a `.subs.json` saved next to the input,
  so move `input/*.subs.json` aside before `base_edit.py`: auto captions have few sentence breaks, and a 30 s clip was
  once widened to 188 s with ">>" marks in its captions.
- **ClipIt's transcript tidies speech.** It drops spoken repeats ("I I", "when I when I"), so `base_edit.py` makes its
  own verbatim Whisper-large pass of the window (disfluent prompt) before finding repeats.
- **Don't use ClipIt's `talk` edit or reframing for the base.** Its zoom cuts push in and ease back (bounce), it
  punches in on keywords, it shrinks tight close-ups into blurred strips, and its face tracking slides toward the new
  face after every camera change. `base_edit.py` + `frame_base.py` replace it: hard cuts, one fixed crop per camera
  shot (framing.md).
- **Work folders are per input file name.** `work/<input name>/` holds ClipIt's transcript (`transcript.json`,
  `speech16k.wav`), base_edit's verbatim cache (`verbatim_<t0>_<t1>.json`, keyed by the window: 4 s before `--start`
  to 4 s after `--end`, with `_<lang>` added for another `MARKCLIP_LANG`), its `recheck/` passes and contact sheets
  (`sheet.jpg`). Copy the input under another name for side experiments; delete a cache file to force a fresh
  transcription.
- **Caption timing comes from the final audio.** Captions timed from source transcripts remapped through jump cuts
  ran up to 0.9 s late. `words.py` transcribes the finished base edit itself.
- **Check what is heard, not what you meant.** `heard_check.py` after every base edit: first word, last word, every
  jump cut. Leaks happen when a cut boundary starts a few hundredths after a word's start.

## Loudness profile of a song (to place its swell)
```
$PY - <<'EOF'
import os, sys, numpy as np; sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
from clipper.media import load_audio
a = load_audio("music/SONG.mp3", 22050, mono=True)[0]; hop = 44100
print(" ".join(f"{20*np.log10(np.sqrt(np.mean(a[i:i+hop]**2))+1e-9):.0f}" for i in range(0, len(a)-hop, hop)))
EOF
```
Each number is 2 s of the song; the jump from about -30 to -15 is the swell.
