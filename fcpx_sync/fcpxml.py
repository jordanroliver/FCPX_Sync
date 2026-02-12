"""FCPXML generator for creating synchronized clips."""

import hashlib
import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from .sync_engine import SyncMatch, get_media_info


# FCPXML version - using 1.11 for broad compatibility
FCPXML_VERSION = "1.11"


def _seconds_to_rational(seconds: float, timebase: int = 1000) -> str:
    """Convert seconds to FCPXML rational time string.

    FCPXML uses rational time like '52840/1000s' meaning 52.84 seconds.
    """
    frac = Fraction(seconds).limit_denominator(timebase * 100)
    return f"{frac.numerator}/{frac.denominator}s"


def _duration_rational(seconds: float, fps_num: int, fps_den: int) -> str:
    """Convert duration to frame-aligned rational time."""
    frame_duration = Fraction(fps_den, fps_num)
    duration = Fraction(seconds).limit_denominator(100000)
    # Round to nearest frame
    frames = round(duration / frame_duration)
    result = frames * frame_duration
    return f"{result.numerator}/{result.denominator}s"


def _make_asset_id(path: Path) -> str:
    """Generate a deterministic asset ID from file path."""
    h = hashlib.md5(str(path.resolve()).encode()).hexdigest()[:8]
    return f"r{h}"


def _file_url(path: Path) -> str:
    """Convert a file path to a file:// URL."""
    resolved = path.resolve()
    return f"file://{quote(str(resolved))}"


def _get_fps(info: dict) -> tuple[int, int]:
    """Extract frame rate as (numerator, denominator) from ffprobe info."""
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            fps_str = stream.get("r_frame_rate", "30/1")
            parts = fps_str.split("/")
            return int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
    return 30, 1  # default


def _get_resolution(info: dict) -> tuple[int, int]:
    """Extract video resolution (width, height) from ffprobe info."""
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream.get("width", 1920), stream.get("height", 1080)
    return 1920, 1080


def _get_audio_info(info: dict) -> tuple[int, int]:
    """Extract (sample_rate, channels) from ffprobe info."""
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            sr = int(stream.get("sample_rate", 48000))
            ch = int(stream.get("channels", 2))
            return sr, ch
    return 48000, 2


