"""Tests for FCPXML generation."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fcpx_sync.fcpxml import generate_fcpxml, _seconds_to_rational
from fcpx_sync.sync_engine import SyncMatch


def test_seconds_to_rational():
    assert _seconds_to_rational(1.0) == "1/1s"
    assert _seconds_to_rational(0.5) == "1/2s"
    assert _seconds_to_rational(0.0) == "0/1s"


def test_fcpxml_structure(tmp_path):
    """Generate FCPXML from fake matches and verify XML structure."""
    # Create dummy media files so paths resolve
    video = tmp_path / "test_video.mov"
    audio = tmp_path / "test_audio.wav"
    video.touch()
    audio.touch()

    match = SyncMatch(
        video_path=video,
        audio_path=audio,
        offset_seconds=0.25,
        correlation_score=0.85,
        video_duration=10.0,
        audio_duration=10.0,
    )

    # Mock get_media_info since we don't have real files
    import fcpx_sync.fcpxml as fcpxml_mod
    original_fn = fcpxml_mod.get_media_info

    def mock_info(path):
        return {
            "streams": [
                {"codec_type": "video", "r_frame_rate": "24/1", "width": 1920, "height": 1080},
                {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
            ],
            "format": {"duration": "10.0"},
        }

    fcpxml_mod.get_media_info = mock_info

    try:
        xml_str = generate_fcpxml([match], event_name="Test Event")

        # Parse and verify structure
        # Strip the DOCTYPE since ET can't parse it
        xml_body = xml_str.split("<!DOCTYPE fcpxml>\n", 1)[1]
        root = ET.fromstring(xml_body)

        assert root.tag == "fcpxml"
        assert root.get("version") is not None

        # Should have resources
        resources = root.find("resources")
        assert resources is not None

        # Should have library > event > sync-clip
        library = root.find("library")
        assert library is not None

        event = library.find("event")
        assert event is not None
        assert event.get("name") == "Test Event"

        sync_clips = event.findall("sync-clip")
        assert len(sync_clips) == 1

        clip = sync_clips[0]
        assert "Synced" in clip.get("name", "")

        # Should have two asset-clips inside the sync-clip
        asset_clips = clip.findall("asset-clip")
        assert len(asset_clips) == 2

    finally:
        fcpxml_mod.get_media_info = original_fn
