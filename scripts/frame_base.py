"""markclip framing: render the base edit straight from the 16:9 source, one fixed 9:16 crop per camera shot.

Why: ClipIt's face tracking slid the crop toward the new face after every camera change; that
read as a "sliding keyframe". Here every source camera shot gets one crop, chosen from the median position of the
person speaking (largest face whose mouth moves most), so a camera change is a straight cut to the final framing.
A jump cut inside the same camera shot switches between a wide and a tight framing (like a second camera), so it never
reads as a jump. Eyes are framed at 38.5 % of the height (740 px of 1920) in every shot.

Also writes BASE.split.mp4 (1080x960, same timing): the bottom half of a split screen, cut from the 16:9 source with
a wider 9:8 window (eyes at 1360 of 1920 once placed under the panel) so the speaker is not over-zoomed, and
BASE.crops.json: per output piece the source shot, crop and face.

Options for other kinds of source (environment, so base_edit.py passes them through; all off by default):
  MARKCLIP_GRAPHICS=1  an explainer with full-screen graphics: a faceless or mostly bright shot (and any bright frame
      inside a presenter shot) is shown whole, not centre-cropped, scaled into a band centred at y 760 on its own
      border colour; a presenter shot that opens on a flash-in (black, white or fading frames) starts on its first
      clean frame.
  MARKCLIP_SPLIT_TOP_PAD=0.12  the split window may reach this share of its height above the source frame (its top
      edge repeated): for a speaker framed too high for the split eye line, in front of a plain wall.
  MARKCLIP_TEXT_BOXES="s0-s1:x0,y0,x1,y1;..."  the source's own burned-in labels (source seconds, source pixels),
      kept whole or left out like the built-in boxes.
  MARKCLIP_ERASE_TEXT=1  erase every burned-in label or logo the source shows (no other show's branding on screen),
      not only the ones a crop would cut.
  MARKCLIP_FORMAT=long  (base_edit.py --long) a 1920x1080 base for long form, no split track; the source's
      burned-in labels are always erased (side layouts would cut them; the edit's own chapter cards replace them).

usage (normally called by base_edit.py): frame_base.py SRC.mp4 PLAN.json AUDIO.wav OUT.mp4"""
import json, os, subprocess, sys
import cv2
import numpy as np

sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
from clipper.media import FFMPEG  # noqa: E402
from clipper.reframe import MODEL  # noqa: E402

LONG = os.environ.get("MARKCLIP_FORMAT") == "long"   # long form: a 1920x1080 base and no split track
W, H, FPS = (1920, 1080, 30) if LONG else (1080, 1920, 30)
EYE_FRAC = 450 / 1080 if LONG else 740 / 1920
TIGHT = 1.14            # the "second camera" on a jump cut inside one shot
FACE_FRAC = 0.42        # a face is never taller than this share of the frame
FACE_FRAC_SPLIT = 0.42  # ...or of the split's bottom half (head and shoulders under the panel)
TEXT_FIX_ZOOM = 2.2      # a text fix may enlarge the source at most this much
ZMAX = 1.15 if LONG else 1.85   # most zoom used to bring a wide shot's eyes to the eye line (keeps 1080p sharp; a
#                                 long-form wide shot stays wide)
PH = 960                # split: bottom half height
SPLIT_EYE = (1360 - PH) / PH   # eye height inside the split's bottom half
SPLIT_WIN = 0.74        # split window height as a share of the source height (wider than the 9:16 crop)
SHOW_TEXT = [(80, 40, 600, 84),        # where podcasts burn text into a 1920x1080 source: chapter label (top left),
             (80, 990, 1470, 1064),    # citation lower third (bottom left), logo (bottom right). A crop must never
             (1650, 976, 1870, 1066)]  # cut through one: it shows it whole or leaves it out.
