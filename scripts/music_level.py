"""How loud music + effects sit under the voice in a finished clip (the base edit's audio is the voice reference).
Target: 9-14 dB under the voice overall (an earlier version sat 28-32 dB under and was inaudible).
usage: music_level.py BASE.mp4 FINAL.mp4"""
import os, sys
import numpy as np
sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
from clipper.media import load_audio
base, out = sys.argv[1], sys.argv[2]
v = load_audio(base, 48000, mono=True)[0]
m = load_audio(out, 48000, mono=True)[0]
n = min(len(v), len(m)); v, m = v[:n], m[:n]
k = float(np.dot(m, v) / np.dot(v, v))
res = m - k * v
db = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
speech = np.convolve(np.abs(v), np.ones(4800) / 4800, "same") > 0.02
print(f"{os.path.basename(out)}: music+sfx is {db(k * v) - db(res):.1f} dB under the voice overall; "
      f"{db(k * v[speech]) - db(res[speech]):.1f} dB under it while he talks, "
      f"{db(k * v[speech]) - db(res[~speech]):.1f} dB in the gaps")
