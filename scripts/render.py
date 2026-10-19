"""markclip renderer: the motion-graphics pass over a base edit, driven by a JSON spec (references/spec-format.md).

House rules enforced here (each one learned from reviews of earlier versions):
  * Two typefaces only: Inter and Instrument Serif (bundled in assets/fonts), one type scale, sentence case.
  * Nothing is ever drawn over a face. Pass 1 renders the background alone and detects every face in every frame;
    each caption, pill, chip and title is then placed where it stays clear of those faces for its whole life, and
    orbit chips steer around them frame by frame.
  * Direct cuts. Layout changes (split, duo, card, image, statement) switch on a single frame; no sliding. Titles,
    pills and chips fade in and out without scale pops or overshoot. Camera zoom never eases back between two cuts: a
    punch-in holds to the next cut, an intense push-in ramps up and holds.
  * Captions (settle and lift): the pill settles in, each word brightens with a small lift as it is spoken, one caption at a
    time. The caption line is fixed for a whole layout stretch (split, duo: on the seam); a layout change makes it jump.
  * No layout flashes: a gap under BRIDGE s between two layouts, or between a layout and a camera cut, is held; a
    layout ending within BRIDGE s of the clip end runs to the end.
  * Eye level is matched across camera angles: every shot is framed so the speaker's eyes sit at the same height.
  * Two people talking get a duo split (one person per half, eyes level) built from the source two-shot.
  * A split's bottom half comes from BASE.split.mp4 (frame_base.py: a wider 9:8 window of the 16:9 source), so the
    speaker is not over-zoomed under the panel; a base without one has its 9:16 frame reframed under the panel.
  * Intense single-speaker lines get a slow push-in plus a subtle handheld shake.
  * Music clearly audible (~10-12 dB under the voice), clicks / paper turns / hits at ~-15 dB.
Writes OUT, OUT_mix.wav, OUT.log.jsonl (per-frame layout, zoom, caption and overlay boxes, faces) or, with --bg-only,
OUT_bg.mp4 (background layer only, for independent QA).
usage: render.py SPEC.json [--bg-only]"""
import json, math, os, subprocess, sys
import cv2
import numpy as np
from PIL import Image, ImageDraw

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get("CLIPIT_DIR", os.path.expanduser("~/.claude/skills/clipit")))
import engine_core as mg  # noqa: E402
from engine_core import (W, H, FPS, SR, clamp, ease_out, paste, glass, rr_mask, soft_blur,  # noqa: E402
                         icon_rgba, glitch, load_img, PAPER, GRID, INK)
from clipper import audio as A  # noqa: E402
from clipper.media import FFMPEG, load_audio, save_audio  # noqa: E402
from clipper.reframe import MODEL as FACE_MODEL  # noqa: E402
assert SR == A.SR, f"mix bus {SR} Hz but ClipIt places and synthesises effects at {A.SR} Hz"

FONTS = os.path.join(SKILL_DIR, "assets", "fonts")        # the only two families allowed: Inter, Instrument Serif
SERIF = os.path.join(FONTS, "InstrumentSerif-Regular.ttf")
SERIF_I = os.path.join(FONTS, "InstrumentSerif-Italic.ttf")
INTER = {w: os.path.join(FONTS, f"Inter-{w}.ttf") for w in ("Regular", "Medium", "SemiBold")}

TYPE = {
    "statement": (SERIF, 132), "display": (SERIF, 88), "headline": (SERIF, 84), "editorial": (SERIF, 78),
    "quote": (SERIF_I, 60), "caption": (INTER["SemiBold"], 62), "caption_em": (SERIF_I, 76),
    "pill": (INTER["Medium"], 44), "body": (INTER["Regular"], 32), "label": (INTER["Medium"], 30),
    "meta": (INTER["Medium"], 25), "counter": (INTER["SemiBold"], 66),
}
WHITE, DIM_INK = (255, 255, 255), (64, 64, 64)
PH = 960                       # split: panel height (top half)
TOPG = (1 - 0.6 * np.linspace(1, 0, 230, dtype=np.float32) ** 1.6)[:, None, None]   # soft top shade (UI legibility)
EYE_SINGLE = 740               # eye height for a single speaker, every camera angle
FACE_FRAC = 0.42               # no zoom past a face this tall (share of the frame): big close-ups keep their size
ZOOM_MAX = 2.3                 # never enlarge the 1080p source more than this (punch-ins on a tight crop went soft)
EYE_SPLIT = 1360               # eye height in the bottom half of a split
EYE_DUO = 420                  # eye height inside each duo half
CAP_SINGLE, CAP_SEAM = 1395, 960
CAP_TOP = 250                  # last resort for one phrase when a close-up fills the lower frame (never on the face)
FACE_PAD = 36                  # clearance kept around every face box
SHOW = ""                      # the spec's "show" name: default panel header label and editorial byline
HAIR_UP, HAIR_SIDE = 0.35, 0.10  # a face box reaches the hair: raised by 35 % of its height, 10 % wider a side
BRIDGE = 0.6                   # layout gaps shorter than this are held (no flash of the full-screen speaker)
LAYOUTS = ("statement", "image", "duo", "split", "editorial")
LONG = False                   # long form (spec "format": "long"): see set_long()
PW = W                         # panel width: the full width in a Short, the side part in long form
SAFE_TOP, SAFE_BOT = 140, 345  # overlays stay clear of the Shorts/Reels UI (long form: of the frame edges)
TITLE_Y = 210


def set_long():
    """Long form: a 1920x1080 canvas, no captions, overlays kept clear of the frame edges instead of the Shorts UI,
    eyes at 450, a split becomes a side layout (the frame in 2 or 3 parts, one of them the animated panel) and a duo
    puts the two people side by side."""
    global LONG, W, H, PH, PW, EYE_SINGLE, SAFE_TOP, SAFE_BOT, TITLE_Y
    LONG, W, H, PH = True, 1920, 1080, 1080
    PW, EYE_SINGLE, SAFE_TOP, SAFE_BOT, TITLE_Y = 960, 450, 60, 60, 80


def font(role):
    return mg.font(*TYPE[role])


def tspr(text, role, color=WHITE, size=None, track=0):
    path, sz = TYPE[role]
    return mg.text_sprite(text, path, size or sz, color, tracking=track)   # engine_core caches every sprite


def fade(t, t0, t1, fin=0.25, fout=0.2):
    """Opacity only: overlays fade, they never pop, overshoot or bounce."""
    if t < t0 or t > t1:
        return 0.0
    return min(ease_out((t - t0) / fin), ease_out((t1 - t) / fout))


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def pad(b, p=FACE_PAD):
    return [b[0] - p, b[1] - p, b[2] + p, b[3] + p]


