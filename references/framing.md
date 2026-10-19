# Framing and camera

How a 16:9 two-camera podcast or interview becomes a steady 9:16 clip (or a steady 16:9 long-form video, section 5):
one fixed crop per camera shot, eyes on one line, no bounce, no sliding, no flashes. Three scripts share the job:

| Script | When | What it decides |
|---|---|---|
| `scripts/frame_base.py` | step 3 (called by `base_edit.py`) | the crop of every camera shot, wide or tight, and the split-screen window |
| `scripts/analyze_base.py` | step 5 (and by `render.py` when `BASE.faces.json` is missing) | faces on every base frame, camera shots, eye height per shot |
| `scripts/render.py` | step 7 | eye-level correction, punch-ins, push-ins, layouts and their timing |

## 1. Base framing (`frame_base.py`)

Usage (normally called by `base_edit.py`): `frame_base.py SRC.mp4 PLAN.json AUDIO.wav OUT.mp4`.

**Camera shots.** For every kept range in `BASE.plan.json` it reads the source frames, detects faces (YuNet, score
0.8 or more, on a 960x540 copy) and finds camera changes: a frame difference above 18 (`CUT_DIFF`) that is also 4x the
local median, at least 7 frames after the previous change. Each kept range is split into camera pieces at those
changes.

**The speaker.** In each piece, faces are grouped by horizontal position (160 px buckets); a group seen in at least 30 %
of the frames scores by mouth movement (x10) plus face size; the median box of the best group is the speaker.

**One fixed crop per piece.** The crop is a 9:16 window placed so the speaker's eyes sit at 38.5 % of its height
(`EYE_FRAC`, 740 of 1920 px). It is as tall as the source allows and only gets shorter (zooms) when the eyes are too
close to the top or bottom of the source to reach that line. Limits:
- never shorter than source height / 1.85 (`ZMAX`) before the tight factor, so a wide shot is not blown up;
- never so short that the face is taller than 42 % of the crop (`FACE_FRAC`): a big close-up keeps its size and its
  eyes sit a little lower instead.

There is no tracking: a camera change is a straight cut from one fixed crop to the next, so nothing slides toward the
new face.

**Jump cuts read as a second camera.** When a new kept range starts and the speaker is still in the same camera shot
(face centre within 12 % of the source width, face height within 25 %), the crop alternates between wide and tight:
tight is the wide crop made 1.14x smaller (`TIGHT`). A jump cut inside one shot therefore always changes the framing
(snapshot `16_jumpcut_wide_tight.jpg`).

**No flashes.** A camera piece shorter than 0.2 s (`HOLD`, a stray frame of another angle) holds the previous output
frame. Every output frame reads a source frame inside its own piece (the index is clamped to the piece), so a crop never
shows one frame of the next angle. A 29.97 fps source is written at 30 fps by holding a frame where needed.

**Text-safe crops.** A crop must never cut through the show's burned-in text while it is on screen. Podcasts
commonly burn text into three places of a 1920x1080 frame (`SHOW_TEXT`, in source pixels): a chapter label top left
(80,40)-(600,84), a citation lower third (80,990)-(1470,1064) and a corner logo (1650,976)-(1870,1066).
`scan()` first checks which boxes are actually on screen in each camera piece (`text_on()`: thin bright strokes inside
the box, at least 4 % of its pixels and twice the strip beside it, over 5 sampled frames), so a crop is only changed
for text that is there; a box whose strokes run on past its right edge is widened to where they end (only the chapter
label varies in length: a long chapter title ends near x 640). The boxes found are written to `BASE.crops.json`
(`texts`) per piece. For each box that is on screen and that the crop cuts partway:
1. nudge the crop sideways just past the box if that takes at most 12 % of the crop's width and keeps it inside the
   source (the speaker sits slightly off centre); otherwise
2. for a window shorter than the source (the split window), shift it up or down just off the box if the eyes move at
   most 45 px; otherwise
3. make the crop shorter so the box falls outside it while the eyes stay on their line (top text: start below it;
   bottom text: end above it), only while the face stays under 42 % of the window (`FACE_FRAC`, `FACE_FRAC_SPLIT`)
   and the crop enlarges the source at most `TEXT_FIX_ZOOM` (2.2x); otherwise
