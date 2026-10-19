"""markclip QA: every per-clip gate in one command, measured from the files (nothing copied from the spec).
  1. spec lint (sentence case, no all-caps, lines fit, captions json clean)
  2. output exists and its length = base length + tail (+-0.2 s)
  3. caption sync against the voice-only base: median between -0.10 and 0.00 s, at most 2 words off by >0.25 s, none
     by >0.5 s, >= 90% of words matched (captions are drawn 0.05 s early on purpose); a disagreement with the reference
     Whisper pass counts only if a short window starting at the caption time does not open with the word
  4. music + effects 9-14 dB under the voice (only when the spec has music)
  5. integrated loudness -14 +-1 LUFS, true peak below -0.5 dBFS
  6. nothing drawn over a face: faces found by an independent detector on the background-only render
     (render.py --bg-only) never intersect a caption / pill / chip / title box from the render log
  7. captions never travel: a phrase never moves mid-phrase, moves between phrases are jumps (>= 40 px), nothing
     else sits on the caption
  8. no bounce: between two cuts (jump cuts too) the zoom never decreases (punch-ins and push-ins hold to the next cut)
  9. eye level: per camera shot, the median eye height sits within 45 px of the layout's target (740 single, 1360
     split bottom; lower where a big close-up may not be zoomed further: faces stay under 42 % of the frame, zoom
     under 1.25x)
     (fails when more than 10% of shots miss)
  Long form ("format": "long"): no subtitles, so no caption sync (3) and no caption travel (7); the eye line is 450
  of 1080 for the full frame and the side layouts.
usage: check.py SPEC.json        prints MARKCLIP CHECK PASSED, or each failure and exits 1"""
import difflib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
import numpy as np  # noqa: E402
from lint_spec import lint  # noqa: E402

LANG = os.environ.get("MARKCLIP_LANG", "en")      # Whisper's language for the sync pass


def probe_dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout)


def loudness(p):
    err = subprocess.run(["ffmpeg", "-nostats", "-i", p, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])
    pk = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)[-1])
    return i, pk


def music_gap_db(base, out):
    from clipper.media import load_audio
    v = load_audio(base, 48000, mono=True)[0]
    m = load_audio(out, 48000, mono=True)[0]
    n = min(len(v), len(m)); v, m = v[:n], m[:n]
    k = float(np.dot(m, v) / np.dot(v, v))
    res = m - k * v
    db = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    return db(k * v) - db(res)


def sync_offsets(base, words, lead=0.05):
    """Caption start (shown `lead` s early) minus where an independent Whisper pass hears each word. Whisper's own
    word starts drift on long passes, so every disagreement over 0.25 s is settled by the audio itself: a short window
    starting at the caption time is transcribed alone, and the caption is in sync when that window opens with the word.
    Returns (offsets, rows for every disagreement)."""
    import mlx_whisper
    from clipper.media import load_audio
    norm = lambda x: re.sub(r"[^\w']", "", x.lower())
    said = lambda w: norm(w.get("src", w["w"]))   # "src": the word as heard, when the caption writes it another way
    caps = [(said(w), w["s"]) for w in words if said(w)]
    audio = load_audio(base, 16000, mono=True)[0]
    r = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/whisper-large-v3-mlx", word_timestamps=True,
                               condition_on_previous_text=False, language=LANG)
    heard = [(norm(w["word"]), w["start"]) for s in r["segments"] for w in s["words"] if norm(w["word"])]
    sm = difflib.SequenceMatcher(None, [c[0] for c in caps], [h[0] for h in heard], autojunk=False)
    off, rows = [], []
    for b in sm.get_matching_blocks():
        for i in range(b.size):
            (wd, s), h = caps[b.a + i], heard[b.b + i][1]
            d = s - lead - h
            if abs(d) > 0.25:
                win = audio[int(max(0, s - 0.08) * 16000):int((s + 0.7) * 16000)]   # does the word start right here?
                rw = mlx_whisper.transcribe(win, path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
                                            condition_on_previous_text=False, language=LANG)["text"]
                ok = any(difflib.SequenceMatcher(None, wd, norm(x)).ratio() >= 0.7    # "then" for "than"; "M-make"
                         for x in rw.replace("-", " ").split()[:3])
                rows.append((wd, s - lead, h, d, f"heard at the caption time ('{rw.strip()[:24]}')" if ok else
                             f"off (caption time hears '{rw.strip()[:24]}')"))
                d = 0.0 if ok else d
            off.append(d)
    return np.array(off), rows


