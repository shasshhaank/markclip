"""Repetition finder for the base edit (house rule: cut repeats and restarts when the meaning stays intact).

Removes the FIRST copy of:
  * an exact consecutive repeat of 1-8 words: "is, is", "and and", "I I", "it's it's", "when he when he",
    "It was a collection of experiences. It was a collection of experiences." (also drops a co-host's line that the
    speaker repeats)
  * an abandoned restart: a short run of function words that starts again differently: "if you if a fight" -> "if a
    fight", "that the that is"
Keeps:
  * emphasis doubles ("really, really", "very very", "no, no")
  * lists and parallel phrasing ("no friends, no family, no partner"): a restart fragment must be function words only and
    must not end in punctuation
Every removal is printed so a human can veto it with --keep-repeat on base_edit.py."""
import re

STOP = {"a", "an", "the", "and", "but", "or", "so", "if", "i", "you", "he", "she", "it", "we", "they", "that", "this",
        "is", "was", "are", "were", "be", "to", "of", "in", "on", "at", "for", "with", "as", "like", "there", "it's",
        "i'm", "you're", "there's", "that's", "what", "when", "how", "any", "my", "your", "his", "her", "their", "do",
        "does", "did", "can", "could", "would", "will", "just", "um", "uh"}
EMPHASIS = {"really", "very", "so", "much", "no", "never", "more", "too", "yeah", "yes", "okay", "right"}


def norm(w):
    return re.sub(r"[^\w']", "", w.lower().replace("’", "'"))


LEAD = {"it", "it's", "its", "there's", "that's", "this", "that", "he", "she", "they", "it'll", "was"}


def stem(t):
    """experiences -> experience: Whisper sometimes hears a plural on one copy of a repeated phrase."""
    return t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") and "'" not in t else t


def find_repeats(words, keep=()):
    """words: [{"w": text, ...}] in order. Returns (set of indices to remove, list of human-readable notes)."""
    toks = [norm(w["w"]) for w in words]
    keep = {" ".join(norm(x) for x in k.split()) for k in keep}     # "when he" stays two words
    remove, notes = set(), []
    i = 0
    while i < len(toks):
        hit = False
        for n in range(8, 0, -1):
            a, b = toks[i:i + n], toks[i + n:i + 2 * n]
            if len(b) == n and a == b and all(a):
                if (n == 1 and a[0] in EMPHASIS) or " ".join(a) in keep:
                    i += 2 * n                      # kept on purpose: no other rule may cut either copy
                    hit = True
                    break
                remove.update(range(i, i + n))
                notes.append(f"repeat: drop '{' '.join(w['w'] for w in words[i:i + n])}' before its second copy")
                i += n
                hit = True
                break
        if hit:
            continue
        for n in range(8, 3, -1):           # near repeat: same phrase, Whisper heard the first word or a plural
            a, b = [stem(x) for x in toks[i:i + n]], [stem(x) for x in toks[i + n:i + 2 * n]]
            if (len(b) == n and a[1:] == b[1:] and toks[i] in LEAD and toks[i + n] in LEAD
                    and " ".join(toks[i:i + n]) not in keep):
                remove.update(range(i, i + n))
                notes.append(f"near repeat: drop '{' '.join(w['w'] for w in words[i:i + n])}' before its second copy")
                i += n
                hit = True
                break
        if hit:
            continue
        for k in (2, 3):
            if i + k < len(toks) and toks[i] == toks[i + k] and toks[i] in STOP:
                frag = words[i:i + k]
                if (all(t in STOP for t in toks[i:i + k])
                        and not any(f["w"].rstrip()[-1:] in ",.;:?!" for f in frag)
                        and toks[i + 1:i + k] != toks[i + k + 1:i + 2 * k]
                        and " ".join(toks[i:i + k]) not in keep):
                    remove.update(range(i, i + k))
                    notes.append(f"restart: drop '{' '.join(f['w'] for f in frag)}' (sentence starts again)")
                    i += k
                    hit = True
                    break
        if not hit:
            i += 1
    return remove, notes


if __name__ == "__main__":
    import json, sys
    ws = json.load(open(sys.argv[1]))
    ws = ws["words"] if isinstance(ws, dict) else ws
    rm, notes = find_repeats(ws)
    print("\n".join(notes) or "no repeats")
