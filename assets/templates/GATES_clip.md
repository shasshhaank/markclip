# Gates: <batch name, e.g. episode 12 Shorts>

OWNS: base/**, words/**, specs/**, output/**, SEO_and_schedule*.md

Scope: <n> videos from <source>, each passing markclip's measured gates and posted in your scheduler's format.

check.py runs nine gates on a Short: spec lint, duration, caption sync, music level, loudness, faces clear, captions
still, no bounce and eye level. A long-form video (`"format": "long"`) has no subtitles, so check.py skips caption sync
there and runs the other eight. Its eye line is 450 of 1080.

- [ ] G0: this ledger states outcomes that can fail
  CHECK: node <unlazy-dir>/scripts/gate-lint.mjs GATES.md
  EXPECT: LINT OK
  EVIDENCE: pending

- [ ] G1: Short 01 passes all nine check.py gates: spec lint, duration, caption sync, music level, loudness, faces clear, captions still, no bounce and eye level
  CHECK: <PY> <markclip>/scripts/check.py specs/01.json
  EXPECT: MARKCLIP CHECK PASSED
  EVIDENCE: pending

- [ ] G2: Short 02 passes all nine check.py gates: spec lint, duration, caption sync, music level, loudness, faces clear, captions still, no bounce and eye level
  CHECK: <PY> <markclip>/scripts/check.py specs/02.json
  EXPECT: MARKCLIP CHECK PASSED
  EVIDENCE: pending

- [ ] G3: long-form video 03 passes the eight check.py gates that apply without subtitles: spec lint, duration, music level, loudness, faces clear, captions still, no bounce and eye level (no caption sync in long form)
  CHECK: <PY> <markclip>/scripts/check.py specs/03_long.json
  EXPECT: MARKCLIP CHECK PASSED
  EVIDENCE: pending

- [ ] G4: the YouTube posting file parses and every video it names exists
  CHECK: <your scheduler's check command> SEO_and_schedule.md
  EXPECT: <the line it prints only when the file parses>
  EVIDENCE: pending

- [ ] G5: each video was watched once with sound; the first 5 s show the speaker; no overlay on a face; music audible; in long form, no subtitles and a side layout only where a concept needs the visual
  EVIDENCE: pending
