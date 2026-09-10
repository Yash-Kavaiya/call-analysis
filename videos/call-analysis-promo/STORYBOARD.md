---
format: 1920x1080
duration: 60s
message: "Every call, fully understood — a raw recording becomes a redacted transcript, scored analytics, and an AI copilot."
arc: Demo Loop — question → intro → demo cycle 1 (ingest → pipeline) → demo cycle 2 (transcript → scoring → copilot) → CTA
audience: contact-center and sales teams drowning in unanalyzed call recordings
mode: autonomous
music: "modern tech underscore — confident, driving, subtle"
---

## Video direction

- **Palette system** (frame.md, verbatim): canvas `bg` #1A1A26, single accent `primary` #76B900
  (eyebrows, numerals, tag pills, progress bar, CTA), headlines `text` #E8E8EF (never green),
  body `text-muted` #8B8BA3, tertiary #656565; cards = `card-bg` rgba(118,185,0,0.04) fill with
  `border` rgba(118,185,0,0.2) 1.5px, 10–14px radii, NO shadows. No second accent color — amber
  #FFB020 and reds appear only as tiny status chips inside captured screenshots, never as chrome.
- **Motion grammar**: long-tail eases (power3 default — smooth over bouncy); every piece reveals
  **on its on-screen-text cue, never front-loaded** (nothing appears before the callout names it);
  held reads stay still — at most a subtle jitter/1–2% drift, never lazy breathing or forced pans.
- **Rhythm / held frames**: energy builds — F1 quick type, F2 calm reveal, F3 working energy,
  F4 mid traversal, F5 assemble, F6 peak (type + answer), F7 resolve. Held beats: F2 tail (plate
  reads), F4 tail (transcript reads), F7 (closing hold).
- **Negative list**: no purple/blue "AI" gradients, no bokeh, no floating decorative shapes
  pretending to be product; both motion failure modes banned — slideshow (everything dumped by
  ~25% then frozen) and screensaver (everything floating independently).
- **Caption band**: bottom ~17% stays clear on every frame (content planned into top ~83%),
  even though this piece is text-driven with no caption groups.

---

## Frame 1 — Hook: What happened on that call?

- status: animated
- scene: Big type punches in — the question every team asks
- duration: 5s
- poster: 2.5s
- transition_in: cut
- voiceover: "What happened on that call?"
- blueprint: kinetic-type-beats (Adapt)
- src: compositions/frames/01-hook.html

Adapt: keep the flat centered bold-type hook (flash sub-shape); two-line question builds
word-by-word on a bare dark canvas, sub-line fades beneath, no product, no screenshot.

Scene 1 (0.0–1.4s): flat `bg` canvas; small green eyebrow "CALL ANALYSIS" + 60×4 accent line
seat top-left; headline "What happened" types in character-by-character with a trailing green
caret at the top-third, left-aligned (h1 ramp, ~60cqw).
Scene 2 (1.4–3.0s): "on that call?" lands word-by-word on the second line; the "?" snaps green
(a one-shot accent — the only move in the shot); caret clears.
Scene 3 (3.0–5.0s): sub-line "A raw recording hides the whole story." fades in muted (#8B8BA3,
body ramp) beneath; hold still to the cut.

## Frame 2 — Product intro: the whole story in one place

- status: animated
- scene: Dashboard plate pushes in as the product is named
- duration: 9s
- poster: 4s
- transition_in: crossfade
- voiceover: "Call Analysis — NVIDIA Contact Center Intelligence. Drop in a recording, get the whole story back."
- blueprint: titlecard-reveal (Adapt)
- asset_candidates: assets/full-page.png — the whole dashboard, initial state
- focal: assets/full-page.png
- roles: full-page.png = background (dim ~40%)
- src: compositions/frames/02-intro.html

Adapt: keep the single restrained reveal + hold; the revealed card is the real dashboard plate
instead of a text card, with the title overlay standing in for the card text.

Scene 1 (0.0–1.6s): full-page.png rises from black with a slow scale-in 95%→100% (power3.out)
to 1x, dim ~40% under a left scrim; nothing else enters.
Scene 2 (1.6–4.5s): eyebrow "CALL ANALYSIS" (green, uppercase 0.08em) slides up on the left
third; headline "NVIDIA Contact Center Intelligence" (h2 ramp) follows; tag-pill "Contact Center
Intelligence" pops top-right of the plate; body line "Drop in a recording — get the whole story
back." fades in muted beneath the headline.
Scene 3 (4.5–9.0s): held read — plate and type hold, at most a 1% continuous scale drift;
nothing new enters.

## Frame 3 — Ingest + pipeline: one upload, five stages

- status: animated
- scene: The pipeline stages light up one by one over the dashboard
- duration: 11s
- poster: 5s
- transition_in: cut
- voiceover: "One upload. Then ASR, diarization, PII redaction, multi-agent analysis — the machine does the work while you watch."
- blueprint: agent-progress-theater (Adapt)
- asset_candidates: assets/full-page.png — the whole dashboard, initial state
- focal: assets/full-page.png
- roles: full-page.png = background (dim ~45%)
- src: compositions/frames/03-pipeline.html