# ================================================================== the background (camera, layouts)
class Background:
    """Everything under the overlays. Pure function of t (given sequential reads), used by both passes."""

    def __init__(self, spec, faces, plan, crops=None):
        self.plan, self.crops = plan, (crops or {}).get("pieces", [])
        self.els = spec["elements"]
        self.shots = faces["shots"]
        self.cuts = [s["t0"] for s in self.shots[1:]]
        self.duo_cache, self.duo_last = {}, None
        ivs = sorted((e for e in self.els if e["type"] in LAYOUTS), key=lambda e: e["t0"])
        for a, b in zip(ivs, ivs[1:]):                  # a short gap between two layouts: hold the first one
            if 0 < b["t0"] - a["t1"] < BRIDGE:
                a["t1"] = b["t0"]
        end = self.shots[-1]["t1"]
        for e in ivs:                                   # a layout ending just before the clip does runs to the end
            if end - e["t1"] < BRIDGE:
                e["t1"] = end + 60.0
        for e in ivs:                                   # ...and snap a layout edge to a camera cut just beside it
            before = [c for c in [0.0] + self.cuts if 0 < e["t0"] - c < BRIDGE]
            after = [c for c in self.cuts if 0 < c - e["t1"] < BRIDGE]
            if before and not any(o is not e and o["t0"] < e["t0"] and o["t1"] > before[-1] for o in ivs):
                e["t0"] = before[-1]
            if after and not any(o is not e and o["t0"] < after[0] and o["t1"] > e["t1"] for o in ivs):
                e["t1"] = after[0]

    # ---- shot / camera
    def shot_at(self, t):
        for s in self.shots:
            if s["t0"] <= t < s["t1"]:
                return s
        return self.shots[-1]

    def next_cut(self, t):
        return next((c for c in self.cuts if c > t + 1e-6), 1e9)

    def eye(self, s):
        ok = lambda x: x.get("eye_y") is not None and 250 <= x["eye_y"] <= 1350   # a face, not a hand or a mic
        if ok(s):
            return s["eye_x"], s["eye_y"]
        known = [x for x in self.shots if ok(x)]
        if not known:
            return W / 2, EYE_SINGLE
        near = min(known, key=lambda x: abs(x["t0"] - s["t0"]))
        return near["eye_x"], near["eye_y"]

    def src_scale(self, t, key="crop", out_h=None):
        """How much the base already enlarges the source here (output px per source px)."""
        p = next((p for p in self.crops if p["o0"] <= t < p["o1"]), None)
        return (out_h or H) / p[key][3] if p and key in p else 1.0

    def extra_zoom(self, t):
        """Punch-ins and intense push-ins. Never decreases between two cuts: holds until the next cut."""
        z, dx, dy, rot = 1.0, 0.0, 0.0, 0.0
        for e in self.els:
            if e["type"] == "punch" and e["t"] <= t < self.next_cut(e["t"]):
                z *= e.get("zoom", 1.08)
            elif e["type"] == "intense" and e["t0"] <= t < max(e["t1"], self.next_cut(e["t1"])):
                ramp = clamp((t - e["t0"]) / max(0.1, e["t1"] - e["t0"]))
                z *= 1 + (e.get("zoom", 1.06) - 1) * ramp
                if t <= e["t1"]:
                    a = e.get("shake", 3.0)
                    dx += a * (math.sin(2 * math.pi * 0.83 * t) + 0.55 * math.sin(2 * math.pi * 1.91 * t + 1.3)) / 1.55
                    dy += a * (math.sin(2 * math.pi * 0.67 * t + 0.7) + 0.5 * math.sin(2 * math.pi * 2.3 * t)) / 1.5
                    rot += 0.12 * math.sin(2 * math.pi * 0.5 * t)
        return z, dx, dy, rot

    def frame_single(self, base, t, target=None, region=None):
        s = self.shot_at(t)
        ex, ey = self.eye(s)
        target = EYE_SINGLE if target is None else target
        y0, y1 = region or (0, H)
        z = max(1.0, (target - y0) / max(ey, 1), (y1 - target) / max(H - ey, 1))
        zmax = min(1.25, max(1.0, FACE_FRAC * H / s["face"][3])) if s.get("face") else 1.25
        if z > zmax:                             # extreme source framing: cap the zoom, move the eyes as close as we can
            z = zmax
            target = float(np.clip(target, y1 - (H - ey) * z, y0 + ey * z))   # still fills the frame edge to edge
        zx, dx, dy, rot = self.extra_zoom(t)
        z = min(z * zx, max(z, ZOOM_MAX / self.src_scale(t)))   # punch-ins stop at ZOOM_MAX x the source pixels
        M = cv2.getRotationMatrix2D((ex, ey), rot, z)
        M[0, 2] += dx
        M[1, 2] += (target - ey) + dy
        out = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return out, z, dx, dy

    # ---- layouts
    def active(self, t, types):
        hit = None
        for e in self.els:
            if e["type"] in types and e["t0"] <= t < e["t1"]:
                hit = e
        return hit

    def layout(self, t):
        if self.active(t, ("statement",)):
            return "statement"
        if self.active(t, ("image",)):
            return "image"
        if self.active(t, ("duo",)):
            return "duo"
        if self.active(t, ("split", "editorial")):
            return "split"
        return "single"

    def render(self, base, t, split=None):
        lay = self.layout(t)
        info = {"layout": lay, "zoom": 1.0, "dx": 0.0, "dy": 0.0}
        if lay == "duo":
            e = self.active(t, ("duo",))
            fr = self.duo_frame(e, t)
            if fr is None and self.duo_last is not None:
                fr = self.duo_last.copy()          # a frame without a readable two-shot holds the last one, no flash
            if fr is None:                       # no two-shot available at all: fall back to the single framing
                lay = info["layout"] = "single"
            else:
                self.duo_last = fr
                return fr, info
        if lay in ("single", "statement"):
            fr, z, dx, dy = self.frame_single(base, t)
            info.update(zoom=z, dx=dx, dy=dy)
            if lay == "statement":               # a title card, not text over a face: near-black, blurred
                fr = (soft_blur(fr, 30).astype(np.float32) * 0.12).astype(np.uint8)
            elif not LONG:                       # a soft top shade under the Shorts/Reels UI
                fr[:230] = (fr[:230].astype(np.float32) * TOPG).astype(np.uint8)
            return fr, info
        if lay == "image":
            e = self.active(t, ("image",))
            pic = cover(load_img(e["img"]), W, H, (t - e["t0"]) / max(0.1, e["t1"] - e["t0"]),
                        e.get("focus", (0.5, 0.45)), e.get("zoom", (1.0, 1.08))).astype(np.float32)
            pic = (pic * (1 - e.get("dim", 0.0))).astype(np.uint8)
            if not LONG:
                pic[:230] = (pic[:230].astype(np.float32) * TOPG).astype(np.uint8)
            return pic, info
        e = self.active(t, ("split", "editorial"))
        panel = e["panel"] if e["type"] == "split" else e.setdefault("_panel", dict(e, kind="editorial"))
        panel.setdefault("t0", e["t0"]); panel.setdefault("t1", e["t1"])
        if LONG:                                 # side layout: the frame in 2 or 3 parts, one of them the panel
            global PW
            PW = W // e.get("parts", 2)                     # the animated part: half, or a third
            sw = W - PW
            fr, z, dx, dy = self.frame_single(base, t)
            x0 = int(np.clip(self.eye(self.shot_at(t))[0] - sw / 2, 0, W - sw))   # the speaker centred in his part
            out = np.empty_like(fr)
            px = sw if e.get("side", "right") == "right" else 0
            sx = 0 if px else PW
            out[:, sx:sx + sw] = fr[:, x0:x0 + sw]
            out[:, px:px + PW] = PANELS[panel["kind"]](panel, t)
            edge = px if px else PW                          # a soft shade on the speaker's side of the seam
            out[:, max(0, edge - 2):edge + 2] = (out[:, max(0, edge - 2):edge + 2] * 0.7).astype(np.uint8)
            info.update(zoom=z, dx=dx, dy=dy)
            return out, info
        if split is None:
            sys.exit("split layout but no BASE.split.mp4: rebuild the base with base_edit.py (frame_base.py)")
        z, dx, dy, rot = self.extra_zoom(t)                # bottom half from the source (9:8 window, eyes at 1360)
        z = min(z, max(1.0, ZOOM_MAX / self.src_scale(t, "split", PH)))
        M = cv2.getRotationMatrix2D((W / 2, EYE_SPLIT - PH), rot, z)
        M[0, 2] += dx; M[1, 2] += dy
        fr = np.empty((H, W, 3), np.uint8)
        fr[PH:] = cv2.warpAffine(split, M, (W, PH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        info.update(zoom=z, dx=dx, dy=dy)
        fr[:PH] = PANELS[panel["kind"]](panel, t)
        sh = np.linspace(0.6, 1.0, 22, dtype=np.float32)[:, None, None]
        fr[PH:PH + 22] = (fr[PH:PH + 22].astype(np.float32) * sh).astype(np.uint8)
        return fr, info

    # ---- duo: two people, one per half, from the source two-shot
    def src_time(self, t):
        for (o0, o1), (r0, _) in zip(self.plan["out"], self.plan["ranges"]):
            if o0 <= t < o1:
                return r0 + (t - o0)
        return None

    def duo_frame(self, e, t):
        if not self.plan:
            return None
        st = self.src_time(t)
        if st is None:
            return None
        cap = self.duo_cache.get("cap")
        if cap is None:
            cap = self.duo_cache["cap"] = cv2.VideoCapture(self.plan["src"])
            self.duo_cache["fps"] = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.duo_cache["det"] = cv2.FaceDetectorYN.create(FACE_MODEL, "", (960, 540), 0.8, 0.3, 50)
        fps = self.duo_cache["fps"]
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(st * fps)))
        ok, src = cap.read()
        if not ok:
            return None
        src = cv2.cvtColor(src, cv2.COLOR_BGR2RGB)
        key = (id(e), self.shot_at(t)["t0"])
        if key not in self.duo_cache:            # fixed crops per shot (median of 5 frames): no camera wandering
            sh = self.shot_at(t)
            det = self.duo_cache["det"]
            det.setInputSize((960, 540))
            samples = []
            for u in np.linspace(sh["t0"] + 0.05, sh["t1"] - 0.05, 5):
                su = self.src_time(u)
                if su is None:
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(su * fps)))
                ok2, fr2 = cap.read()
                if not ok2:
                    continue
                _, f = det.detect(cv2.resize(fr2, (960, 540), interpolation=cv2.INTER_AREA))
                sc = fr2.shape[1] / 960
                pp = sorted([[v * sc for v in r[:8]] for r in (f if f is not None else [])], key=lambda r: -r[2] * r[3])[:2]
                if len(pp) == 2:
                    samples.append(sorted(pp, key=lambda r: r[0]))
            self.duo_cache[key] = ([[float(np.median([sm[p][j] for sm in samples])) for j in range(8)] for p in (0, 1)]
                                   if samples else None)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(st * fps)))
            ok, src_bgr = cap.read()
            if ok:
                src = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2RGB)
        people = self.duo_cache[key]
        if not people:
            return None
        if e.get("top", "left") == "right":
            people = people[::-1]
        out = np.zeros((H, W, 3), np.uint8)
        fh = e.get("face_h", 300)
        if LONG:                                 # side by side, one per half, eyes level
            hw = W // 2
            for half, p in enumerate(people):
                ex, ey = (p[4] + p[6]) / 2, (p[5] + p[7]) / 2
                s = max(fh / max(p[3], 1), H / src.shape[0], hw / src.shape[1])
                M = np.array([[s, 0, hw / 2 - s * ex], [0, s, EYE_SINGLE - s * ey]], np.float32)
                out[:, half * hw:(half + 1) * hw] = cv2.warpAffine(src, M, (hw, H), flags=cv2.INTER_CUBIC,
                                                                   borderMode=cv2.BORDER_REFLECT)
            out[:, hw - 2:hw + 2] = 12
            return out
        for half, p in enumerate(people):
            ex, ey = (p[4] + p[6]) / 2, (p[5] + p[7]) / 2
            s = max(fh / max(p[3], 1), PH / src.shape[0], W / src.shape[1])
            M = np.array([[s, 0, W / 2 - s * ex], [0, s, EYE_DUO - s * ey]], np.float32)
            out[half * PH:(half + 1) * PH] = cv2.warpAffine(src, M, (W, PH), flags=cv2.INTER_CUBIC,
                                                            borderMode=cv2.BORDER_REFLECT)
        out[PH - 2:PH + 2] = 12
        return out


