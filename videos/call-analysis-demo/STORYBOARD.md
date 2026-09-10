---
format: 1920x1080
duration: 90s
message: "Every call recording becomes a complete contact-center intelligence report"
arc: Hook → Promise → Pipeline → Proof → Trust → CTA
audience: "Contact center / CX leads, support ops, and AI builders"
mode: collaborative
music: confident minimal tech underscore
---

## Video direction

- **palette system** — from `frame.md`: dark ink ground `#0a0a0f`; panels `#16161f` / cards `#1a1a26`; hairlines `#2a2a3d`; cream text `#e8e8ef`; muted `#8b8ba3`; the single accent NVIDIA green `#76b900` (dim `#5a8f00`, glow `rgba(118,185,0,0.25)`) for kickers, rules, tags, and focal glows; `#ff5c5c` / `#ffb020` / `#4da3ff` reserved as semantic status only (never decoration). Two registers only — dark ground with cream text, accent on dark; no third color family.
- **type by role** — display: Segoe UI 800–900, lowercase, tight negative tracking (the broadside primitive); body: Segoe UI 400–600; chrome/kickers/labels/numbers: mono (Consolas via `@font-face local()`, uppercase, ~0.14em tracking). Fonts resolve from the sketch files' `@font-face` pattern — no invented families.
- **motion grammar** — smooth long-tail settles (`power3`; overshoot only on the one playful moment, the 87 count-up landing). **VO-paced reveal model**: every frame reveals each piece on its spoken cue, never front-loads the first ~25%, keeps content arriving into the back ~50%. During a hold: at most **subtle jitter** on the focal; no lazy breathing, no back-half pan/push. Internal scene seams are velocity-matched cuts (`cut-catalog.md`).
- **rhythm / held frames** — Frames 1, 2, 5, 8 are reveal-driven (type + pipeline + grid + lockup); **Frames 6 and 7 are the breathers** — the dashboard and the copilot answer land early and then hold still and read, so the video breathes before the CTA. Frame 6 holds the count-up result; Frame 7 holds the answered question.
- **negative list** — no off-brand gradients / purple-blue "AI" glow; no decorative shapes standing in for real assets (real screenshots dress the sketches); never both failure modes: no slideshow (front-load then freeze) and no screensaver (everything floating independently). No narration text rendered as on-screen copy — visible text is short motion-graphics copy only.

---

## Frame 1 — Every call tells you something

- scene: Two dark beats of kinetic type on the bare NVIDIA-green canvas — the hook lands, then resolves
- voiceover: "Every call tells you something. Most teams never hear it."
- duration: 6s
- poster: 3s
- transition_in: cut
- status: animated
- src: compositions/frames/01-hook.html
- type: hook
- persuasion: Pain validation
- beat: curiosity + frustration
- blueprint: kinetic-type-beats (Adapt)
- asset_candidates:
- sfx: none

narrativeRole: Open in the viewer's outcome language — the value of *hearing* calls — before any product name. Creates the tension the rest of the video resolves.
keyMessage: Call recordings are full of signal your team never hears.

Adapt: keep the in-place beat-swap signature; two statement beats instead of a word cycle, kicker chrome above, accent rule between.
Scene 1 (0.0–1.2s): bare ink ground; kicker "CALL ANALYSIS" (mono chrome, accent) enters via per-word staggered reveal (`dynamic-content-sequencing`), centered upper-third; accent stub rule draws in beneath it (`svg-path-draw`). Centered, ~45% of frame, 2 depth layers.
Scene 2 (1.2–3.2s): as the VO says "every call tells you something," the line assembles per-word (`dynamic-content-sequencing`), cream display 800, dead-center; a soft accent glow blooms behind it on the final word (`ambient-glow-bloom`). Centered, hero ≥40%.
Scene 3 (3.2–5.0s): on "most teams never hear it," the second line swaps in via hard-cut flash word-swap (`discrete-text-sequence`) in accent green, landing with a spring-pop settle (`spring-pop-entrance`, long-tail); both lines now read stacked. Centered, held hierarchy by color.
Scene 4 (5.0–6.0s): hold — at most subtle jitter on the accent line (`sine-wave-loop`, low amplitude); no breathing, no drift.

## Frame 2 — The pipeline reveal

- scene: A recording file enters left; glowing pipeline nodes ASR → Diarization → PII → 6 Agents carry it right; it transforms into the live dashboard on the right
- voiceover: "Call Analysis turns any recording — into a complete contact center intelligence report."
- duration: 13s
- poster: 6s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/02-pipeline.html
- type: product_intro
- persuasion: Future pacing
- beat: curiosity → clarity
- blueprint: spatial-pan-stations (Adapt)
- focal: assets/detail-dark.png
- roles: detail-dark = cutout (the report the pipeline lands on) · node cards = supporting · file chip = supporting
- asset_candidates: assets/detail-dark.png — call detail dashboard, the transformation target
- sfx: riser

