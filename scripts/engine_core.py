"""markclip engine core: easing, compositing, liquid glass, pixel-art icons, glitch, caption phrasing.
Shared by render.py. No font paths live here: render.py passes the bundled Inter / Instrument Serif files in."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 44100   # SR: ClipIt's place/fade/sfx/duck/normalize all assume 44.1 kHz
INK, PAPER, GRID = (22, 22, 22), (244, 242, 237), (226, 224, 218)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def back(x, s=1.4):
    """Ease out with a slight overshoot: the caption pill settles in."""
    x = clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def ease_in_out(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


_fonts, _sprites = {}, {}


def font(path, size):
    k = (path, size)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, size)
    return _fonts[k]


def text_sprite(text, path, size, color=(255, 255, 255), tracking=0):
    k = (text, path, size, color, tracking)
    if k in _sprites:
        return _sprites[k]
    f = font(path, size)
    asc, desc = f.getmetrics()
    w = int(f.getlength(text) + tracking * max(0, len(text) - 1)) + 4
    img = Image.new("RGBA", (max(w, 1), asc + desc + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = 2
        for ch in text:
            d.text((x, 2), ch, font=f, fill=color + (255,))
            x += f.getlength(ch) + tracking
    else:
        d.text((2, 2), text, font=f, fill=color + (255,))
    _sprites[k] = np.array(img)
    return _sprites[k]


def paste(frame, spr, x, y, alpha=1.0, anchor="tl"):
    """Alpha-composite an RGBA sprite onto the RGB frame. (x, y) is the anchor point."""
    if alpha <= 0.003 or spr is None:
        return
    h, w = spr.shape[:2]
    if anchor == "c":
        x, y = x - w / 2, y - h / 2
    elif anchor == "tc":
        x = x - w / 2
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = spr[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = s[..., 3:4] / 255.0 * alpha
    reg = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (reg * (1 - a) + s[..., :3] * a).astype(np.uint8)


_masks = {}


def rr_mask(w, h, r):
    k = (w, h, r)
    if k not in _masks:
        ss = 3
        m = Image.new("L", (w * ss, h * ss), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], r * ss, fill=255)
        _masks[k] = np.array(m.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0
    return _masks[k]


def soft_blur(img, sigma):
    if sigma < 1:
        return img
    h, w = img.shape[:2]
    f = 4 if min(h, w) > 64 else 1
    small = cv2.resize(img, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma / f)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def glass(frame, x, y, w, h, r=None, alpha=1.0, tint=(255, 255, 255), tint_a=0.14, blur=28, shadow=True):
    """Liquid-glass panel: frosted copy of what's behind, a little tint, a bright rim and a top sheen."""
    if alpha <= 0.003:
        return
    r = h // 2 if r is None else r
    x, y, w, h = int(x), int(y), int(w), int(h)
    pad = 40
    X0, Y0 = max(0, x - pad), max(0, y - pad)
    X1, Y1 = min(frame.shape[1], x + w + pad), min(frame.shape[0], y + h + pad)
    if X1 <= X0 or Y1 <= Y0:
        return
    m = np.zeros((Y1 - Y0, X1 - X0), np.float32)
    mm = rr_mask(w, h, r)
    mx0, my0 = x - X0, y - Y0
    sx0, sy0 = max(0, -mx0), max(0, -my0)
    ex, ey = min(w, m.shape[1] - mx0), min(h, m.shape[0] - my0)
    if ex <= sx0 or ey <= sy0:              # shape entirely outside the frame
        return
    m[my0 + sy0:my0 + ey, mx0 + sx0:mx0 + ex] = mm[sy0:ey, sx0:ex]
    reg = frame[Y0:Y1, X0:X1].astype(np.float32)
    if shadow:   # soft drop shadow
        sh = cv2.GaussianBlur(np.roll(m, 10, axis=0), (0, 0), 16)
        reg *= (1 - 0.28 * alpha * sh[..., None])
    fro = soft_blur(reg, blur)
    fro = fro * (1 - tint_a) + np.array(tint, np.float32) * tint_a
    yy = np.linspace(0, 1, reg.shape[0], dtype=np.float32)[:, None, None]
    sheen = np.clip((my0 + h * 0.5 - yy * reg.shape[0]) / (h * 0.5), 0, 1) * 0.10   # brighter top half
    fro = fro + 255 * sheen
    inner = cv2.erode(m, np.ones((5, 5), np.uint8))
    rim = np.clip(m - inner, 0, 1)
    out = reg * (1 - m[..., None] * alpha) + fro * m[..., None] * alpha
    out = out * (1 - rim[..., None] * 0.55 * alpha) + 255 * rim[..., None] * 0.55 * alpha
    frame[Y0:Y1, X0:X1] = np.clip(out, 0, 255).astype(np.uint8)


