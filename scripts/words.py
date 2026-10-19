"""markclip step 4: caption word timings taken from the FINAL base edit's own audio (Whisper large), so every caption
lands when the word is heard (source times remapped through jump cuts ran up to 0.9 s late). Word times then come
from short Whisper passes over each voiced stretch (retime_by_pauses), so no caption lights up inside a pause.

Also repairs Whisper's punctuation so no capital ever appears mid-sentence: when a capitalised word follows a word
without . ? !, the full stop Whisper dropped is restored ("fight The" -> "fight. The"); a word after . ? ! gets its
capital. Proper nouns and "I" are left alone (--keep adds names).

usage: words.py BASE.mp4 OUT.json [--fix wrong=right ...] [--keep Name ...] [--insert word@s-e ...]
                [--retime word@near=start ...] [--period-after word@time ...]"""
import argparse, json, os, sys

sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))

KEEP = {"I", "I'm", "I've", "I'd", "I'll", "YouTube", "Instagram"}   # + --keep names
LANG = os.environ.get("MARKCLIP_LANG", "en")      # Whisper's language; the English prompt only steers English
PUNCT_PROMPT = "So, I think that's right. And then he said, \"No, actually.\" It ends there, with the two of them." \
    if LANG == "en" else None


def transcribe_words(path, chunk=24.0, overlap=2.0):
    """Whisper large in 24 s chunks with a punctuated example prompt: one long pass can drift into lowercase run-on
    text with no full stops ("so i think she is"), which would put stray lowercase/caps on screen."""
    import mlx_whisper
    from clipper.media import load_audio
    full = load_audio(path, 16000, mono=True)[0]
    dur = len(full) / 16000
    cands, c0 = [], 0.0
    while c0 < dur - 0.05:
        a0, a1 = max(0.0, c0 - overlap), min(dur, c0 + chunk + overlap)
        r = mlx_whisper.transcribe(full[int(a0 * 16000):int(a1 * 16000)], path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
                                   word_timestamps=True, condition_on_previous_text=False, language=LANG,
                                   initial_prompt=PUNCT_PROMPT)
        for sg in r["segments"]:
            for w in sg["words"]:
                if w["word"].strip():
                    s_, e_ = w["start"] + a0, w["end"] + a0
                    core = c0 <= (s_ + e_) / 2 < min(dur, c0 + chunk)
                    cands.append({"w": w["word"].strip(), "s": round(s_, 3), "e": round(e_, 3), "core": core})
        c0 += chunk
    # each chunk's own core first; a word only its neighbour heard (Whisper skipped it at a chunk edge) fills the hole
    words = [w for w in cands if w["core"]]
    for w in cands:
        same = lambda k: k["w"].lower().strip(".,?!") == w["w"].lower().strip(".,?!") and abs(k["s"] - w["s"]) < 0.4
        if not w["core"] and not any((k["s"] < w["e"] - 0.02 and w["s"] + 0.02 < k["e"]) or same(k) for k in words):
            words.append(w)
    out = []
    for w in sorted(words, key=lambda w: w["s"]):
        w.pop("core", None)
        p = out[-1] if out else None
        if p and p["w"].lower().strip(".,?!") == w["w"].lower().strip(".,?!") and w["s"] < p["e"]:
            p["w"], p["e"] = w["w"], max(p["e"], w["e"])  # both chunks heard one word at their seam: keep one copy,
            continue                                     # spelled as the later chunk heard it (it knows what follows)
        out.append(w)
    return out


def loudness(audio, sr=16000, hop=0.01):
    """Per-10 ms RMS of the voice and a silence threshold well below the speaking level."""
    import numpy as np
    n = int(hop * sr)
    rms = np.sqrt(np.convolve(audio.astype(np.float64) ** 2, np.ones(n) / n, "same")[::n])
    return rms, 0.15 * np.median(rms[rms > np.percentile(rms, 40)])