narrativeRole: The promise (message) lands here by beat 2: one recording becomes the full report. The pipeline visual IS the product's core idea — the whole project in one sweep.
keyMessage: This is the whole pipeline — recording in, intelligence out.

Adapt: keep the station-traversal signature but left→right on one flat canvas instead of a virtual camera pan — the file moves, the stations reveal in sequence, and the last station hands off to the dashboard.
Scene 1 (0.0–1.5s): title "call analysis — recording in, report out" (display 800, accent on "report out") assembles per-word top-left (`dynamic-content-sequencing`); a CALL.M4A file chip enters from the left edge (spring-pop entrance, long-tail settle), mono chrome label. Asymmetric 70/30, 3 depth layers.
Scene 2 (1.5–5.5s): as the VO says "turns any recording into…", the four station cards reveal left→right, one per spoken beat — ASR, DIARIZATION, PII SCRUB, 6 AI AGENTS — each popping with a spring-pop entrance (`spring-pop-entrance`, long-tail settle) and a green node icon; arrows between stations draw on (`svg-path-draw`) as each handoff lands. Full-width strip across the frame's middle band, 3 depth layers.
Scene 3 (5.5–9.5s): on "…into a complete contact center intelligence report," the last station hands off right — detail-dark.png screenshot assembles as the target panel on the right ~40% (spring-pop entrance), a green glow blooming behind it (`ambient-glow-bloom`).
Scene 4 (9.5–13.0s): hold the full pipeline + dashboard read — at most subtle jitter on the dashboard panel (`sine-wave-loop`); no drift, no breathing.

## Frame 3 — Drop in a recording

- scene: The real ingest screen (ingest-dark.png) slides in; a file card drops into it and a transcript starts appearing line by line
- voiceover: "Drop in an M4A or a WAV. Whisper transcribes it in seconds — GPU or CPU, it adapts."
- duration: 12s
- poster: 6s
- transition_in: crossfade
- status: animated
- src: compositions/frames/03-ingest.html
- type: feature_showcase
- persuasion: Show-don't-tell proof
- beat: ease + relief
- blueprint: device-surface-showcase (Adapt)
- focal: assets/ingest-dark.png
- roles: ingest-dark = cutout (the hero surface, real screenshot) · file chip = supporting · transcript lines = supporting (rebuilt overlay)
- asset_candidates: assets/ingest-dark.png — ingest/upload screen
- sfx: pop

narrativeRole: First proof beat — the frictionless entry point (upload) and the instant transcription result. Evidence for the promise.
keyMessage: Any audio file in, clean transcript out — no setup.

Adapt: keep the held-surface showcase signature but one surface and one flow — the real ingest screenshot is the window, rebuilt overlay elements animate on top.
Scene 1 (0.0–1.8s): ingest-dark.png enters as the hero window (crossfade-up, smooth long-tail), centered ~70% of frame; browser chrome dots + title strip sit above it. Centered, 3 depth layers.
Scene 2 (1.8–4.2s): on "drop in an M4A or a WAV," a file chip drops onto the upload zone with a spring-pop settle (`spring-pop-entrance`) — mono filename `support-call-2411.m4a` + a "TRANSCRIBING…" status that pulses once (finite, `asr-keyword-glow` register); the upload zone's dashed border glows accent.
Scene 3 (4.2–9.0s): as the VO says "Whisper transcribes it in seconds," transcript lines reveal sequentially into a side panel, one per beat (`dynamic-content-sequencing`), each line a short cream bar with an accent underline on the active one; GPU/CPU badge chip pops beside the panel (`spring-pop-entrance`).
Scene 4 (9.0–12.0s): hold — the transcript panel reads full; subtle jitter on the active line only; no drift.

## Frame 4 — Who said what, safely

- scene: detail-dark.png transcript shows speakers separated (Agent/Customer tags); a PII redaction strip (redact-check.png) confirms scrubbed data
- voiceover: "Speakers separated automatically. And sensitive data — phones, cards, IDs — redacted before any AI touches it."
- duration: 12s
- poster: 6s
- transition_in: crossfade
- status: animated
- src: compositions/frames/04-diarization-pii.html
- type: feature_showcase
- persuasion: Friction reduction + Risk reversal
- beat: trust + control
- blueprint: compose
- focal: assets/detail-dark.png
- roles: detail-dark = cutout (transcript surface, real screenshot base) · speaker tags = supporting (rebuilt) · redact-check = supporting (real confirmation strip)
- asset_candidates: assets/detail-dark.png — transcript with speaker tags; assets/redact-check.png — PII redaction confirmation strip
- sfx: click

