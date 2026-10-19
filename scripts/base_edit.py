"""markclip step 3, the base edit: a clean 9:16 talking edit of one moment (1920x1080 with --long), cut with
ClipIt's audio tools.

House rules built in (learned from reviews of earlier versions):
  * CUT LITTLE. Only repeats/restarts (dedupe.py), long fillers (an "um" of 0.45 s+, or one inside 0.9 s+ of pause)
    and dead air of 1 s+ are cut; short pauses and short fillers stay, with breathing room around every word (an
    earlier version cut every 0.45 s pause and split inside stretched words: too many jump cuts, clipped words).
    A cut that would remove under MIN_CUT s is skipped (it would land mid-voice); the clip starts just before the
    voice onset, never on it.
  * DIRECT CUTS, NO SLIDING. frame_base.py frames each source camera shot with one fixed crop (ClipIt's tracking slid
    toward the new face after camera changes); a jump cut inside one camera shot switches wide <-> tight framing.
  * Tangents are removed with --drop a-b (source seconds); a cut starts at a word's own start time.
  * Words whose time span swallowed a pause can be --retime'd; typos --fix'ed.
  * Podcast close-ups stay full-frame (no "fit" shrink into blurred strips).
  * No captions, no title here: render.py draws them (Inter / Instrument Serif only).
Writes OUT.plan.json (the source-to-output map render.py needs for duo split screens) and OUT.voice.wav; frame_base.py
then writes OUT, OUT.split.mp4 (not with --long) and OUT.crops.json (--preview stops after the plan).

usage: base_edit.py VIDEO --start S --end E --out OUT [--drop a-b ...] [--fix wrong=right ...]
                    [--retime old=new[:end] ...] [--keep-repeat "words" ...] [--no-dedupe] [--preview N]
                    [--cut a-b ...] [--recheck] [--long]"""
import argparse, copy, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CLIPIT = os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit"))
sys.path.insert(0, CLIPIT)
import numpy as np  # noqa: E402
import clip  # noqa: E402  (ClipIt's CLI module: work())
from clipper import audio as A  # noqa: E402
from clipper.media import load_audio, save_audio  # noqa: E402
from clipper.transcribe import snap_speech  # noqa: E402
from dedupe import find_repeats  # noqa: E402

SR = A.SR
DEAD_AIR = 1.0          # only silences at least this long are cut
KEEP_AFTER, KEEP_BEFORE = 0.22, 0.15   # breathing room left around words at a dead-air cut
MIN_CUT = 0.2           # a repeat whose cut would remove less than this stays: a tiny cut lands mid-voice for nothing
LONG_FILLER, LONG_FILLER_SPAN = 0.45, 0.9
LANG = os.environ.get("MARKCLIP_LANG", "en")      # Whisper's language; the disfluent prompt is English only
VERBATIM_PROMPT = "Umm, so, so I I think, like, you know, uh, it's it's like that that, and and I I mean, yeah." \
    if LANG == "en" else None


def verbatim_transcript(video, t0, t1, wd, chunk=24.0, overlap=2.0):
    """Word-for-word transcript of the clip window (Whisper large, disfluent prompt) so spoken repeats and restarts
    ("I I", "the the", "if you if a") are kept for dedupe; ClipIt's transcript tidies them away. Transcribed in
    24 s chunks (one long pass skipped a whole opening once); each word is kept from the chunk whose core holds it.
    Cached in wd."""
    cache = os.path.join(wd, f"verbatim_{t0:.1f}_{t1:.1f}{'' if LANG == 'en' else '_' + LANG}.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    import mlx_whisper
    words, segs = [], []
    c0 = t0
    while c0 < t1 - 0.05:
        a0, a1 = max(t0, c0 - overlap), min(t1, c0 + chunk + overlap)
        audio = load_audio(video, 16000, mono=True, start=a0, dur=a1 - a0)[0]
        r = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/whisper-large-v3-mlx", word_timestamps=True,
                                   language=LANG, condition_on_previous_text=False, initial_prompt=VERBATIM_PROMPT)
        core0, core1 = c0, min(t1, c0 + chunk)
        for sg in r["segments"]:
            mid = (sg["start"] + sg["end"]) / 2 + a0
            if core0 <= mid < core1:
                segs.append({"start": round(sg["start"] + a0, 3), "end": round(sg["end"] + a0, 3),
                             "text": sg["text"].strip()})
            for w in sg.get("words", []):
                m = (w["start"] + w["end"]) / 2 + a0
                if core0 <= m < core1:
                    words.append({"w": w["word"].strip(), "s": round(w["start"] + a0, 3),
                                  "e": round(w["end"] + a0, 3), "p": round(w.get("probability", 1.0), 3)})
        c0 += chunk
    words.sort(key=lambda w: w["s"])
    tr = {"language": LANG, "lang_conf": 1.0, "lang_probs": [[LANG, 1.0]], "segments": segs, "words": words,
          "model": "large"}
    os.makedirs(wd, exist_ok=True)
    json.dump(tr, open(cache, "w"))
    return tr


