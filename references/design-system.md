# Design system

Everything here is drawn by `scripts/render.py` (with `scripts/engine_core.py`), checked for text by
`scripts/lint_spec.py` and measured by `scripts/check.py`. Stills of every component are in `assets/snapshots/`
(section 9; start with `00_components_overview.jpg`). Camera, eye lines and layout timing are in framing.md. Sizes
below are for a 1080x1920 Short; long form (1920x1080, no subtitles) uses the same type, colour and components on its
own canvas (sections 4 and 5, and long-form.md).

## Contents
1. Rules
2. Type
3. Colour and glass
4. Canvas and safe zones
5. Layouts
6. Components
7. Captions
8. Motion, density, pacing
9. Snapshots

## 1. Rules
- **Two typefaces only: Inter and Instrument Serif**, from `assets/fonts/` (SIL Open Font License). Nothing else on
  screen: no system fonts, no other display faces. render.py and lint_spec.py load only these files.
- **One type scale, weights by role** (section 2). Never pick a size or weight ad hoc.
- **Sentence case everywhere.** No title case, no all-caps labels, no random capitals. Capitals only start a sentence
  (or a "·"-separated segment) or are proper nouns: "I" (and I'm, I've, I'd, I'll), YouTube, Instagram and "Ep." are
  built in; add the show's, the speaker's and every other name in the spec's `proper_nouns`, real acronyms in
  `acronyms`. Captions inherit Whisper's
  punctuation, so `words.py` restores dropped full stops ("fight The" -> "fight. The").
- **Consistent alignment:** left-aligned inside panels and cards on one 64 px margin; titles, pills, captions and
  statements centred.
- **Never place any overlay over any face**, hair included. No caption, pill, chip, orbit chip or title may touch
  anyone's face, above all the speaker's. How it is enforced:
  - **The hair margin.** Pass 1 of render.py renders the background alone and detects every face on every frame
    (YuNet, score 0.8 or more). Each box is raised by 35 % of its height and widened by 10 % a side (also of its
    height), so it covers the hair; `check.py` widens its own boxes the same way.
  - **Placement.** Each overlay is placed where it stays clear of those boxes for its whole life, with 36 px of
    clearance (20 px for captions). A title, drawn centred, may only move up or down.
  - **The 16 px draw-time margin.** At draw time a title, pill, chip or orbit chip that would come within 16 px of a
    face (hair included), or overlap the live caption, is skipped for that frame, so the renderer is always a little
    stricter than `check.py`'s independent detector.
  - **The last resort: the top of the hair, never the face.** Only when no position clears the hair may a title touch
    the top of the hair (render.py prints a `! placement:` line; at draw time that title is held to the face box
    itself instead of the 16 px margin). Likewise, when no caption line clears the hair (a
    close-up filling the lower frame), a phrase may take a line over the top of the hair, never the face; the render
    log marks those frames `cap_hair: true`.
  - **The check.** `check.py` re-detects faces on the background-only render and fails the clip on any overlap: with
    the hair box for captions (unless `cap_hair`), pills, chips and orbit chips; with the face box itself for titles
    and `cap_hair` captions.

  Split panels, full-frame paintings and statements are layouts, not overlays; overlays drawn on a painting clear the
  painted face too.
- **Captions jump, they never glide** (section 7).
- **Direct cuts, no bounce, no sliding** (framing.md): each change of shot or layout happens on one frame; a punch-in
  holds to the next cut; layout gaps under 0.6 s are held.