EXTRA_TEXT = [(tuple(map(float, span.split("-"))), tuple(map(int, box.split(","))))     # MARKCLIP_TEXT_BOXES
              for span, box in (r.split(":") for r in os.environ.get("MARKCLIP_TEXT_BOXES", "").split(";") if r)]
GRAPHICS = os.environ.get("MARKCLIP_GRAPHICS") == "1"
ERASE_ALL = os.environ.get("MARKCLIP_ERASE_TEXT") == "1"     # erase every burned-in label or logo, not only cut ones
SPLIT_TOP_PAD = float(os.environ.get("MARKCLIP_SPLIT_TOP_PAD", 0))
FIT_CY, FIT_BAND = (540, 1080) if LONG else (760, 880)   # a graphic fills at most the band 320-1200 in a Short
#                                                           (clear of the caption line at 1395), the frame in long form
GRAPHIC_GRAY = 170      # a frame whose median gray is above this is a graphic (even if a cartoon face is found on it)
HOLD = 0.2              # a camera piece shorter than this (a stray frame of another angle) holds the previous frame
CUT_DIFF = 18.0


def text_on(grays, box):
    """The burned-in text box if it is on screen (thin bright strokes inside it, well above the same-size strip beside
    it), widened to where its strokes end (a chapter label is as long as its title); else None."""
    x0, y0, x1, y1 = (int(v / 2) for v in box)                  # SHOW_TEXT is in 1920x1080, frames are 960x540
    h = y1 - y0
    r0 = y0 + h + 4 if y0 < 270 else y0 - h - 4
    ins, ref, cols = [], [], []
    for g in grays:
        hp = g - cv2.blur(g, (9, 9))
        ins.append(np.mean(hp[y0:y1, x0:x1] > 40)); ref.append(np.mean(hp[r0:r0 + h, x0:x1] > 40))
        cols.append((hp[y0:y1] > 40).any(0))
    if not (np.mean(ins) > 0.04 and np.mean(ins) > 2 * np.mean(ref)):
        return None
    if box[1] > 270:                                              # only the chapter label varies in length
        return box
    end = x1
    for x in np.flatnonzero(np.any(cols, 0)[x1:]) + x1:          # strokes running on past the box's right edge
        if x > end + 16:                                          # a gap wider than two letters: the text ended
            break
        end = x
    return box if end == x1 else (box[0], box[1], int(min(2 * end + 8, 2 * len(cols[0]))), box[3])


