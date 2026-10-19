"""Caption sync, word by word: caption word times (words json, shown 0.05 s early) against an independent Whisper pass
over the voice-only BASE edit (same timeline as the final, no music: loud scores confuse Whisper), with every
disagreement over 0.25 s settled by the audio itself (check.py's gate 3 uses the same measure).
usage: sync_check.py BASE.mp4 WORDS.json"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check import sync_offsets  # noqa: E402

base, words = sys.argv[1], json.load(open(sys.argv[2]))
off, rows = sync_offsets(base, words)
for wd, c, h, d, verdict in rows:
    print(f"   {wd:12s} caption {c:6.2f} heard {h:6.2f} ({d:+.2f})  {verdict}")
print(f"{os.path.basename(base)}: {len(off)}/{len(words)} matched | caption minus heard: median {sorted(off)[len(off) // 2]:+.2f}s, "
      f"worst {max(off, key=abs):+.2f}s, |off|>0.25s: {sum(abs(d) > 0.25 for d in off)}")