def retime_by_pauses(words, audio, sr=16000, merge=0.2, pad=0.12):
    """Whisper's word starts drift on long chunks with pauses: a word can start where the previous one ended ("person
    ... who"), so its caption lights up early, or late. Re-time every word from short passes: the audio is cut at its
    real pauses and each voiced stretch is transcribed alone (Whisper times words well on short audio, and no word can
    land inside a pause). Text stays as the main pass wrote it; matched words take the new times."""
    import difflib, re
    import mlx_whisper
    rms, thr = loudness(audio)
    loud = rms > thr
    segs, k = [], 0
    while k < len(loud):
        if loud[k]:
            j = k
            while j < len(loud) and (loud[j] or loud[j:j + int(merge * 100)].any()):
                j += 1
            if j - k >= 8:
                segs.append((k / 100, j / 100))
            k = j
        else:
            k += 1
    heard = []
    for a, b in segs:
        a0, b0 = max(0.0, a - pad), min(len(audio) / sr, b + pad)
        r = mlx_whisper.transcribe(audio[int(a0 * sr):int(b0 * sr)], path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
                                   word_timestamps=True, condition_on_previous_text=False, language=LANG)
        ws = [(w["word"], max(a, w["start"] + a0), min(b, w["end"] + a0)) for sg in r["segments"]
              for w in sg["words"] if w["word"].strip()]
        if ws:                                                 # a stretch starts with its first word; Whisper puts
            ws[0] = (ws[0][0], a, ws[0][2])                    # that start late ("a bucket", "is the first")
        heard += ws
    norm = lambda x: re.sub(r"[^\w']", "", x.lower())
    sm = difflib.SequenceMatcher(None, [norm(w["w"]) for w in words], [norm(h[0]) for h in heard], autojunk=False)
    n = 0
    for blk in sm.get_matching_blocks():
        for i in range(blk.size):
            w, h = words[blk.a + i], heard[blk.b + i]
            if abs(w["s"] - h[1]) > 0.02:
                n += 1
            w["s"], w["e"] = round(h[1], 2), round(max(h[2], h[1] + 0.05), 2)
    for a, b in zip(words, words[1:]):                         # unmatched words: keep them in order
        b["s"] = max(b["s"], a["s"])
    return n, len(segs)


def join_hyphens(words):
    """Whisper splits hyphenated words ("deep", "-seated"): join them so the caption reads "deep-seated"."""
    out = []
    for w in words:
        if out and w["w"].startswith("-"):
            out[-1]["w"] += w["w"]; out[-1]["e"] = w["e"]
        else:
            out.append(w)
    return out


def repair_case(words, keep):
    changes = []
    for i in range(1, len(words)):
        word, prev = words[i]["w"], words[i - 1]["w"]
        core = word.strip(".,?!\"'“”")
        if core and core[0].isupper() and core not in keep and not prev.rstrip().endswith((".", "?", "!")):
            words[i - 1]["w"] = prev.rstrip(",") + "."
            changes.append(f"{prev} {word} -> {words[i - 1]['w']} {word}")
        elif prev.rstrip().endswith((".", "?", "!")) and core and core[0].islower():
            words[i]["w"] = word[0].upper() + word[1:]
            changes.append(f"{prev} {word} -> {prev} {words[i]['w']}")
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("out")
    ap.add_argument("--fix", action="append", default=[], help="wrong=right, e.g. coach=coached")
    ap.add_argument("--keep", action="append", default=[], help="proper noun that may be capitalised mid-sentence")
    ap.add_argument("--insert", action="append", default=[],
                    help="word@start-end for a word Whisper never wrote down (check heard_check first), e.g. flag.@24.7-25.0")
    ap.add_argument("--retime", action="append", default=[],
                    help="word@near=start: the word nearest 'near' really starts at 'start' (when check.py's sync "
                         "window says it is heard elsewhere), e.g. a@30.5=29.98")
    ap.add_argument("--period-after", action="append", default=[],
                    help="word@seconds that ends a sentence Whisper ran on (e.g. flag@29.4 before 'I think')")
    a = ap.parse_args()
    words = transcribe_words(a.base)
    from clipper.media import load_audio
    moved = retime_by_pauses(words, load_audio(a.base, 16000, mono=True)[0])
    words = join_hyphens(words)
    for rt in a.retime:
        wd, rest = rt.rsplit("@", 1)
        near, start = (float(x) for x in rest.split("="))
        hit = min((w for w in words if w["w"].strip(".,?!").lower() == wd.lower()), key=lambda w: abs(w["s"] - near))
        hit["s"] = start
    for ins in a.insert:
        wd, span = ins.rsplit("@", 1)
        t0, t1 = (float(x) for x in span.split("-"))
        words.append({"w": wd, "s": t0, "e": t1})
    words.sort(key=lambda w: w["s"])
    fixes = dict(f.split("=", 1) for f in a.fix)
    for w in words:
        w["w"] = fixes.get(w["w"], w["w"])
    force = {"I", "I'm", "I've", "I'd", "I'll", "YouTube", "Instagram"} | set(a.keep)   # always capitalised
    canon = {k.lower(): k for k in force}
    for w in words:                                            # "i" -> "I", names in their real casing
        core = w["w"].strip(".,?!\"'")
        if core.lower() in canon:
            w["w"] = w["w"].replace(core, canon[core.lower()])
    for pa in a.period_after:
        wd, t = pa.rsplit("@", 1)
        hit = min((w for w in words if w["w"].strip(".,") == wd), key=lambda w: abs(w["s"] - float(t)))
        if not hit["w"].endswith((".", "?", "!")):
            hit["w"] = hit["w"].rstrip(",") + "."
    changes = repair_case(words, KEEP | set(a.keep))
    json.dump(words, open(a.out, "w"), indent=0)
    print(f"{a.out}: {len(words)} words; case repairs: {changes or 'none'}; re-timed over voiced stretches (words, stretches): {moved}")
    print(" ".join(f"{w['w']}@{w['s']:.2f}" for w in words))


if __name__ == "__main__":
    main()
