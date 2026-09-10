"""Sarvam AI TTS for the call-analysis demo voiceover.

Reads SCRIPT.md, synthesizes one WAV per frame line (bulbul:v2, en-IN), caches by
content hash, and writes the engine-shaped voices meta to audio_meta.json so the
product-launch assemble/captions pipeline consumes it.

Usage:
  SARVAM_API_KEY=... python sarvam_voice.py [--speaker anushka] [--pace 1.0]
"""

import base64
import hashlib
import json
import os
import re
import sys
import wave
from pathlib import Path

import requests

API_URL = "https://api.sarvam.ai/text-to-speech"
ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "SCRIPT.md"
VOICE_DIR = ROOT / "assets" / "voice"
OUT_META = ROOT / "audio_meta.json"
MAX_CHARS = 1400  # safety margin under the 1500-char request limit


def get_key():
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not key:
        raise SystemExit("SARVAM_API_KEY not set")
    return key


def parse_script(md_text):
    """Parse SCRIPT.md into [{frame, text}] — same rules as the audio adapter."""
    out = []
    cur = None
    for raw in md_text.splitlines():
        line = raw.rstrip("\n")
        h = re.match(r"^#{2,3}\s+.*?\(frame\s+(\d+)\)", line, re.I)
        if h:
            if cur and cur["text"].strip():
                out.append(cur)
            cur = {"frame": int(h.group(1)), "text": ""}
            continue
        if cur is None:
            continue
        if re.match(r"^\s*\*\*", line):
            continue
        m = re.match(r"^(?: {4,}|\t)(.+)$", line)
        if m:
            cur["text"] += (" " if cur["text"] else "") + m.group(1).strip()
    if cur and cur["text"].strip():
        out.append(cur)
    return out


def chunk_text(text):
    """Split into <=MAX_CHARS chunks at sentence boundaries."""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(buf) + len(sentence) + 1 > MAX_CHARS and buf:
            parts.append(buf)
            buf = sentence
        else:
            buf = (buf + " " + sentence).strip() if buf else sentence
    if buf:
        parts.append(buf)
    return parts


def synthesize(text, speaker, pace, api_key):
    payload = {
        "text": text,
        "target_language_code": "en-IN",
        "speaker": speaker,
        "pitch": 0.0,
        "pace": pace,
        "loudness": 1.0,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "model": "bulbul:v2",
    }
    r = requests.post(API_URL, json=payload, headers={"api-subscription-key": api_key}, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Sarvam error {r.status_code}: {r.text[:300]}")
    audios = r.json()["audios"]
    return base64.b64decode("".join(audios))


def main():
    speaker = "anushka"
    pace = 1.0
    args = sys.argv[1:]
    if "--speaker" in args:
        speaker = args[args.index("--speaker") + 1]
    if "--pace" in args:
        pace = float(args[args.index("--pace") + 1])

    key = get_key()
    lines = parse_script(SCRIPT.read_text(encoding="utf-8"))
    if not lines:
        raise SystemExit("no spoken lines found in SCRIPT.md")

    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    voices = []
    for line in lines:
        fid = line["frame"]
        cache_key = hashlib.sha256(f"bulbul:v2|en-IN|{speaker}|0.0|{pace}|{line['text']}".encode()).hexdigest()[:24]
        wav_path = VOICE_DIR / f"{fid:02d}.wav"
        cache_path = VOICE_DIR / f"{cache_key}.wav"
        src = cache_path if cache_path.exists() else wav_path
        if not src.exists():
            chunks = chunk_text(line["text"])
            parts = []
            for c in chunks:
                parts.append(synthesize(c, speaker, pace, key))
            # All chunks are 22050 Hz mono 16-bit WAV from Sarvam — concat raw PCM.
            pcm = b"".join(p[44:] for p in parts)  # strip each chunk's WAV header
            with wave.open(str(cache_path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(pcm)
            print(f"  syn {fid:02d}: {line['text'][:60]}... ({len(pcm)/22050/2:.2f}s)")
            src = cache_path
        # Copy cache → canonical frame path if needed
        if src.resolve() != wav_path.resolve() and not wav_path.exists():
            wav_path.write_bytes(src.read_bytes())
        # Measure duration
        with wave.open(str(wav_path), "rb") as w:
            dur = w.getnframes() / w.getframerate()
        voices.append({"id": f"{fid:02d}", "path": f"assets/voice/{fid:02d}.wav", "duration_s": round(dur, 3), "words": []})
        print(f"  ok  {fid:02d}: {dur:.2f}s")

    meta = {
        "tts_provider": "sarvam",
        "voice_id": speaker,
        "bgm": None,
        "bgm_pending": False,
        "bgm_provider": None,
        "bgm_pid": None,
        "bgm_log": None,
        "bgm_mode": None,
        "bgm_target_duration_s": None,
        "bgm_seed_duration_s": None,
        "bgm_loop_count": None,
        "voices": voices,
        "sfx": [],
        "total_duration_s": round(sum(v["duration_s"] for v in voices), 3),
    }
    OUT_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"✓ wrote {OUT_META} — {len(voices)} voices, {meta['total_duration_s']}s total")


if __name__ == "__main__":
    main()
