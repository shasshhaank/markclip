# Spec format (input to `scripts/render.py`)

One JSON file per video. Paths inside it are relative to the folder you run `render.py` and `check.py` from (the job
folder). Five complete examples are in `assets/examples/specs/`, four Shorts with their caption words in
`assets/examples/words/` and one long-form video (no words: long form has no subtitles):

| Example | Shows |
|---|---|
| `01.json` shame and achievement | hook title, statements with punch-ins, grid splits with icon morphs and a counter, intense push-in, a label pill, editorial end card |
| `02.json` desert island test | grid split, statement, orbit chips with icons, a serif quote pill, editorial end card |
| `03.json` first fight | statement, grid splits, a list panel that ticks items in, intense push-in |
| `04.json` Casanova | painting split with a name pill, full-frame painting with an image orbit, framed engraving with strike pills, a music hand-off (Spring -> Winter) |
| `05_long.json` long form | `"format": "long"`: hook title, statements, side layouts in two parts and in three parts (panel left), an editorial card in a side layout, a label pill, no subtitles (walk-through in long-form.md) |

The examples name music files (`music/...mp3`) and pictures (`images/...jpg`) that are **not bundled**: fetch your own
(sound-design.md, design-references.md) and change the paths. Their `base`, `words` and `out` paths assume the job
folder layout `base/ words/ specs/ music/ images/ output/`.

## Top level
```json
{
  "show": "The podcast",
  "base": "base/02.mp4",
  "words": "words/02.json",
  "out": "output/02_desert_island_test.mp4",
  "tail": 0.5,
  "fix": [["coach", "coached"]],
  "emphasis": ["desert", "island", "nobody", "validation,"],
  "proper_nouns": ["Casanova"],
  "music": [{"file": "music/x.mp3", "start": 14.0, "t0": 0.0, "db": -9, "fade_in": 0.6, "fade_out": 1.8}],
  "sfx": [{"t": 6.9, "name": "paper"}, {"t": 13.3, "name": "hit", "db": -12}],
  "elements": []
}
```

| Key | Required | Meaning (default) |
|---|---|---|
| `format` | no | `"long"` for a 1920x1080 long-form video without subtitles (long-form.md); a 1080x1920 Short when absent |
| `show` | no | the show's name: the default left label of every panel header row and the default editorial byline ("": none). Put it in `proper_nouns` too if it has capitals mid-sentence |
| `base` | yes | the base edit from `base_edit.py` (`--long` for long form); `BASE.plan.json`, `BASE.crops.json`, `BASE.split.mp4` (Shorts) and `BASE.faces.json` are read from beside it |
| `words` | Shorts with captions | caption words from `words.py`, timed on that base; not needed in long form or with `"captions": false` |
| `captions` | no | `false` turns the subtitles off in a Short (true); long form never draws them |
| `out` | yes | the finished clip; `OUT_mix.wav`, `OUT.log.jsonl` and `OUT_bg.mp4` are written beside it |
| `tail` | no | seconds of hold after the base ends (0) |
| `fade_out` | no | the last seconds of the video fade to black (0.6) |
| `fix` | no | `[[wrong, right], ...]` caption word fixes, exact whole words |
| `emphasis` | no | caption words set in the serif italic accent (matched lower case, punctuation ignored) |
| `proper_nouns` | no | words the linter allows to be capitalised mid-sentence (I, I'm, I've, I'd, I'll, YouTube, Instagram, Ep. are built in; add the show's and the speaker's names) |
| `acronyms` | no | all-caps words the linter allows |
| `music` | no | one entry per track; several entries make a hand-off |
| `sfx` | no | effects |
| `duck_db` | no | how far music dips under speech (-4) |
| `elements` | yes | the graphics, below |

**`music` entry:** `file`, `start` (seconds into the song, 0), `t0` / `t1` (where it plays in the clip, 0 to the end
including the tail), `db` (level relative to the voice, -9: lands about 10-12 dB under it), `fade_in` (0.5),
`fade_out` (1.5).
**`sfx` entry:** `t`, `name`, `db` (relative to the voice, -15), `seed` (0; vary it so repeated effects differ).
Names: `click`, `paper` (page turn), `hit`, `boom`, `sub_drop`, `glitch`, and the rest of ClipIt's generated set
(sound-design.md).

