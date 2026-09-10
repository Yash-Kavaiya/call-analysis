# Captured assets — Call Analysis demo

No URL capture: this is a local project (src/call_analysis/web/). Source material is
the user's own real dashboard screenshots plus the dashboard's live CSS tokens.

## Screenshots (real, from the user's dashboard)

| File | What it shows | Size |
|------|---------------|------|
| ingest-dark.png | Ingest / upload view (dark theme) — the "drop a recording" screen | 1440x960 |
| calls-dark.png | Calls list (dark) — fleet of analyzed calls with statuses | 1440x960 |
| detail-dark.png | Call detail view (dark) — transcript + scorecard | 1440x960 |
| insights.png | Insights view — sentiment / trends | 1536x770 |
| history-dark.png | History view (dark) | 1536x770 |
| metrics.png | Metrics panel — KPIs | 889x567 |
| redact-check.png | PII redaction confirmation strip | 550x84 |
| copilot.png | RAG copilot answer strip | 1377x157 |

## Brand tokens

Dark charcoal (#0a0a0f bg, #16161f panels, #1a1a26 cards, #2a2a3d borders),
NVIDIA emerald green accent (#76b900 / #5a8f00 dim / rgba(118,185,0,.25) glow),
text #e8e8ef, muted #8b8ba3, danger #ff5c5c, warn #ffb020, info #4da3ff.
Fonts: Segoe UI / system-ui; mono: ui-monospace, Cascadia Code, Consolas.

## Narrative material

README + .review-full.md were read at intent time. The video's copy is drawn from
the project's real positioning: ingest → ASR → diarization → PII scrub →
multi-agent analysis → dashboard, on the NVIDIA free AI stack.
