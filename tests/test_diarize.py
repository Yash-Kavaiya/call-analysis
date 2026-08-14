"""Diarization heuristic tests."""

from call_analysis.audio.diarize import diarize_segments, format_diarized_transcript
from call_analysis.models import TranscriptSegment


def test_diarize_alternates_on_pause():
    segs = [
        TranscriptSegment(0.0, 1.0, "Hello how may I help you today", "SPEAKER_00"),
        TranscriptSegment(2.5, 4.0, "I need help with my bill", "SPEAKER_00"),
        TranscriptSegment(4.2, 5.0, "Sure let me check", "SPEAKER_00"),
    ]
    out = diarize_segments(segs, pause_threshold=0.8)
    assert out[0].speaker == "SPEAKER_00"  # agent cue
    assert out[1].speaker == "SPEAKER_01"  # customer cue
    assert "SPEAKER" in format_diarized_transcript(out)


def test_diarize_empty():
    assert diarize_segments([]) == []