PAL = dict(k=(28, 28, 28), w=(255, 255, 255), r=(232, 58, 46), R=(168, 32, 30), y=(255, 206, 46), o=(246, 146, 38),
           g=(66, 194, 96), G=(30, 122, 64), b=(62, 132, 232), B=(30, 78, 168), c=(150, 214, 246), s=(242, 212, 146),
           S=(206, 168, 96), n=(146, 94, 52), N=(96, 60, 34), l=(206, 206, 206), d=(124, 124, 124), p=(255, 170, 190),
           m=(222, 62, 204), t=(236, 210, 170))


N = 24


def _px(draw_fn, t):
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(im), t)
    return im


def ic_island(d, t):
    d.ellipse([16, 1, 22, 7], fill=PAL["y"])
    d.rectangle([0, 17, 23, 23], fill=PAL["b"])
    for i in range(4):   # moving wave glints
        x = int((i * 7 + t * 6) % 26) - 2
        d.line([x, 19 + (i % 2) * 2, x + 2, 19 + (i % 2) * 2], fill=PAL["c"])
    d.ellipse([3, 13, 18, 20], fill=PAL["s"], outline=PAL["S"])
    sway = int(round(math.sin(t * 2.2)))
    d.line([10, 15, 9, 9, 10 + sway, 5], fill=PAL["n"], width=2)
    for pts in ([10, 5, 4, 7, 2, 10], [10, 5, 16, 6, 18, 9], [10, 5, 7, 2, 5, 3], [10, 5, 13, 2, 16, 3]):
        d.line([p + (sway if i % 2 == 0 else 0) for i, p in enumerate(pts)], fill=PAL["G"], width=2)


def ic_eye(d, t, slash=True):
    d.ellipse([2, 6, 21, 17], fill=PAL["w"], outline=PAL["k"], width=1)
    look = int(round(math.sin(t * 1.7) * 2))
    d.ellipse([8 + look, 7, 15 + look, 15], fill=PAL["b"])
    d.ellipse([10 + look, 9, 13 + look, 12], fill=PAL["k"])
    d.point([11 + look, 9], fill=PAL["w"])
    if slash:
        d.line([3, 21, 21, 3], fill=PAL["w"], width=4)
        d.line([3, 21, 21, 3], fill=PAL["r"], width=2)


def _heart(d, col=PAL["r"], dark=PAL["R"], beat=0):
    d.ellipse([2 - beat, 3 - beat, 12, 13], fill=col)
    d.ellipse([11, 3 - beat, 21 + beat, 13], fill=col)
    d.polygon([(2 - beat, 9), (21 + beat, 9), (11.5, 21 + beat)], fill=col)
    d.line([(15, 16), (12, 20)], fill=dark, width=1)
    d.rectangle([5, 6, 6, 7], fill=PAL["w"])
    d.point([7, 5], fill=PAL["w"])


def ic_heart(d, t):
    _heart(d, beat=1 if (t * 1.6) % 1 < 0.18 else 0)


def ic_heart_broken(d, t):
    _heart(d)
    gap = 1 if t > 0.2 else 0
    d.line([(11, 4), (13, 8), (10, 11), (13, 14), (11, 18), (12, 21)], fill=PAL["k"], width=1 + gap)


def ic_heart_mended(d, t):
    _heart(d)
    d.polygon([(6, 15), (16, 5), (19, 8), (9, 18)], fill=PAL["t"])
    for p in ((10, 11), (12, 11), (11, 12), (13, 10)):
        d.point(p, fill=PAL["S"])


def ic_flag(d, t):
    d.line([5, 3, 5, 22], fill=PAL["k"], width=2)
    w = [int(round(math.sin(t * 5 + i * 0.7))) for i in range(5)]
    d.polygon([(6, 4), (11, 4 + w[1]), (15, 4 + w[2]), (20, 4 + w[3]), (20, 13 + w[3]), (15, 13 + w[2]),
               (11, 13 + w[1]), (6, 13)], fill=PAL["g"], outline=PAL["G"])
    d.rectangle([3, 21, 9, 22], fill=PAL["d"])


def ic_bucket(d, t):
    d.arc([5, 1, 18, 14], 180, 360, fill=PAL["d"], width=1)
    d.polygon([(4, 7), (19, 7), (17, 19), (6, 19)], fill=PAL["l"], outline=PAL["k"])
    d.rectangle([4, 7, 19, 8], fill=PAL["d"])
    lvl = 9 + int((t * 2.5) % 9)        # water keeps running out
    d.polygon([(5, lvl), (18, lvl), (17, 18), (6, 18)], fill=PAL["b"])
    d.rectangle([11, 19, 12, 19], fill=PAL["k"])   # the hole
    for i in range(3):                  # drops falling from the hole
        yy = 20 + int(((t * 9) + i * 1.3) % 4)
        d.point([11 + (i % 2), yy], fill=PAL["c"])


def ic_trophy(d, t):
    d.polygon([(6, 3), (17, 3), (16, 11), (12, 14), (11, 14), (7, 11)], fill=PAL["y"], outline=PAL["o"])
    d.arc([2, 3, 9, 10], 90, 270, fill=PAL["o"], width=2)
    d.arc([14, 3, 21, 10], 270, 90, fill=PAL["o"], width=2)
    d.rectangle([10, 14, 13, 17], fill=PAL["o"])
    d.rectangle([7, 18, 16, 20], fill=PAL["N"])
    if (t * 1.3) % 1 < 0.3:
        d.point([9, 5], fill=PAL["w"]), d.point([9, 6], fill=PAL["w"])