## 2. Type
| Role | Font | Size (px at 1080 wide) | Used for |
|---|---|---|---|
| statement | Instrument Serif Regular | 132 (accent words: Italic 140, warm gold) | full-frame loud lines |
| display | Instrument Serif Regular | 88 (72 when it must shrink to clear a face) | hook title |
| headline | Instrument Serif Regular | 84 | split-panel titles |
| editorial | Instrument Serif Regular | 78 | editorial card headline |
| quote | Instrument Serif Italic | 60 | quoted words in pills ("Relationships are hard") |
| caption | Inter SemiBold | 62 | subtitles |
| caption accent | Instrument Serif Italic | 76, warm gold | emphasis words inside captions |
| counter | Inter SemiBold | 66 | animated numbers |
| pill | Inter Medium | 44 (52 for checklist items in a list panel) | labels, checklists |
| body | Inter Regular | 32 | panel body text |
| label | Inter Medium | 30 | chip labels |
| meta | Inter Medium | 25 | kicker, panel header row, byline, picture caption |

Line fits (checked by the linter with the real fonts): statement lines <= 960 px (accent words measured at 140, 28 px
between words), title lines <= 900, pill text <= 900, panel titles <= 952, editorial headlines <= 784, and a grid
panel's title block must not run into its icon. In long form the limits follow the 1920 px frame: statements
<= 1800, titles and pills <= 1740, panel titles <= the part's width - 128 (832 in a half, 512 in a third). Break lines
by meaning ("would you still / *do it?*"), not by width alone.

## 3. Colour and glass
- Text white; accent warm gold `(255, 226, 160)` for statement and caption accents.
- Paper `(244, 242, 237)` with a 40 px grid in `(226, 224, 218)`; ink `(22, 22, 22)`; secondary ink `(64, 64, 64)`
  (body, meta, header row); header rule `(196, 194, 188)`.
- Editorial card: page `(252, 251, 248)`, illustration panel `(244, 239, 231)`.
- Framed picture: dark `(18, 17, 16)`, caption `(200, 198, 192)`.
- Strike-through red `(236, 76, 64)`; checklist tick green `(52, 150, 90)`.
- **Liquid glass** (engine_core.glass): a blurred copy of the frame behind, a tint, a 10 % top sheen, a bright rim and
  a soft drop shadow. Titles and chips: white tint 14-18 %. Captions: near-black `(16, 16, 20)` at 36 %, blur 22.
  Pills and chip labels: near-black `(18, 18, 22)` at 30-32 %.
- Footage is not graded. In a Short the top 230 px of single and image layouts get a soft shade (up to 60 % darker) so the phone
  UI stays legible; the top 22 px of a split's bottom half get a short shade under the seam; a duo's seam is a 4 px
  dark line.

