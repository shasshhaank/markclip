---
name: markclip
description: Edit talking-head video (podcasts, interviews, explainers) into finished videos in one premium house style, as 1080x1920 Shorts and Reels with liquid-glass captions that light word by word and as 1920x1080 long-form edits in the same style without subtitles. Finds the strongest whole thought, cuts only repeats, long fillers and dead air, frames every camera shot with one fixed eye-level crop, renders Inter and Instrument Serif motion graphics (glass titles, pixel-icon grid panels, editorial cards, full-frame serif statements, orbit chips) that never cover a face, mixes famous tension music under the voice, proves every video with measured QA gates and writes posting files. Use it whenever someone says markclip or mark clip, asks for clips, Shorts or Reels in this style, wants a podcast or interview moment turned into a polished Short, wants a long-form edit in the same style, or asks for more clips like these, even if they never name the skill.
---

# Mark Clip (markclip)

An editing library for talking-head video in one house style. It makes two kinds of video and proves each one with
measurements:
- **Shorts and Reels** (1080x1920): one whole thought, 25-55 s, captions lighting word by word, split-screen panels,
  statements, orbit chips, music under the voice. The workflow below.
- **Long form** (1920x1080): several minutes in the same look, without subtitles, full frame most of the time, built
  from 2 or 3 parts, with an animated side panel only where a concept needs it. Section "Long form" below and
  `references/long-form.md`.

Look at `assets/snapshots/00_components_overview.jpg` first: a labelled sheet of every component and both formats.
Snapshots `01_` to `20_` show each component and rule, `21_` to `23_` the long-form layouts; all are explained in
`references/design-system.md` (section 9). `assets/showcase/` holds finished examples (`shorts_sheet.jpg`,
`caption_lift.gif`, `long_sheet.jpg`, `long_side.gif`).

## Requirements and setup
- **An Apple Silicon Mac.** Every transcription runs Whisper large-v3 through mlx-whisper
  (`mlx-community/whisper-large-v3-mlx`, about 3 GB, downloaded on first use).
- **The ClipIt skill** (default `~/.claude/skills/clipit`) with its Python environment `~/.clipit/venv`, made once by
  ClipIt's `install.sh`. markclip uses it for fetching sources (yt-dlp), transcripts, the YuNet face model, audio helpers and
  media I/O; NumPy, OpenCV, Pillow, pyloudnorm and mlx-whisper come with that environment. Set `CLIPIT_DIR` if ClipIt
  lives elsewhere, and check the setup with `$PY $CLIPIT_DIR/clip.py doctor`.
- **ffmpeg and ffprobe on the PATH** (render.py and check.py call them by name).
- Optional: Node 16+ for an unlazy gate ledger (step 8).
- Install markclip by putting this folder at `~/.claude/skills/markclip/` (or `.claude/skills/markclip/` in a project).
- Shell setup used below:
  ```
  PY=~/.clipit/venv/bin/python
  S=~/.claude/skills/markclip              # this skill's folder
  export CLIPIT_DIR=${CLIPIT_DIR:-$HOME/.claude/skills/clipit}
  ```
- Fill in `references/brief.md` once per job from the client's or platform's brief: it decides whether a video is
  accepted.

## The job folder (every file the workflow writes)
Work in one job folder and run every command from it; spec paths are relative to it. Keep every earlier version: make a
new folder (`v2/`, `v3/`...) instead of overwriting. NN is the video number (01, 02...).

