# Sound design

## The bed must be audible
Music sits **9-14 dB under the voice** (aim for 10-12 dB). An earlier version put it 28-32 dB under, where it was
inaudible: the gain was set from the whole song's loudness while the section used was a quiet intro. So `render.py`
now works on the section it actually uses:
1. it takes the song from `start` for the length of `t0`-`t1`;
2. levels it against a 1 s loudness envelope (quiet passages lifted up to +12 dB, loud ones pulled down up to -6 dB,
   gain smoothed);
3. scales it to the voice's speech RMS plus `db` (default -9);
4. fades it (`fade_in` 0.5 s, `fade_out` 1.5 s by default) and ducks it only 4 dB under speech (`duck_db`).

Spec `"db": -9` lands around 10-12 dB under the voice. The whole mix (voice + music + effects) is normalised to
-14 LUFS with a soft limiter at -1 dBFS (ClipIt's `audio.normalize`); `check.py` wants -14 +-1 LUFS and a true peak
below -0.5 dBFS. Always measure:
```
$PY $S/scripts/music_level.py base/02.mp4 output/02_x.mp4
```
It prints how far music + effects sit under the voice overall, while the speaker talks, and in the gaps. The overall number is
the one `check.py` gates (9-14 dB). Too quiet: raise `db` (towards -7); too loud: lower it (towards -11).

## Pick famous music that fits the subject
Use recognisable tracks that match the topic, and "something bad's about to happen" tension for the
reflective/hard-truth moments. Proven picks:

| Subject | Track | Where to start | Why |
|---|---|---|---|
| ambition, achievement, status, shame | Nicholas Britell, "Succession" main title | 0 s (full power from bar 1) | money/status tension |
| solitude, purpose, doing it for yourself | Hans Zimmer, "Interstellar" main theme | ~14 s (organ swells ~22 s) | big, lonely, building |
| fights, relationships going wrong | Clint Mansell / Kronos Quartet, "Lux Aeterna" | ~20 s (strings rise ~24 s) | dread |
| 18th-century / Casanova / history | Vivaldi "Spring" for the wild life, then "Winter" I (Allegro non molto) when the story turns sad | Winter from ~22 s of the track (example 04), so its outburst (~36 s) lands on the key line | period-correct and dramatic |
| reflective inner work (softer) | Ludovico Einaudi, "Experience" (slowed + reverb) | 0 s | emotional build |
| relationships (soft) | "All of Me" piano cover | ~40 s (chorus) | the love song everyone knows |

Line the track's biggest moment up with the clip's turn: find the loud passages with a 2 s loudness profile
(the snippet in clipit-extraction.md) and offset `start` so the swell lands on the statement. Songs with vocals fight
the speech: use instrumental, piano or orchestral versions. A hand-off is two `music` entries that overlap by under
a second (example `04.json`: Spring until 10.28 s, Winter from 9.5 s).

### Getting the files
YouTube fetches are bot-blocked after bursts (`clip.py fetch --audio URL` works when it isn't). SoundCloud has the
same fan uploads and official soundtrack uploads, through the same yt-dlp:
```
$PY -m yt_dlp --flat-playlist --print "%(duration)s|%(title).70s|%(uploader).28s|%(url)s" "scsearch8:succession main title theme"
$PY -m yt_dlp -x --audio-format mp3 -o "music/%(title).60s [sc%(id)s].%(ext)s" "THE_API_SOUNDCLOUD_URL"
```
Prefer official uploads (Milan Records, Nonesuch) or clean orchestral recordings. These are copyrighted: say once that
claims are possible; don't re-argue it every batch, and never add audio tricks to dodge Content ID.

## Effects at about -15 dB under the voice
| Moment | Effect | `db` |
|---|---|---|
| a pill, chip or label appears | `click` (vary `seed`) | -15 |
| a split panel or card comes in | `paper` (page turn) | -15 |
| it goes away | `paper` (another seed) | -18 |
| a statement starts | `hit` | -12 |
| the key word of a statement / punch-in | `boom` | -13 to -14 |
| a dark beat ("never happy", "nothing") | `sub_drop` | -14 to -16 |
| a pixel icon glitch-morphs | `click` + `glitch` | -15 / -18 |

An effect's `db` is relative to the voice's RMS, measured over the effect's audible part. All effects are generated in
code, so they are copyright-free: `paper` by `render.paper_turn`, the rest by ClipIt's `audio.sfx` (also available:
`whoosh`, `swoosh`, `swish`, `pop`, `impact`, `drop`, `riser`, `downlifter`, `reverse_cymbal`, `rewind`, `typing`,
`shutter`, `tape_stop`; markclip's look rarely needs them). Never stack two effects within 0.1 s; never put an effect
on top of a word you want heard clearly.

## Long form
The same levels apply (9-14 dB under the voice, effects about -15 dB, -14 LUFS), with fewer effects: a click or
paper turn where a side panel comes in, a hit under each part's statement card, nothing on the full-frame stretches
in between. A bed under several minutes is easier to hear when it changes with the parts: hand off to a new track
(two `music` entries overlapping by under a second) at each part's statement, and let a long stretch of plain talk
fall to the quiet passage of a track rather than loop a swell (long-form.md).
