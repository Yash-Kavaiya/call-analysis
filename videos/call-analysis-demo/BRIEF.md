---
workflow: product-launch-video
flow: automation
storyboard: yes
message: "Every call recording becomes a complete contact-center intelligence report"
destination: youtube
aspect: 1920x1080
language: en
audience: "Contact center / CX leads, support ops, and AI tinkerers"
length: 90s
angle: pipeline reveal
narration: yes
music: yes
---

## Intent

A product demo for the **Call Analysis — Contact Center Intelligence** project:
an open-source pipeline that turns raw call recordings into QA scorecards,
compliance flags, sentiment timelines, and CRM action items — built entirely on
NVIDIA's free AI stack.

The chosen concept is **The Pipeline Reveal**: a call recording enters the left
of the frame and flows right through glowing pipeline stages — ASR transcription,
speaker diarization, PII detection & redaction, then six NVIDIA NIM AI agents —
until it transforms into the live NVIDIA-themed dashboard with a QA scorecard,
sentiment chart, and interactive transcript. Dark NVIDIA-green aesthetic, modern
tech-demo feel, confident and clean. The video shows the whole project end to
end and uses the user's real dashboard screenshots as its visual assets.

Tone: punchy SaaS demo, value-before-evidence — show the "wow" of a call
becoming a scored report within seconds, then explain the pieces.

## Assets

User's real dashboard screenshots (source of truth for the dashboard visuals,
staged on the timeline; rebuilt UI only where a component needs internal motion):

- calls-dark.png — calls list (dark theme), 1440x960
- detail-dark.png — call detail view (dark), 1440x960
- ingest-dark.png — ingest/upload view (dark), 1440x960
- metrics.png — metrics panel, 889x567
- redact-check.png — PII redaction confirmation strip, 550x84
- copilot.png — RAG copilot answer strip, 1377x157
- insights.png — insights view, 1536x770
- history-dark.png — history view (dark), 1536x770

## Customizations

- **Voiceover**: Sarvam AI bulbul:v2 (user's own voice pipeline) — not the
  stock HeyGen/Kokoro path. Generate per-frame VO with the Sarvam API
  (`api-subscription-key` header), WAV at 22050 Hz, and hand-build the
  audio_meta.json in the engine's neutral shape so captions/assemble consume it.
- **Music bed**: a music bed under the narration (retrieved/sourced, since
  HeyGen is not signed in — product-launch BGM retrieve is skipped offline).
- **Captions**: kinetic captions carrying the narration (user chose VO + music;
  captions on top for feed viewing without sound).

## Notes

- Sarvam speakers: female `anushka`/`manisha`/`vidya`/`arya`, male
  `abhilash`/`karun`/`hitesh`. Narration language en-IN.
- The dashboard brand: dark charcoal + NVIDIA emerald green (see
  src/call_analysis/web/styles.css for the exact palette).
- No HeyGen credential on this machine (auth status: not signed in) — offline
  engines only; Sarvam is used for VO per explicit user choice.
- Screenshots live in the user's home dir; copy them into the project before staging.
