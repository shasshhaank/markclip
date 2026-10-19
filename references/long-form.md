# Long form: 16:9 videos in the house style, without subtitles

A long-form markclip is a 1920x1080 video of several minutes (a whole argument, a story, an interview segment) in the
same look as the Shorts: the same fonts, glass, pixel icons, statements, framing and sound. Three things differ:
**no subtitles**, **no split screen unless it is really needed**, and the video is built from **parts**: the frame
splits into two or three parts, one of them an animated panel you design, and the timeline falls into two or three
parts that each open on a statement card. Snapshots: `21_long_full_frame.jpg`, `22_long_side_two_parts.jpg`,
`23_long_side_three_parts.jpg`; the example spec is `assets/examples/specs/05_long.json` (section 10).

## Contents
1. When to make one
2. What changes from a Short
3. The base
4. The spec
5. Layouts
6. Panel sizing
7. Parts and chapter cards
8. Overlays
9. Audio, render and QA
10. Walk-through: 05_long.json

## 1. When to make one
When the user asks for a long-form edit, a 16:9 video, a YouTube main-feed upload or "the longer cut" in the markclip
style. Pick the stretch with the same scoring as a Short (cutting-formula.md): a hook in the first sentence, the
speaker on camera at the start, one whole argument with a payoff, no ad reads; only longer (a few minutes) and with
two or three clear turns that become its parts.

## 2. What changes from a Short
| | Short | Long form |
|---|---|---|
| canvas | 1080x1920 | 1920x1080, 30 fps |
| base | `base_edit.py ... --out base/01.mp4` | `base_edit.py ... --long --out base/05.mp4` (no `BASE.split.mp4`) |
| eye line | 740 (single), 1360 (split bottom), 420 (duo half) | 450 everywhere: full frame, the speaker's part of a side layout, each duo half |
| eye-line zoom in the base | at most 1.85x | at most 1.15x (wide shots stay wide) |
| subtitles | the whole way, from `words.py` | none: no `words`, no `words.py`, no caption sync gate |
| split screen | panel on top, speaker below (4-8 s) | a side layout, only when a concept really needs a visual |
| overlay safe zone | y 140-1575 (phone UI) | y 60-1020, x 8-1912 (the frame edges) |
| hook title | y 210 | y 80 |
| top shade | the top 230 px of single and image frames | none |
| statements | at most two, the turn | one per later part (the chapter cards; the hook title opens part one), plus a turn if it earns it |
| QA | nine check.py gates | eight (caption sync is skipped), eye line 450 |

Everything else is the same: direct cuts, one fixed crop per camera shot, the wide/tight "second camera" (1.14x) at a
jump cut inside one shot, text-safe crops, no zoom bounce, punch-ins and push-ins (2.3x source limit), nothing ever
over a face, music 9-14 dB under the voice, -14 LUFS.

## 3. The base
```
$PY $S/scripts/base_edit.py input/X.mp4 --start 612.4 --end 905.0 --long --out base/05.mp4
$PY $S/scripts/heard_check.py base/05.mp4
$PY $S/scripts/analyze_base.py base/05.mp4
```
`--long` sets `MARKCLIP_FORMAT=long` for `frame_base.py`. It writes `base/05.mp4` (1920x1080, 30 fps, the edited
voice), `base/05.plan.json`, `base/05.crops.json` and `base/05.voice.wav`; no split track. The cutting rules are the
Shorts' (cut little: repeats, restarts, long fillers, dead air of 1 s or more; never mid-word; a cut under 0.2 s is
skipped; the voice pre-roll), and every `base_edit.py` flag works (`--drop`, `--cut`, `--keep-repeat`, `--recheck`).
Framing (framing.md, section 5): eyes at 450 of 1080; to reach that line a wide shot is enlarged at most 1.15x, so it
stays wide; the tight crop of a jump cut is 1.14x of the wide one; faces stay under 42 % of the frame; the source's
burned-in labels and logos are always erased in long form (a side layout would cut them, and the edit's own serif
chapter cards replace them). Skip `words.py`: long form has no subtitles.