narrativeRole: Two features that answer the trust question — who's talking (diarization) and is customer data safe (PII). Removes the compliance objection before it's raised.
keyMessage: It knows who said what — and scrubs customer data before any AI sees it.

Scene 1 (0.0–2.0s): detail-dark.png transcript surface enters (crossfade-up), centered ~70%; its rows dim slightly so the rebuilt speaker layer reads. Centered, 3 depth layers.
Scene 2 (2.0–5.5s): on "speakers separated automatically," AGENT / CUSTOMER tag pills pop in on successive transcript rows (`spring-pop-entrance`, staggered by row index) — agent tags accent-green tinted, customer tags neutral; each tag lands with a soft click register.
Scene 3 (5.5–9.5s): as the VO names "phones, cards, IDs," redaction blocks sweep across sensitive spans in the rows (highlight marker, `css-marker-patterns`, ink fill); then on "redacted before any AI touches it," the redact-check.png confirmation strip slides in below the panel (`push / focus`) with a green glow (`ambient-glow-bloom`) — the visual receipt.
Scene 4 (9.5–12.0s): hold — transcript + confirmation strip read together; subtle jitter on the strip only; no drift.

## Frame 5 — Six AI agents go to work

- scene: Six agent cards assemble in a staggered grid — QA Scorecard, Compliance & Risk, Sentiment, Root Cause, CRM Actions, Copilot — each popping in with an icon
- voiceover: "Then six NVIDIA AI agents go to work: QA scorecards, compliance flags, sentiment, root cause, CRM actions — and a copilot for what comes next."
- duration: 15s
- poster: 7s
- transition_in: crossfade
- status: animated
- src: compositions/frames/05-agents.html
- type: benefit_highlight
- persuasion: Feature-to-benefit translation
- beat: awe + confidence
- blueprint: grid-card-assemble (Reproduce)
- asset_candidates:
- sfx: pop, pop, pop

narrativeRole: Enumerate breadth the way the product ships it — six specialist agents, each named as the value it delivers. The heart of the "intelligence" claim.
keyMessage: Six specialist AI agents analyze every call, not just one generic model.

Scene 1 (0.0–1.8s): title "six nvidia ai agents go to work" assembles per-word top-center (`dynamic-content-sequencing`), accent on "nvidia ai agents"; a green stub rule draws beneath (`svg-path-draw`). Centered, 2 depth layers.
Scene 2 (1.8–11.0s): as the VO names each agent, its card pops into a 3×2 grid with a spring-pop entrance (`spring-pop-entrance`, long-tail settle, stagger by card index) — QA Scorecard (0–100 · coaching), Compliance & Risk (policy flags), Sentiment (emotion timeline), Root Cause (intent + resolution), CRM Actions (follow-ups), Copilot (RAG · ask anything) — each card an icon block (accent-tinted) + name + mono sub-label. Grid assembly via `center-outward-expansion` cascade, cards ~28% of frame width, 3 depth layers.
Scene 3 (11.0–15.0s): hold the full grid — at most subtle jitter on the Copilot card (the payoff); no breathing, no drift.

## Frame 6 — Every score on one dashboard

- scene: calls-dark.png list → metrics.png KPIs → detail-dark.png scorecard sequence; a QA score counts up on the focal card
- voiceover: "Every score, every flag, every trend — on one dashboard."
- duration: 12s
- poster: 6s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/06-dashboard.html
- type: benefit_highlight
- persuasion: Show-don't-tell proof
- beat: control + clarity
- blueprint: dataviz-countup (Adapt)
- focal: assets/calls-dark.png
- roles: calls-dark = cutout (left list panel, real screenshot) · metrics = supporting · detail-dark = supporting (right scorecard)
- asset_candidates: assets/calls-dark.png — fleet calls list; assets/metrics.png — KPI metrics; assets/detail-dark.png — call detail with scorecard
- sfx: none

narrativeRole: Consolidate the proof — the dashboard is where all six agents' work becomes glanceable. The payoff of the whole pipeline.
keyMessage: The whole report fits on one screen you can actually read.