def merge_backbone(verb, back, gap=1.0):
    """The verbatim pass can skip a whole stretch (a disfluent prompt sometimes makes Whisper drop a chunk). Fill every
    stretch of >= `gap` s with no verbatim word from ClipIt's normal transcript, so no speech is ever treated as
    silence. Only fills real gaps, so a word is never listed twice (which dedupe would read as a repeat)."""
    vw = sorted(verb, key=lambda w: w["s"])
    out = list(vw)
    for w in back:
        m = (w["s"] + w["e"]) / 2
        if not any(v["s"] - gap / 2 <= m <= v["e"] + gap / 2 for v in vw):
            out.append(dict(w))
    return sorted(out, key=lambda w: w["s"])


def voiced(env, t0, t1, thr, min_len=0.35):
    """True when [t0, t1] holds at least min_len s of audio above the speech threshold (20 ms frames)."""
    a, b = int(t0 * 50), int(t1 * 50)
    return int((env[a:b] > thr).sum()) >= min_len * 50


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video"); p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True); p.add_argument("--out", required=True)
    p.add_argument("--drop", action="append", default=[], help="a-b source seconds to cut out (a tangent)")
    p.add_argument("--fix", action="append", default=[], help="wrong=right transcript fix")
    p.add_argument("--retime", action="append", default=[], help="OLD_START=NEW_START[:NEW_END]")
    p.add_argument("--keep-repeat", action="append", default=[], help="a repeat dedupe must keep (veto)")
    p.add_argument("--no-dedupe", action="store_true")
    p.add_argument("--cut", action="append", default=[], help="a-b source seconds of audio to remove exactly (a stutter)")
    p.add_argument("--long", action="store_true",
                   help="long form: a 1920x1080 base (no split track) for a 16:9 video without subtitles")
    p.add_argument("--recheck", action="store_true",
                   help="after the edit, transcribe it again and cut any repeat the first pass missed (one retry)")
    p.add_argument("--preview", type=float, help="plan only: write OUT.plan.json and OUT.voice.wav, skip the render")
    a = p.parse_args()

    from clipper.transcribe import transcribe
    wd = clip.work(a.video)
    back = copy.deepcopy(transcribe(a.video, wd, model="large"))          # coverage + sentence segments
    verb = verbatim_transcript(a.video, max(0.0, a.start - 4), a.end + 4, wd)  # repeats and restarts
    tr = back
    lo, hi = max(0.0, a.start - 4), a.end + 4
    tr["words"] = [w for w in back["words"] if not lo <= w["s"] < hi] + \
        merge_backbone(verb["words"], [w for w in back["words"] if lo <= w["s"] < hi])
    tr["words"].sort(key=lambda w: w["s"])
    drops = [tuple(float(x) for x in d.split("-")) for d in a.drop]
    fixes = dict(f.split("=", 1) for f in a.fix)
    retime = {round(float(o), 2): [float(x) for x in n.split(":")] for o, n in (r.split("=") for r in a.retime)}

    words = []
    for w in tr["words"]:
        rt = retime.get(round(w["s"], 2))
        if rt:
            w["s"], w["e"] = rt[0], (rt[1] if len(rt) > 1 else w["e"])
        if any(d0 <= w["s"] < d1 for d0, d1 in drops):
            continue
        txt = w["w"].strip()
        if txt.startswith(">>"):
            txt = txt[2:].strip()
        txt = fixes.get(txt, txt)
        if not txt or (txt.startswith("[") and txt.endswith("]")):
            continue
        w["w"] = txt
        w["filler"] = txt.strip(" ,.").lower() in ("um", "uh", "umm", "uhh", "hmm", "erm")
        words.append(w)
    words.sort(key=lambda w: w["s"])

    s0, s1, clean = snap_speech(a.video, a.start, a.end, tr)
    if abs(s0 - a.start) > 0.3 or abs(s1 - a.end) > 0.3:
        print(f"  clip moved to {s0:.2f}-{s1:.2f}s so it starts and ends on whole sentences")
    if not clean:
        print("  ! no clear pause at one end; check the first and last words with heard_check.py")
    inside = [w for w in words if w["s"] >= s0 - 0.05 and w["s"] < s1 + 0.05]

    allw = sorted(tr["words"], key=lambda w: w["s"])          # every transcribed word, dropped ones included
    starts = [w["s"] for w in allw]
    import bisect

    def next_start(w):                                          # a cut never runs into the next word
        k = bisect.bisect_right(starts, w["s"] + 1e-6)
        return allw[k]["s"] if k < len(allw) else 1e9

    def prev_end(w):
        k = bisect.bisect_left(starts, w["s"] - 1e-6) - 1
        return allw[k]["e"] if k >= 0 else -1e9

    removed = set()
    if not a.no_dedupe:
        removed, notes = find_repeats([w for w in inside], a.keep_repeat)
        for n in notes:
            print("  dedupe", n)
    for i, w in enumerate(inside):                      # fillers: only long ones go (a short "um" is natural)
        if w.get("filler"):
            gap_b = w["s"] - (inside[i - 1]["e"] if i > 0 else w["s"])
            gap_a = (inside[i + 1]["s"] if i + 1 < len(inside) else w["e"]) - w["e"]
            if (w["e"] - w["s"]) >= LONG_FILLER or (w["e"] - w["s"]) + gap_b + gap_a >= LONG_FILLER_SPAN:
                removed.add(i)
                print(f"  filler: drop '{w['w']}' at {w['s']:.2f}s ({w['e'] - w['s']:.2f}s long)")

    # keep-ranges: cut around every removed repeat or long filler, and at dead air >= DEAD_AIR
    kept = [(i, w) for i, w in enumerate(inside) if i not in removed]
    if not kept:
        sys.exit("nothing left to keep")
    # speech-presence guard: never cut a "pause" that actually holds untranscribed speech
    mono = load_audio(a.video, 16000, mono=True)[0]
    env = np.array([np.sqrt(np.mean(mono[k:k + 320] ** 2)) for k in range(0, len(mono) - 320, 320)])
    spoken = np.concatenate([env[int(w["s"] * 50):int(w["e"] * 50)] for _, w in kept])
    thr = 0.3 * float(np.median(spoken)) if spoken.size else 0.01
    in_drop = lambda t0, t1: any(d0 < t1 and t0 < d1 for d0, d1 in drops)
    ranges = []
    seg_a = max(s0, kept[0][1]["s"] - 0.12, prev_end(kept[0][1]) + 0.02)
    lo, k = prev_end(kept[0][1]) + 0.02, int(seg_a * 50)     # start just before the voice, never on it
    while k - 1 > lo * 50 and env[k - 1] > 0.25 * thr and seg_a - (k - 1) / 50 < 0.3:
        k -= 1
    seg_a = max(lo, k / 50 - 0.06)
    (pi, pw) = kept[0]
    for i, w in kept[1:]:
        gone = [inside[k] for k in range(pi + 1, i) if k in removed]
        if gone:                                         # a repeat or a long filler: cut around it, nothing more
            end_a = max(pw["e"] + 0.02, min(pw["e"] + 0.12, gone[0]["s"] - 0.01, next_start(pw) - 0.02))
            nxt_a = min(w["s"] - 0.02, max(w["s"] - 0.10, gone[-1]["e"] + 0.01, prev_end(w) + 0.02))
            if nxt_a - end_a >= MIN_CUT:
                ranges.append([seg_a, end_a])
                seg_a = nxt_a
            else:
                print(f"  kept '{' '.join(g['w'] for g in gone)}': its cut would be only {nxt_a - end_a:.2f}s")
        elif w["s"] - pw["e"] >= DEAD_AIR:
            g0, g1 = pw["e"] + 0.1, w["s"] - 0.1
            if not in_drop(g0, g1) and voiced(env, g0, g1, thr):
                print(f"  ! kept {g0:.2f}-{g1:.2f}s: speech the transcript missed (check heard_check)")
            else:
                ranges.append([seg_a, min(pw["e"] + KEEP_AFTER, next_start(pw) - 0.02)])
                seg_a = max(w["s"] - KEEP_BEFORE, prev_end(w) + 0.02)
        pi, pw = i, w
    ranges.append([seg_a, min(s1 + 0.1, pw["e"] + 0.3, next_start(pw) - 0.02)])
    for c0, c1 in (tuple(float(x) for x in c.split("-")) for c in a.cut):      # exact audio cuts
        nxt = []
        for r0, r1 in ranges:
            if c1 <= r0 or c0 >= r1:
                nxt.append([r0, r1])
            else:
                if c0 > r0:
                    nxt.append([r0, c0])
                if c1 < r1:
                    nxt.append([c1, r1])
        ranges = nxt
    ranges = [r for r in ranges if r[1] - r[0] > 0.04]

    t = sum(r1 - r0 for r0, r1 in ranges)
    full = load_audio(a.video, SR)
    segs = [full[:, int(r0 * SR):int(r1 * SR)] for r0, r1 in ranges]
    voice = np.concatenate([A.fade(x, 0.01, 0.01) if x.shape[1] > 2 * int(0.01 * SR) else x for x in segs], axis=1)
    apath = os.path.splitext(a.out)[0] + ".voice.wav"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    save_audio(apath, A.normalize(voice), SR)
    out_times, o = [], 0.0
    for r0, r1 in ranges:
        out_times.append([round(o, 4), round(o + r1 - r0, 4)])
        o += r1 - r0
    plan_path = os.path.splitext(a.out)[0] + ".plan.json"
    json.dump({"src": os.path.abspath(a.video), "ranges": ranges, "out": out_times, "removed": sorted(removed)},
              open(plan_path, "w"), indent=1)
    if a.preview:
        print(f"  preview only: {len(ranges)} pieces, {t:.1f}s")
        return
    import subprocess
    env = dict(os.environ, **({"MARKCLIP_FORMAT": "long"} if a.long else {}))
    subprocess.run([sys.executable, os.path.join(HERE, "frame_base.py"), a.video, plan_path, apath, a.out], check=True,
                   env=env)
    print(f"  {len(ranges)} pieces, {t:.1f}s, cuts only at repeats / long fillers / dead air >= {DEAD_AIR:.0f}s; "
          f"plan -> {plan_path}")
    if a.recheck:                                    # cached per edit: a rebuilt base never reuses a stale transcript
        edit_id = hashlib.sha1(json.dumps(ranges).encode()).hexdigest()[:10]
        rwd = os.path.join(wd, "recheck", f"{os.path.splitext(os.path.basename(a.out))[0]}_{edit_id}")
        heard = verbatim_transcript(a.out, 0.0, t, rwd)["words"]
        rm, notes = find_repeats(heard, a.keep_repeat)
        if rm:
            def to_src(tb):
                for (o0, o1), (r0, _) in zip(out_times, ranges):
                    if o0 <= tb <= o1:
                        return r0 + (tb - o0)
            cuts = []
            for k in sorted(rm):
                nxt = next((heard[j]["s"] for j in range(k + 1, len(heard)) if j not in rm), heard[k]["e"])
                s0_, s1_ = to_src(heard[k]["s"] - 0.02), to_src(nxt - 0.02)
                if s0_ is not None and s1_ is not None and s1_ - s0_ >= MIN_CUT:
                    cuts.append(f"{s0_:.3f}-{s1_:.3f}")
            for n in notes:
                print("  recheck", n)
            if not cuts:
                print("  recheck: only repeats too short to cut cleanly are left")
                return
            argv = [x for x in sys.argv[1:] if x != "--recheck"]
            for c in cuts:
                argv += ["--cut", c]
            print(f"  re-cutting with {cuts}")
            subprocess.run([sys.executable, os.path.abspath(__file__)] + argv, check=True)
        else:
            print("  recheck: no repeats left")


if __name__ == "__main__":
    main()