def scan(src, ranges):
    """Faces (score >= 0.8, with eye and mouth landmarks) and camera cuts for every source frame inside the ranges."""
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    det = cv2.FaceDetectorYN.create(MODEL, "", (960, 540), 0.8, 0.3, 50)
    pieces = []
    for r0, r1 in ranges:
        f_start = int(round(r0 * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_start)
        frames, diffs, prev, mouths = [], [], None, []
        for _ in range(max(1, int(round((r1 - r0) * fps)))):
            ok, fr = cap.read()
            if not ok:
                break
            small = cv2.resize(fr, (960, 540), interpolation=cv2.INTER_AREA)
            _, f = det.detect(small)
            sc = fr.shape[1] / 960
            faces = [[float(v) * sc for v in r[:14]] + [float(r[14])] for r in (f if f is not None else [])]
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
            tiny = cv2.resize(gray, (64, 36))
            diffs.append(0.0 if prev is None else float(np.mean(np.abs(tiny - prev))))
            prev = tiny
            mouths.append(gray)
            frames.append(faces)
        d = np.array(diffs)
        cuts = [0]
        for k in range(1, len(d)):
            loc = np.concatenate([d[max(0, k - 8):k], d[k + 1:k + 9]])
            if d[k] > CUT_DIFF and d[k] > 4 * (np.median(loc) + 1e-3) and k - cuts[-1] > 6:
                cuts.append(k)
        cuts.append(len(frames))
        for a, b in zip(cuts, cuts[1:]):
            sample = [mouths[a:b][i] for i in np.linspace(0, b - a - 1, min(5, b - a)).astype(int)]
            texts = [b for b in (text_on(sample, box) for box in SHOW_TEXT) if b]
            texts += [box for (e0, e1), box in EXTRA_TEXT if e0 < r0 + b / fps and r0 + a / fps < e1]
            pieces.append({"src0": r0 + a / fps, "src1": r0 + b / fps, "f0": f_start + a, "f1": f_start + b, "texts": texts,
                           "sc": float(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) / 960,
                           "frames": frames[a:b], "gray": mouths[a:b]})
    return pieces, fps


def speaker(piece):
    """Median box of the face whose mouth moves most (the person talking); the largest face if only one."""
    tracks = {}
    for fr_i, faces in enumerate(piece["frames"]):
        for f in faces:
            key = int(f[0] + f[2] / 2) // 160            # faces bucketed by horizontal position
            tracks.setdefault(key, []).append((fr_i, f))
    if not tracks:
        return None
    best, best_score = None, -1.0
    for key, items in tracks.items():
        if len(items) < max(3, len(piece["frames"]) * 0.3):
            continue
        motion = []
        for (i0, f0), (i1, f1) in zip(items, items[1:]):
            if i1 != i0 + 1:
                continue
            sc = piece.get("sc", 2.0)                        # full-res -> 960-wide analysis frame
            x0, y0 = int(f1[10] / sc), int(f1[11] / sc)        # mouth corners
            x1 = int(f1[12] / sc)
            g0, g1 = piece["gray"][i0], piece["gray"][i1]
            ya, yb = max(0, y0 - 12), min(g0.shape[0], y0 + 12)
            xa, xb = max(0, min(x0, x1) - 6), min(g0.shape[1], max(x0, x1) + 6)
            if yb > ya and xb > xa:
                motion.append(float(np.mean(np.abs(g1[ya:yb, xa:xb] - g0[ya:yb, xa:xb]))))
        size = np.median([f[2] * f[3] for _, f in items])
        score = (np.mean(motion) if motion else 0.0) * 10 + size / 1e5
        if score > best_score:
            best, best_score = items, score
    if best is None:
        best = max(tracks.values(), key=len)
    a = np.array([f for _, f in best])
    return {"cx": float(np.median(a[:, 0] + a[:, 2] / 2)), "eye_y": float(np.median((a[:, 5] + a[:, 7]) / 2)),
            "face_y": float(np.median(a[:, 1])), "face_h": float(np.median(a[:, 3])), "face_w": float(np.median(a[:, 2]))}


def window(sp, h_max, eye_frac, aspect, tight, sw, sh, face_frac=FACE_FRAC, texts=(), top_pad=0.0):
    """Source window of aspect w/h whose eyes sit at eye_frac of its height: as tall as h_max allows, shorter (zoomed)
    only when the eyes are too high or low in the source to reach the eye line, never below sh / ZMAX, and never so
    short that the face fills more than face_frac of it (a big close-up keeps its size and sits a little lower).
    top_pad lets the window start that share of its height above the frame."""
    ch = h_max
    if sp is not None:
        ch = min(ch, sp["eye_y"] / eye_frac, (sh - sp["eye_y"]) / (1 - eye_frac))
    ch = max(ch, sh / ZMAX) / tight
    if sp is not None:
        ch = max(ch, min(sh, sp["face_h"] / face_frac))
    cw = ch * aspect
    if sp is None:
        return [(sw - cw) / 2, (sh - ch) / 2, cw, ch]
    x0 = float(np.clip(sp["cx"] - cw / 2, 0, sw - cw))
    y0 = float(np.clip(sp["eye_y"] - eye_frac * ch, -top_pad * ch, sh - ch))
    for tx0, ty0, tx1, ty1 in texts * 2:              # never cut through the show's text that is on screen
        inside = y0 <= ty0 and ty1 <= y0 + ch          # the crop holds the box's full height
        if not (x0 < tx1 and tx0 < x0 + cw and y0 < ty1 and ty0 < y0 + ch) or (inside and x0 <= tx0 and tx1 <= x0 + cw):
            continue
        right, left = tx1 + 4 - x0, x0 + cw - (tx0 - 4)            # nudge sideways: box out on the left / right
        if min(right, left) <= 0.12 * cw and 0 <= x0 + (right if right <= left else -left) <= sw - cw:
            x0 += right if right <= left else -left
            continue
        if ch < sh:                                    # or shift the window just off it, if the eyes move <= 45 px
            y2 = ty1 + 4 if ty1 < sh / 2 else ty0 - 4 - ch
            if 0 <= y2 <= sh - ch and abs(y2 - y0) * (W / aspect) / ch <= 45:
                y0 = y2
                continue
        top, bot = (ty1 + 4, sh) if ty1 < sh / 2 else (0, ty0 - 4)   # or leave it out above/below, eyes kept
        ch2 = min(ch, (sp["eye_y"] - top) / eye_frac, (bot - sp["eye_y"]) / (1 - eye_frac))
        if ch2 >= sp["face_h"] / face_frac and (W / aspect) / ch2 <= TEXT_FIX_ZOOM:
            ch, cw = ch2, ch2 * aspect
            x0 = float(np.clip(sp["cx"] - cw / 2, 0, sw - cw))
            y0 = float(np.clip(sp["eye_y"] - eye_frac * ch, top, bot - ch))
        # else leave the crop (never push the speaker aside or past the limits): erase() removes what it cuts
    return [x0, y0, cw, ch]


def cut_boxes(win, texts):
    """The text boxes this window would cut partway (it holds neither none nor all of the box)."""
    x0, y0, cw, ch = win
    return [b for b in texts if x0 < b[2] and b[0] < x0 + cw and y0 < b[3] and b[1] < y0 + ch
            and not (x0 <= b[0] and b[2] <= x0 + cw and y0 <= b[1] and b[3] <= y0 + ch)]


def inside_boxes(win, texts):
    """Every text box a window shows at all: the split's bottom half never shows the show's text (it would sit under
    the seam caption, half covered, right below a panel that already names the topic)."""
    x0, y0, cw, ch = win
    return [b for b in texts if x0 < b[2] and b[0] < x0 + cw and y0 < b[3] and b[1] < y0 + ch]


def erase(fr, boxes):
    """Inpaint the strokes of burned-in text a crop would cut through (the show's backgrounds are soft, so it vanishes)."""
    fr = fr.copy()
    for x0, y0, x1, y1 in boxes:
        a0, b0 = max(0, x0 - 10), max(0, y0 - 10)
        roi = fr[b0:y1 + 10, a0:x1 + 10]
        g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)
        inner = g[y0 - b0:y1 - b0, x0 - a0:x1 - a0]
        strokes = ((inner - cv2.blur(g, (9, 9))[y0 - b0:y1 - b0, x0 - a0:x1 - a0]) > 25) | (inner > np.median(inner) + 30)
        mask = np.zeros(g.shape, np.uint8)                       # thin strokes (edges) and bold ones (brighter than
        mask[y0 - b0:y1 - b0, x0 - a0:x1 - a0] = strokes * 255   # the box's background), grown a little
        fr[b0:y1 + 10, a0:x1 + 10] = cv2.inpaint(roi, cv2.dilate(mask, np.ones((7, 7), np.uint8)), 7, cv2.INPAINT_TELEA)
    return fr