## 4. The spec
Copy `assets/examples/specs/05_long.json` and change it. Keys that matter in long form (spec-format.md has all):

| Key | Long form |
|---|---|
| `format` | `"long"`: required, switches the renderer, the linter and check.py to long form |
| `show` | the show's name: the default left header label of every panel and the editorial byline |
| `base`, `out`, `tail`, `fade_out` | as for a Short |
| `words` | leave it out (no subtitles; `captions` is ignored) |
| `music`, `sfx`, `duck_db` | as for a Short |
| `elements` | the layouts and overlays below, in 1920x1080 pixels |
| `parts` (on a `split` or `editorial` element) | 2: the panel is a half (960 px); 3: the panel is a third (640 px) and the speaker gets two thirds (default 2) |
| `side` (same elements) | where the animated panel sits: `"right"` (default) or `"left"`; the speaker takes the other side |

Run `lint_spec.py` as for a Short; with `"format": "long"` it measures against the 1920 px frame (section 6).

## 5. Layouts
Priority when windows overlap, as in a Short: statement, image, duo, split/editorial, single. Every change happens on
one frame; a gap under 0.6 s between two layouts is held; a layout ending within 0.6 s of the end runs to the end;
layout edges near a camera cut snap onto it (framing.md, section 4).

**Full frame (default).** The speaker fills the 1920x1080 frame, eyes at 450, one fixed crop per camera shot; the
render corrects the eye line with at most 1.25x zoom and never past a face 42 % of the frame tall. This is the layout
for most of a long video (snapshot `21_long_full_frame.jpg`).

**Side layout** (`split` or `editorial` with `parts` and `side`; snapshots `22_long_side_two_parts.jpg`,
`23_long_side_three_parts.jpg`). The frame is cut into parts:

| `parts` | panel (animated part) | speaker's part | with `"side": "right"` | with `"side": "left"` |
|---|---|---|---|---|
| 2 | 960 x 1080 | 960 x 1080 | speaker x 0-960, panel x 960-1920 | panel x 0-960, speaker x 960-1920 |
| 3 | 640 x 1080 | 1280 x 1080 | speaker x 0-1280, panel x 1280-1920 | panel x 0-640, speaker x 640-1920 |

The speaker's part is cut from the same full-frame render (eye line 450, punch-ins and push-ins included), centred on
the speaker's eyes and kept inside the frame, so the eyes do not jump when a side layout starts or ends. The seam is
a 4 px line darkened to 70 %. Use a side layout only where the speaker explains a concept that a visual makes clearer
(a number, a list, a metaphor, a person or a painting they name), for as long as they talk about it (about 5-15 s),
and go back to full frame after it. Three parts suit a compact visual (an icon, a counter, a portrait) and keep more
of the speaker; two parts suit a list, a wide picture or a headline. Alternate `side` when two side layouts come
close together, so the panel does not always sit on one side.

**Statement.** The near-black blurred full frame (12 % brightness) with Instrument Serif 132 lines centred on the frame
(lines up to 1800 px), each word fading in; it hides every overlay while it is up. The speaker's exact words, as in a
Short. In long form it opens each part after the first (section 7).

**Image.** A painting or document fills the 1920x1080 frame with a slow push (`zoom` [1.0, 1.08], `focus`, `dim`);
overlays (orbit chips, pills) are placed off its painted faces.

**Duo.** Two people side by side, one per 960 px half, eyes at 450, faces `face_h` tall (300), from the source
two-shot; `top: "left"` (default) puts the left seat in the left half, `"right"` swaps them; a 4 px dark seam.

## 6. Panel sizing
Every panel is drawn at its part's width (PW = 1920 / `parts`: 960 or 640) and the full height (1080), on the same
recipes as the Shorts' top-half panels (design-system.md, section 6):