def face_overlaps(path, spec):
    import cv2
    from clipper.reframe import MODEL
    out = spec["out"]
    logp = os.path.splitext(out)[0] + ".log.jsonl"
    if not os.path.exists(logp):
        return None
    bg = out.replace(".mp4", "_bg.mp4")
    if not os.path.exists(bg) or os.path.getmtime(bg) < os.path.getmtime(out):
        subprocess.run([sys.executable, os.path.join(HERE, "render.py"), path, "--bg-only"], check=True,
                       capture_output=True)
    log = [json.loads(l) for l in open(logp)]
    det = cv2.FaceDetectorYN.create(MODEL, "", (540, 960), 0.8, 0.3, 50)   # input size set per frame
    cap = cv2.VideoCapture(bg)
    hits, i = [], 0
    while True:
        ok, fr = cap.read()
        if not ok or i >= len(log):
            break
        if i % 2 == 0 and log[i]["layout"] != "statement":
            half = (fr.shape[1] // 2, fr.shape[0] // 2)         # 540x960 for a Short, 960x540 in long form
            det.setInputSize(half)
            _, f = det.detect(cv2.resize(fr, half, interpolation=cv2.INTER_AREA))
            raw = [[r[0] * 2, r[1] * 2, (r[0] + r[2]) * 2, (r[1] + r[3]) * 2] for r in (f if f is not None else [])]
            hair = [[r[0] - 0.1 * (r[3] - r[1]), r[1] - 0.35 * (r[3] - r[1]), r[2] + 0.1 * (r[3] - r[1]), r[3]]
                    for r in raw]                   # render.py's hair margin (35 % up, 10 % a side of the box height)
            caption = [("caption", log[i]["cap"])] if log[i]["cap"] else []
            for kind, b in [(b[0], b[1:]) for b in log[i]["boxes"]] + caption:
                hair_ok = kind == "title" or (kind == "caption" and log[i].get("cap_hair"))
                faces = raw if hair_ok else hair              # titles (and a caption the render logged as placed
                                                              # by the hair fallback) may touch hair, never a face
                if any(b[0] < fb[2] and fb[0] < b[2] and b[1] < fb[3] and fb[1] < b[3] for fb in faces):
                    hits.append(log[i]["t"])
        i += 1
    return hits


def caption_and_bounce(spec):
    out = []
    log = [json.loads(l) for l in open(os.path.splitext(spec["out"])[0] + ".log.jsonl")]
    shots = json.load(open(os.path.splitext(spec["base"])[0] + ".faces.json"))["shots"]
    cuts = [s_["t0"] for s_ in shots]
    for a, b in zip(log, log[1:]):
        if a["cap"] and b["cap"]:
            ya, yb = (a["cap"][1] + a["cap"][3]) / 2, (b["cap"][1] + b["cap"][3]) / 2
            same = abs((a["cap"][2] - a["cap"][0]) - (b["cap"][2] - b["cap"][0])) < 2 and a["layout"] == b["layout"]
            if ya != yb and (same or abs(ya - yb) < 40):
                out.append(f"caption moves at {b['t']:.2f}s")
        new_shot = any(a["t"] - 0.02 < c <= b["t"] + 0.02 for c in cuts)
        if b["layout"] == a["layout"] and not new_shot and b["zoom"] < a["zoom"] - 1e-4:
            out.append(f"zoom eases back at {b['t']:.2f}s (bounce)")
    for r in log:
        if r["cap"]:
            for bx in r["boxes"]:
                c = r["cap"]
                if bx[1] < c[2] and c[0] < bx[3] and bx[2] < c[3] and c[1] < bx[4]:
                    out.append(f"{bx[0]} on the caption at {r['t']:.2f}s")
    return out[:6]


def eye_level(spec):
    import cv2
    from clipper.reframe import MODEL
    log = [json.loads(l) for l in open(os.path.splitext(spec["out"])[0] + ".log.jsonl")]
    fa = json.load(open(os.path.splitext(spec["base"])[0] + ".faces.json"))
    shots = fa["shots"]
    long = spec.get("format") == "long"             # one eye line (450 of 1080) for the speaker and the side layout
    fh = 1080 if long else 1920
    det = cv2.FaceDetectorYN.create(MODEL, "", (540, 960), 0.8, 0.3, 50)   # input size set per frame
    cap = cv2.VideoCapture(spec["out"].replace(".mp4", "_bg.mp4"))
    per, i = {}, 0
    while True:
        ok, fr = cap.read()
        if not ok or i >= len(log):
            break
        lay = log[i]["layout"]
        if i % 2 == 0 and lay in ("single", "split"):
            half = (fr.shape[1] // 2, fr.shape[0] // 2)         # 540x960 for a Short, 960x540 in long form
            det.setInputSize(half)
            _, f = det.detect(cv2.resize(fr, half, interpolation=cv2.INTER_AREA))
            fs = [r for r in (f if f is not None else []) if long or lay == "single" or r[1] * 2 > 960]
            if fs:
                r = max(fs, key=lambda r: r[2] * r[3])
                k = next((j for j, s_ in enumerate(shots) if s_["t0"] <= log[i]["t"] < s_["t1"]), -1)
                per.setdefault((k, lay), []).append(float(r[5] + r[7]) - log[i]["dy"])
        i += 1
    errs = []
    for (k, lay), ys in per.items():
        sh = shots[k] if k >= 0 else {}
        ey = sh.get("eye_y")
        if len(ys) < 4 or ey is None or not 250 <= ey <= 1350:
            continue
        want, y0, y1 = (450.0, 0, 1080) if long else (740.0, 0, 1920) if lay == "single" else (1360.0, 960, 1920)
        if lay == "split" and not long:
            errs.append(abs(float(np.median(ys)) - want))      # framed from the source: eyes at 1360, no zoom cap
            continue
        z = max(1.0, (want - y0) / ey, (y1 - want) / (fh - ey))
        zmax = min(1.25, max(1.0, 0.42 * fh / sh["face"][3])) if sh.get("face") else 1.25   # render.py's face cap
        if z > zmax:
            want = float(np.clip(want, y1 - (fh - ey) * zmax, y0 + ey * zmax))
        errs.append(abs(float(np.median(ys)) - want))
    return errs


def main(path):
    spec = json.load(open(path))
    fails = []
    for x in lint(spec, os.getcwd()):
        fails.append("lint: " + x)
    out, base = spec["out"], spec["base"]
    if not os.path.exists(out):
        fails.append(f"output missing: {out}")
    else:
        want = probe_dur(base) + spec.get("tail", 0)
        got = probe_dur(out)
        print(f"  duration {got:.2f}s (base + tail {want:.2f}s)")
        if abs(got - want) > 0.2:
            fails.append(f"duration {got:.2f}s, expected {want:.2f}s")
        words = json.load(open(spec["words"])) if spec.get("words") else []
    if os.path.exists(out) and spec.get("format") != "long" and spec.get("captions") is not False:
        off, rows = sync_offsets(base, words)
        late = int((abs(off) > 0.25).sum())
        for wd, c, h, d, verdict in rows:
            if verdict.startswith("off"):
                print(f"    {wd:12s} caption {c:6.2f} heard {h:6.2f} ({d:+.2f})")
        print(f"  caption sync: {len(off)}/{len(words)} words matched, median {np.median(off):+.3f}s, "
              f"{late} beyond 0.25s, worst {off[np.argmax(abs(off))]:+.2f}s")
        if not (-0.10 <= np.median(off) <= 0.0) or late > 2 or abs(off).max() > 0.5 or len(off) < 0.9 * len(words):
            fails.append("caption sync outside tolerance")
    elif os.path.exists(out):
        print("  caption sync: no subtitles in this format")
    if os.path.exists(out):
        if spec.get("music"):
            g = music_gap_db(base, out)
            print(f"  music + effects {g:.1f} dB under the voice")
            if not 9.0 <= g <= 14.0:
                fails.append(f"music level {g:.1f} dB under the voice (want 9-14)")
        hits = face_overlaps(path, spec)
        if hits is not None:
            print(f"  faces clear: {len(hits)} frames with an overlay on a face")
            if hits:
                fails.append(f"overlay on a face at {sorted(set(round(h, 1) for h in hits))[:8]}")
        for x in caption_and_bounce(spec):
            fails.append(x)
        errs = eye_level(spec)
        print(f"  eye level: {len(errs)} shots, worst {max(errs or [0]):.0f} px off")
        if errs and sum(e > 45 for e in errs) > 0.1 * len(errs):
            fails.append("eye level drifts across shots")
        i, pk = loudness(out)
        print(f"  loudness {i:.1f} LUFS, peak {pk:.1f} dBFS")
        if abs(i + 14) > 1.0 or pk > -0.5:
            fails.append(f"loudness {i:.1f} LUFS / peak {pk:.1f} dBFS (want -14+-1 LUFS, peak < -0.5)")
    for x in fails:
        print("  FAIL", x)
    if fails:
        print("MARKCLIP CHECK FAILED")
        sys.exit(1)
    print("MARKCLIP CHECK PASSED")


if __name__ == "__main__":
    main(sys.argv[1])