def bright(g):
    return float(np.median(g)) > GRAPHIC_GRAY


def lead_in(pc, n_max=6):
    """Black, white or fading frames opening a presenter piece (a flash-in transition in the source): count them so the
    piece can open on its first clean frame instead."""
    ref = float(np.median(pc["gray"][min(len(pc["gray"]) - 1, n_max + 4)]))   # the shot's settled brightness
    k = 0
    while k < min(n_max + 1, len(pc["gray"])) and abs(float(np.median(pc["gray"][k])) - ref) > 25:
        k += 1
    return k if k <= n_max else 0


def graphic_box(pc, sw, sh):
    """Source window holding everything that ever appears on the graphic's canvas (union over the piece's bright
    frames), padded; fit() scales it into the band."""
    gs = [g for g in pc["gray"] if bright(g)]
    if not gs:
        return [0.0, 0.0, float(sw), float(sh)]
    mask = np.zeros(gs[0].shape, bool)
    for g in gs[::2]:
        bg = np.median(np.concatenate([g[:4].ravel(), g[-4:].ravel(), g[:, :4].ravel(), g[:, -4:].ravel()]))
        mask |= np.abs(g - bg) > 28
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return [0.0, 0.0, float(sw), float(sh)]
    sc = pc.get("sc", 2.0)
    x0, x1, y0, y1 = xs.min() * sc, (xs.max() + 1) * sc, ys.min() * sc, (ys.max() + 1) * sc
    pad = 0.03 * sw
    x0, x1 = max(0.0, x0 - pad), min(float(sw), x1 + pad)
    y0, y1 = max(0.0, y0 - pad), min(float(sh), y1 + pad)
    return [x0, y0, x1 - x0, y1 - y0]


