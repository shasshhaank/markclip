"""markclip step 1: a whole episode's YouTube subtitles (ClipIt's track choice: uploader's own, else auto -orig, never
auto-translated) as OUTDIR/<id>.txt in ~10 s lines (timed words in <id>.json), to read chapters and pick moments
before downloading any video.
Sleeps between ids: bursts of YouTube requests get the IP bot-blocked.
usage: episode_subs.py OUTDIR VIDEO_ID [VIDEO_ID ...]"""
import glob, json, os, sys, tempfile, time
sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
from clipper import ytsubs

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for vid in sys.argv[2:]:
    url = f"https://www.youtube.com/watch?v={vid}"
    info = json.loads(ytsubs._ytdlp("-J", "--", url).stdout or "{}")
    choice = ytsubs.pick(info)
    print(vid, "track:", choice, flush=True)
    if not choice:
        continue
    kind, track = choice
    with tempfile.TemporaryDirectory() as d:
        ytsubs._ytdlp("--skip-download", "--write-subs" if kind == "own" else "--write-auto-subs", "--sub-langs", track,
                      "--sub-format", "json3", "-o", os.path.join(d, "s.%(ext)s"), "--", url)
        files = glob.glob(os.path.join(d, "*.json3"))
        if not files:
            print(vid, "no subtitle file", flush=True)
            continue
        words, segs = ytsubs.parse(json.load(open(files[0])))
    json.dump({"words": words, "segments": segs}, open(f"{out}/{vid}.json", "w"))
    with open(f"{out}/{vid}.txt", "w") as f:   # ~10 s lines, easy to read
        line, t0 = [], None
        for w in words:
            if t0 is None:
                t0 = w["s"]
            line.append(w["w"])
            if w["e"] - t0 >= 10:
                f.write(f"[{int(t0)//3600}:{int(t0)%3600//60:02d}:{int(t0)%60:02d}] {' '.join(line)}\n")
                line, t0 = [], None
        if line:
            f.write(f"[{int(t0)//3600}:{int(t0)%3600//60:02d}:{int(t0)%60:02d}] {' '.join(line)}\n")
    print(vid, len(words), "words", flush=True)
    time.sleep(8)
