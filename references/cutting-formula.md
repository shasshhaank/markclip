# Cutting formula: finding the moment and cutting the base

## 1. Pick the episode
Start from the newest episode the brief allows (references/brief.md), unless the user names one. Chapter times are
usually in the video description or on the show's own site. Long podcast episodes run for hours, and shorter uploads
are often cuts of them; a podcast's own RSS audio usually has the same runtime as its video upload, give or take a few
seconds, if you ever need audio while YouTube is blocking you.

Pull the whole episode's subtitles first (cheap, no video):
```
$PY $S/scripts/episode_subs.py subs VIDEO_ID [VIDEO_ID ...]
```
The first argument is the output folder. Per id it writes `subs/ID.txt` (one line per ~10 s, `[H:MM:SS] words`) and
`subs/ID.json` (word timings). It takes the uploader's own track, else YouTube's auto captions in the original
language (never an auto-translation), and sleeps 8 s between ids (bursts get the IP bot-blocked).

Read only the chapters that match the platform (see brief.md, platform fit): print a time window with
`awk -v A=START_S -v B=END_S -F'[][]' '{split($2,t,":"); s=t[1]*3600+t[2]*60+t[3]; if (s>=A && s<=B) print}' subs/ID.txt`.

## 2. Score candidate moments
A good moment has all of these:
1. **A hook in its first sentence**: an absolute claim ("The most important moment in any relationship is the first
   fight"), a test or question ("would you still do it if nobody knew?"), or a story opener ("I read a biography of
   Casanova...").
2. **The main speaker talking**, on camera, in the first 5 s. Check on a contact sheet who is talking; a moment that
   opens on the host's or interviewer's question doesn't qualify unless the brief is about that person.
3. **One complete thought** of 25-55 s once pauses are trimmed (YouTube Shorts 25-45 s works best, Reels up to
   55 s). A long-form video is a whole argument of several minutes, in 2 or 3 parts (long-form.md).
4. **A payoff at the end**: the reframe, the answer, the sad turn. Endings that trail into the next topic don't
   count.
5. **Nothing factually shaky on screen.** If the speaker hedges a fact ("present-day Slovakia or something") and it's
   wrong, cut that sentence instead of captioning it.
6. **No sponsor read inside the window.** Ads often sit at chapter ends ("This episode is brought to you by...").

Pick as many per platform as the user asks for, each from a different idea (two clips about the same idea in one
batch look like recycling).

## 3. Cut the base edit (`scripts/base_edit.py`)
Fetch only the window plus about 10 s each side (clipit-extraction.md), then:
```
$PY $S/scripts/base_edit.py input/X.mp4 --start 21.44 --end 87.0 --drop 54.70-67.80 --out base/01.mp4
$PY $S/scripts/heard_check.py base/01.mp4
```
All times are seconds in the input file (a fetched section starts at 0), not episode times. Word times are in the
verbatim transcript base_edit caches at `work/<input name>/verbatim_<t0>_<t1>.json`.

| Flag | Meaning |
|---|---|
| `--start S --end E` (required) | the moment, on word times; it is snapped to whole sentences and real pauses (ClipIt's `snap_speech`), and a move over 0.3 s is printed |
| `--out OUT` (required) | the base, normally `base/NN.mp4` |
| `--drop a-b` (repeatable) | words starting inside a-b are removed: a tangent, or a word leaking in from the previous sentence ("Anyway,"). In the middle of the clip the audio they leave becomes a cut only when the gap between the kept words is 1 s or more; for a shorter piece of audio use `--cut` |
| `--cut a-b` (repeatable) | remove exactly this audio (a stutter, a short leaked word) |
| `--fix wrong=right` (repeatable) | transcript typo fix before repeat detection |
| `--retime OLD=NEW[:END]` (repeatable) | give the word that starts at OLD (to 0.01 s) a new start, and optionally a new end, when its span swallowed a pause |
| `--keep-repeat "words"` (repeatable) | veto a repeat removal (exact words, case and punctuation ignored): both copies stay and no other rule may cut either |
| `--no-dedupe` | no repeat removal at all |
| `--recheck` | after the edit, transcribe the finished base again word for word (cached under `work/<input name>/recheck/`) and cut any repeat the first pass missed: it re-runs itself once with those `--cut`s; repeats whose cut would be under 0.2 s stay |
| `--preview N` | plan only: write `OUT.plan.json` and `OUT.voice.wav`, skip the video (any non-zero number) |
| `--long` | long form: a 1920x1080 base with eyes at 450, no split track (it sets `MARKCLIP_FORMAT=long` for `frame_base.py`; long-form.md) |

### What gets cut (and nothing else)
- **Repeats and restarts** (`scripts/dedupe.py`). The window is transcribed word for word (Whisper large-v3, a
  disfluent prompt, 24 s chunks, 2 s overlap) because ClipIt's transcript tidies repeats away; any stretch of 1 s or
  more the verbatim pass skipped is filled from ClipIt's transcript. Removed, always the first copy:
  - an exact repeat of 1-8 words: "is, is", "I I", "when he when he", a whole repeated sentence (this also removes a
    co-host's line that the speaker then repeats);
  - a near repeat of 4-8 words that differs only in its first word (both lead words such as it, it's, that, this,
    he, she, they, was) or by a plural ("It was a collection of experiences. That was a collection of experience.");
  - an abandoned restart: 2-3 function words that start again ("if you if a fight" -> "if a fight").
  Kept: emphasis doubles (really, very, so, much, no, never, more, too, yeah, yes, okay, right), lists and parallel
  phrasing ("no friends, no family, no partner": a restart fragment must be function words only with no punctuation).
  Every removal is printed (`dedupe repeat: drop '...'`); read them and veto one with `--keep-repeat` if it changes
  the meaning.
- **Long fillers**: um, uh, umm, uhh, hmm, erm when the filler lasts 0.45 s or more, or the filler plus the pauses
  around it make 0.9 s or more. Short fillers stay (they sound natural).
- **Dead air of 1 s or more** (`DEAD_AIR`), leaving 0.22 s after the last word and 0.15 s before the next. If that gap
  holds 0.35 s or more of audio above 30 % of the speech level (speech the transcript missed), it is kept and flagged
  (`! kept a-b: speech the transcript missed`): check it with `heard_check.py`.

Everything else stays: short pauses, breaths, small fillers. An earlier version cut every 0.45 s pause and split
inside stretched words; it was choppy and clipped words.

### Cut boundaries
- A cut never starts or ends inside a word: around a removed repeat it keeps up to 0.12 s after the last kept word and
  starts again up to 0.10 s before the next one, never touching a neighbouring word (0.02 s guard).
- **Minimum cut 0.2 s** (`MIN_CUT`): a repeat or long filler whose cut would remove less than that stays
  (`kept '...': its cut would be only 0.xx s`); a tiny cut lands mid-voice and gains nothing.
- **Voice pre-roll**: the clip starts just before the voice, never on it. From 0.12 s before the first word (or the
  snapped start, if later) it walks back in 20 ms steps while the audio is still above a quarter of the speech
  threshold (30 % of the median loudness of the kept words), up to 0.3 s, then adds 0.06 s, and never reaches back
  into the previous word (0.02 s guard).
- The end: 0.3 s after the last word at most, 0.1 s past the snapped end, and never into the next word.
- A drop or cut boundary must begin at a word's own start time, or the next word leaks in (a 0.02 s miss let "Like"
  slip into a cut). That is why `heard_check.py` runs after every base: the first word, the last word and each jump
  cut must read as whole sentences with no leaked word, and no co-host word may leak at the end.

### Outputs
| File | Contents |
|---|---|
| `base/NN.mp4` | 1080x1920 (1920x1080 with `--long`), 30 fps, the edited voice; one fixed crop per camera shot (framing.md) |
| `base/NN.split.mp4` | 1080x960, the split screen's bottom half from a wider 9:8 window, no audio (not written with `--long`) |
| `base/NN.plan.json` | `{"src", "ranges", "out", "removed"}`: source path, kept source ranges, their output times, removed word indices |
| `base/NN.crops.json` | per camera piece: source shot, crop, split window, speaker, wide or tight |
| `base/NN.voice.wav` | the edited voice, normalised (the base's audio track) |

It prints `N pieces, T s, cuts only at repeats / long fillers / dead air >= 1s`.

### Two speakers and camera
- A jump cut inside one camera shot switches between the wide and the tight crop (x1.14), so it reads as a second
  camera, not a jump (framing.md).
- **Two people trading lines** that must stay: mark the window with a `duo` element (one person per half, eyes level;
  side by side in long form). Otherwise keep the clip to one speaker; dedupe often removes the co-host's echo for
  you.

## 4. Beat structure (what the 25-55 s of a Short is made of)
| Beat | Time | What happens |
|---|---|---|
| Hook | 0-4.5 s | the speaker on camera + liquid-glass title (their idea in a few words) |
| Setup | ~4-8 s | their framing; first loud statement if the hook line is a punch ("but it *backfires*") |
| Explain | middle | split-screen panel for the concept, orbit chips or checklist pills for lists |
| Turn | wherever the line lands | full-frame statement of the speaker's exact words + punch-in + bass hit, on the music |
| Payoff | last 4-6 s | editorial end card with the takeaway, or a final statement ("It ends in *nothing.*") |

Density: something new every 3-6 s, at most two statements per clip, split windows 4-8 s each, and the speaker's face
on screen for at least half the runtime (the speaker is the anchor of every clip). A long-form video has its own,
calmer structure: parts opened by statement cards, the speaker full frame most of the time, a side layout only where
a concept needs it (long-form.md).