def generate_fcpxml(
    matches: list[SyncMatch],
    event_name: str = "Synced Clips",
) -> str:
    """Generate an FCPXML document with synchronized clips.

    Creates an FCPXML file with one sync-clip per matched video/audio pair.
    The sync-clip combines the video with the external audio at the correct
    time offset.

    Args:
        matches: List of SyncMatch results from the sync engine.
        event_name: Name for the FCPX event.

    Returns:
        FCPXML document as a string.
    """
    # Root element
    fcpxml = ET.Element("fcpxml", version=FCPXML_VERSION)

    # Resources section
    resources = ET.SubElement(fcpxml, "resources")

    # Collect format and asset info for each file
    format_ids = {}  # (width, height, fps_num, fps_den) -> format_id
    asset_map = {}   # path -> (asset_id, format_id, duration_rational)

    format_counter = 0

    for match in matches:
        # Video info
        v_info = get_media_info(match.video_path)
        fps_num, fps_den = _get_fps(v_info)
        width, height = _get_resolution(v_info)
        v_sr, v_ch = _get_audio_info(v_info)

        # Create format for this video if needed
        format_key = (width, height, fps_num, fps_den)
        if format_key not in format_ids:
            format_counter += 1
            fmt_id = f"r{format_counter}"
            format_ids[format_key] = fmt_id

            frame_dur = _seconds_to_rational(fps_den / fps_num)
            fmt_elem = ET.SubElement(resources, "format", {
                "id": fmt_id,
                "name": f"FFVideoFormat{height}p{fps_num // fps_den if fps_den == 1 else round(fps_num / fps_den * 100) / 100}",
                "frameDuration": frame_dur,
                "width": str(width),
                "height": str(height),
            })

        v_fmt_id = format_ids[format_key]
        v_dur_rat = _duration_rational(match.video_duration, fps_num, fps_den)

        # Video asset
        v_asset_id = _make_asset_id(match.video_path)
        if match.video_path not in asset_map:
            v_asset = ET.SubElement(resources, "asset", {
                "id": v_asset_id,
                "name": match.video_path.stem,
                "src": _file_url(match.video_path),
                "start": "0/1s",
                "duration": v_dur_rat,
                "format": v_fmt_id,
                "hasVideo": "1",
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": str(v_ch),
                "audioRate": str(v_sr),
            })
            asset_map[match.video_path] = (v_asset_id, v_fmt_id, v_dur_rat)

        # Audio info
        a_info = get_media_info(match.audio_path)
        a_sr, a_ch = _get_audio_info(a_info)
        a_dur_rat = _seconds_to_rational(match.audio_duration)

        # Audio-only format
        a_fmt_key = ("audio", a_sr, a_ch)
        if a_fmt_key not in format_ids:
            format_counter += 1
            a_fmt_id = f"r{format_counter}"
            format_ids[a_fmt_key] = a_fmt_id
            ET.SubElement(resources, "format", {
                "id": a_fmt_id,
                "name": "FFAudioFormat",
            })

        a_fmt_id = format_ids[a_fmt_key]

        # Audio asset
        a_asset_id = _make_asset_id(match.audio_path)
        if match.audio_path not in asset_map:
            ET.SubElement(resources, "asset", {
                "id": a_asset_id,
                "name": match.audio_path.stem,
                "src": _file_url(match.audio_path),
                "start": "0/1s",
                "duration": a_dur_rat,
                "format": a_fmt_id,
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": str(a_ch),
                "audioRate": str(a_sr),
            })
            asset_map[match.audio_path] = (a_asset_id, a_fmt_id, a_dur_rat)

    # Library > Event > Project structure
    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name=event_name)

    for match in matches:
        v_asset_id, v_fmt_id, v_dur_rat = asset_map[match.video_path]
        a_asset_id, a_fmt_id, a_dur_rat = asset_map[match.audio_path]

        clip_name = f"{match.video_path.stem} - Synced"

        # The offset determines where the audio starts relative to the video.
        # In FCPXML sync-clip, the video is the "anchor" and the audio clips
        # inside have offsets relative to the sync-clip's timeline.
        #
        # If offset_seconds > 0: audio should start AFTER video begins
        # If offset_seconds < 0: audio starts BEFORE video begins

        offset = match.offset_seconds

        # sync-clip duration = the shorter of the two overlapping durations
        if offset >= 0:
            overlap_duration = min(match.video_duration, match.audio_duration + offset) - offset
        else:
            overlap_duration = min(match.video_duration + offset, match.audio_duration) - abs(offset)
        overlap_duration = max(overlap_duration, min(match.video_duration, match.audio_duration))

        v_info = get_media_info(match.video_path)
        fps_num, fps_den = _get_fps(v_info)

        sync_dur = _duration_rational(match.video_duration, fps_num, fps_den)

        # Create the sync-clip
        sync_clip = ET.SubElement(event, "sync-clip", {
            "name": clip_name,
            "start": "0/1s",
            "duration": sync_dur,
            "format": v_fmt_id,
            "tcFormat": "NDF",
        })

        # Video asset-clip (anchor - starts at 0)
        ET.SubElement(sync_clip, "asset-clip", {
            "ref": v_asset_id,
            "name": match.video_path.stem,
            "offset": "0/1s",
            "start": "0/1s",
            "duration": v_dur_rat,
            "format": v_fmt_id,
            "tcFormat": "NDF",
            "audioRole": "dialogue",
        })

        # Audio asset-clip with sync offset
        # The offset here positions the audio relative to the sync-clip timeline
        audio_offset = _seconds_to_rational(offset) if offset >= 0 else _seconds_to_rational(0)
        audio_start = _seconds_to_rational(abs(offset)) if offset < 0 else "0/1s"

        ET.SubElement(sync_clip, "asset-clip", {
            "ref": a_asset_id,
            "name": match.audio_path.stem,
            "offset": audio_offset,
            "start": audio_start,
            "duration": a_dur_rat,
            "audioRole": "dialogue.dialogue-1",
            "tcFormat": "NDF",
        })

        # Sync source to configure audio roles
        sync_source = ET.SubElement(sync_clip, "sync-source", sourceID="storyline")
        audio_role_src = ET.SubElement(sync_source, "audio-role-source", {
            "role": "dialogue.dialogue-1",
            "active": "1",
        })

    # Serialize to string with XML declaration and DOCTYPE
    ET.indent(fcpxml, space="  ")
    xml_str = ET.tostring(fcpxml, encoding="unicode", xml_declaration=False)

    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = f'<!DOCTYPE fcpxml>\n'

    return header + doctype + xml_str + "\n"