def cover(img, w, h, t01, focus=(0.5, 0.45), zoom=(1.0, 1.08)):
    ih, iw = img.shape[:2]
    z = zoom[0] + (zoom[1] - zoom[0]) * clamp(t01)
    sc = max(w / iw, h / ih) * z
    cw, ch = w / sc, h / sc
    x0 = clamp(focus[0] * iw - cw / 2, 0, max(0, iw - cw)); y0 = clamp(focus[1] * ih - ch / 2, 0, max(0, ih - ch))
    M = np.array([[sc, 0, -x0 * sc], [0, sc, -y0 * sc]], np.float32)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


# ================================================================== split panels (top half)
def panel_grid(e, t):
    if "_base" not in e:
        bg = Image.new("RGB", (PW, PH), PAPER)
        d = ImageDraw.Draw(bg)
        for gx in range(0, PW, 40):
            d.line([gx, 0, gx, PH], fill=GRID)
        for gy in range(0, PH, 40):
            d.line([0, gy, PW, gy], fill=GRID)
        m = 64
        d.rectangle([0, 0, PW, 200], fill=PAPER)
        l, r = (list(e.get("labels", (SHOW, ""))) + [""])[:2]
        d.text((m, 150), l, font=font("meta"), fill=DIM_INK)
        if r:
            d.text((PW - m - font("meta").getlength(r), 150), r, font=font("meta"), fill=DIM_INK)
        d.line([m, 196, PW - m, 196], fill=(196, 194, 188), width=2)
        ty = 222
        for line in e.get("title", "").split("\n"):
            d.text((m, ty), line, font=font("headline"), fill=INK)
            ty += TYPE["headline"][1]
        if e.get("body"):
            lines = e["body"].split("\n")
            by = PH - 70 - 44 * len(lines)
            for line in lines:
                d.text((m, by), line, font=font("body"), fill=DIM_INK)
                by += 44
        e["_base"] = np.array(bg)
    pan = e["_base"].copy()
    seq = e.get("icons", [])
    if seq:
        cur = [i for i in seq if i["t"] <= t] or seq[:1]
        size = e.get("icon_size", min(400, int((0.36 if LONG else 0.42) * PW)))   # long: under a 2-line title
        spr = icon_rgba(cur[-1]["name"], t - e["t0"], size)
        g = max([1 - (t - i["t"]) / 0.28 for i in seq[1:] if 0 <= t - i["t"] < 0.28] or [0])
        if g > 0:
            spr = glitch(spr, g, int(t * 30))
        paste(pan, spr, e.get("icon_x", PW - 0.825 * size), e.get("icon_y", 520 * PH / 960), 1.0, anchor="c")
    if e.get("counter"):
        c = e["counter"]
        p = mg.ease_in_out((t - c["t0"]) / max(0.1, c["t1"] - c["t0"]))
        v = int(c["from"] + (c["to"] - c["from"]) * p)
        paste(pan, tspr(f"{v:,}{c.get('suffix', '')}", "counter", INK), 64, c.get("y", 780 if LONG else 560), 1.0)
    return pan


