"""PII scrubber unit tests."""

from call_analysis.models import TranscriptSegment
from call_analysis.pii.scrubber import scrub_pii, scrub_text


def test_scrub_email_and_phone():
    text = "Contact me at jane.doe@example.com or +1-415-555-0100 please"
    scrubbed, findings = scrub_text(text)
    assert "jane.doe@example.com" not in scrubbed
    assert "[EMAIL]" in scrubbed
    assert "[PHONE]" in scrubbed
    types = {f.entity_type for f in findings}
    assert "EMAIL" in types
    assert "PHONE" in types


def test_scrub_segments():
    segs = [
        TranscriptSegment(0, 1, "My SSN is 123-45-6789", "SPEAKER_00"),
    ]
    result = scrub_pii(segs[0].text, segs)
    assert "[SSN]" in result.scrubbed_text
    assert "[SSN]" in result.scrubbed_segments[0].text
    assert result.scrubbed_segments[0].speaker == "SPEAKER_00"


def test_empty_text():
    scrubbed, findings = scrub_text("")
    assert scrubbed == ""
    assert findings == []