| Path | Written by | Contents |
|---|---|---|
| `subs/ID.txt`, `subs/ID.json` | `episode_subs.py` (step 1) | a whole episode's subtitles in ~10 s lines `[H:MM:SS] words`; word timings |
| `input/<topic>_<start>-<end>.mp4` | `clip.py fetch` (step 2), renamed | the source window at 1080p; move its `.subs.json` aside |
| `music/`, `images/` | `clip.py fetch --audio`, yt-dlp, you | the tracks and approved pictures a spec names |
| `work/<video name>/` | ClipIt, `base_edit.py` | ClipIt's `transcript.json` and `speech16k.wav`, base_edit's word-for-word cache `verbatim_<t0>_<t1>.json`, `recheck/`, contact sheets (`sheet.jpg`) |
| `base/NN.mp4` | `base_edit.py` + `frame_base.py` (step 3) | 1080x1920 (long form 1920x1080), 30 fps, the edited voice, one fixed crop per camera shot |
| `base/NN.split.mp4` | same (Shorts only) | 1080x960, no audio: the split screen's bottom half (a wider 9:8 window) |
| `base/NN.plan.json` | same | `src`, kept source `ranges`, their `out` times, `removed` word indices |
| `base/NN.crops.json` | same | per camera piece: output and source times, crop and split windows, speaker, wide or tight, held, burned-in text found |
| `base/NN.voice.wav` | same | the edited voice, normalised (the base's audio track) |
| `base/NN.faces.json` | `analyze_base.py` (step 5) | faces on every frame, camera shots, eye height per shot |
| `words/NN.json` | `words.py` (step 4, Shorts only) | caption words `[{"w", "s", "e"}, ...]` timed on the base |
| `specs/NN.json` | you (step 6) | the video's spec (`references/spec-format.md`) |
| `output/NN_x.mp4` | `render.py` (step 7) | the finished video, H.264 + AAC, -14 LUFS |
| `output/NN_x_mix.wav` | same | the mix: voice, music, effects |
| `output/NN_x.log.jsonl` | same | one line per frame: `t`, `layout`, `zoom`, `dx`/`dy` (shake), `cap` (caption box), `cap_hair`, `boxes` (overlays), `faces` (hair included) |
| `output/NN_x_bg.mp4` | `render.py --bg-only` (check.py makes it) | the background without overlays, for independent QA |
| `SEO_and_schedule.md`, `SEO_and_schedule_IG.md` | you (step 9) | posting files |
| `GATES.md` | you (optional, step 8) | the batch's gate ledger, with the filled-in brief |

## House rules (each one came from a review of a real render; the why matters)
**Type and text**
1. **Inter and Instrument Serif only, one type scale**, weights by role (`references/design-system.md`). Why: mixed
   fonts and ad-hoc sizes read as cheap. The fonts are bundled in `assets/fonts/`; render.py and the linter load
   nothing else.
2. **Sentence case, no random capitals, consistent alignment** (left inside panels and cards on a 64 px margin;
   titles, pills, captions and statements centred). Why: title case and all-caps labels look templated.
   `lint_spec.py` enforces it (names go in the spec's `proper_nouns`); `words.py` restores the full stops Whisper
   drops so captions never show a capital mid-sentence.

**Faces**
3. **Never place any overlay over any face**, above all the speaker's. A face counts with its hair: each detected box is
   raised by 35 % of its height and widened by 10 % a side (also of its height). Why: the speaker's face is the clip.
   render.py detects faces on a background-only pass and places every caption, pill, chip, orbit chip and title clear
   of them for its whole life (36 px clearance, 20 px for captions); at draw time a title, pill or chip within 16 px
   of a face is skipped for that frame, so the renderer is stricter than `check.py`, which re-detects faces on its own
   and fails any overlap. Only as a last resort, when no position clears the hair, may a title or a caption touch the
   top of the hair, never the face itself; such a caption is marked `cap_hair` in the render log and check.py holds it
   (and every title) to the face box.

**Cutting** (`references/cutting-formula.md`)
4. **Cut little.** Only repeats and restarts ("is, is", "if you if a fight"), long fillers (an "um" of 0.45 s or
   more) and dead air of 1 s or more are cut; never mid-word; short pauses and small fillers stay. A cut that
   would remove less than 0.2 s is skipped (`MIN_CUT`). The clip starts just before the voice onset, never on it
   (a short voice pre-roll). Why: cutting every pause made clips choppy and clipped words; a tiny cut lands mid-voice
   for nothing; starting on the voice eats the first consonant.
5. **A jump cut inside one camera shot switches wide <-> tight** (tight = 1.14x). Why: it reads as a second camera
   instead of a jump (snapshot `16_jumpcut_wide_tight.jpg`).

**Camera** (`references/framing.md`)
6. **Direct cuts to one fixed crop per camera shot.** No tracking, no sliding back to the face after a camera change;
   a crop never reads a frame of the next shot. Why: tracking slid toward the new face after every camera change, and
   one stray frame of another angle reads as a flash.
7. **No zoom bounce.** A punch-in holds to the next cut; an intense push-in ramps up and holds; zoom never decreases
   inside a shot; punch-ins and push-ins never enlarge the source past 2.3x. Why: zooms that eased back read as a
   bounce, and past 2.3x a 1080p source goes soft.
8. **Match eye level across angles**: eyes at 740 px (single), 1360 (split bottom half), 420 (each duo half); 450 in
   long form. No face taller than 42 % of the frame; big close-ups keep their size and their eyes sit a little lower.
   Why: eyes jumping between angles is jarring; an over-zoomed face crowds the caption and goes soft.
9. **Split screens show the speaker head and shoulders**: the bottom half is a wider 9:8 window of the 16:9 source
   (`BASE.split.mp4`) with the face at most 42 % of the half (snapshot `15_split_head_and_shoulders.jpg`). Why:
   re-cropping the 9:16 base for the half over-zoomed the speaker and pushed the hair into the seam caption.
10. **Crops never cut through the show's burned-in text while it is on screen** (chapter label, citation lower
    third, corner logo). `frame_base.py` detects which of them is on screen in each camera piece; for each one a crop
    would cut, it nudges the crop sideways past it (at most 12 % of the crop's width), else shifts a split window off
    it (eyes moved at most 45 px), else makes the crop shorter so the text falls outside it with the eyes kept on
    their line (face under 42 %, source enlarged at most 2.2x, `TEXT_FIX_ZOOM`), else keeps the framing and erases
    the cut-off strokes (inpainting). The split's bottom half shows no show text at all (it is erased there). The
    speaker is never pushed aside to dodge text. A crop that holds a label whole shows it; a label's box is widened to
    the label's own length. Why: half a label looks like a mistake (snapshot `20_text_safe_crop.jpg`).
11. **Two people talking get a duo split** (one per half, eyes level; side by side in long form), never a camera
    swinging between them (snapshot `18_duo_split.jpg`).
12. **Intense lines get a slow push-in (about 6 %) plus a subtle 3 px handheld shake**, held to the next cut. Why: it
    adds weight without an effect (snapshot `19_intense_push_in.jpg`).
13. **Layouts change on one frame, without flashes.** A gap under 0.6 s between two layouts (or a layout and a camera
    cut) is held; a layout ending within 0.6 s of the end runs to the end. Why: a one-frame flash of the full-screen
    speaker between two panels reads as a glitch (snapshot `17_direct_layout_change.jpg`).

**Captions** (Shorts; `references/design-system.md`, section 7)
14. **The caption look**: a dark glass pill settles in (94 % -> 100 % size with a slight overshoot), the phrase shows
    dim at 38 %, and each word brightens with a 6 px lift as it is spoken (0.05 s early). Why: static captions felt
    dead; the lift guides the eye word by word (snapshot `13_caption_word_lift.jpg`).
15. **One caption at a time.** The next pill shows once the previous phrase's last word has lit for 0.15 s, at the
    earliest 0.15 s and never later than 0.05 s before its own first word. Phrases are at most 4 words / 22 characters
    (a phrase closes as soon as it reaches either), except that a sentence's last word may join (up to 5 words /
    28 characters), so it never sits alone. A phrase does not end on a weak word ("the", "of", "a"...) unless only
    two words remain, and a comma never makes a one-word pill ("it,"). Why: overlapping or early-switching pills and
    one-word scraps are hard to read.
16. **Captions jump, they never glide.** The caption line is fixed for each layout stretch (split and duo: on the seam
    at 960, never over the panel's text) and jumps only when the layout changes. Only when a close-up fills the lower
    frame does a phrase move (lower lines first, then a top line at 250 px). Why: a caption drifting up and down reads
    as sliding.
17. **No caption flashes around statement cards.** A statement replaces the captions with the speaker's exact words;
    leftover slivers of a phrase around it are not drawn.
18. **Caption timing comes from the final audio**: words are re-timed from short Whisper passes over each voiced
    stretch of the finished base (the first word of a stretch starts at the stretch's onset, where Whisper puts it
    late), and the sync gate settles disagreements with a short window at the caption time. Why: source times
    remapped through jump cuts ran up to 0.9 s late, and long Whisper passes start words early.

**Sound and graphics** (`references/sound-design.md`)
19. **Music must be audible**: 9-14 dB under the voice (aim 10-12), famous and on-topic, "something bad's about to
    happen" tension for hard truths (Succession, Interstellar, Lux Aeterna, Vivaldi Winter). Effects (clicks, paper
    turns, hits) at about -15 dB. The mix is -14 LUFS. Why: a bed 28-32 dB under was inaudible; loud effects bury words.
20. **Split screen where it explains a concept** (Shorts: 4-8 s, a panel the speaker is talking about; long form: a
    side layout only when the concept really needs it), at most two statements per Short, something new every 3-6 s
    in a Short, the speaker's face on screen at least half the time.

**The brief** (`references/brief.md`)
21. **Work to the brief.** Before picking moments, fill in the checklist in `references/brief.md` from the client's or
    platform's brief: sources allowed, the speaker's face in the first seconds, subtitles, whole thoughts, ad reads,
    outside material, tags, audience regions and posting times, repost limits, quality policy. Where it is silent the
    house defaults hold: only the source the user named, the speaker on camera in the first 5 s, subtitles the whole
    way in a Short (none in long form), one whole thought with a payoff, no ad reads, no outside video (outside images
    only once the user confirms each), no brand logos, no clickbait, never the same clip on two platforms. Why: the
    brief decides whether a video is accepted.

## Workflow (Shorts)

### 1. Pick moments
Newest episode first, unless the brief or the user says otherwise. Get the chapters (the video description or the
show's site) and the whole episode's subtitles without any video:
```
$PY $S/scripts/episode_subs.py subs VIDEO_ID [VIDEO_ID ...]     # -> subs/ID.txt (~10 s lines), subs/ID.json
```
Choose as many moments per platform as the user asks for, each a different idea, matched to the platform as the
brief says, with the scoring in `references/cutting-formula.md`: hook in the first sentence, the speaker on camera,
one complete 25-55 s thought, a payoff, no shaky facts, no sponsor read.

### 2. Extract
```
$PY $CLIPIT_DIR/clip.py fetch --res 1080 --section 2:46:40-2:48:45 "https://www.youtube.com/watch?v=ID"
$PY $CLIPIT_DIR/clip.py sheet input/X.mp4 --n 12                 # -> work/X/sheet.jpg: who is on camera
```
Fetch the window plus about 10 s each side, at 1080p (the text-safe crop boxes are in 1920x1080 pixels), one request at
a time (bursts get the IP bot-blocked). Rename the file to `input/<topic>_<start>-<end>.mp4`, move its `.subs.json`
aside (it breaks sentence snapping), and confirm on the contact sheet who is on camera
(`references/clipit-extraction.md`).

### 3. Base edit (direct cuts, repeats removed, fixed framing)
```
$PY $S/scripts/base_edit.py input/X.mp4 --start 21.44 --end 87.0 --drop 54.70-67.80 --out base/01.mp4
$PY $S/scripts/heard_check.py base/01.mp4
```
Times are seconds in the input file. It writes `base/01.mp4`, `base/01.split.mp4`, `base/01.plan.json`,
`base/01.crops.json` and `base/01.voice.wav` (table above; framing by `scripts/frame_base.py`) and prints
`N pieces, T s, cuts only at repeats / long fillers / dead air >= 1s`.

Read every `dedupe` line it prints and veto a removal with `--keep-repeat "words"`; `--recheck` re-listens to the
edit and cuts repeats that are left; `--cut a-b` removes exact audio; `--retime`, `--fix`, `--no-dedupe`, `--preview`
are in `references/cutting-formula.md`. In the heard check, the first and last words and each jump cut must be whole
sentences with no leaked word; fix boundaries and re-run.

### 4. Words for captions (timed on the base itself)
```
$PY $S/scripts/words.py base/01.mp4 words/01.json --fix coach=coached --keep Casanova
```
Writes `words/01.json` (`[{"w", "s", "e"}, ...]`) and prints every word with its time. It transcribes the base in
24 s chunks, re-times every word from short Whisper passes over each voiced stretch between pauses (the stretch's
first word takes the stretch's onset), joins Whisper's split hyphen words (`join_hyphens`: "deep -seated" ->
"deep-seated") and repairs case: a capital after a word without . ? ! gets the full stop Whisper dropped.
- `--fix wrong=right`: a misheard word; `--keep Name`: a proper noun that stays capitalised (the speaker's name);
- `--insert word@s-e`: a word Whisper never wrote down (confirm it with `heard_check.py`);
- `--period-after word@t`: ends a sentence Whisper ran on;
- `--retime word@near=start`: the word nearest `near` really starts at `start`, for a word `check.py`'s sync window
  hears elsewhere (e.g. `a@30.5=29.98`).
A word whose caption is written differently from how it is heard can carry `"src"` (the word as heard); the sync
gate matches on it (`references/spec-format.md`, the words file).

### 5. Faces and shots
```
$PY $S/scripts/analyze_base.py base/01.mp4
```
Writes `base/01.faces.json` and prints the eye height of every shot. render.py makes it only when it is missing, so
re-run this after every base rebuild.

### 6. Plan the beats and write the spec
Use the beat structure in `references/cutting-formula.md` and the components in `references/design-system.md`; copy
the closest example from `assets/examples/specs/` (`01.json`-`04.json`) and follow `references/spec-format.md`. Set
`"show"` to the show's name (the panels' header label and the editorial byline) and add the show's and the speaker's
names to `proper_nouns`. Pick music and place effects with `references/sound-design.md`. Every on-screen fact (dates,
names) must be verified; statements and quote pills must be the speaker's exact words. Then:
```
$PY $S/scripts/lint_spec.py specs/01.json        # SPEC LINT OK, or each finding
```

### 6b. Rebuilt a base after writing its spec? Re-time the spec, don't rewrite it
```
cp words/01.json words/01_old.json
$PY $S/scripts/words.py base/01.mp4 words/01.json
$PY $S/scripts/retime_spec.py specs/01.json words/01_old.json words/01.json specs/01_new.json
$PY $S/scripts/analyze_base.py base/01.mp4
```
`retime_spec.py` moves every time in the spec with the words around it (`--base`, `--words`, `--out` rewrite those
paths). Check the printed match share; a low one means the speech changed.

### 7. Render
```
$PY $S/scripts/render.py specs/01.json
```
Two passes: the background alone (eye-level framing, splits, duo, paintings, statements) with face detection on every
frame, then the overlays placed off every face. It writes the spec's `out` (e.g. `output/01_x.mp4`) plus
`output/01_x_mix.wav` and `output/01_x.log.jsonl`. `render.py specs/01.json --bg-only` writes `output/01_x_bg.mp4`
(check.py makes it when needed). Every `! placement:` line it prints is an overlay it could not keep off a face (or a
title that had to touch the top of the hair): move or shorten that element and re-render.

### 8. QA (measured)
```
$PY $S/scripts/check.py specs/01.json        # MARKCLIP CHECK PASSED, or each FAIL line (exit 1)
$PY $CLIPIT_DIR/clip.py sheet output/01_x.mp4 --n 12
```
check.py runs nine gates on the files: spec lint, duration, caption sync, music level, loudness, faces clear,
captions still, no bounce and eye level (`references/qa-gates.md`, with the tools for each failure: `sync_check.py`,
`heard_check.py`, `music_level.py`). Then look at the sheet and full-size frames at every element, and watch once with
sound if you can; say which you did. For a batch, keep a gate ledger (`assets/templates/GATES_clip.md`, unlazy format).

### 9. Deliver
Write one posting file per platform (`references/posting.md`; filled-in examples in `assets/templates/`): a
`**Videos folder:**` line, then per video `## <n>. <file.mp4> | <Day Mon D YYYY, H:MM AM TZ>` with `**Title:**`,
`**Description:**` and `**Tags:**`; always the year; times when the brief's audience is awake (a US audience: US
daytime, one post every 3 hours). Validate them with your scheduler's checker if it has one, send the videos, and
report: what each video is, the music, what you measured, how each meets the brief, whatever you could not verify.

## Long form (1920x1080, no subtitles)
Make one when the user wants a longer 16:9 video (a YouTube main-feed upload, "the longer cut") in this style. The
steps are the Shorts' with these changes (`references/long-form.md` has every number and a walk-through of
`assets/examples/specs/05_long.json`):
1. **Pick** a whole argument of a few minutes with two or three clear turns, scored as in step 1.
2. **Base:** add `--long`:
   ```
   $PY $S/scripts/base_edit.py input/X.mp4 --start 612.4 --end 905.0 --long --out base/05.mp4
   $PY $S/scripts/heard_check.py base/05.mp4
   $PY $S/scripts/analyze_base.py base/05.mp4
   ```
   It sets `MARKCLIP_FORMAT=long` for `frame_base.py` and writes a 1920x1080 base (no split track) with the eyes at
   450 of 1080; the zoom that brings a wide shot's eyes to that line is at most 1.15x, so wide shots stay wide; the
   wide/tight "second camera" at jump cuts works as in a Short, and the source's burned-in labels and logos are
   always erased (a side layout would cut them; your own chapter cards replace them).
3. **No subtitles:** skip `words.py`; the spec has no `words`.
4. **Spec:** copy `05_long.json` and set `"format": "long"` (a 1920x1080 canvas, captions off, overlays kept 60 px from
   the top and bottom edges instead of the Shorts UI zones, hook title at y 80, no top shade). Layouts:
   - **full frame** (the default): the speaker, eyes at 450, for most of the video;
   - **side layout**: a `split` (or `editorial`) element with `"parts": 2` (the speaker's half and an animated panel
     half) or `"parts": 3` (the speaker's two thirds and a panel third), and `"side": "right"` (default) or `"left"`
     for where the animated part sits. Panels (`grid`, `list`, `image`, `framed`, `editorial`) draw at the part's
     width and the full height; you choose which animation each concept gets. No split screen unless it is really
     needed: only where the speaker explains a concept that a visual makes clearer, then back to full frame;
   - **statements** (full-frame serif cards of the speaker's exact words) open the later parts (chapters); the hook
     title opens the first;
   - **image** (a full-frame picture), **duo** (two people side by side), pills, chips, orbit chips, `punch`,
     `intense`, music and sfx as in a Short.
5. **Lint, render, check:** `lint_spec.py` measures against the 1920 px frame (panel titles against 1920 / `parts`);
   `render.py` writes the 1920x1080 video; `check.py` runs eight gates (no caption sync in long form; eye line 450;
   faces clear, loudness, music, no bounce). Look at a still of every side layout: editorial headlines in a third are
   not measured by the linter.
6. **Deliver** with the posting file's long-form rules (no `#shorts`; chapter times = the parts).

## Options (environment variables, all off by default)
| Variable | Read by | Effect |
|---|---|---|
| `MARKCLIP_LANG=hi` | `base_edit.py`, `words.py`, `heard_check.py`, `check.py` | Whisper's language (default `en`); the English prompts that steer disfluent and punctuated transcripts are off for any other language |
| `MARKCLIP_GRAPHICS=1` | `frame_base.py` (via `base_edit.py`) | an explainer with full-screen graphics: faceless or mostly bright shots (and bright frames inside a presenter shot) are shown whole on their own canvas colour instead of centre-cropped; flash-in frames at the start of a presenter shot are skipped |
| `MARKCLIP_SPLIT_TOP_PAD=0.12` | same | the split window may reach this share of its height above the source frame: for a speaker framed too high, in front of a plain wall |
| `MARKCLIP_TEXT_BOXES="s0-s1:x0,y0,x1,y1;..."` | same | the source's own burned-in labels (source seconds, 1920x1080 source pixels), kept whole or left out like the built-in ones |
| `MARKCLIP_ERASE_TEXT=1` | same | erase every burned-in label or logo the source shows, not only the ones a crop would cut |
| `MARKCLIP_FORMAT=long` | same | set by `base_edit.py --long`: the 1920x1080 long-form base |
| `CLIPIT_DIR` | every script | where ClipIt lives (default `~/.claude/skills/clipit`) |

Spec-level switches: `"show"` (the show's name for panel headers and bylines, default empty), `"captions": false`
(a Short without subtitles), `"format": "long"`. Built-in burned-in text boxes (`SHOW_TEXT` in `frame_base.py`): a
chapter label top left, a lower third and a corner logo, where podcasts commonly put them; each is detected per camera
piece before a crop is changed for it (`references/framing.md`).

## Files
**scripts/**
- `scripts/episode_subs.py`: a whole episode's YouTube subtitles as text, before any download (step 1)
- `scripts/base_edit.py`: the base edit: verbatim transcript, cuts, voice, plan (step 3); `--long` for long form;
  calls `scripts/frame_base.py`
- `scripts/frame_base.py`: one fixed crop per camera shot, wide/tight jump cuts, text-safe crops, the split window,
  the long-form 16:9 framing and the source options above
- `scripts/dedupe.py`: the repeat and restart finder base_edit uses (`dedupe.py WORDS.json` lists them on its own)
- `scripts/heard_check.py`: what is actually heard in a video, with times
- `scripts/words.py`: caption words timed on the base (step 4)
- `scripts/analyze_base.py`: faces and camera shots of a base (step 5)
- `scripts/lint_spec.py`: the text rules (step 6), with the long-form limits
- `scripts/retime_spec.py`: moves a spec onto a rebuilt base (step 6b)
- `scripts/render.py`: the renderer (step 7), Shorts and long form, with `scripts/engine_core.py` (easing, glass,
  pixel icons, glitch, caption phrasing)
- `scripts/check.py`: every QA gate in one command (step 8); `scripts/sync_check.py` (caption sync word by word),
  `scripts/music_level.py` (music under the voice)

**references/**
- `references/brief.md`: the brief checklist to fill from any client or platform brief, with house defaults
- `references/cutting-formula.md`: picking moments, every base_edit flag, what gets cut, beat structure
- `references/clipit-extraction.md`: ClipIt commands and gotchas
- `references/framing.md`: crops, text-safe crops, eye lines, face caps, zoom limits, duo, layout timing, long-form
  framing, source options
- `references/design-system.md`: type, colour, layouts, components, captions, motion, every snapshot explained
- `references/design-references.md`: the two design references with their sources, the editorial card, pixel icons,
  images
- `references/sound-design.md`: music level, track picks, effects
- `references/spec-format.md`: every spec field with defaults, the words file, long-form fields, re-timing a spec
- `references/long-form.md`: long form end to end: base, spec, layouts, panel sizing, parts, overlays, audio, QA,
  the example walked through
- `references/qa-gates.md`: the check.py gates, failure fixes, the by-eye pass
- `references/posting.md`: posting-file format and text rules

**assets/**
- `assets/fonts/`: Inter (Regular, Medium, SemiBold), Instrument Serif (Regular, Italic), `OFL-Inter.txt`,
  `OFL-InstrumentSerif.txt`
- `assets/design-references/`: `ref1_liquid_cycle_108supply.jpg`, `ref3_dgrees_pixel_grid.mp4`,
  `ref3_dgrees_pixel_grid_frames.jpg`
- `assets/snapshots/` (all .jpg): 00_components_overview, 01_hook_title_glass, 02_statement_loud_line,
  03_orbit_chips_around_speaker, 04_split_grid_panel_pixel_icon, 05_split_grid_panel_counter, 06_statement_multiline,
  07_checklist_pills, 08_quote_pill_serif, 09_split_image_painting, 10_liquid_cycle_painting_orbit,
  11_split_framed_strike_pills, 12_editorial_end_card_icon, 13_caption_word_lift, 14_captions_serif_accent,
  15_split_head_and_shoulders, 16_jumpcut_wide_tight, 17_direct_layout_change, 18_duo_split, 19_intense_push_in,
  20_text_safe_crop, 21_long_full_frame, 22_long_side_two_parts, 23_long_side_three_parts
- `assets/showcase/`: `shorts_sheet.jpg` (frames from the example Shorts), `caption_lift.gif` (the caption word lift),
  `long_sheet.jpg` (frames from the long-form example), `long_side.gif` (a long-form side layout in motion)
- `assets/examples/specs/` and `assets/examples/words/`: `01.json`-`04.json`, four complete Shorts, and
  `assets/examples/specs/05_long.json`, a long-form video (music and images they name are not bundled)
- `assets/templates/GATES_clip.md` (batch gate ledger), `assets/templates/SEO_and_schedule.example.md` (YouTube
  posting file), `assets/templates/SEO_and_schedule_IG.example.md` (Instagram posting file)
- `README.md`: overview, showcase, requirements, install, usage, folder map, credits