def panel_image(e, t):
    pic = cover(load_img(e["img"]), PW, PH, (t - e["t0"]) / max(0.1, e["t1"] - e["t0"]), e.get("focus", (0.5, 0.4)),
                e.get("zoom", (1.0, 1.08)))
    return (pic.astype(np.float32) * (1 - e.get("dim", 0.0))).astype(np.uint8)


def panel_framed(e, t):
    pan = np.zeros((PH, PW, 3), np.uint8) + np.array(e.get("bg", (18, 17, 16)), np.uint8)
    img = load_img(e["img"])
    ih, iw = img.shape[:2]
    bh = e.get("h", 560)
    bw = int(iw * bh / ih)
    z = 1 + 0.05 * clamp((t - e["t0"]) / max(0.1, e["t1"] - e["t0"]))
    pic = cv2.resize(img, (int(bw * z), int(bh * z)), interpolation=cv2.INTER_AREA)
    oy, ox = (pic.shape[0] - bh) // 2, (pic.shape[1] - bw) // 2
    paste(pan, np.dstack([pic[oy:oy + bh, ox:ox + bw], (rr_mask(bw, bh, 18) * 255).astype(np.uint8)]),
          PW / 2, 150 + bh / 2, 1.0, anchor="c")
    if e.get("caption"):
        paste(pan, tspr(e["caption"], "meta", (200, 198, 192)), PW / 2, 150 + bh + 30, 1.0, anchor="tc")
    return pan


def panel_editorial(e, t):
    """Editorial card as the top half: illustration (pixel icon or painting), serif headline, Inter byline."""
    if "_base" not in e:
        bg = Image.new("RGB", (PW, PH), (252, 251, 248))
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([48, 150, PW - 48, 600], 18, fill=(244, 239, 231))
        hy = 640
        for line in e["headline"].split("\n"):
            d.text((64, hy), line, font=font("editorial"), fill=INK)
            hy += int(TYPE["editorial"][1] * 1.06)
        d.text((64, hy + 16), e.get("byline", SHOW), font=font("meta"), fill=DIM_INK)  # clear of the seam caption
        e["_base"] = np.array(bg)
    pan = e["_base"].copy()
    if e.get("img"):
        pic = cover(load_img(e["img"]), PW - 96, 450, clamp((t - e["t0"]) / 4), e.get("focus", (0.5, 0.4)), (1.0, 1.05))
        paste(pan, np.dstack([pic, (rr_mask(PW - 96, 450, 18) * 255).astype(np.uint8)]), 48, 150, 1.0)
    if e.get("icon"):
        spr = icon_rgba(e["icon"], t - e["t0"], min(380, int(0.4 * PW)))
        sh = spr.copy(); sh[..., :3] = 0; sh[..., 3] = (sh[..., 3] * 0.22).astype(np.uint8)
        paste(pan, sh, PW / 2 + 22, 395, 1.0, anchor="c")
        paste(pan, spr, PW / 2, 375, 1.0, anchor="c")
    return pan


def panel_list(e, t):
    """Grid panel whose items tick in as they are said: a check in a circle + Inter Medium text, left aligned."""
    if "_base" not in e:
        e["_base"] = panel_grid({k: v for k, v in e.items() if k not in ("_base", "icons", "counter", "body")}, t)
    pan = e["_base"].copy()
    y = e.get("list_y", 360 + 84 * (len(e.get("title", "").split("\n")) - 1))
    for it in e["items"]:
        a = clamp((t - it["t"]) / 0.25)
        if a > 0:
            cx, cy = 96, y + 34
            cv2.circle(pan, (cx, cy), 26, (52, 150, 90), -1, cv2.LINE_AA)
            cv2.polylines(pan, [np.array([[cx - 12, cy + 1], [cx - 3, cy + 10], [cx + 13, cy - 9]], np.int32)], False,
                          (255, 255, 255), 5, cv2.LINE_AA)
            paste(pan, tspr(it["text"], "pill", INK, size=52), 148, y + 2, a)
        y += 112
    return pan


PANELS = dict(grid=panel_grid, image=panel_image, framed=panel_framed, editorial=panel_editorial, list=panel_list)


# ================================================================== overlays (placed face-free, fade only)
def title_boxes(e):
    lines = e["text"].split("\n")
    size = e.get("_size") or TYPE["display"][1]
    lh = int(size * 1.06)
    pw = max(tspr(l, "display", size=size).shape[1] for l in lines) + 96
    ph = lh * len(lines) + 44
    y = e.get("y", TITLE_Y)
    return [[(W - pw) / 2, y - (52 if e.get("kicker") else 0), (W + pw) / 2, y + ph]]


def pill_box(e, x, y):
    spr = tspr(e["text"], "quote" if e.get("quote") else "pill")
    pw, ph = spr.shape[1] + 68, TYPE["pill"][1] * 1.2 + 34
    return [x - pw / 2, y - ph / 2, x + pw / 2, y + ph / 2]


def chip_box(x, y, r, label):
    lab = (tspr(label, "label").shape[1] + 36) / 2 if label else 0
    return [x - max(r + 12, lab), y - r - 12, x + max(r + 12, lab), y + r + (70 if label else 12)]


def draw_title(fr, e, a):
    lines = e["text"].split("\n")
    size = e.get("_size") or TYPE["display"][1]
    sprs = [tspr(l, "display", size=size) for l in lines]
    lh = int(size * 1.06)
    pw = max(s.shape[1] for s in sprs) + 96
    ph = lh * len(lines) + 44
    y = e["_y"]
    glass(fr, (W - pw) / 2, y, pw, ph, r=46, alpha=a)
    for i, s in enumerate(sprs):
        paste(fr, s, W / 2, y + 16 + i * lh, a, anchor="tc")
    if e.get("_kicker"):
        paste(fr, tspr(e["_kicker"], "meta", (235, 235, 235), track=1), W / 2, y - 46, a, anchor="tc")


def draw_statement(fr, e, t):
    a = fade(t, e["t0"], e["t1"], 0.12, 0.2)
    lines = e["text"].split("\n")
    lh = int(TYPE["statement"][1] * 1.02)
    y0 = H / 2 - lh * len(lines) / 2
    n = 0
    for i, line in enumerate(lines):
        sprs, inside = [], False
        for w in line.split(" "):
            inside = inside or w.startswith("*")
            sprs.append(mg.text_sprite(w.strip("*"), SERIF_I, TYPE["statement"][1] + 8, (255, 226, 160))
                        if inside else tspr(w.strip("*"), "statement"))
            inside = inside and not w.endswith("*")
        tw = sum(s.shape[1] for s in sprs) + 28 * (len(sprs) - 1)
        x = (W - tw) / 2
        for s in sprs:
            k = ease_out((t - e["t0"] - 0.06 * n) / 0.18)      # word by word, opacity only
            paste(fr, s, x, y0 + i * lh, a * clamp(k))
            x += s.shape[1] + 28
            n += 1