| Panel | Layout inside its part (half: PW 960; third: PW 640) |
|---|---|
| `grid` | paper with a 40 px grid; header row at y 150 (Inter Medium 25; left label = `labels[0]` or the spec's `show`, right label right-aligned), a rule at y 196 from x 64 to PW - 64; Instrument Serif 84 title from y 222 at x 64 (84 px a line); Inter 32 body bottom-left, 44 px a line, ending 70 px above the bottom; pixel icon default size min(400, 0.36 x PW) = 345 (half) or 230 (third), centred at x PW - 0.825 x size = 675 or 450, y 585, glitch-morphing at each later icon's `t`; optional counter (Inter SemiBold 66) at x 64, y 780 (below the icon; 560 in a Short) |
| `list` | the grid's header and title; checklist items tick in at their `t`: a green circle at x 96 with a white tick, Inter Medium 52 text at x 148, first item at `list_y` (360, plus 84 for each extra title line), 112 px apart |
| `image` | a painting covers the whole part with a slow push (1.0 -> 1.08 around `focus`) |
| `framed` | a sharp picture `h` px tall (560) centred in the part from y 150 on a dark ground, Inter Medium 25 caption at 150 + h + 30 |
| `editorial` | off-white page; a warm illustration panel from x 48 to PW - 48, y 150-600; a pixel icon min(380, 0.4 x PW) = 380 (half) or 256 (third) at (PW / 2, 375) with a hard shadow, or a painting (PW - 96) x 450; Instrument Serif 78 headline from y 640 at x 64; Inter Medium 25 byline 16 px under it (the spec's `show` unless `byline` is given) |

What the linter measures, and what it leaves to you:
- panel titles at most PW - 128 wide: 832 px in a half, 512 px in a third (about 17 characters of Instrument Serif
  84 a line in a third), and a grid title block clear of the icon at the long-form defaults;
- hook titles and pills at most 1740 px, statement lines at most 1800 px;
- **not measured:** editorial headlines in a side layout are held to 784 px whatever the part; in a third keep each
  line under 512 px yourself (about 18 characters at 78 px); grid body lines and list items should also stay under
  PW - 128 (about 32 characters of Inter 32 in a third); a `framed` picture wider than the part is cut at its edges,
  so lower `h` for a landscape picture in a third. Look at a still of every side layout.

## 7. Parts and chapter cards
Build the video from two or three parts (chapters), each one turn of the argument: for example the claim, why it
fails, what works instead. Open every part after the first on a statement card: the speaker's exact line that turns
the argument, 1-3 s, with a `hit` under it and a `punch` on the key word if it lands hard; the music can hand off
there (section 9). Give each part at most one or two side layouts, placed where its concept is explained, and keep
the speaker full frame for the rest, at least two thirds of the part. A hook title opens the first part (0-4.5 s);
an editorial card in a side layout can close the last one with the takeaway. If the video is posted with chapter
times, they are the parts' start times (posting.md).

## 8. Overlays
Titles, pills, chips and orbit chips work as in a Short and follow the same face rules: every face box is raised by
35 % of its height and widened by 10 % a side for the hair, each overlay keeps 36 px clear of it for its whole life,
a title, pill or chip within 16 px of a face is skipped at draw time, and as a last resort a title may touch the top
of the hair, never the face. Positions are in 1920x1080 pixels:
- overlays stay between y 60 and 1020 and x 8 and 1912; pills and chips default to x 960 (`y` is required);
- the hook title defaults to y 80; with a kicker (46 px above the glass panel) the renderer moves it down to about
  y 140 so the kicker clears the 60 px margin; title lines up to 1740 px;
- overlays dodge faces, not panel text: keep pills and chips over the speaker's part of a side layout (or on a full
  frame stretch), never over the panel;
- orbit chips circle the speaker's face within the same y 60-1020 band.

## 9. Audio, render and QA
**Audio** is the Shorts' (sound-design.md): famous, on-topic music 9-14 dB under the voice (aim 10-12, spec `db` -9),
effects about -15 dB, the mix at -14 LUFS. Fewer effects than a Short: a paper turn when a side panel comes in, a
click when an icon morphs or a pill appears, a hit under each part's statement. A bed under several minutes reads
better when it changes with the parts: hand off at each statement (two `music` entries overlapping by under a
second).

**Render and check** from the job folder:
```
$PY $S/scripts/lint_spec.py specs/05.json
$PY $S/scripts/render.py specs/05.json
$PY $S/scripts/check.py specs/05.json
```
`render.py` writes `output/05_long.mp4` (1920x1080, H.264 + AAC), `output/05_long_mix.wav` and
`output/05_long.log.jsonl`; `check.py` makes `output/05_long_bg.mp4` and runs eight gates: spec lint (1920 px
limits), duration, music level, loudness, faces clear, captions still (trivially, nothing to move), no bounce and eye
level (450 of 1080 for full-frame and side frames, per camera shot, within 45 px, at most 10 % of shots off); it
prints `caption sync: no subtitles in this format` and ends `MARKCLIP CHECK PASSED`. Then look at a contact sheet
(`$PY $CLIPIT_DIR/clip.py sheet output/05_long.mp4 --n 12`) and full-size stills of every side layout and card, and
watch once with sound: no subtitles anywhere, each part opens on its card, every side layout earns its place, panel
text fits its part, the speaker's eyes hold their line across layouts.

## 10. Walk-through: `assets/examples/specs/05_long.json`
A demonstration of about 47 s, cut from the shame-and-achievement moment (the Short `01.json`) on a long-form base. It
packs every long-form layout into one short piece, so it uses far more side layouts than a real long video would.
`"format": "long"`, `"show": "The podcast"`, no `words`, `tail` 0.5; music: the "Succession" main title from 0 s at
`db` -9 (fades 0.3 / 1.8 s).

| Time (s) | Element | What it shows |
|---|---|---|
| 0.16-2.9 | `title`, kicker "The podcast · Episode 26" | the hook on the full-frame speaker, "You can't achieve your / way out of shame" (click at 0.16) |
| 2.95-4.05 | `statement` "but it *backfires.*" + `punch` at 3.4 | the first turn: the card that opens part two (hit at 2.95, boom at 3.4) |
| 6.36-11.15 | `split`, grid, default `parts` 2 and `side` right | speaker half on the left, panel half on the right: "Perform your way / out of shame?", icons trophy -> arrow_up (8.5) -> heart_broken (10.12), two body lines (paper in, a click per morph) |
| 11.15-15.72 | `intense` 1.06, shake 3 | a slow push-in with a 3 px handheld shake on the full frame (sub drop at 11.15) |
| 18.97-26.32 | `split`, grid, `parts` 3, `side` left | panel third on the left, speaker in the right two thirds: "More views" with the eye icon and a counter from 1,204 to 1,204,331 views (19.94-25.84, at the default y 780, below the icon) |
| 26.38-28.64 | `statement` "It's just going / to keep feeling like / it's *not enough.*" + `punch` at 28.1 | the second turn: the card that opens part three (hit, boom) |
| 28.74-31.84 | `split`, grid, `parts` 2, `side` right | "A bucket with / a hole in it" with the leaking bucket icon (paper in at 28.74, paper out at 31.84, -18 dB) |
| 33.2-36.6 | `pill` "Shame  →  guilt" at (1500, 760) | a label on the full frame, placed clear of the face |
| 41.71-46.72 | `editorial`, `parts` 2, `side` left | the payoff: the mended-heart icon over "Your failures don't make / you a bad person.", byline "The podcast"; it runs to the end |

To make your own: cut the base with `--long`, copy this spec, set `show`, `base`, `out` and the music, keep the
full-frame stretches long, write one statement per part from the speaker's exact words, and add a side layout only
where a concept needs one.
