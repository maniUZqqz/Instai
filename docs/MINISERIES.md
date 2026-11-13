# Mini-series channel mode

Run a series as a channel: seasons of short episodes, recurring ORIGINAL characters, a hook in the first seconds, a cliffhanger at the end, a consistent look and a fixed posting schedule - in the
family of formats of the stick-figure series the owner follows (zombie stickman, ended survived, persianstickverse, thebinaqsh, plunk_guy, akumadub, stickchoicex).
Code: `instai/channel/`. UI: series > "Mini-series channel". New page format "کانال مینی‌سریال" (`mini_series_channel`) with its own development template.

## What was analysed, and what was NOT copied

Only **format, length, pacing and hooks** (`channel/conventions.py`). No character, story, title, catchphrase or joke of any channel is used, and the cast / catchphrase fields are the owner's own.
The channels themselves could not be opened in this round (no platform access), so the conventions are the general shape of the genre, supported only by general public guidance searched on
2026-11-13 - the stickman-video guide on clippie.ai (30-60 s typical, a hook and cliffhanger matter more than the drawing, scene change every 2-3 s, survival "Day 1 of..." series), fiverr.com's
short-form structure guide (a 2-3 s hook that promises payoff), and a Medium piece on episodic Reels (a micro-cliffhanger in the last 5 s). Marketing blogs; their numbers are rough and no retention
claim is used. **Unverified against any named channel's analytics.**

| Convention | Value used |
|---|---|
| Episode length | 20-60 s, default 30 s (escape 35 s, comedy 25 s) |
| Hook | inside the first 2 s: open in the middle of the danger or a question |
| Beats (share of the runtime) | hook 0-7 %, setup 7-20 %, escalation 20-55 %, twist 55-70 %, crisis 70-93 %, cliffhanger 93-100 % |
| Cutting | about 2.2-2.6 s per shot, 3.5-5 cuts per 10 s |
| Cliffhanger | the last 3 s; the next episode answers it in its first seconds ("payoff of the previous"), recap at most 2 s |
| Variety | one location and one goal per episode; no hook or cliffhanger repeated word for word; no 3 episodes in a row in one place |
| Recognition | every character one colour and one visible marker (the stick kit gives both) |
| Sound | strong effects, minimal music, a short silence before the reveal |
| Schedule | fixed weekdays and hour (default the page's publishing profile), shown as a reminder only |

## The season plan and its checks (`channel/planner.py`, `tests/test_channel.py`)

* Job `channel.season` (model; the deterministic skeleton is the fallback) writes the **slate**: per episode a title, hook, logline, escalation, twist, cliffhanger, payoff of the previous
  cliffhanger, characters, location, length and the **threads** it opens and closes (open questions).
* Validation: every episode has a hook and a cliffhanger (the finale's is a warning); every episode after the first says how the previous cliffhanger is answered; no thread stays open more than
  `max_thread_span` (4) episodes or more than `max_open_threads` (4) at once; **every thread is closed by the finale** (error otherwise); every cast member appears; runtimes inside the genre's range.
* The owner edits any row; any edit withdraws the approval. "Approve" is refused while there are errors. "Create the episodes" writes the approved slate into the series (episodes keep their work),
  puts the hook / twist / cliffhanger into each episode's notes and **starts each episode's beat sheet** (studio ladder) from the genre's beat template and the slate row.
* The script writer receives `channel` (hook within N seconds, cliffhanger in the last N, recap length, cast with markers and catchphrases, the genre's rules and this episode's row).
* Look: set once (the art-style stage of the ladder); characters are locked once (identity lock; stick characters are drawn by code and animate through the puppet renderer, so a 30-second episode needs no
  GPU). Posting: `planner.schedule` computes the dates (local time and UTC); nothing is published automatically.