def draw_pill(fr, e, t, a, x, y):
    spr = tspr(e["text"], "quote" if e.get("quote") else "pill")
    b = pill_box(e, x, y)
    glass(fr, b[0], b[1], b[2] - b[0], b[3] - b[1], alpha=a, tint=(18, 18, 22), tint_a=0.30)
    paste(fr, spr, x, y + 2, a, anchor="c")
    if e.get("strike") is not None and t >= e["strike"]:
        p = ease_out((t - e["strike"]) / 0.28)
        x0 = x - spr.shape[1] / 2
        cv2.line(fr, (int(x0), int(y + 4)), (int(x0 + spr.shape[1] * p), int(y + 4)), (236, 76, 64), 5, cv2.LINE_AA)


def draw_chip(fr, x, y, r, a, img=None, icon=None, t=0, label=None):
    if a <= 0.003:
        return
    glass(fr, x - r - 12, y - r - 12, 2 * r + 24, 2 * r + 24, r=r + 12, alpha=a, tint_a=0.18)
    d = int(2 * r)
    if img is not None:
        h, w = img.shape[:2]
        sd = min(h, w)
        crop = img[(h - sd) // 4:(h - sd) // 4 + sd, (w - sd) // 2:(w - sd) // 2 + sd]
        crop = cv2.resize(crop, (d, d), interpolation=cv2.INTER_AREA)
        paste(fr, np.dstack([crop, (rr_mask(d, d, d // 2) * 255).astype(np.uint8)]), x, y, a, anchor="c")
    elif icon:
        paste(fr, icon_rgba(icon, t, int(d * 0.8)), x, y, a, anchor="c")
    if label:
        s = tspr(label, "label")
        lw, lh = s.shape[1] + 36, s.shape[0] + 14
        glass(fr, x - lw / 2, y + r + 20, lw, lh, alpha=a, tint=(18, 18, 22), tint_a=0.32, shadow=False)
        paste(fr, s, x, y + r + 20 + lh / 2, a, anchor="c")


# ================================================================== placement
class Planner:
    """Decides every overlay position once, from the faces pass 1 found over that overlay's whole life."""

    def __init__(self, faces_by_frame, layouts):
        self.F, self.L = faces_by_frame, layouts

    def faces_in(self, t0, t1, pad_=FACE_PAD):
        out = []
        for k in range(max(0, int(t0 * FPS)), min(len(self.F), int(math.ceil(t1 * FPS - 1e-6)))):   # [t0, t1)
            out.extend(pad(b, pad_) for b in self.F[k])
        return out

    def free(self, boxes, t0, t1, avoid=(), pad_=FACE_PAD):
        fs = self.faces_in(t0, t1, pad_)
        for b in boxes:
            if b[0] < 8 or b[2] > W - 8 or b[1] < SAFE_TOP or b[3] > H - SAFE_BOT:
                return False
            if any(overlap(b, f) for f in fs) or any(overlap(b, o) for o in avoid):
                return False
        return True

    def place_group(self, boxes, t0, t1, avoid=(), dxs=range(-600, 601, 30)):
        """Smallest move (dx, dy) that clears every face for the group's life; None if nothing fits."""
        if self.free(boxes, t0, t1, avoid):
            return 0, 0
        cands = sorted(((dx, dy) for dx in dxs for dy in range(-900, 901, 30)),
                       key=lambda d: d[0] ** 2 + (1.3 * d[1]) ** 2)
        for dx, dy in cands:
            moved = [[b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy] for b in boxes]
            if self.free(moved, t0, t1, avoid):
                return dx, dy
        return None


def plan_overlays(spec, planner, phrases, face_planner):
    els = spec["elements"]
    notes = []
    cap_boxes = []                                    # captions are placed first: everything else avoids them
    widths = [sum(tspr(w["w"].strip(), "caption").shape[1] + 16 for w in ph) + 80 for ph in phrases]
    runs, k0 = {}, 0                                  # one caption line per layout run (no up/down drift)
    for k in range(1, len(planner.L) + 1):
        if k == len(planner.L) or planner.L[k] != planner.L[k0]:
            lay = planner.L[k0]
            if lay != "statement":
                r0, r1 = k0 / FPS, k / FPS
                ws = [wd for ph, wd in zip(phrases, widths) if ph[0]["s"] - 0.15 < r1 and r0 < ph[0]["ph_end"]] or [0]
                tries = [CAP_SEAM] if lay in ("split", "duo") else [CAP_SINGLE, 1455, 1515]   # never over panel text
                runs[k0] = next((yy for yy in tries if planner.free([[W / 2 - max(ws) / 2, yy - 60,
                                                                       W / 2 + max(ws) / 2, yy + 60]], r0, r1, pad_=20)),
                                None)
            k0 = k
    run_start = lambda t: max((k for k in runs if k <= int(t * FPS)), default=None)
    for j, ph in enumerate(phrases):                  # a pill shows only once the previous phrase's last word has lit
        prev_last = phrases[j - 1][-1]["s"] - 0.05 + 0.15 if j else -1.0
        ph[0]["_show0"] = min(ph[0]["s"] - 0.05, max(ph[0]["s"] - 0.15, prev_last))
    for ph, width in zip(phrases, widths):
        t0, t1 = ph[0]["_show0"], ph[0]["ph_end"]
        segs, cur = [], None
        for k in range(int(t0 * FPS), int(t1 * FPS) + 1):
            lay = planner.L[k] if 0 <= k < len(planner.L) else "single"
            if lay != cur:
                segs.append([k / FPS, k / FPS, lay]); cur = lay
            segs[-1][1] = (k + 1) / FPS
        ph_place = []
        after_stmt = False
        for s0, s1, lay in segs:
            if lay == "statement":
                ph_place.append([s0, s1, None, False]); after_stmt = True; continue
            speaks = any(s0 <= w["s"] - 0.05 < s1 for w in ph)
            if (after_stmt and not speaks) or (s1 - s0 < 0.4 and not speaks) or (s1 - s0 < 0.2):
                ph_place.append([s0, s1, None, False]); continue   # a leftover or a flash around a statement
            rk = run_start(s0)
            if rk is not None and runs[rk] is not None:   # the run's fixed line is clear of faces for the whole run
                y = runs[rk]
                ph_place.append([s0, s1, y, False])
                cap_boxes.append(([W / 2 - width / 2, y - 60, W / 2 + width / 2, y + 60], s0, s1))
                continue
            base_y = CAP_SEAM if lay in ("split", "duo") else CAP_SINGLE
            tries = [base_y] + ([1455, 1515, CAP_TOP] if lay not in ("split", "duo") else [])
            prev_y = cap_boxes[-1][0][1] + 60 if cap_boxes else None
            if prev_y in tries:                          # stay put between phrases unless a face forces a move
                tries = [prev_y] + [y_ for y_ in tries if y_ != prev_y]
            y = next((yy for yy in tries if planner.free([[W / 2 - width / 2, yy - 60, W / 2 + width / 2, yy + 60]],
                                                          s0, s1, pad_=20)), None)
            hair_ok = False
            if y is None:                       # a close-up fills the frame: the caption may touch hair, never a face
                y = next((yy for yy in tries if face_planner.free([[W / 2 - width / 2, yy - 60, W / 2 + width / 2,
                                                                     yy + 60]], s0, s1, pad_=20)), None)
                hair_ok = y is not None
                if y is None:
                    y = base_y; notes.append(f"caption at {s0:.1f}s could not clear a face")
            ph_place.append([s0, s1, y, hair_ok])
            cap_boxes.append(([W / 2 - width / 2, y - 60, W / 2 + width / 2, y + 60], s0, s1))
        ph[0]["_place"] = ph_place

    def cap_avoid(t0, t1):
        return [b for b, s0, s1 in cap_boxes if s0 < t1 and t0 < s1]

    groups = {}
    for i, e in enumerate(els):
        if e["type"] in ("pill", "chip"):
            groups.setdefault(e.get("group", f"_{i}"), []).append(e)
    for g, members in groups.items():
        t0, t1 = min(m["t0"] for m in members), max(m["t1"] for m in members)
        placed = False
        for variant in ("as_given", "grid2", "shrink1", "shrink2", "shrink3"):
            pos = [(m.get("x", W / 2), m["y"]) for m in members]
            if variant == "grid2" and len(members) >= 3:          # a tall stack becomes two columns
                y0 = min(p[1] for p in pos)
                pos = [(W / 2 + (-1 if j % 2 == 0 else 1) * 250, y0 + (j // 2) * 120) for j in range(len(members))]
            elif variant == "grid2":
                continue
            scale = {"shrink1": 0.85, "shrink2": 0.72, "shrink3": 0.6}.get(variant, 1.0)
            if scale < 1 and all(m["type"] == "pill" for m in members):
                continue                                          # pills keep their type size; only chips shrink
            boxes = [pill_box(m, x, y) if m["type"] == "pill" else
                     chip_box(x, y, m.get("r", 110) * scale, m.get("label")) for m, (x, y) in zip(members, pos)]
            mv = planner.place_group(boxes, t0, t1, cap_avoid(t0, t1))
            if mv is not None:
                for m, (x, y) in zip(members, pos):
                    m["_x"], m["_y"], m["_rs"] = x + mv[0], y + mv[1], scale
                placed = True
                break
        if not placed:
            notes.append(f"group {g} at {t0:.1f}s could not clear every face for its whole life: skipped (move it "
                         "to a wider shot or shorten it)")      # a pill that blinks on and off near a face is worse
            for m in members:
                m["_skip"] = True
    for e in els:
        if e["type"] == "title":
            e["_y"], e["_kicker"], e["_size"] = e.get("y", TITLE_Y), e.get("kicker"), None
            for kicker, size in ((e.get("kicker"), None), (None, None), (e.get("kicker"), 72), (None, 72)):
                trial = dict(e, kicker=kicker, _size=size)
                mv = planner.place_group(title_boxes(trial), e["t0"], e["t1"], cap_avoid(e["t0"], e["t1"]),
                                         dxs=(0,))                 # a title is drawn centred: it may only move up/down
                if mv is not None:
                    e["_y"], e["_kicker"], e["_size"] = e.get("y", TITLE_Y) + mv[1], kicker, size
                    break
            else:                                     # nothing clears the hair: the title may touch it, never a face
                for kicker, size in ((e.get("kicker"), None), (None, None), (e.get("kicker"), 72), (None, 72)):
                    trial = dict(e, kicker=kicker, _size=size)
                    mv = face_planner.place_group(title_boxes(trial), e["t0"], e["t1"], cap_avoid(e["t0"], e["t1"]),
                                                  dxs=(0,))
                    if mv is not None:
                        e["_y"], e["_kicker"], e["_size"], e["_hair_ok"] = e.get("y", TITLE_Y) + mv[1], kicker, size, True
                        notes.append("title touches the top of the hair (nothing else fits), clear of the face")
                        break
                else:
                    notes.append("title could not clear every face: hidden where it would touch one")
    return notes


def smooth_face(F, L, i, lo=0, hi=None, half=6):
    """Union of every face box within +-0.2 s of frame i (same layout, same camera shot [lo, hi)): orbit chips steer
    around everywhere the face is about to be, including fast moves, and never borrow a face across a cut."""
    hi = len(F) if hi is None else hi
    boxes = [b for k in range(max(lo, i - half), min(hi, i + half + 1)) if L[k] == L[i] for b in F[k]]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def orbit_layout(e, t, face):
    """Chip centres for an orbit at time t. The chips travel a rounded-rectangle track drawn around the padded face
    box (so neither a chip nor its label can ever touch the face). If the whole track fits the frame they circle the
    face; otherwise they sit still, evenly spaced along the longest part of the track that fits (flanking the face);
    failing that, a row below the chin or above the head. Returns [(x, y), ...] or None."""
    n = len(e["chips"])
    r = max(c.get("r", 96) for c in e["chips"])
    lab = max((tspr(c["label"], "label").shape[1] + 36) / 2 if c.get("label") else 0 for c in e["chips"])
    hw, top, bot = max(r + 12, lab), r + 12, r + 70
    f = face or [W / 2 - 150, 560, W / 2 + 150, 940]
    P = pad(f)
    R = [P[0] - hw, P[1] - bot, P[2] + hw, P[3] + top]                 # chip centres on this rectangle clear P
    A = [hw + 8, SAFE_TOP + 10 + top, W - hw - 8,                      # where a chip centre may go
         (H - SAFE_BOT if LONG else CAP_SINGLE - 60) - bot - 12]
    step = 6.0
    pts = []
    for (x0, y0, x1, y1) in ((R[0], R[1], R[2], R[1]), (R[2], R[1], R[2], R[3]), (R[2], R[3], R[0], R[3]),
                             (R[0], R[3], R[0], R[1])):
        m = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        pts += [(x0 + (x1 - x0) * k / m, y0 + (y1 - y0) * k / m) for k in range(m)]
    ok = [A[0] <= x <= A[2] and A[1] <= y <= A[3] for x, y in pts]
    need = n * (2 * hw + 24) / step
    if all(ok) and len(pts) >= need:
        off = (t - e["t0"]) * e.get("speed", 0.45) * 160 / step
        return [pts[int(j * len(pts) / n + off) % len(pts)] for j in range(n)]
    best, cur = [], []
    for k in range(2 * len(pts)):                                       # longest run that fits (wrapping)
        if ok[k % len(pts)]:
            cur.append(pts[k % len(pts)])
            if len(cur) > len(best):
                best = list(cur)
            if len(cur) >= len(pts):
                break
        else:
            cur = []
    if len(best) >= need:
        return [best[int((j + 0.5) * len(best) / n)] for j in range(n)]
    for rows in (1, 2):                                                # still rows below the chin, then above
        per = math.ceil(n / rows)
        if W / (per + 1) < 2 * hw + 12:
            continue
        xs = [W * (j + 1) / (per + 1) for j in range(per)]
        step_y = top + bot + 16
        for y0, sgn in ((P[3] + top, 1), (P[1] - bot, -1)):
            ys = [y0 + sgn * k * step_y for k in range(rows)]
            if all(A[1] <= y <= A[3] for y in ys):
                return [(xs[j % per], ys[j // per]) for j in range(n)]
    cell_w, cell_h = 2 * hw + 16, top + bot + 16                       # a small grid beside the face
    for cols in (1, 2):
        rows_ = math.ceil(n / cols)
        y_top = max(A[1], (P[1] + P[3]) / 2 - (rows_ - 1) * cell_h / 2)
        ys = [y_top + k * cell_h for k in range(rows_)]
        if ys[-1] > A[3]:
            continue
        for side in sorted((-1, 1), key=lambda sd: -((P[0]) if sd < 0 else (W - P[2]))):
            edge = P[0] - hw if side < 0 else P[2] + hw
            xs = [edge + side * k * cell_w for k in range(cols)]
            if all(A[0] <= x <= A[2] for x in xs):
                return [(xs[j % cols], ys[j // cols]) for j in range(n)]
    return None


# ================================================================== captions
def draw_caption(fr, ph, t, emph, y, lead=0.05):
    sprs, total, gap = [], 0, 16
    for w in ph:
        word = w["w"].strip()
        key = word.lower().strip(".,?!\"'")
        s = tspr(word, "caption_em", (255, 226, 160)) if key in emph else tspr(word, "caption")
        sprs.append((w, s)); total += s.shape[1] + gap
    total -= gap
    hh = int(TYPE["caption"][1] * 1.25)
    k0 = t - ph[0].get("_show0", ph[0]["s"] - lead - 0.10) + 1 / FPS     # visible on its first frame
    p_in = ease_out(k0 / 0.16)
    a = min(p_in, ease_out((ph[0]["ph_end"] - t) / 0.12))
    sc = 0.94 + 0.06 * mg.back(clamp(k0 / 0.16))           # the pill settles in: 94 % -> a hair over -> 100 %
    glass(fr, W / 2 - (total / 2 + 40) * sc, y - (hh / 2 + 18) * sc, (total + 80) * sc, (hh + 36) * sc, alpha=a,
          tint=(16, 16, 20), tint_a=0.36, blur=22)
    x = W / 2 - total / 2
    for w, s in sprs:                                      # each word brightens with a small lift as it is spoken
        k = clamp((t - (w["s"] - lead)) / 0.10)
        lift = -6 * math.sin(math.pi * clamp((t - (w["s"] - lead)) / 0.30))
        paste(fr, s, x, y - s.shape[0] / 2 + lift + 2, a * (0.38 + 0.62 * ease_out(k)))
        x += s.shape[1] + gap
    return [W / 2 - total / 2 - 40, y - hh / 2 - 18, W / 2 + total / 2 + 40, y + hh / 2 + 18]


# ================================================================== audio
def paper_turn(seed=0, dur=0.42):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    hi = np.convolve(noise - np.convolve(noise, np.ones(6) / 6, "same"), np.ones(2) / 2, "same")
    env = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    spikes = np.zeros(n)
    for _ in range(14):
        i = int(rng.integers(0, n - 400)); spikes[i:i + 400] += np.exp(-np.linspace(0, 6, 400)) * rng.uniform(0.5, 1)
    low = np.convolve(rng.standard_normal(n), np.ones(60) / 60, "same") * np.exp(-np.linspace(0, 5, n)) * 3
    x = hi * env * (0.5 + spikes) + low * env
    x /= np.max(np.abs(x)) + 1e-9
    return np.stack([x, x]).astype(np.float32)


def sfx_clip(name, seed=0):
    return paper_turn(seed) if name == "paper" else A.sfx(name, seed)


def level_bed(seg, target_rms, strength=0.55, win=1.0):
    mono = np.abs(seg).mean(axis=0)
    k = int(win * SR)
    env = np.sqrt(np.convolve(mono ** 2, np.ones(k) / k, "same")) + 1e-6
    g = np.clip((target_rms / env) ** strength, 10 ** (-6 / 20), 10 ** (12 / 20))
    g = np.convolve(g, np.ones(k // 2) / (k // 2), "same")
    return seg * g[None, :]


def mix_audio(spec, base, dur, out_wav):
    voice = load_audio(base, SR)
    tail = int(spec.get("tail", 0) * SR)
    mix = np.pad(voice, ((0, 0), (0, tail)))
    speech = voice[:, np.abs(voice).mean(axis=0) > 0.01]
    v_rms = np.sqrt(np.mean(speech ** 2)) if speech.size else 0.05
    duck = np.pad(A.duck_envelope(voice, depth_db=spec.get("duck_db", -4)), (0, tail), constant_values=1.0)
    for m in spec.get("music", []):
        song = load_audio(m["file"], SR)
        t0, t1 = m.get("t0", 0.0), m.get("t1", dur + spec.get("tail", 0))
        st = int(m.get("start", 0) * SR)
        seg = song[:, st:st + int((t1 - t0) * SR)]
        target = v_rms * 10 ** (m.get("db", -9) / 20)
        seg = level_bed(seg, target)
        seg = seg * target / (np.sqrt(np.mean(seg ** 2)) + 1e-9)
        seg = A.fade(seg, m.get("fade_in", 0.5), m.get("fade_out", 1.5))
        i0 = int(t0 * SR)
        L = min(seg.shape[1], mix.shape[1] - i0)
        mix[:, i0:i0 + L] += seg[:, :L] * duck[None, i0:i0 + L]
    for s in spec.get("sfx", []):
        c = sfx_clip(s["name"], s.get("seed", 0))
        g = v_rms * 10 ** (s.get("db", -15) / 20) / (np.sqrt(np.mean(c[:, np.abs(c).mean(0) > 1e-3] ** 2)) + 1e-9)
        A.place(mix, c, s["t"], g)
    save_audio(out_wav, A.normalize(mix), SR)


# ================================================================== main
class BaseReader:
    def __init__(self, path, h=None):
        self.p = subprocess.Popen([FFMPEG, "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE)
        self.h, self.last = h or H, None

    def read(self):
        raw = self.p.stdout.read(W * self.h * 3)
        if raw and len(raw) == W * self.h * 3:
            self.last = np.frombuffer(raw, np.uint8).reshape(self.h, W, 3).copy()
        return self.last.copy()

    def close(self):
        self.p.terminate()


def detect_faces(det, fr):
    small = cv2.resize(fr, (fr.shape[1] // 2, fr.shape[0] // 2), interpolation=cv2.INTER_AREA)
    det.setInputSize((fr.shape[1] // 2, fr.shape[0] // 2))
    _, f = det.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    return [[float(r[0] - HAIR_SIDE * r[3]) * 2, float(r[1] - HAIR_UP * r[3]) * 2,
             float(r[0] + r[2] + HAIR_SIDE * r[3]) * 2, float(r[1] + r[3]) * 2] for r in (f if f is not None else [])]


def face_only(boxes):
    """The detector's own face box back from a hair-padded one (titles may touch the top of the hair, never a face)."""
    out = []
    for x0, y0, x1, y1 in boxes:
        h = (y1 - y0) / (1 + HAIR_UP)
        out.append([x0 + HAIR_SIDE * h, y1 - h, x1 - HAIR_SIDE * h, y1])
    return out


def main():
    args = sys.argv[1:]
    bg_only = "--bg-only" in args
    path = [a for a in args if not a.startswith("--")][0]
    spec = json.load(open(path))
    global SHOW
    SHOW = spec.get("show", "")
    if spec.get("format") == "long":
        set_long()
    base = spec["base"]
    fpath = os.path.splitext(base)[0] + ".faces.json"
    if not os.path.exists(fpath):
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "analyze_base.py"), base], check=True)
    faces = json.load(open(fpath))
    ppath = os.path.splitext(base)[0] + ".plan.json"
    plan = json.load(open(ppath)) if os.path.exists(ppath) else None
    words = json.load(open(spec["words"])) if spec.get("words") else []      # long form: no subtitles
    for a_, b_ in spec.get("fix", []):
        for w in words:
            if w["w"].strip() == a_:
                w["w"] = b_
    phrases = ([] if LONG or spec.get("captions") is False
               else mg.build_phrases([dict(w) for w in words if w["w"].strip()], 4, 22))
    emph = set(x.lower().strip(".,?!\"'") for x in spec.get("emphasis", []))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", base],
                               capture_output=True, text=True).stdout)
    nfr = int((dur + spec.get("tail", 0)) * FPS)
    cpath = os.path.splitext(base)[0] + ".crops.json"
    bgr = Background(spec, faces, plan, json.load(open(cpath)) if os.path.exists(cpath) else None)
    det = cv2.FaceDetectorYN.create(FACE_MODEL, "", (540, 960), 0.8, 0.3, 50)   # a face = score >= 0.8

    spath = os.path.splitext(base)[0] + ".split.mp4"
    split_reader = (lambda: BaseReader(spath, H - PH)) if os.path.exists(spath) else (lambda: None)

    # ---- pass 1: background only, faces in every frame
    rd, rs = BaseReader(base), split_reader()
    F, L = [], []
    for i in range(nfr):
        fr, info = bgr.render(rd.read(), i / FPS, rs.read() if rs else None)
        L.append(info["layout"])
        F.append(detect_faces(det, fr) if info["layout"] != "statement" else [])
    rd.close()
    if rs:
        rs.close()
    planner = Planner(F, L)
    notes = plan_overlays(spec, planner, phrases, Planner([face_only(f) for f in F], L))
    for n in notes:
        print("  ! placement:", n)

    out = spec["out"].replace(".mp4", "_bg.mp4") if bg_only else spec["out"]
    wav = os.path.splitext(spec["out"])[0] + "_mix.wav"
    if not bg_only:
        mix_audio(spec, base, dur, wav)
    enc_cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-"] + ([] if bg_only else ["-i", wav]) + ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
                                                                 "-pix_fmt", "yuv420p"] + \
              ([] if bg_only else ["-c:a", "aac", "-b:a", "192k", "-shortest"]) + ["-movflags", "+faststart", out]
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)
    log = None if bg_only else open(os.path.splitext(spec["out"])[0] + ".log.jsonl", "w")
    rd, rs = BaseReader(base), split_reader()
    els = spec["elements"]
    for i in range(nfr):
        t = i / FPS
        fr, info = bgr.render(rd.read(), t, rs.read() if rs else None)
        boxes, cap, cap_hair = [], None, False
        if not bg_only:
            lay = info["layout"]
            live = [ph for ph in phrases if ph[0]["_show0"] <= t <= ph[0]["ph_end"]]
            if live:                                       # one caption at a time: the newest phrase wins a hand-over
                ph = max(live, key=lambda p_: p_[0]["s"])
                for s0, s1, y, hair_ok in ph[0].get("_place", []):
                    if s0 <= t < s1 and y is not None:
                        cap = [round(v) for v in draw_caption(fr, ph, t, emph, y)]
                        cap_hair = hair_ok
            clear = lambda b: (not any(overlap(b, pad(f, 16)) for f in F[i])  # 16 px stricter than
                               and not (cap and overlap(b, cap)))             # check.py's detector
            if lay == "statement":
                for e in els:
                    if e["type"] == "statement" and e["t0"] <= t < e["t1"]:
                        draw_statement(fr, e, t)
            for e in els:
                if e["type"] == "title":
                    a = fade(t, e["t0"], e["t1"], 0.3, 0.3)
                    tb = title_boxes(dict(e, y=e["_y"], kicker=e["_kicker"]))[0]
                    if a > 0 and lay != "statement" and (clear(tb) or (e.get("_hair_ok") and not any(
                            overlap(tb, f) for f in face_only(F[i])) and not (cap and overlap(tb, cap)))):
                        draw_title(fr, e, a)
                        boxes.append(["title"] + [round(v) for v in tb])
                elif e["type"] == "pill" and not e.get("_skip"):
                    a = fade(t, e["t0"], e["t1"])
                    pb = pill_box(e, e["_x"], e["_y"])
                    if a > 0 and lay != "statement" and clear(pb):
                        draw_pill(fr, e, t, a, e["_x"], e["_y"])
                        boxes.append(["pill"] + [round(v) for v in pb])
                elif e["type"] == "chip" and not e.get("_skip"):
                    a = fade(t, e["t0"], e["t1"])
                    r = e.get("r", 110) * e.get("_rs", 1.0)
                    cb = chip_box(e["_x"], e["_y"], r, e.get("label"))
                    if a > 0 and lay != "statement" and clear(cb):
                        draw_chip(fr, e["_x"], e["_y"], r, a, img=load_img(e["img"]) if e.get("img") else None,
                                  icon=e.get("icon"), t=t, label=e.get("label"))
                        boxes.append(["chip"] + [round(v) for v in cb])
                elif e["type"] == "orbit" and e["t0"] <= t <= e["t1"] + 0.3 and lay != "statement":
                    sh = bgr.shot_at(t)
                    pos = orbit_layout(e, t, smooth_face(F, L, i, int(round(sh["t0"] * FPS)),
                                                         int(round(sh["t1"] * FPS))))
                    if pos is None:
                        pos = e.get("_last_pos") or []
                        if not pos:
                            e["_hidden"] = e.get("_hidden", 0) + 1
                    else:
                        e["_last_pos"] = pos
                    for (x, y), c in zip(pos, e["chips"]):
                        a = fade(t, c.get("t", e["t0"]), c.get("t_out", e["t1"]), 0.25, 0.25)
                        if a <= 0:
                            continue
                        r = c.get("r", 96)
                        if not clear(chip_box(x, y, r, c.get("label"))):
                            continue                    # last line of defence: never on a face or the caption
                        draw_chip(fr, x, y, r, a, img=load_img(c["img"]) if c.get("img") else None,
                                  icon=c.get("icon"), t=t, label=c.get("label"))
                        boxes.append(["orbit"] + [round(v) for v in chip_box(x, y, r, c.get("label"))])
            fade_len = spec.get("fade_out", 0.6)
            if t > nfr / FPS - fade_len:
                fr = (fr.astype(np.float32) * clamp((nfr / FPS - t) / fade_len)).astype(np.uint8)
            log.write(json.dumps({"t": round(t, 3), "layout": lay, "zoom": round(info["zoom"], 4),
                                  "dx": round(info["dx"], 2), "dy": round(info["dy"], 2), "cap": cap, "cap_hair": cap_hair,
                                  "boxes": boxes, "faces": [[round(v) for v in f] for f in F[i]]}) + "\n")
        enc.stdin.write(fr.tobytes())
    enc.stdin.close(); enc.wait(); rd.close()
    if rs:
        rs.close()
    if log:
        log.close()
    for e in els:
        if e.get("_hidden"):
            print(f"  ! placement: orbit at {e['t0']:.1f}s hid its chips on {e['_hidden']} frame(s) (no face-free room)")
    print("done:", out)


if __name__ == "__main__":
    main()
