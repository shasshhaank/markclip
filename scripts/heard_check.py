"""What is actually HEARD in a rendered clip (Whisper large, English or MARKCLIP_LANG), with times: use it on every
base edit to confirm the first and last words and that no word of a dropped tangent or a co-host's line leaks in.
usage: heard_check.py CLIP.mp4 [...]"""
import os, sys
sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
import mlx_whisper
from clipper.media import load_audio

for out in sys.argv[1:]:
    audio = load_audio(out, 16000, mono=True)[0]
    r = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/whisper-large-v3-mlx", word_timestamps=True,
                               condition_on_previous_text=False, language=os.environ.get("MARKCLIP_LANG", "en"))
    print("==", os.path.basename(out), f"{len(audio) / 16000:.1f}s")
    for s in r["segments"]:
        print(f"  [{s['start']:5.1f}-{s['end']:5.1f}] {s['text'].strip()}")
