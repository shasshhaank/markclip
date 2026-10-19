# Design references

The two references the markclip look is modelled on. Copies are in `assets/design-references/`; the originals are on
Pinterest. They set the look; the rules in design-system.md override whatever here would break them (the
references use other typefaces; markclip uses only Inter and Instrument Serif). Both belong to their creators and are
bundled only as visual reference.

## 1. "Liquid Cycle" by 108.supply
- File: `assets/design-references/ref1_liquid_cycle_108supply.jpg`
- Source: https://www.pinterest.com/pin/1142506999243895572/ (108.supply's "Liquid Cycle" freebie)

A dark classic painting (Leonardo's "Lady with an Ermine") with frosted liquid-glass circular portrait chips orbiting
it and one frosted pill label ("Visionaries") in the middle.
**Taken:** liquid-glass pills and chips (frosted copy of the frame + tint + bright rim), orbiting chips, the single
calm label, paintings as subject matter. Used for hook titles, captions, chips, the Casanova "experiences" orbit.

## 2. dgrees.studio pixel grid
- Files: `assets/design-references/ref3_dgrees_pixel_grid.mp4` (the animation),
  `assets/design-references/ref3_dgrees_pixel_grid_frames.jpg` (frames from it)
- Source: https://www.pinterest.com/pin/1079104760730137038/

A light grid page: pixel-art icons (ghost, cherries, potion, heart, invader) that glitch-morph into each other, short
grotesk titles top-left, a thin header row, small body text.
**Taken:** the paper grid panel, header row, title top-left, pixel icons with glitch morphs on a spoken cue. Used for
split-screen explainer panels in Shorts and the animated part of a long-form side layout.

## The editorial card (markclip's own)
The payoff card is markclip's own design, built from the two references above: an off-white page `(252, 251, 248)`
with a warm illustration panel `(244, 239, 231)` holding one hard-shadowed pixel icon (or a painting), a big
Instrument Serif headline under it, a small Inter byline and a lot of air. It takes the grid panel's calm paper and
pixel icons, sets the takeaway as a headline, and leaves out the grid so it reads as the last word. Snapshot
`12_editorial_end_card_icon.jpg` shows it; design-system.md (section 6) gives its sizes.

## What markclip built from them
`assets/snapshots/00_components_overview.jpg` is a labelled sheet of the Shorts snapshots: hook title (`01_`),
statements (`02_`, `06_`), orbit chips (`03_`), split grid panels with an icon and a counter (`04_`, `05_`), checklist
(`07_`), quote pill (`08_`), split painting (`09_`), the painting-and-orbit "liquid cycle" (`10_`), framed engraving
with strike pills (`11_`), editorial end card (`12_`), the caption word lift (`13_`), captions with serif accents
(`14_`), split head and shoulders (`15_`), a wide-to-tight jump cut (`16_`), a direct layout change (`17_`), the duo
split (`18_`), an intense push-in (`19_`) and a text-safe crop (`20_`). The long-form layouts follow: the full-frame
speaker (`21_`), a side layout in two parts (`22_`) and in three parts (`23_`). design-system.md (section 9) explains
each one.

## Icons available (pixel art, drawn in code: `engine_core.ICONS`)
`island`, `eye`, `eye_slash`, `heart`, `heart_broken`, `heart_mended`, `flag` (green), `bucket` (leaking), `trophy`,
`arrow_up` (a red arrow), `grave`, `firework`. Add new ones in `engine_core.py` as small `ImageDraw` functions on a
24x24 grid (they are scaled with nearest-neighbour, so draw pixel by pixel) and register them in `ICONS`.

## Images
Outside images are allowed once the user confirms each one (references/brief.md); outside video is not. Prefer
public-domain paintings and documents from Wikimedia Commons (fetch with the REST summary API or the Commons search
API and record the licence). Verify any date or fact printed next to an image (e.g. "Casanova, 1725-1798",
"Casanova at 63 · engraving, 1788"). Put them in the job's `images/` folder and reference them from the spec.
