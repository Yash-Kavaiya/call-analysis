# Asset inventory — Call Analysis dashboard capture

Source: live app at http://127.0.0.1:8787/ (dark NVIDIA-themed dashboard, real analyzed call data).

## Screenshots (capture/screenshots/)

- `full-page.png` (1920x1337, 1x) — the full dashboard in its initial state: sidebar with
  NVIDIA logo + "Call Analysis / Contact Center Intelligence", Ingest panel (Upload Recording,
  Import sample buttons), Fleet analytics stat grid, Calls list (completed calls with QA scores),
  and the empty main panel ("Select or upload a call", pipeline subtitle "ASR → Diarization → PII →
  Multi-agent analysis"). Best base plate for the wide dashboard shots.
- `scroll-000.png` / `scroll-100.png` (1920x1080, 1x) — viewport-sized captures at top/bottom.
- `detail-top.png` (3840x2160, 2x) — a completed call selected: top of the detail view with
  Dynamic Waveform Viewer, Agent Scorecard (per-agent scores), and Sentiment Charts.
- `detail-scroll.png` (3840x2160, 2x) — same call, scrolled: Interactive Transcript (with PII
  pill), AI Agent Insights cards (QA scorecard, compliance risk, sentiment/emotion, root
  cause/intent, CRM action items, call copilot).
- `detail-copilot.png` (3840x2160, 2x) — the Interactive Call Copilot (RAG) panel with a real
  answered question about the call.

## Brand tokens (capture/extracted/tokens.json)

- Palette: bg `#0A0A0F`, panel `#16161F`, card `#1A1A26`, border `#2A2A3D`, text `#E8E8EF`,
  muted `#8B8BA3`, NVIDIA green `#76B900` (dim `#5A8F00`, glow rgba(118,185,0,.25)),
  danger `#FF5C5C`, warn `#FFB020`, info `#4DA3FF`.
- Font: Segoe UI (weights 400/600/700), system fallback.
- Radius: 12px. Title: "Call Analysis — NVIDIA Contact Center Intelligence".

## SVGs / fonts (capture/assets/)

- `assets/svgs/` — any site SVGs (favicon etc.), `assets/fonts/` — captured font files.
