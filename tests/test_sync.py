"""Tests for the timecode-based sync engine."""

import pytest

from fcpx_sync.sync_engine import Timecode, match_by_timecode, MediaFile
from pathlib import Path


def test_timecode_parse():
    tc = Timecode.parse("01:02:03:04", fps=24.0)
    assert tc.hours == 1
    assert tc.minutes == 2
    assert tc.seconds == 3
    assert tc.frames == 4


def test_timecode_parse_drop_frame():
    tc = Timecode.parse("01:02:03;04", fps=29.97)
    assert tc.hours == 1
    assert tc.frames == 4


def test_timecode_to_seconds():
    tc = Timecode.parse("01:00:00:00", fps=24.0)
    assert tc.to_seconds() == 3600.0

    tc2 = Timecode.parse("00:00:01:12", fps=24.0)
    assert tc2.to_seconds() == 1.5


def test_timecode_str():
    tc = Timecode.parse("01:02:03:04", fps=24.0)
    assert str(tc) == "01:02:03:04"


def _make_media(name, tc_str, duration, is_video=True, fps=24.0):
    """Helper to create a MediaFile for testing."""
    return MediaFile(
        path=Path(f"/fake/{name}"),
        timecode=Timecode.parse(tc_str, fps=fps) if tc_str else None,
        duration=duration,
        has_video=is_video,
        has_audio=not is_video,
        fps_num=24,
        fps_den=1,
        width=1920 if is_video else 0,
        height=1080 if is_video else 0,
        sample_rate=48000,
        channels=2,
    )


def test_match_overlapping_timecodes():
    """Video and audio with overlapping TC ranges should match."""
    video = _make_media("clip1.mov", "01:00:00:00", 10.0, is_video=True)
    audio = _make_media("take1.wav", "00:59:58:00", 20.0, is_video=False)

    matches = match_by_timecode([video], [audio])

    assert len(matches) == 1
    assert matches[0].video.path.name == "clip1.mov"
    assert matches[0].audio.path.name == "take1.wav"
    # Video TC (3600s) - Audio TC (3598s) = 2.0s offset
    assert abs(matches[0].offset_seconds - 2.0) < 0.01


def test_match_same_timecode():
    """Video and audio starting at exact same TC should have 0 offset."""
    video = _make_media("clip.mov", "01:00:00:00", 10.0, is_video=True)
    audio = _make_media("take.wav", "01:00:00:00", 10.0, is_video=False)

    matches = match_by_timecode([video], [audio])

    assert len(matches) == 1
    assert abs(matches[0].offset_seconds) < 0.01


def test_no_match_when_no_overlap():
    """Files with non-overlapping TC ranges should not match."""
    video = _make_media("clip.mov", "01:00:00:00", 5.0, is_video=True)
    audio = _make_media("take.wav", "02:00:00:00", 5.0, is_video=False)

    matches = match_by_timecode([video], [audio])

    assert len(matches) == 0


def test_multiple_files_matched_correctly():
    """Multiple videos should match to the correct audio files."""
    v1 = _make_media("clip1.mov", "01:00:00:00", 10.0, is_video=True)
    v2 = _make_media("clip2.mov", "01:05:00:00", 10.0, is_video=True)

    a1 = _make_media("take1.wav", "00:59:59:00", 20.0, is_video=False)
    a2 = _make_media("take2.wav", "01:04:59:00", 20.0, is_video=False)

    matches = match_by_timecode([v1, v2], [a1, a2])

    assert len(matches) == 2
    # v1 should match a1, v2 should match a2
    match_map = {m.video.path.name: m.audio.path.name for m in matches}
    assert match_map["clip1.mov"] == "take1.wav"
    assert match_map["clip2.mov"] == "take2.wav"


def test_raises_when_no_timecode_on_video():
    """Should raise ValueError if no video files have timecode."""
    video = _make_media("clip.mov", None, 10.0, is_video=True)
    audio = _make_media("take.wav", "01:00:00:00", 10.0, is_video=False)

    with pytest.raises(ValueError, match="No video files have embedded timecode"):
        match_by_timecode([video], [audio])


def test_raises_when_no_timecode_on_audio():
    """Should raise ValueError if no audio files have timecode."""
    video = _make_media("clip.mov", "01:00:00:00", 10.0, is_video=True)
    audio = _make_media("take.wav", None, 10.0, is_video=False)

    with pytest.raises(ValueError, match="No audio files have embedded timecode"):
        match_by_timecode([video], [audio])
