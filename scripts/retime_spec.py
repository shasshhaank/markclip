"""Re-time a spec after its base edit was rebuilt (different cuts shift every moment).

Aligns the old and new caption words (same speech, so the same words), then moves every time in the spec ("t", "t0",
"t1", "strike", "t_out", nested ones too: icons, items, chips, counters, music, sfx) along with the words around it:
piecewise linear between matched words, a plain shift beyond the first or last one. Song offsets ("start") stay.

usage: retime_spec.py OLD_SPEC.json OLD_WORDS.json NEW_WORDS.json NEW_SPEC.json [--base B] [--words W] [--out O]"""
import argparse, difflib, json, re

import numpy as np

TIME_KEYS = {"t", "t0", "t1", "strike", "t_out"}


def anchors(old, new):
    norm = lambda w: re.sub(r"[^\w']", "", w["w"].lower())
    sm = difflib.SequenceMatcher(None, [norm(w) for w in old], [norm(w) for w in new], autojunk=False)
    pts = sorted((old[i + k][key], new[j + k][key]) for i, j, n in sm.get_matching_blocks() for k in range(n)
                 for key in ("s", "e"))
    mono = []
    for a, b in pts:                                  # keep the map increasing in both directions
        if not mono or (a > mono[-1][0] and b > mono[-1][1]):
            mono.append((a, b))
    matched = sum(n for _, _, n in sm.get_matching_blocks())
    return np.array(mono), matched / max(1, len(old))


def mapper(pts):
    xo, xn = pts[:, 0], pts[:, 1]

    def f(t):
        if t <= xo[0]:
            return round(t + xn[0] - xo[0], 2)
        if t >= xo[-1]:
            return round(t + xn[-1] - xo[-1], 2)
        return round(float(np.interp(t, xo, xn)), 2)
    return f


def walk(x, f, moved):
    if isinstance(x, dict):
        for k, v in x.items():
            if k in TIME_KEYS and isinstance(v, (int, float)):
                x[k] = f(v)
                moved.append(x[k] - v)
            else:
                walk(v, f, moved)
    elif isinstance(x, list):
        for v in x:
            walk(v, f, moved)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("old_words"); ap.add_argument("new_words"); ap.add_argument("new_spec")
    ap.add_argument("--base"); ap.add_argument("--words"); ap.add_argument("--out")
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    pts, share = anchors(json.load(open(a.old_words)), json.load(open(a.new_words)))
    moved = []
    for key in ("elements", "music", "sfx"):
        walk(spec.get(key, []), mapper(pts), moved)
    for key in ("base", "words", "out"):
        if getattr(a, key):
            spec[key] = getattr(a, key)
    json.dump(spec, open(a.new_spec, "w"), indent=1, ensure_ascii=False)
    print(f"{a.new_spec}: {share:.0%} of old words matched; {len(moved)} times moved, "
          f"shift {min(moved, default=0):+.2f} to {max(moved, default=0):+.2f} s")


if __name__ == "__main__":
    main()