## 4. Canvas and safe zones
**Shorts:** 1080 x 1920, 30 fps. Phone UI covers about the top 130 px and bottom 350 px: overlays are only placed
between y 140 and 1575 and x 8-1072; panel header rows start at 150 px. Caption lines: 1395 (single, then 1455, 1515,
last resort 250), 960 = the seam (split and duo: always; never over the panel's text). Eye lines: 740 single, 1360
split bottom half, 420 per duo half.

**Long form:** 1920 x 1080, 30 fps, no subtitles. There is no phone UI: overlays are placed between y 60 and 1020 and
x 8-1912, the hook title defaults to y 80, and no top shade is drawn. Eye line 450 for the full frame, the speaker's
part of a side layout and each person of a side-by-side duo. Panels are as tall as the frame (1080) and as wide as
their part (960 or 640). Details: long-form.md.

## 5. Layouts (switch on a single frame)
| Layout | Looks like | Use for |
|---|---|---|
| single | the speaker, eye-locked, one fixed crop per camera shot (`16_`) | most of the clip |
| split | top half = panel (grid card, list, painting, framed picture, editorial card); bottom half = the speaker, head and shoulders, from `BASE.split.mp4` (`04_`, `15_`) | explaining a concept while the speaker keeps talking (4-8 s) |
| duo | top half = one person, bottom half = the other, eyes level (`18_`) | two people trading lines |
| image | full-frame painting or document with a slow push; overlays allowed off its faces (`10_`) | story cutaways (the "liquid cycle") |
| statement | near-black blurred frame (12 % brightness), big serif line of the speaker's exact words (`02_`, `06_`) | the turn, at most two per clip (long form: the card that opens each part) |

Priority when windows overlap: statement, image, duo, split/editorial, single.

**Long form** has the same layouts on a 1920x1080 canvas: single is the full-frame speaker; a `split` or `editorial`
becomes a **side layout**, the frame in `"parts": 2` (the speaker's half and the panel's half) or `3` (the speaker's two
thirds and the panel's third), with `"side"` (`"right"` default, or `"left"`) saying where the animated panel sits;
image fills the frame; duo puts the two people side by side; statements open each part (snapshots `21_`-`23_`,
long-form.md). Use a side layout only where a concept really needs the visual.

## 6. Components
- **Hook title** (`01_`): an optional Inter meta kicker (light grey, tracked; the examples use "The podcast · Episode 26")
  46 px above a liquid-glass panel (radius 46) with the idea in Instrument Serif display, default y 210, 0-4.5 s,
  0.3 s fades. The speaker's idea, accurately, in a few words; never clickbait. If it would touch a face (hair included) it moves
  up or down by the smallest shift that clears it; failing that it drops the kicker, then shrinks to 72 px, then both;
  failing all, the same steps run again against the face alone, so it may touch the top of the hair, never the face
  (`! placement: title touches the top of the hair`); if even that fails it is hidden on the frames where it would
  touch a face.
- **Statement** (`02_`, `06_`): the speaker's exact words for that moment; key words `*in accent*`; centred lines; each word
  fades in over 0.18 s, 0.06 s after the previous. Replaces the captions while up, so it must be verbatim.
- **Orbit chips** (`03_`, `10_`): liquid-glass circles (radius 96: a pixel icon or a square crop of an image) with
  Inter labels in small dark glass pills. They travel a rectangular track drawn around the padded face (every face
  box within 0.2 s, hair included; speed 0.45 by default, about 72 px a second along the track), so neither chip nor
  label can touch it; if the track does not fit the frame they sit still along the longest part that fits, else in a
  row below the chin or above the head, else in a small grid beside the face. A chip that would touch a face or the
  caption on some frame is skipped on that frame.
- **Split grid panel** (`04_`, `05_`): dgrees-style paper grid; header row at 150 px (left: the spec's `show` name
  unless `labels` says otherwise, the examples' "The podcast"; right e.g. "Ep. 26 · Failure") over a rule; serif headline top-left from 222 px; pixel icon (centre default
  (750, 520), 400 px) that glitch-morphs (0.28 s) at each later icon's time; Inter body bottom-left ending 70 px above
  the seam; optional counter (Inter SemiBold 66, eased count with thousands separators and a suffix).
- **List panel** (`07_`): the grid panel's header and title with checklist items that tick in as the speaker says them: a green
  circle with a white tick and Inter Medium 52 text, 112 px apart. Short checklists can also be pills with a `✓`
  prefix.
- **Pills** (`07_`, `08_`, `11_`): Inter Medium 44 in near-black glass, or a **quote pill** in Instrument Serif
  Italic 60 inside curly quotes, which you type into its text (only words the speaker actually said). `strike` crosses one out
  with a red line drawn over 0.28 s. Give a stack one `group` so it moves as one when it has to dodge a face: a group
  of 3+ may become two columns; chips in a group may shrink to 85, 72 or 60 %; pills keep their type size.
- **Split painting / framed picture** (`09_`, `11_`): a painting fills the top half with a slow push (1.0 -> 1.08,
  around `focus`); a small or low-resolution picture is shown sharp in a rounded frame on dark (560 px tall by
  default, 5 % push) with an Inter meta caption ("Casanova at 63 · engraving, 1788").
- **Editorial card** (`12_`): markclip's payoff card (design-references.md), drawn as a split panel: an off-white
  page with a warm illustration panel (a 380 px pixel icon with a hard shadow, or a painting) above an Instrument
  Serif headline and an Inter byline (default: the spec's `show`, empty without one). Use as the payoff in the last
  4-6 s.
- **Captions** (`13_`, `14_`): section 7.
- **Chip**: a static glass circle (radius 110) with a crop of the person the speaker is talking about or an icon,
  plus an optional label; in the first seconds, kept off the speaker's face.

Pixel icons (drawn in code, `engine_core.ICONS`): see design-references.md.

## 7. Captions
**Phrases** (`engine_core.build_phrases`): at most 4 words / 22 characters: a phrase closes as soon as it reaches
4 words or 22 characters. A phrase always ends at . ? !, and at a comma once it has 2 or more words (no one-word "it,"
pill). Where it reaches the size limit:
- if the next word ends the sentence and the phrase with it stays within 28 characters, that word joins (up to
  5 words / 28 characters), so a sentence's last word never sits alone ("would you still do / it?" becomes one
  phrase); if it would not fit, the phrase's own last word moves on with it instead (when the phrase has 3+ words);
- a phrase does not end on a weak word (a, an, the, of, to, in, on, at, for, with, and, but, or, my, your, his, her,
  their, its, our, is, was, be, if, that, when, who, which, it, I, you, we, they, he, she): the break backs up past
  them while 2+ words remain ("the" starts the next pill instead of ending this one), so only a two-word phrase may
  still end on one ("at it");
- a comma does not break when the next word ends the sentence and fits ("no partner, nothing." stays one pill).

Whisper's split hyphen words are joined before phrasing ("deep -seated" -> "deep-seated", words.py `join_hyphens`).

**Look:** Inter SemiBold 62, white, 16 px between words, inside a near-black glass pill (36 %, blur 22, 40 px side
padding). Words listed in the spec's `emphasis` (matched lower case, punctuation ignored) are set in Instrument Serif
Italic 76, warm gold.

**Motion, word by word** (snapshot `13_caption_word_lift.jpg`):
- the pill fades in over 0.16 s while settling from 94 % to 100 % size with a slight overshoot (ease-out-back), and is
  visible from its first frame;
- the whole phrase shows dim, at 38 % opacity;
- each word brightens to 100 % over 0.10 s, starting 0.05 s before it is spoken, and lifts 6 px and settles back over
  0.30 s as it lights;
- the pill fades out over its last 0.12 s.

**Hand-over, one caption at a time:** the next pill shows once the previous phrase's last word has lit for 0.15 s
(that word's start + 0.10 s, since words light 0.05 s early), at the earliest 0.15 s and never later than 0.05 s
before its own first word. There is no fixed delay: after a pause the pill shows 0.15 s before its first word; in fast
speech it waits for the previous last word, up to 0.05 s before its own. A phrase stays up until 0.7 s after its last
word ends or 0.02 s before the next phrase's first word, whichever is first. When two phrases overlap for a moment,
only the newer one is drawn.

**Position: fixed per layout stretch.** For each stretch of one layout, render.py picks one caption line that is
clear of every face (20 px padding) for the whole stretch and wide enough for its widest phrase: single and image
layouts try 1395, 1455, 1515; split and duo use 960 (on the seam) only, so a caption never covers panel text. Every phrase in that stretch uses that line;
the caption jumps only when the layout changes (snapshot `17_direct_layout_change.jpg`). Only when no line is clear
for the whole stretch (a close-up filling the lower frame) does each phrase find its own line: it stays on the
previous phrase's line if that is clear, else tries the lower lines and finally the top line at 250 px (split and duo:
960). If none of them clears the hair, the phrase takes the first that clears the face itself: it may touch
the top of the hair, never the face, and the log marks it `cap_hair`. If nothing clears even the face, render.py
prints `! placement: caption at Xs could not clear a face` and uses the default line.

**Around statements:** a statement replaces the captions while it is up. After a statement, the rest of a phrase is
shown only if one of its words is still to be spoken; a piece of a phrase shorter than 0.4 s with no word starting in
it, or any piece shorter than 0.2 s, is not drawn. So no caption flashes on or off around a statement card.

**Other overlays** are placed after the captions and avoid their boxes; at draw time whatever would overlap the
live caption is skipped for that frame.

## 8. Motion, density, pacing
- Overlays fade in 0.25 s and out 0.2 s (title 0.3 / 0.3, statement 0.12 / 0.2). No scale pops, no overshoot, no bob,
  no sliding (the caption pill's settle and word lift are the one exception). Orbit chips move only along their track.
- Pixel icons may glitch-morph (0.28 s of slice displacement with a chroma split) on a spoken cue; their idle animation
  (waves, flag, drip, heartbeat) stays inside the icon.
- Camera: static per shot except `punch` and `intense` (framing.md). The last 0.6 s of the clip fades to black (spec
  `fade_out`).
- Something new every 3-6 s; at most two statements; split windows 4-8 s; the speaker visible at least half the
  runtime; no overlay on screen longer than it takes to read twice.

## 9. Snapshots (`assets/snapshots/`)
Stills from real renders made by these scripts. Look at them before designing a clip; each shows the component or rule
it is named after.

| File | Shows |
|---|---|
| `00_components_overview.jpg` | a labelled contact sheet of every snapshot below |
| `01_hook_title_glass.jpg` | hook title: the kicker over a liquid-glass panel |
| `02_statement_loud_line.jpg` | one-line statement with a gold italic accent |
| `03_orbit_chips_around_speaker.jpg` | orbit chips circling the speaker's face, clear of it |
| `04_split_grid_panel_pixel_icon.jpg` | split screen: grid panel with a pixel icon, caption on the seam |
| `05_split_grid_panel_counter.jpg` | split screen: grid panel with a counter |
| `06_statement_multiline.jpg` | multi-line statement |
| `07_checklist_pills.jpg` | list panel: checklist items ticking in as the speaker says them |
| `08_quote_pill_serif.jpg` | quote pill in serif italic, clear of the hair |
| `09_split_image_painting.jpg` | split screen: a painting in the top half, with a label pill |
| `10_liquid_cycle_painting_orbit.jpg` | full-frame painting with orbiting image chips (the "liquid cycle"), clear of the painted face |
| `11_split_framed_strike_pills.jpg` | framed engraving with struck-through pills |
| `12_editorial_end_card_icon.jpg` | editorial end card with a pixel icon, serif headline and byline |
| `13_caption_word_lift.jpg` | one phrase over 5-6 moments: the pill settling in (94 % -> 100 %), the words dim at 38 %, each word brightening with its 6 px lift as it is spoken. The pill appears once the previous phrase's last word has lit for 0.15 s, never later than 0.05 s before its own first word (section 7) |
| `14_captions_serif_accent.jpg` | a caption with a serif italic accent word |
| `15_split_head_and_shoulders.jpg` | split screen: the speaker head and shoulders under the panel (a 9:8 window of the source, face under 42 % of the half), caption on the seam |
| `16_jumpcut_wide_tight.jpg` | side by side: the last frame before and the first frame after a jump cut inside one camera shot: wide, then tight (1.14x) |
| `17_direct_layout_change.jpg` | side by side: the last split frame and the first full-screen frame: a direct cut, the caption jumping to its new line |
| `18_duo_split.jpg` | duo: two people, one per half, eyes level (420 px inside each half) |
| `19_intense_push_in.jpg` | side by side: the start and the end of an intense push-in, same shot |
| `20_text_safe_crop.jpg` | text-safe crop: the 16:9 source frame with the 9:16 crop window drawn on it and dashed boxes where its burned-in chapter label and logo were (erased), next to the resulting 9:16 frame, which shows no cut text (framing.md) |
| `21_long_full_frame.jpg` | long form: the full-frame 1920x1080 speaker, eyes at 450, no subtitles (long-form.md) |
| `22_long_side_two_parts.jpg` | long form, side layout in two parts (`"parts": 2`): the speaker's half beside an animated panel half, one eye line |
| `23_long_side_three_parts.jpg` | long form, side layout in three parts (`"parts": 3`): the speaker in two thirds beside an animated panel in the other third |