Adapt: keep trigger → working theater → receipt; the working theater is a 4-step pipeline strip
below the real dashboard (the machine's "work"), receipt = all steps checked green.

Scene 1 (0.0–2.0s): full-page.png at ~0.9x, dim ~45%; a green pulse ring (expanding fading
rings) marks the Ingest panel; callout "One upload." pops top-left (h3 ramp).
Scene 2 (2.0–8.5s): a 4-step pipeline strip slides up beneath the plate — "ASR" → "Diarization"
→ "PII Redaction" → "Multi-Agent Analysis" — each pill lights green in sequence (~1.6s apart):
active pill pulses with a thin arc spinner + status word ("Working…"), then flips to a solid
green check; a 3px progress bar sweeps across the strip behind them.
Scene 3 (8.5–11.0s): all four pills checked; callout completes — "Five stages. Zero manual
work." fades in beneath "One upload."; strip and plate hold to the cut.

## Frame 4 — Transcript + PII: a transcript you can trust

- status: animated
- scene: The redacted interactive transcript scrolls with PII findings flagged
- duration: 10s
- poster: 5s
- transition_in: crossfade
- voiceover: "A redacted, interactive transcript — every piece of personally identifiable information found and flagged."
- blueprint: transcript-scroll-artifact-reveal (Adapt)
- asset_candidates: assets/detail-transcript.png — detail view showing the interactive transcript card
- focal: assets/detail-transcript.png
- roles: detail-transcript.png = background (dim ~30%)
- src: compositions/frames/04-transcript.html

Adapt: keep traverse → hinge → artifact; the traversal is a slow element drift over the real
screenshot, the hinge is the PII pill spring, the artifact is the redaction highlight sweep on
the transcript rows.

Scene 1 (0.0–3.0s): detail-scroll.png pushed into the transcript region, dim ~30%; a slow
continuous downward drift (reading pace, ~5% of surface) starts immediately; callout "A
transcript you can trust." (h2 ramp) top-left, clear of the caption band.
Scene 2 (3.0–5.5s): drift eases to a stop (power4.out); a green PII pill "PII redacted" springs
in beside the "Interactive Transcript" card header; two or three transcript rows flash a green
selection-highlight sweep left→right (redaction finds).
Scene 3 (5.5–10.0s): sub-line "PII redacted automatically — every finding flagged." fades in
muted; held read to the end — at most subtle jitter.

## Frame 5 — Scorecards + sentiment: scored on every axis

- status: animated
- scene: Scorecards and sentiment charts assemble over the real detail view
- duration: 10s
- poster: 5s
- transition_in: cut
- voiceover: "QA scorecard, compliance risk, sentiment, root cause, action items — every call scored on every axis."
- blueprint: grid-card-assemble (Adapt)
- asset_candidates: assets/detail-top.png — detail view top: waveform, scorecards, sentiment
- focal: assets/detail-top.png
- roles: detail-top.png = background (dim ~30%)
- src: compositions/frames/05-scorecards.html

Adapt: keep the staggered assemble + hold; the grid items are small tinted metric chips floating
over the real detail screenshot, each popping into its slot with a green tick.

Scene 1 (0.0–2.0s): detail-top.png (waveform + Agent Scorecard + Sentiment Charts) at ~0.8x,
dim ~30%; callout "Scored on every axis." (h2 ramp) top-left.
Scene 2 (2.0–7.5s): five tinted metric chips assemble in a 2-col arrangement over the scorecard
region, ~1.1s apart: "QA scorecard", "Compliance risk", "Sentiment", "Root cause & intent",
"CRM action items" — each fades + slides into its slot with a green tick mark popping on its
left.
Scene 3 (7.5–10.0s): a fleet stat card pops center-bottom over the plate — "14 calls · scored"
(stat-num green numeral + muted label); chip array and card hold to the cut.

## Frame 6 — Copilot: ask the call anything

- status: animated
- scene: A real copilot question is typed and answered from the transcript
- duration: 11s
- poster: 5s
- transition_in: cut
- voiceover: "Ask the call anything — 'What was the customer's main concern?' — answered straight from the transcript."
- blueprint: prompt-type-submit-generate (Adapt)
- asset_candidates: assets/detail-copilot.png — copilot panel with answered question
- focal: assets/detail-copilot.png
- roles: detail-copilot.png = background (dim ~30%)
- src: compositions/frames/06-copilot.html

Adapt: keep one ask → generating state → answer; the input is the real copilot input on the
screenshot, the answer block resolves with a green ring highlight.

Scene 1 (0.0–2.0s): detail-copilot.png pushed into the copilot panel, dim ~30%; callout "Ask
the call anything." (h2 ramp) top-left.
Scene 2 (2.0–6.5s): the question types character-by-character into the copilot input with a
green caret: "What was the customer's main concern, and what action item did the agent commit
to?"; the Ask button pulses green on submit.
Scene 3 (6.5–9.5s): generating state — three pulsing dots in the log; then the answer row
resolves: a green ring/glow blooms around the answer block as it settles (the payload).
Scene 4 (9.5–11.0s): sub-line "RAG over the transcript — grounded, no guessing." fades in
muted; hold to the cut.

## Frame 7 — CTA: every call, fully understood

- status: animated
- scene: Closing — the promise, then the one call to action
- duration: 6s
- poster: 3s
- transition_in: crossfade
- voiceover: "Every call, fully understood. Get a free NVIDIA API key and run it locally today."
- blueprint: kinetic-type-beats (Adapt)
- src: compositions/frames/07-cta.html

Adapt: keep the centered beat build + hold; atmosphere (rings + dot grid) behind, headline
builds word-by-word, then the one solid green CTA pill pops beneath.

Scene 1 (0.0–2.2s): flat `bg` canvas with faint concentric closing rings + a 3×3 green dot grid
(atmosphere, centered, ~10% opacity); headline "Every call," lands word-by-word centered (h1
ramp).
Scene 2 (2.2–4.2s): "fully understood." lands; a 60×4 green accent line draws beneath the
headline.
Scene 3 (4.2–6.0s): the one solid green `cta-button` pill pops in centered under the line —
"Get a free NVIDIA API key"; muted sub-line "Runs locally · build.nvidia.com" fades beneath;
the 3px progress bar completes to 100%; hold to the final frame.