def fit(fr, w, h, cy, box=None):
    """The graphic's content window, as large as fits the band (at most 1:1 source pixels), centred on a canvas of
    the frame's own border colour (the graphics sit on a plain canvas)."""
    sh_, sw_ = fr.shape[:2]
    x0, y0, bw, bh = box or [0, 0, sw_, sh_]
    k = min(w / bw, min(FIT_BAND, h) / bh, 1.0)
    ow, oh = int(round(bw * k)), int(round(bh * k))
    border = np.concatenate([fr[:6].reshape(-1, 3), fr[-6:].reshape(-1, 3), fr[:, :6].reshape(-1, 3),
                             fr[:, -6:].reshape(-1, 3)])
    out = np.empty((h, w, 3), np.uint8); out[:] = np.median(border, axis=0).astype(np.uint8)
    xo, yo = (w - ow) // 2, int(np.clip(cy - oh / 2, 0, h - oh))
    M = np.array([[k, 0, -x0 * k], [0, k, -y0 * k]], np.float32)
    out[yo:yo + oh, xo:xo + ow] = cv2.warpAffine(fr, M, (ow, oh), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
    return out


def warp(fr, box, w, h):
    x0, y0, cw, ch = box
    M = np.array([[w / cw, 0, -x0 * w / cw], [0, h / ch, -y0 * h / ch]], np.float32)
    return cv2.warpAffine(fr, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)


def main(src, plan_path, wav, out):
    plan = json.load(open(plan_path))
    ranges = plan["ranges"]
    pieces, fps = scan(src, ranges)
    cap = cv2.VideoCapture(src)
    sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    prev_sp, prev_zf, o = None, 1.0, 0.0
    meta = []
    for pc in pieces:
        sp = speaker(pc)
        same_camera = (prev_sp is not None and sp is not None and abs(sp["cx"] - prev_sp["cx"]) < 0.12 * sw
                       and abs(sp["face_h"] - prev_sp["face_h"]) < 0.25 * prev_sp["face_h"])
        new_range = any(abs(pc["src0"] - r0) < 1e-3 for r0, _ in ranges)
        zf = (TIGHT if prev_zf == 1.0 else 1.0) if (same_camera and new_range) else 1.0   # jump cut -> other "camera"
        crop = window(sp, sh, EYE_FRAC, W / H, zf, sw, sh, texts=pc["texts"])
        split = window(sp, sh * SPLIT_WIN, SPLIT_EYE, W / PH, zf, sw, sh, FACE_FRAC_SPLIT, pc["texts"], SPLIT_TOP_PAD)
        dur = pc["src1"] - pc["src0"]
        graphic = GRAPHICS and bool(sp is None or np.mean([bright(g) for g in pc["gray"]]) > 0.5)
        lead = lead_in(pc) if GRAPHICS and not graphic else 0
        meta.append({"o0": round(o, 3), "o1": round(o + dur, 3), "src0": pc["src0"], "src1": pc["src1"], "zf": zf,
                     "f0": pc["f0"], "f1": pc["f1"],
                     "crop": [round(v, 1) for v in crop], "split": [round(v, 1) for v in split], "speaker": sp,
                     "texts": pc["texts"], "erase_crop": (inside_boxes if ERASE_ALL or LONG else cut_boxes)(crop,
                                                                                                    pc["texts"]),
                     "erase_split": inside_boxes(split, pc["texts"]),
                     "hold": dur < HOLD and bool(meta), "fit": graphic, "lead": lead,
                     "bright": [k for k, g in enumerate(pc["gray"]) if GRAPHICS and k >= lead and bright(g)],
                     "gbox": graphic_box(pc, sw, sh) if GRAPHICS else None})
        if graphic:
            sp = meta[-1]["speaker"] = None
        o += dur
        if not meta[-1]["hold"]:
            prev_sp, prev_zf = (sp or prev_sp), zf
    enc = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r",
                            str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                            out], stdin=subprocess.PIPE)
    split_out = os.path.splitext(out)[0] + ".split.mp4"
    enc2 = None if LONG else subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{PH}", "-r",
                             str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt",
                             "yuv420p", split_out], stdin=subprocess.PIPE)
    img = img2 = None
    n_out = int(round(o * FPS))
    next_idx, last_fr = None, None
    for i in range(n_out):
        t = i / FPS
        m = next((m for m in meta if m["o0"] <= t < m["o1"]), meta[-1])
        if m["hold"] and img is not None:                  # a stray frame of another angle: hold the last frame
            enc.stdin.write(img.tobytes())
            if enc2:
                enc2.stdin.write(img2.tobytes())
            continue
        # stay inside this shot, past any flash-in frames it opens on
        idx = min(max(int(round((m["src0"] + t - m["o0"]) * fps)), m["f0"] + m["lead"]), m["f1"] - 1)
        if next_idx is not None and idx == next_idx - 1 and last_fr is not None:
            fr = last_fr                                   # 30 fps out from 29.97 in: hold one frame
        else:
            if idx != next_idx:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if ok:
                last_fr, next_idx = fr, idx + 1
            else:
                fr, next_idx = last_fr, None
        if m["fit"] or idx - m["f0"] in m["bright"]:        # a graphic frame (even inside a presenter piece)
            img, img2 = fit(fr, W, H, FIT_CY, m["gbox"]), None if LONG else fit(fr, W, PH, PH / 2, m["gbox"])
        else:
            img = warp(erase(fr, m["erase_crop"]) if m["erase_crop"] else fr, m["crop"], W, H)
            img2 = None if LONG else warp(erase(fr, m["erase_split"]) if m["erase_split"] else fr, m["split"], W, PH)
        enc.stdin.write(img.tobytes())
        if enc2:
            enc2.stdin.write(img2.tobytes())
    enc.stdin.close(); enc.wait()
    if enc2:
        enc2.stdin.close(); enc2.wait()
    json.dump({"fps_src": fps, "src_size": [sw, sh], "pieces": meta}, open(os.path.splitext(out)[0] + ".crops.json", "w"),
              indent=1)
    print(f"  framed {len(meta)} camera pieces ({sum(m['zf'] > 1 for m in meta)} tight, "
          f"{sum(m['hold'] for m in meta)} held, {sum(m['fit'] for m in meta)} graphics) -> {out}"
          + ("" if LONG else f" + {split_out}"))


if __name__ == "__main__":
    main(*sys.argv[1:5])
