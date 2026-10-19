# QA gates

A clip is done only when its gates pass on the finished files. Measure; don't eyeball numbers.

## Automatic: `scripts/check.py SPEC.json`
Run it from the job folder. It prints each measurement, then `MARKCLIP CHECK PASSED`, or each `FAIL` line and
`MARKCLIP CHECK FAILED` (exit 1). Nothing is copied from the spec: everything is measured from the files. It needs
the render log (`OUT.log.jsonl`) and makes the background-only render `OUT_bg.mp4` itself (`render.py --bg-only`)
when it is missing or older than the clip. It runs nine gates on a Short, in this order (a long-form video,
`"format": "long"`, has no subtitles: the caption sync gate prints `caption sync: no subtitles in this format` and the
other eight run; the same holds for a Short whose spec sets `"captions": false`):

| Gate | Pass when |
|---|---|
| spec lint | `lint_spec.py` finds nothing: sentence case, no all-caps, every line fits, accent markup balanced, no capital mid-sentence in the captions json |
| duration | output length = base length + `tail`, within 0.2 s |
| caption sync (Shorts with captions) | against the voice-only base (no music: loud scores confuse Whisper): median offset -0.10 to 0.00 s (captions light 0.05 s early on purpose), at most 2 words off by more than 0.25 s, none by more than 0.5 s, at least 90 % of caption words matched |
| music level | music + effects 9-14 dB under the voice, overall (only when the spec has music) |
| faces clear | an independent face detector (YuNet, score 0.8 or more) on the background-only render finds no face under any caption, pill, chip, orbit chip or title box from the render log (every 2nd frame; statement frames skipped). Each face box is raised by 35 % of its height and widened by 10 % a side (also of its height) for the hair; a title, and a caption the log marks `cap_hair` (render.py's last resort), are checked against the face box itself, so they may touch the top of the hair but never the face |
| captions still | a caption never moves while the same phrase and layout are up; a move between phrases is a jump of 40 px or more; no other overlay box sits on the caption |
| no bounce | inside one layout and one camera shot the zoom never decreases (punch-ins and push-ins hold to the next cut) |
| eye level | for single and split frames, per camera shot, the median eye height is within 45 px of the target (740 single, 1360 split bottom; long form: 450 of 1080 for the full frame and the speaker's part of a side layout; for single and long form, moved to where render.py's zoom cap of 1.25x and 42 % face height leaves the eyes); fails when more than 10 % of shots miss |
| loudness | -14 +-1 LUFS integrated, true peak below -0.5 dBFS |

**How caption sync is settled.** check.py transcribes the whole base once with Whisper large-v3 and aligns those words
with the caption words. Whisper's own word starts drift on long passes, so it is not trusted alone: every word it
places more than 0.25 s from its caption is settled by the audio. A short window from 0.08 s before the caption time
to 0.7 s after it is transcribed alone; if one of its first three words matches the caption word (70 % similar:
"then" for "than", "M-make"), the caption is in sync and that word counts as 0 s off. Otherwise the offset stands and
is printed.

The duo layout's eye level is not part of check.py; check duo windows on stills.

## Separate tools when something fails
| Tool | Use |
|---|---|
| `sync_check.py BASE.mp4 WORDS.json` | the caption sync gate, word by word, with every disagreement and its verdict |
| `heard_check.py CLIP.mp4 [...]` | what is actually said, segment by segment, with times (first word, last word, every jump cut) |
| `music_level.py BASE.mp4 FINAL.mp4` | music + effects under the voice: overall, while the speaker talks, in the gaps |
| `lint_spec.py SPEC.json [...]` | the text rules only (`SPEC LINT OK`) |

Common failures:
- **Caption sync**: re-run `words.py` on the current base (a base rebuilt after the words were made is the usual
  cause); add a word Whisper never wrote down with `--insert word@s-e`; fix a misheard word with `--fix`; when the
  sync window hears a word at another time, move it with `--retime word@near=start` (e.g. `a@30.5=29.98`: the "a"
  nearest 30.5 s starts at 29.98 s).
- **Faces clear**: move the overlay (`x`, `y`), shorten it, or give a stack one `group`; read the `! placement:` lines
  render.py printed. The log's `faces` field holds the hair-padded boxes render.py placed around, frame by frame.
- **Eye level**: re-run `analyze_base.py` (a stale `BASE.faces.json` from an earlier base) and re-render.
- **Music level**: change the track's `db` (higher = louder) and re-render.
- **Captions still / no bounce**: usually a hand-edited layout window; re-render from the spec and check again.

## By eye (look at stills, then one full playback with sound)
- Contact sheet: `$PY $CLIPIT_DIR/clip.py sheet output/X.mp4 --n 12`, plus full-size frames at each element.
- The speaker's face is visible in the first 5 s (or as the brief says); nothing covers any face; captions sit on
  their line.
- No cut feels like a bounce; no caption moves while it is up; eye level holds across camera changes; no one-frame
  flash of the full-screen speaker between layouts or of another angle at a camera cut.
- Statements say exactly what is heard; titles and cards say what the speaker means, accurately.
- Music is clearly there under the voice and its swell lands on the turn.
- Long form: no subtitles anywhere; each part opens on its statement card; a side layout appears only where the
  speaker explains something its panel shows, and its panel text fits its part (editorial headlines in a third are
  not measured by the linter: look at them, long-form.md).
Say honestly which of these you checked (stills only, or real-time playback).

## A job ledger (optional: [unlazy](https://github.com/Leonxlnx/unlazy))
For a batch, copy `assets/templates/GATES_clip.md` to `GATES.md` in the job folder and write the gates before
editing (unlazy format: one `CHECK:` command and `EXPECT:` line per gate). Lint it with unlazy's `gate-lint.mjs`, read
and approve the checks with `gate-check.mjs --approve`, run them, and report met and unmet counts. Without unlazy,
run each `CHECK:` line by hand and record the output under `EVIDENCE:`.
