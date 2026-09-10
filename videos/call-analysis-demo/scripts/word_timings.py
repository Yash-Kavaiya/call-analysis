"""Add word timings to audio_meta.json voices using faster-whisper (small.en).

Reads audio_meta.json (written by sarvam_voice.py), transcribes each voice WAV,
and fills voices[].words with the flat [{id,text,start,end}] shape the
captions pipeline consumes.
"""

import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "audio_meta.json"


def main():
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    meta = json.loads(META.read_text(encoding="utf-8"))
    for v in meta["voices"]:
        wav = ROOT / v["path"]
        segments, _ = model.transcribe(str(wav), word_timestamps=True, language="en")
        words = []
        for seg in segments:
            for w in (seg.words or []):
                words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
        # re-id contiguous
        for i, w in enumerate(words):
            w["id"] = f"w{i}"
        v["words"] = words
        print(f"  {v['id']}: {len(words)} words")
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"✓ word timings → {META}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
