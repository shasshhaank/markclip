"""markclip spec linter: the house text rules, checked before a render.
  * sentence case: after the first word of a sentence (or of a "·"-separated segment), a capital is allowed only for
    proper nouns ("I", names; add more with "proper_nouns" in the spec) - no title case, no random capitals
  * no ALL-CAPS words (add real acronyms with "acronyms" in the spec)
  * every line fits its box at its type size (measured with the bundled fonts); a split panel's title clears its icon
  * *accent* markup in statements is balanced
  * the captions' words json has no capital mid-sentence (run words.py's repair if this fails)
usage: lint_spec.py SPEC.json [...]      prints SPEC LINT OK, or the findings and exits 1"""
import json, os, re, sys

from PIL import ImageFont

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(SKILL_DIR, "assets", "fonts")
SERIF, SERIF_I = os.path.join(F, "InstrumentSerif-Regular.ttf"), os.path.join(F, "InstrumentSerif-Italic.ttf")
INTER_M = os.path.join(F, "Inter-Medium.ttf")
PROPER = {"I", "I'm", "I've", "I'd", "I'll", "YouTube", "Instagram", "Ep."}   # + the spec's proper_nouns
W = 1080


def width(text, path, size):
    return ImageFont.truetype(path, size).getlength(text)


def words_of(text):
    return re.findall(r"[A-Za-z][A-Za-z'’.\-]*", text)


def case_findings(text, where, proper, acronyms):
    out = []
    for seg in re.split(r"[.?!:·—]\s+|\n\n", text.replace("*", "")):
        ws = words_of(seg)
        for i, w in enumerate(ws):
            core = w.strip(".'’")
            if len(core) >= 2 and core.isupper() and core not in acronyms:
                out.append(f"{where}: all-caps '{w}' in {text!r}")
            elif i > 0 and core[:1].isupper() and core not in proper and w not in proper:
                out.append(f"{where}: capital mid-sentence '{w}' in {text!r} (sentence case only; proper nouns go in"
                           f" the spec's proper_nouns)")
    return out


def fit_findings(text, where, path, size, maxw):
    out = []
    for line in text.split("\n"):
        wpx = width(line.replace("*", ""), path, size)
        if wpx > maxw:
            out.append(f"{where}: line {line!r} is {wpx:.0f}px wide, max {maxw}px at this size - break it")
    return out


def lint(spec, spec_dir="."):
    proper = PROPER | set(spec.get("proper_nouns", []))
    acr = set(spec.get("acronyms", []))
    f = []
    fw = 1920 if spec.get("format") == "long" else W      # the frame width: lines that fit a Short fit long form too

    def txt(t, where):
        f.extend(case_findings(t, where, proper, acr))

    for i, e in enumerate(spec.get("elements", [])):
        tag = f"elements[{i}] {e['type']}"
        if "parts" in e or "side" in e:                 # side layouts: long form only, 2 or 3 parts, left or right
            if fw == W:
                f.append(f"{tag}: parts/side need \"format\": \"long\"")
            elif e.get("parts", 2) not in (2, 3) or e.get("side", "right") not in ("left", "right"):
                f.append(f"{tag}: parts must be 2 or 3 and side left or right")
                continue
        if e["type"] == "title":
            txt(e["text"], tag); f.extend(fit_findings(e["text"], tag, SERIF, 88, fw - 180))
            if e.get("kicker"):
                txt(e["kicker"], tag + " kicker")
        elif e["type"] == "statement":
            txt(e["text"], tag)
            for line in e["text"].split("\n"):          # measured exactly as render.py sets it
                ws, inside, total = line.split(" "), False, 0.0
                for w in ws:
                    inside = inside or w.startswith("*")
                    total += width(w.strip("*"), SERIF_I if inside else SERIF, 140 if inside else 132)
                    inside = inside and not w.endswith("*")
                total += 28 * (len(ws) - 1)
                if total > fw - 120:
                    f.append(f"{tag}: line {line!r} is {total:.0f}px wide, max {fw - 120}px - break it")
            stars = re.findall(r"(?:^|\s)\*|\*(?=\s|$|[.,?!])", e["text"])
            if len(stars) % 2:
                f.append(f"{tag}: unbalanced *accent* markup in {e['text']!r}")
        elif e["type"] == "pill":
            txt(e["text"], tag); f.extend(fit_findings(e["text"], tag, SERIF_I if e.get("quote") else INTER_M,
                                                       60 if e.get("quote") else 44, fw - 180))
        elif e["type"] == "chip" and e.get("label"):
            txt(e["label"], tag)
        elif e["type"] == "orbit":
            for c in e.get("chips", []):
                if c.get("label"):
                    txt(c["label"], tag + " chip")
        elif e["type"] == "editorial":
            hw = min(784, fw // e.get("parts", 2) - 128) if fw > W else 784   # long form: the panel's own width
            txt(e["headline"], tag); f.extend(fit_findings(e["headline"], tag, SERIF, 78, hw))
            if e.get("byline"):
                txt(e["byline"], tag + " byline")
        elif e["type"] == "split":
            p = e["panel"]
            pw = fw // e.get("parts", 2) if fw > W else W       # long form: the panel is a half or a third
            ph = 1080 if fw > W else 960                         # ...and the full height
            for k in ("title", "body", "caption", "headline", "byline"):
                if p.get(k):
                    txt(p[k], f"{tag} panel.{k}")
            for lab in p.get("labels", []):
                if lab:
                    txt(lab, f"{tag} panel.labels")
            for it in p.get("items", []):                # list panel
                txt(it["text"], f"{tag} panel.items")
            if p.get("title"):
                f.extend(fit_findings(p["title"], f"{tag} panel.title", SERIF, 84, pw - 128))
                if p.get("icons"):                       # the title block must not run into the icon
                    t_bottom = 222 + 84 * len(p["title"].split("\n")) + 8
                    t_right = 64 + max(width(l, SERIF, 84) for l in p["title"].split("\n"))
                    isz = p.get("icon_size", min(400, int((0.36 if fw > W else 0.42) * pw)))
                    i_left, i_top = p.get("icon_x", pw - 0.825 * isz) - isz / 2, p.get("icon_y", 520 * ph / 960) - isz / 2 - 8
                    if t_right > i_left and t_bottom > i_top:
                        f.append(f"{tag} panel.title: title block (right {t_right:.0f}, bottom {t_bottom}) overlaps the"
                                 f" icon (left {i_left:.0f}, top {i_top:.0f}) - move the icon or break the title")
    wpath = os.path.join(spec_dir, spec["words"]) if spec.get("words") and not os.path.isabs(spec["words"]) else spec.get("words")
    if wpath and os.path.exists(wpath):
        ws = json.load(open(wpath))
        for a, b in spec.get("fix", []):
            for w in ws:
                if w["w"].strip() == a:
                    w["w"] = b
        for prev, w in zip(ws, ws[1:]):
            core = w["w"].strip(".,?!\"'“”")
            if core[:1].isupper() and core not in proper and not prev["w"].rstrip().endswith((".", "?", "!")):
                f.append(f"captions: capital mid-sentence '{prev['w']} {w['w']}' at {w['s']:.2f}s (re-run words.py)")
    return f


def main():
    bad = 0
    for path in sys.argv[1:]:
        spec = json.load(open(path))
        findings = lint(spec, os.getcwd())
        for x in findings:
            print(f"  {os.path.basename(path)}: {x}")
        bad += len(findings)
    if bad:
        print(f"SPEC LINT FAILED: {bad} finding(s)")
        sys.exit(1)
    print("SPEC LINT OK")


if __name__ == "__main__":
    main()