4. keep the framing (the speaker is never pushed off to the side to dodge text) and erase the cut-off strokes
   instead: `erase()` inpaints the text inside the box (thin strokes found by their edges, bold letters by being
   brighter than the box's background; podcast backgrounds are usually soft-focus, so it vanishes), only for the
   window that would cut it (`erase_crop` in `BASE.crops.json`).

The split's bottom half shows no show text at all: every box its window overlaps is erased (`erase_split`), since it
would sit under the seam caption right below a panel that already names the topic. A crop that holds a box whole (its
full width and height) shows it; with `MARKCLIP_ERASE_TEXT=1` every box a crop shows is erased too (section 6). Each
box is checked twice, after the others have had their turn. A label held whole at the edge of a crop loses its first
letters while a punch-in or push-in (section 3) enlarges the frame, as at 23.6-24.6 s of the desert-island example;
leave the punch off such a shot when the label must stay whole. Snapshot `20_text_safe_crop.jpg` shows a source frame
with its chapter label and the crop window drawn on it, next to the 9:16 frame that results. These boxes assume a
1080p source (fetch with `--res 1080`); for a show whose text sits elsewhere, list its boxes in `MARKCLIP_TEXT_BOXES`
(section 6) or edit `SHOW_TEXT` to its own burned-in text.

**The split-screen window.** For the bottom half of a split screen, the same piece gets a second, wider window:
aspect 9:8 (1080x960), 74 % of the source height (`SPLIT_WIN`), eyes at (1360 - 960) / 960 = 41.7 % of the half (eye
line 1360 once placed under the panel), face no taller than 42 % of the half (`FACE_FRAC_SPLIT`, so the hair stays
clear of the seam caption): head and shoulders (snapshot `15_split_head_and_shoulders.jpg`).
The same text-safe rule and the same wide/tight choice apply. Cropping the 9:16 base again for the half over-zoomed the
speaker; this window comes straight from the 16:9 source.

**Outputs.**
- `BASE.mp4`: 1080x1920, 30 fps, H.264 CRF 17, the voice track from `BASE.voice.wav` (AAC 192k).
- `BASE.split.mp4`: 1080x960, same timing, no audio: the bottom half of every split screen.
- `BASE.crops.json`: `{"fps_src", "src_size", "pieces": [{"o0", "o1", "src0", "src1", "zf", "f0", "f1", "crop",
  "split", "speaker", "hold"}]}`: per piece its output and source times, source frame range, zoom factor (1.0 wide,
  1.14 tight), crop and split windows `[x, y, w, h]` in source pixels, speaker box and whether it is held.

It prints `framed N camera pieces (k tight, h held)`.

## 2. Faces and shots (`analyze_base.py`)

`analyze_base.py BASE.mp4 [BASE.mp4 ...]` writes `BASE.faces.json`:
- `frames`: per base frame, faces `[x, y, w, h, eye_y, eye_x, score]` (YuNet 0.8 or more, detected at half size),
  largest first;
- `shots`: the base cut into shots at camera changes (difference above 18 and 4x the local median, changes within
  0.3 s merged where they settle) and at every jump cut of `BASE.plan.json`; per shot the median eye position and face
  box of the largest face (`eye_y` null when no face was seen).

It prints the eye height of every shot. `render.py` runs it only when `BASE.faces.json` is missing, so **re-run it by
hand after rebuilding a base** (a stale file puts every layout and caption decision on the old cuts).

## 3. Camera at render time (`render.py`)

**Eye level.** Single layout: if a shot's eyes are not at 740 (`EYE_SINGLE`), the frame is zoomed just enough to put
them there while still filling the frame edge to edge. That zoom is capped at 1.25x and at the point where the face
would pass 42 % of the frame height (`FACE_FRAC`); past the cap the eyes sit as close to 740 as the cap allows. Shots
whose eye height is outside 250-1350 px (a hand or a microphone, not a face) borrow the nearest real shot's eyes.

| Layout | Eye line |
|---|---|
| single (and the blurred background of a statement) | 740 |
| split, bottom half | 1360 (from `BASE.split.mp4`) |
| duo, each half | 420 inside the half |

**Punch-in** (`punch`, default 1.08x): a direct zoom at `t` that holds until the next camera cut, then cuts back.
**Intense push-in** (`intense`, default 1.06x over `t0`-`t1`, shake 3 px): the zoom ramps up across the window and holds
until the next cut after `t1`; a subtle handheld shake (two sine waves per axis, plus 0.12 degrees of rotation) runs
only during the window. Keep shake at 3 px and never above 6 px (more reads as a wobble). The shake moves the frame;
it never changes the zoom (snapshot `19_intense_push_in.jpg`: the start and the end of one push-in).

**Zoom limits.** Punch-ins and push-ins never take the source past 2.3x enlargement (`ZOOM_MAX`, output pixels per
source pixel, measured from `BASE.crops.json`); a punch-in on a tight crop past that went soft. If the base crop
already enlarges more than 2.3x (a far wide shot can reach about 3.3x, more on its tight crop), the punch-in adds
nothing there. Zoom never
decreases between two cuts, so nothing bounces.

**Split bottom half.** Read from `BASE.split.mp4`; punch-ins and push-ins apply around the eye line with the same 2.3x
limit. A split layout needs `BASE.split.mp4` (base_edit.py always writes it); render.py stops with a message if it
is missing.

**Duo.** Built from the source two-shot (the `src` file in `BASE.plan.json`): per camera shot, the two largest faces
are measured on 5 frames and their median boxes fixed for the whole shot (no wandering). Each person is scaled so their
face is `face_h` px tall (default 300, never less than needed to fill the half), eyes at 420 in their half; `top` picks
which seat goes on top (`"left"` default, or `"right"`). A frame without a readable two-shot holds the last duo frame;
with none at all the layout falls back to single (snapshot `18_duo_split.jpg`).

## 4. Layout timing

Layout priority at any moment: statement, then image, then duo, then split/editorial, then single. Every change happens
on one frame (no slides, no wipes; snapshot `17_direct_layout_change.jpg`). Before rendering, `render.py` adjusts
the layout windows from the spec:
- a gap shorter than 0.6 s (`BRIDGE`) between two layouts is held: the first layout runs until the second starts, so
  the full-screen speaker never flashes in between;
- a layout ending within 0.6 s of the clip's end runs to the end;
- a layout edge within 0.6 s of a camera cut moves onto that cut (start back to a cut just before it, end forward to a
  cut just after it), unless another layout already covers that stretch.

Times you write in the spec are therefore the intent; the render log (`OUT.log.jsonl`, `layout` per frame) shows what
was drawn.

## 5. Long form (`base_edit.py --long`)

`--long` sets `MARKCLIP_FORMAT=long` for `frame_base.py`, which then frames the same way for a 16:9 frame:
- **Canvas.** `BASE.mp4` is 1920x1080, 30 fps; no `BASE.split.mp4` is written (long form has no stacked split).
- **Eye line 450 of 1080** (`EYE_FRAC` 41.7 %) for every camera shot.
- **Wide shots stay wide.** The zoom used to bring a wide shot's eyes to the line is at most 1.15x (`ZMAX`), instead
  of 1.85x for a Short; past that the eyes sit a little off the line rather than the shot being blown up.
- **The same rules otherwise:** one fixed crop per camera shot, the wide/tight "second camera" (1.14x) at a jump cut
  inside one shot, faces under 42 % of the frame, held stray frames. Burned-in text is not dodged but erased: every
  box a long-form crop shows is inpainted (`inside_boxes` when `LONG`), since a side layout would cut it and the
  edit's own chapter cards replace it.

At render time (`"format": "long"` in the spec) the single layout puts the eyes at 450 with the same 1.25x zoom cap
and 42 % face limit; punch-ins and push-ins work as in a Short (2.3x source limit). A side layout cuts the speaker's
part out of that same full frame, centred on the speaker's eyes, so the eye line holds across layouts. A duo puts the
two people side by side, one per 960 px half, eyes at 450, with a 4 px dark seam. Layouts, panels and numbers:
long-form.md.

## 6. Options for other kinds of source (environment variables, all off by default)

Set them for `base_edit.py` (it passes them on to `frame_base.py`):

| Variable | Effect |
|---|---|
| `MARKCLIP_GRAPHICS=1` | an explainer with full-screen graphics: a faceless or mostly bright shot (and any bright frame inside a presenter shot) is shown whole, not centre-cropped, on a canvas of its own border colour (a Short: scaled into a band centred at y 760, at most 880 px tall, never enlarged past 1:1; long form: the whole frame); a presenter shot that opens on a flash-in (black, white or fading frames) starts on its first clean frame |
| `MARKCLIP_SPLIT_TOP_PAD=0.12` | the split window may reach this share of its height above the source frame (its top edge repeated): for a speaker framed too high for the split eye line, in front of a plain wall |
| `MARKCLIP_TEXT_BOXES="s0-s1:x0,y0,x1,y1;..."` | the source's own burned-in labels (source seconds, 1920x1080 source pixels), kept whole or left out exactly like the built-in boxes |
| `MARKCLIP_ERASE_TEXT=1` | erase every burned-in label or logo a crop shows (no other show's branding on screen), not only the ones it would cut |
| `MARKCLIP_FORMAT=long` | set by `base_edit.py --long`: the 1920x1080 long-form base (section 5) |

