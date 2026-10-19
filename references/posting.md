# Posting files

If your scheduler reads markdown, write one file per platform in this format. Filled-in examples (with `<...>`
placeholders for the show's own names and handles): `assets/templates/SEO_and_schedule.example.md` (YouTube: Shorts
and a long-form video) and `assets/templates/SEO_and_schedule_IG.example.md` (Instagram Reels).

## Format (must parse; run your scheduler's checker if it has one)
- `**Videos folder:** /absolute/path/to/output` above the first video.
- Per video: `## <n>. <file.mp4> | <Day Mon D YYYY, H:MM AM TZ>` (e.g. `## 1. 01_x.mp4 | Thu Oct 15 2026, 11:00 AM ET`),
  then `**Title:**` (one line, <= 100 chars, no `<` or `>`), `**Description:**` (multi-line, runs until the tags),
  `**Tags:**` (comma-separated, <= 500 chars total).
- Always the year, in every heading and in any summary table above the first video; notes only at the end under
  `###`.
- Replace every `<...>` placeholder before scheduling: a title never keeps one.

## Timing
Post when the brief's audience is awake (references/brief.md). For a US audience: US daytime only (8 AM-8 PM
Eastern), one post every 3 hours; a slot that would fall after 8 PM moves to 8 AM ET the next day. Start at the next
open slot after the channel's last scheduled post (confirm with the user). Write times in the timezone your scheduler
reads (TZ, e.g. ET), and mind daylight-saving changes when converting.

## Text rules
- Lead with the idea in the video, not a summary of the show; no clickbait; facts verified.
- YouTube Shorts: the title ends `#shorts`; description = one or two lines of the idea, a source line
  (`From "<episode title>" on <Show name>.`), the handles the brief asks for, a music credit line (`🎵 Music: ...`),
  then 5-7 hashtags.
- YouTube long form: the same description shape, a title without `#shorts`; add chapter times in the description if
  the video has parts (`0:00 <part one>`, `2:40 <part two>`).
- Instagram Reels: the title is the hook line; the description adds the handles and a music credit; tags become
  hashtags (<= 30).
- Each platform gets its own cut: never the same clip on two platforms, and only the platforms the user asked for.
