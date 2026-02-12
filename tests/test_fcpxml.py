"""Tests for FCPXML generation."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fcpx_sync.fcpxml import generate_fcpxml, _seconds_to_rational
from fcpx_sync.sync_engine import SyncMatch, MediaFile, Timecode


def test_seconds_to_rational():
    assert _seconds_to_rational(1.0) == "1/1s"
    assert _seconds_to_rational(0.5) == "1/2s"
    assert _seconds_to_rational(0.0) == "0/1s"


def _make_media(name, tc_str, duration, is_video=True):
    return MediaFile(
        path=Path(f"/fake/{name}"),
        timecode=Timecode.parse(tc_str, fps=24.0),
        duration=duration,
        has_video=is_video,
        has_audio=False if is_video else True,
        fps_num=24,
        fps_den=1,
        width=1920 if is_video else 0,
        height=1080 if is_video else 0,
        sample_rate=48000,
        channels=2,
    )


def test_fcpxml_structure():
    """Generate FCPXML from matches and verify XML structure."""
    video = _make_media("test_video.mov", "01:00:00:00", 10.0, is_video=True)
    audio = _make_media("test_audio.wav", "01:00:00:00", 10.0, is_video=False)

    match = SyncMatch(video=video, audio=audio, offset_seconds=0.0)

    xml_str = generate_fcpxml([match], event_name="Test Event")

    # Parse and verify structure (strip DOCTYPE since ET can't parse it)
    xml_body = xml_str.split("<!DOCTYPE fcpxml>\n", 1)[1]
    root = ET.fromstring(xml_body)

    assert root.tag == "fcpxml"
    assert root.get("version") is not None

    resources = root.find("resources")
    assert resources is not None

    library = root.find("library")
    assert library is not None

    event = library.find("event")
    assert event is not None
    assert event.get("name") == "Test Event"

    sync_clips = event.findall("sync-clip")
    assert len(sync_clips) == 1

    clip = sync_clips[0]
    assert "Synced" in clip.get("name", "")

    # Video asset-clip should be inside a spine
    spine = clip.find("spine")
    assert spine is not None
    video_clips = spine.findall("asset-clip")
    assert len(video_clips) == 1

    # Audio asset-clip is a direct child of sync-clip (not in spine)
    audio_clips = clip.findall("asset-clip")
    assert len(audio_clips) == 1


def test_video_without_audio_flag():
    """Video with has_audio=False should not have audioRole on its asset-clip."""
    video = _make_media("video.mov", "01:00:00:00", 10.0, is_video=True)
    audio = _make_media("audio.wav", "01:00:00:00", 10.0, is_video=False)

    match = SyncMatch(video=video, audio=audio, offset_seconds=0.0)
    xml_str = generate_fcpxml([match])

    xml_body = xml_str.split("<!DOCTYPE fcpxml>\n", 1)[1]
    root = ET.fromstring(xml_body)

    sync_clip = root.find(".//sync-clip")

    # Video clip in spine — should NOT have audioRole since has_audio=False
    video_clip = sync_clip.find("spine/asset-clip")
    assert video_clip.get("audioRole") is None

    # Audio clip — should have audioRole
    audio_clip = sync_clip.find("asset-clip")
    assert audio_clip.get("audioRole") == "dialogue"


def test_asset_uses_media_rep():
    """Assets must use media-rep child elements, not src attribute."""
    video = _make_media("video.mov", "01:00:00:00", 10.0, is_video=True)
    audio = _make_media("audio.wav", "01:00:00:00", 10.0, is_video=False)

    match = SyncMatch(video=video, audio=audio, offset_seconds=0.0)
    xml_str = generate_fcpxml([match])

    xml_body = xml_str.split("<!DOCTYPE fcpxml>\n", 1)[1]
    root = ET.fromstring(xml_body)

    assets = root.findall(".//asset")
    assert len(assets) >= 2

    for asset in assets:
        # No src attribute on asset itself
        assert asset.get("src") is None
        # Must have a media-rep child with src and kind
        media_rep = asset.find("media-rep")
        assert media_rep is not None
        assert media_rep.get("src") is not None
        assert media_rep.get("kind") == "original-media"


def test_asset_start_uses_timecode():
    """Asset start should use the media's actual timecode, not 0/1s."""
    video = _make_media("video.mov", "13:09:56:18", 10.0, is_video=True)
    audio = _make_media("audio.wav", "13:09:48:00", 60.0, is_video=False)

    match = SyncMatch(video=video, audio=audio, offset_seconds=8.75)
    xml_str = generate_fcpxml([match])

    xml_body = xml_str.split("<!DOCTYPE fcpxml>\n", 1)[1]
    root = ET.fromstring(xml_body)

    assets = root.findall(".//asset")
    for asset in assets:
        start = asset.get("start")
        # Should NOT be 0/1s — should reflect actual timecode
        assert start != "0/1s"
