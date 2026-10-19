"""markclip step 5: faces and camera shots of a base edit, for eye-level matching and face-safe layout.
Every frame: YuNet faces (ClipIt's model) with eye landmarks. Shots: split at the base's own jump cuts
(BASE.plan.json) and at camera-angle changes (big frame differences). Per shot: median eye position and face box of
the largest face. Writes BASE.faces.json.
usage: analyze_base.py BASE.mp4 [BASE.mp4 ...]"""
import json, os, sys
import cv2
import numpy as np

sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
from clipper.reframe import MODEL  # noqa: E402

DS = 0.5          # detect on a half-size frame (fast, still finds wide-shot faces)
CUT_DIFF = 18.0   # a camera change: frame difference above this AND 4x the local median (motion is not a cut)
CLUSTER = 0.3     # detections closer than this are one transition; the shot starts where it settles


def detect(det, fr):
    small = cv2.resize(fr, None, fx=DS, fy=DS, interpolation=cv2.INTER_AREA)
    det.setInputSize((small.shape[1], small.shape[0]))
    _, faces = det.detect(small)
    out = []
    for f in (faces if faces is not None else []):
        x, y, w, h = (float(v) / DS for v in f[:4])
        ey = (float(f[5]) + float(f[7])) / 2 / DS
        ex = (float(f[4]) + float(f[6])) / 2 / DS
        out.append([round(x), round(y), round(w), round(h), round(ey), round(ex), round(float(f[14]), 3)])
    return sorted(out, key=lambda b: -b[2] * b[3])


def analyze(base):
    cap = cv2.VideoCapture(base)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    det = cv2.FaceDetectorYN.create(MODEL, "", (540, 960), 0.8, 0.3, 50)   # >= 0.8: real faces score 0.92+, mics and hands 0.6-0.77
    frames, diffs, prev = [], [0.0], None
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(detect(det, fr))
        tiny = cv2.cvtColor(cv2.resize(fr, (64, 114), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            diffs.append(float(np.mean(np.abs(tiny - prev))))
        prev = tiny
        i += 1
    dur = i / fps
    d = np.array(diffs)
    raw = [k for k in range(1, len(d)) if d[k] > CUT_DIFF and
           d[k] > 4 * (np.median(np.concatenate([d[max(0, k - 8):k], d[k + 1:k + 9]])) + 1e-3)]
    cuts = [0.0]
    for k in raw:
        tk = round(k / fps, 3)
        if tk - cuts[-1] < CLUSTER and cuts[-1] > 0:
            cuts[-1] = tk                       # same transition: move the cut to where it settles
        elif tk - cuts[-1] >= CLUSTER:
            cuts.append(tk)
    plan = os.path.splitext(base)[0] + ".plan.json"
    if os.path.exists(plan):                      # the base edit's own jump cuts are always cuts
        for o0, _ in json.load(open(plan))["out"][1:]:
            cuts = [c for c in cuts if abs(o0 - c) > 0.12]
            cuts.append(round(o0, 3))
    cuts = sorted(cuts) + [dur]
    shots = []
    for t0, t1 in zip(cuts, cuts[1:]):
        fs = [frames[k][0] for k in range(int(t0 * fps), min(len(frames), int(t1 * fps))) if frames[k]]
        if fs:
            a = np.array(fs, np.float32)
            shots.append({"t0": t0, "t1": t1, "eye_y": float(np.median(a[:, 4])), "eye_x": float(np.median(a[:, 5])),
                          "face": [float(np.median(a[:, j])) for j in range(4)], "seen": len(fs)})
        else:
            shots.append({"t0": t0, "t1": t1, "eye_y": None, "eye_x": None, "face": None, "seen": 0})
    out = {"fps": fps, "duration": dur, "frames": frames, "shots": shots}
    path = os.path.splitext(base)[0] + ".faces.json"
    json.dump(out, open(path, "w"))
    print(f"{path}: {i} frames, {len(shots)} shots; eye heights per shot: "
          f"{[None if s['eye_y'] is None else int(s['eye_y']) for s in shots]}")


if __name__ == "__main__":
    for b in sys.argv[1:]:
        analyze(b)