Adapt: keep the count-up signature; instead of a push-through stat grid, two dashboard panels flank a hero scorecard whose ring counts up — the breather frame.
Scene 1 (0.0–2.0s): calls-dark.png list panel enters from the left wing (crossfade-up), ~40% width, real screenshot; its score column reads. Asymmetric 60/40, 3 depth layers.
Scene 2 (2.0–4.5s): as the VO says "every score, every flag, every trend," metrics.png KPI panel and the hero scorecard assemble into the right ~60% (`center-outward-expansion`); the QA ring sweeps and the number counts 0→87 on a single heavy long-tail ease (`counting-dynamic-scale`, the one playful overshoot), landing with an accent glow bloom (`ambient-glow-bloom`).
Scene 3 (4.5–12.0s): **held read** — the full dashboard holds still and reads; subtle jitter on the 87 only; no breathing, no pan, no push. (Allocated breather before the copilot beat.)

## Frame 7 — Ask the call anything

- scene: detail-dark.png holds as the copilot strip (copilot.png) types a supervisor question and an answer streams beneath it
- voiceover: "Ask anything about the call. The copilot answers — grounded in the transcript."
- duration: 10s
- poster: 5s
- transition_in: crossfade
- status: animated
- src: compositions/frames/07-copilot.html
- type: benefit_highlight
- persuasion: Show-don't-tell proof
- beat: ease + power
- blueprint: prompt-type-submit-generate (Adapt)
- focal: assets/detail-dark.png
- roles: detail-dark = cutout (call surface base, dimmed) · copilot = supporting (real answer strip) · question line = supporting (rebuilt typed overlay)
- asset_candidates: assets/detail-dark.png — call detail surface; assets/copilot.png — RAG copilot answer strip
- sfx: typing

narrativeRole: The closing wow — not just reports, but a grounded Q&A over the call. One more proof that the intelligence is real and verifiable.
keyMessage: Supervisors can interrogate any call conversationally — with grounded answers.

Adapt: keep the ask-then-answer signature; one typed question, one streamed grounded answer, no submit button theater.
Scene 1 (0.0–2.5s): detail-dark.png holds dimmed as the base; on "ask anything about the call," a supervisor question line types in the copilot composer (`type-on with caret`, `discrete-text-sequence`) — "Why did this customer call today?" — centered upper-middle, mono label "SUPERVISOR" above.
Scene 2 (2.5–7.0s): on "the copilot answers," copilot.png answer strip enters (`push / focus`) and the answer text streams word-by-word beneath it (`per-word staggered reveal`, `dynamic-content-sequencing`); a "GROUNDED IN TRANSCRIPT · 00:41–02:12" citation line pops in accent (`spring-pop-entrance`).
Scene 3 (7.0–10.0s): **held read** — question + grounded answer hold; subtle jitter on the citation line; no drift, no breathing. (Breather before the CTA.)

## Frame 8 — Open source, free AI

- scene: The brand lockup assembles: "Call Analysis — Contact Center Intelligence", then the CTA line types in: Open source · Built on NVIDIA's free AI stack · build.nvidia.com
- voiceover: "Open source. Built on NVIDIA's free AI stack. Run it yourself — today."
- duration: 10s
- poster: 5s
- transition_in: crossfade
- status: animated
- src: compositions/frames/08-cta.html
- type: cta
- persuasion: Risk reversal + Urgency
- beat: motivation + inevitability
- blueprint: kinetic-type-beats (Adapt)
- asset_candidates:
- sfx: none

narrativeRole: Convert — the project is free, open source, and on NVIDIA's free stack, so the ask is zero-cost to try. Ends the loop the hook opened.
keyMessage: It's open source and runs on free AI — try it today.

Adapt: keep the beat-by-beat closing-line signature; the brand lockup builds first, then the CTA facts, then the URL lands.
Scene 1 (0.0–1.8s): kicker "OPEN SOURCE" (mono chrome, accent) reveals per-word top-center (`dynamic-content-sequencing`); accent stub rule draws in. Centered, 2 depth layers.
Scene 2 (1.8–3.5s): on "built on nvidia's free ai stack," the wordmark "call analysis" assembles — display 900, accent on "analysis" — via per-word staggered reveal (`dynamic-content-sequencing`), dead-center, with a green glow bloom behind (`ambient-glow-bloom`).
Scene 3 (3.5–7.0s): on "run it yourself," the facts row reveals left→right (`per-word staggered reveal`) — "BUILT ON NVIDIA'S FREE AI STACK" · "SELF-HOSTED" — mono chrome, muted; the accent dot between them pops (`spring-pop-entrance`).
Scene 4 (7.0–9.5s): on "today," the URL pill `build.nvidia.com` springs in dead-center (`spring-pop-entrance`, long-tail) in mono green with an accent border and glow (`ambient-glow-bloom`) — the single clickable-looking object.
Scene 5 (9.5–10.0s): final frame — a quiet settle as the lockup holds; the only exit tween in the video (fade-out tail, subtle).
