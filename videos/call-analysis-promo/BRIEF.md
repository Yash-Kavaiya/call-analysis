---
workflow: product-launch-video
flow: automation
storyboard: no
message: "Every call, fully understood — a raw recording becomes a redacted transcript, scored analytics, and an AI copilot."
destination: youtube
aspect: 1920x1080
language: en
length: 60s
angle: show-it-as-is
narration: no
---

## Intent

A product demo of the Call Analysis desktop app (NVIDIA Contact Center Intelligence). Show the real dashboard in action: ingest a call recording, watch the pipeline (ASR → diarization → PII redaction → multi-agent analysis) light up, then reveal the redacted interactive transcript, agent scorecards, sentiment charts, and the RAG copilot answering a question about the call. Text-driven with a music bed — no voiceover. Clean, confident, modern; the UI itself is the star.

## Assets

- Live dashboard screenshots captured from the running app at http://127.0.0.1:8787/ (real analyzed call data present in data/calls/).

## Customizations

- Text-driven: on-screen callouts/captions carry the message; no narration.
- Music bed for energy; no SFX needed.

## Notes

- The app is local-only (127.0.0.1). Backend must be running to capture; a real NVIDIA API key is configured in the project's .env.
- Pipeline: ASR → Diarization → PII → Multi-agent analysis (QA scorecard, compliance risk, sentiment/emotion, root cause/intent, CRM action items, call copilot).
- Brand: "Call Analysis — Contact Center Intelligence", NVIDIA-powered.