## Elements
Times are seconds on the base edit's timeline: read them from the words json. Every overlay is checked against faces
at render time; give a natural position and the renderer moves it only if a face is in the way. Layout windows (`split`,
`editorial`, `image`, `duo`, `statement`) are adjusted at render time: short gaps are held and edges snap to nearby
camera cuts (framing.md, Layout timing).

| type | fields (default) | notes |
|---|---|---|
| `title` | `t0 t1 text kicker y` (no kicker, y 210; long form y 80) | hook, 0-4.5 s; `\n` breaks lines; the examples' kicker is "The podcast · Episode 26" |
| `statement` | `t0 t1 text` | the speaker's exact words in that window; `*accent words*`; `\n` breaks lines; hides captions and overlays; at most 2 per clip |
| `punch` | `t zoom` (1.08) | direct punch-in held until the next camera cut |
| `intense` | `t0 t1 zoom shake` (1.06, 3) | slow push-in across t0-t1 plus handheld shake in px (keep 3, never above 6); the zoom holds to the next cut |
| `split` | `t0 t1 panel{...}` (long form also `parts side`: 2, "right") | Shorts: top-half panel, speaker below (eyes at 1360), captions on the seam (960; never over the panel's text). Long form: a side layout, the frame in `parts` 2 or 3 with the panel a half or a third, on the `side` "right" or "left" |
| `editorial` | `t0 t1 headline icon or img focus byline` (long form also `parts side`) | payoff card drawn as a split panel; `byline` defaults to the spec's `show` |
| `image` | `t0 t1 img focus zoom dim` ([0.5, 0.45], [1.0, 1.08], 0) | full-frame painting or document; `zoom` is [start, end] of a slow push; `dim` 0-1 darkens it |
| `duo` | `t0 t1 top face_h` ("left", 300) | two-person split from the source two-shot; `top`: which seat ("left" or "right") goes on top (long form: on the left); `face_h`: face height in px |
| `pill` | `t0 t1 text x y quote strike group` (x 540, long form 960; y required) | label; `quote: true` = serif italic (type the curly quotes into `text`: `"“Keep trying”"`); `strike` = time to cross it out; pills with the same `group` move together. A pill or chip group that no position keeps clear of every face for its whole life is skipped entirely (render.py prints `! placement: group ... skipped`): move it to a wider shot or shorten it |
| `chip` | `t0 t1 x y r img or icon label group` (x 540, long form 960; r 110; y required) | static glass circle with an image crop or a pixel icon |
| `orbit` | `t0 t1 speed chips[...]` (speed 0.45) | chips circle the face (every face box within 0.2 s, hair included); each chip: `img` or `icon`, `label`, `t` (in), `t_out` (out), `r` (96) |

### Split panels (`panel.kind`)
| kind | fields (default) |
|---|---|
| `grid` | `labels` [left, right] header row (left defaults to the spec's `show`), `title` (serif, `\n` allowed), `body` (Inter, `\n` allowed), `icons` [{`t`, `name`}] (the icon changes, with a glitch, at each `t`), `icon_x icon_y icon_size` (750, 520, 400: the icon's centre and size; long form: size min(400, 0.36 x the part's width), x the part's width - 0.825 x size, y 585), optional `counter` {`t0 t1 from to suffix y`} (y 560) |
| `list` | `labels`, `title`, `items` [{`t`, `text`}] (each item ticks in at its `t`), optional `list_y` (first item's top, 360 for a one-line title) |
| `image` | `img focus zoom dim` ([0.5, 0.4], [1.0, 1.08], 0): a painting fills the top half (long form: its part) |
| `framed` | `img h caption bg` (h 560, bg [18, 17, 16]): a sharp picture in a rounded frame on dark, Inter caption under it at 150 + h + 30 px. Pills and chips dodge faces and captions, not panel text, so leave them a row: the Casanova example's h 480 keeps its strike pills between the picture's caption and the seam caption |
| `editorial` | as the `editorial` element |

`focus` is the point of the picture to keep in view, as fractions [x, y] of its width and height. In long form
every panel is drawn at its part's width (1920 / `parts`: 960 or 640) and the full height (1080), with the same header
row at 150, title from 222 and body ending 70 px above the bottom (long-form.md, panel sizing).

## The words file (`words.py` output)
`[{"w": "Shame", "s": 0.21, "e": 0.55}, ...]`: the caption word as shown, its start and its end in seconds on the
base. A word may also carry `"src"`, the word as heard, when the caption writes it differently (another script or
spelling, a number written as digits): `check.py` and `sync_check.py` match the audio against `src`, and the caption
still shows `w`. Add `src` by hand; `words.py` never writes it.

## Long form
```json
{"format": "long", "show": "The podcast", "base": "base/05.mp4", "out": "output/05_long.mp4", "tail": 0.5,
 "elements": [
  {"type": "title", "t0": 0.16, "t1": 2.9, "kicker": "The podcast · Episode 26", "text": "You can't achieve your\nway out of shame"},
  {"type": "statement", "t0": 2.95, "t1": 4.05, "text": "but it *backfires.*"},
  {"type": "split", "t0": 18.97, "t1": 26.32, "parts": 3, "side": "left", "panel": {"kind": "grid", "title": "More views",
   "icons": [{"t": 18.97, "name": "eye"}], "counter": {"t0": 19.94, "t1": 25.84, "from": 1204, "to": 1204331, "suffix": " views"}}},
  {"type": "editorial", "t0": 41.71, "t1": 46.72, "parts": 2, "side": "left", "icon": "heart_mended",
   "headline": "Your failures don't make\nyou a bad person."}]}
```
No `words`, no captions; `parts` and `side` sit on the `split` or `editorial` element, not inside the panel. Everything
else (music, sfx, punch, intense, pills, chips, orbit, image, duo) is written as for a Short, in 1920x1080 pixels.
The full example is `assets/examples/specs/05_long.json`; long-form.md walks through it.

## Duo example
```json
{"type": "duo", "t0": 31.2, "t1": 38.6, "top": "left", "face_h": 300}
```
Use it only when two people trade lines that must stay; it needs `BASE.plan.json` (written by base_edit.py) to find
the source two-shot.

## Worked example (desert island, abridged)
```json
{"type": "title", "t0": 0.09, "t1": 5.02, "kicker": "The podcast · Episode 26", "text": "The desert island test", "y": 210},
{"type": "split", "t0": 6.86, "t1": 12.87, "panel": {"kind": "grid",
  "labels": ["The podcast", "Ep. 26 · Failure"], "title": "The desert\nisland test",
  "body": "Nobody would ever know.\nWould you still do it?",
  "icons": [{"t": 6.86, "name": "island"}, {"t": 11.68, "name": "eye_slash"}], "icon_x": 760, "icon_y": 470, "icon_size": 420}},
{"type": "statement", "t0": 12.87, "t1": 14.34, "text": "would you still\n*do it?*"},
{"type": "punch", "t": 13.7},
{"type": "orbit", "t0": 19.14, "t1": 23.72, "speed": 0.55, "chips": [
  {"icon": "heart", "t": 19.16, "t_out": 23.48, "label": "Likes"},
  {"icon": "eye", "t": 19.27, "t_out": 23.55, "label": "Views"}]},
{"type": "editorial", "t0": 24.52, "t1": 29.5, "icon": "island", "headline": "Would you still do it\nif no one knew?"}
```
Run `lint_spec.py` before rendering; it measures every line with the real fonts and enforces sentence case.

## After rebuilding a base: re-time, don't rewrite
A new base edit shifts every moment. Keep the old words file, make the new one, and move the spec with its words:
```
cp words/01.json words/01_old.json
$PY $S/scripts/words.py base/01.mp4 words/01.json
$PY $S/scripts/retime_spec.py specs/01.json words/01_old.json words/01.json specs/01_new.json
```
`retime_spec.py OLD_SPEC OLD_WORDS NEW_WORDS NEW_SPEC [--base B] [--words W] [--out O]` aligns the old and new words
(same speech, so the same words) and moves every `t`, `t0`, `t1`, `strike` and `t_out` in `elements`, `music` and
`sfx` (nested ones too: icons, items, chips, counters): piecewise linear between matched words, a plain shift before
the first or after the last. Song offsets (`start`) stay. `--base/--words/--out` rewrite those paths in the new spec.
It prints the share of old words matched and the range of shifts; a low share means the speech changed, so check the
elements by eye. Then re-run `analyze_base.py` on the new base, lint and render.