def ic_grave(d, t):
    d.rectangle([0, 20, 23, 23], fill=PAL["G"])
    d.rounded_rectangle([6, 4, 17, 21], 5, fill=PAL["l"], outline=PAL["d"])
    d.text((9, 7), "?", fill=PAL["d"])


def ic_firework(d, t):
    for k, (col, cx, cy, off) in enumerate(((PAL["r"], 8, 8, 0.0), (PAL["y"], 15, 14, 0.33), (PAL["m"], 7, 16, 0.66))):
        ph = (t * 0.8 + off) % 1
        r0, r1 = ph * 7, 1.5 + ph * 7
        if ph > 0.85:
            continue
        for a in range(10):
            ang = a * math.pi / 5 + k * 0.3
            d.line([cx + r0 * math.cos(ang), cy + r0 * math.sin(ang), cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)],
                   fill=col, width=1)
        d.point([cx, cy], fill=PAL["w"])


def ic_arrow_up(d, t):
    lift = int(round(math.sin(t * 3) * 1))
    d.polygon([(4, 20), (9, 22), (20, 19), (15, 17)], fill=(30, 30, 30, 90))                 # hard shadow
    d.polygon([(8, 20 - lift), (8, 11 - lift), (4, 11 - lift), (11, 3 - lift), (18, 11 - lift), (14, 11 - lift),
               (14, 20 - lift)], fill=PAL["r"], outline=PAL["k"])
    d.polygon([(14, 11 - lift), (18, 11 - lift), (18, 12 - lift), (15, 12 - lift), (15, 21 - lift), (14, 20 - lift)],
              fill=PAL["R"])


ICONS = dict(arrow_up=ic_arrow_up, island=ic_island, eye=lambda d, t: ic_eye(d, t, False), eye_slash=ic_eye, heart=ic_heart,
             heart_broken=ic_heart_broken, heart_mended=ic_heart_mended, flag=ic_flag, bucket=ic_bucket,
             trophy=ic_trophy, grave=ic_grave, firework=ic_firework)


def icon_rgba(name, t, size):
    im = _px(ICONS[name], t).resize((size, size), Image.NEAREST)
    return np.array(im)


def glitch(spr, amt, seed):
    """dgrees-style glitch between icons: horizontal slices jump sideways, with a chroma split."""
    if amt <= 0:
        return spr
    rng = np.random.default_rng(seed)
    out = spr.copy()
    h = spr.shape[0]
    for _ in range(int(3 + amt * 9)):
        y0 = int(rng.integers(0, h - 4)); y1 = min(h, y0 + int(rng.integers(4, max(5, h // 6))))
        out[y0:y1] = np.roll(spr[y0:y1], int(rng.integers(-1, 2) * amt * h * 0.12), axis=1)
    out[..., 0] = np.roll(out[..., 0], int(amt * 10), axis=1)
    return out


_imgs = {}


def load_img(path):
    if path not in _imgs:
        im = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
        _imgs[path] = im
    return _imgs[path]


WEAK = {"a", "an", "the", "of", "to", "in", "on", "at", "for", "with", "and", "but", "or", "my", "your", "his", "her",
        "their", "its", "our", "is", "was", "be", "if", "that", "when", "who", "which", "it", "i", "you", "we", "they",
        "he", "she"}


def build_phrases(words, max_words=4, max_chars=22):
    """Caption phrases: break at . ? ! always, at a comma once the phrase has 2+ words (no one-word "it," pill), and
    at the size limit, but never right after a weak word ("do it on a / desert island" -> "do it / on a desert") and
    never leaving a sentence's last word alone ("would you still do / it?" -> one phrase)."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        txt = " ".join(x["w"] for x in cur)
        nxt = words[i + 1]["w"].rstrip() if i + 1 < len(words) else ""
        final = nxt.endswith((".", "?", "!"))
        fits = len(txt) + 1 + len(nxt) <= max_chars + 6
        if w["w"].rstrip().endswith((".", "?", "!")) or (w["w"].rstrip().endswith(",") and len(cur) >= 2
                                                          and not (final and fits)):
            out.append(cur)
            cur = []
        elif len(cur) >= max_words or len(txt) >= max_chars:
            if final and fits:
                continue                                       # take the sentence's last word along
            carry = [cur.pop()] if final and len(cur) >= 3 else []
            while len(cur) >= 3 and cur[-1]["w"].strip().lower() in WEAK:
                carry.insert(0, cur.pop())                     # back up past weak words, keep two or more
            out.append(cur)
            cur = carry
    if cur:
        out.append(cur)
    for i, ph in enumerate(out):
        nxt = out[i + 1][0]["s"] if i + 1 < len(out) else ph[-1]["e"] + 0.6
        ph_end = min(nxt - 0.02, ph[-1]["e"] + 0.7)
        for w in ph:
            w["ph_end"] = ph_end
    return out
